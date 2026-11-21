"""Mech Royale bot v0.

Layers, top to bottom each tick:
  1. bookkeeping  (threat memory, stuck detection, FFA evidence)
  2. targeting    (pick a mech / NPC / crate to shoot)
  3. aiming+fire  (lead for the gun, direct for laser, cone for lightning, ballistic mortar)
  4. movement     (zone > retreat > fight spacing + strafe > loot > farm > drop > hold zone)
"""
import math
import os
import random
import sys
import time

import numpy as np

import mechfight as mf
from world import World
from nav import Nav

TAU = 2 * math.pi
UPGRADE_PRIORITY = [
    "armor", "plating", "nanites", "laser_damage", "lightning_efficiency", "gun_damage", "gun_rate",
    "laser_charge", "gyros", "gun_mag", "lightning_range", "lightning_chain", "reactor", "capacitor",
    "servos", "sensors", "mortar_reload", "mortar_splash", "mortar_velocity", "jets", "gun_velocity", "laser_pierce",
]
WEAPON_RANK = {"laser": 3.0, "lightning": 2.5, "gun": 2.0, "mortar": 1.0}


def wrap(a):
    return (a + math.pi) % TAU - math.pi


def yaw_to(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def hdist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def unit(v):
    n = math.hypot(v[0], v[1])
    return (v[0] / n, v[1] / n) if n > 1e-9 else (0.0, 0.0)


class Bot:
    name = "jb-mech"

    def __init__(self, hello):
        t0 = time.time()
        self.cfg = cfg = hello["config"]
        self.slot = hello["slot"]
        self.rng = random.Random(hello.get("seed", 0))
        self.world = World(hello["map"]["dir"])
        g = dict(np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "nav.npz")))
        self.nav = Nav(self.world, g)
        self.W = cfg["weapons"]
        self.reach = cfg["loot"]["pickup_radius"]
        # state
        self.target_id = None
        self.strafe = 1.0
        self.strafe_until = 0.0
        self.last_pos = None
        self.stuck_t = 0.0
        self.unstick_until = 0.0
        self.unstick_dir = (1.0, 0.0)
        self.last_dmg = None  # (t, bearing, by)
        self.enemy_seen = {}  # id -> (t, pos, vel, hp, weapons)
        self.noise = []  # (t, bearing, dist, kind)
        self.my_kills = 0
        self.ffa_score = 0.0
        self.prev_alive = None
        self.scan_phase = self.rng.random() * TAU
        self.bad_pickups = {}
        self.prev_move = (0.0, 0.0)
        self.recovering = False
        self.cover = None
        self.cover_t = -99.0
        # warm up lazy imports / caches so the first real decision isn't slow
        try:
            self.nav.steer((0.0, 0.0), (100.0, 50.0))
            self.world.los((0, 0, 5), (50, 50, 5))
        except Exception as ex:
            mf.log(f"warmup failed: {ex}")
        mf.log(f"init {time.time() - t0:.2f}s, nav nodes {len(self.nav.nodes)}")

    # ------------------------------------------------------------------ helpers
    def zone_at(self, z, t):
        c0, r0 = z["center"], z["radius"]
        c1, r1 = z["next_center"], z["next_radius"]
        s0, s1 = z["shrink_start"], z["shrink_end"]
        if t <= s0:
            return c0, r0
        if t >= s1 or s1 <= s0:
            return c1, r1
        f = (t - s0) / (s1 - s0)
        return [c0[0] + (c1[0] - c0[0]) * f, c0[1] + (c1[1] - c0[1]) * f], r0 + (r1 - r0) * f

    def slots(self, me):
        return [w["kind"] if w else None for w in me["weapons"]]

    def weapon(self, me, kind):
        for i, w in enumerate(me["weapons"]):
            if w and w["kind"] == kind:
                return i, w
        return None, None

    def center_of(self, m):
        scale = 1 + self.cfg["cubes"]["size_per_cube"] * m.get("cubes", 0)
        if m.get("kind") == "npc":
            return [m["pos"][0], m["pos"][1], m["pos"][2] + self.cfg["npc"]["height"] * 0.5]
        return [m["pos"][0], m["pos"][1], m["pos"][2] + 4.5 * scale]

    def radius_of(self, m):
        if m.get("kind") == "npc":
            return self.cfg["npc"]["radius"]
        return 2.5 * (1 + self.cfg["cubes"]["size_per_cube"] * m.get("cubes", 0))

    def aim_vec(self, yaw, pitch):
        return (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))

    def aim_err_ok(self, me, want_yaw, want_pitch, dist, radius, height):
        ay, ap = me["aim"]
        ey = abs(wrap(ay - want_yaw))
        ep = abs(ap - want_pitch)
        tol_y = math.atan2(radius * 0.75, max(dist, 1.0)) + 0.004
        tol_p = math.atan2(height * 0.35, max(dist, 1.0)) + 0.004
        return ey <= tol_y and ep <= tol_p

    # ------------------------------------------------------------------ main
    def act(self, obs):
        me = obs["self"]
        t = obs["t"]
        pos = me["pos"]
        p2 = (pos[0], pos[1])
        act = {"tick": obs["tick"]}
        mstats = me["stats"]
        muzzle = [pos[0], pos[1], pos[2] + mstats.get("muzzle_height", 7.0)]
        eye = [pos[0], pos[1], pos[2] + mstats.get("eye_height", 8.0)]
        hp_frac = me["hp"] / max(me["max_hp"], 1)

        # ---- upgrades
        if obs.get("offer"):
            ch = obs["offer"]["choices"]
            rank = {u: i for i, u in enumerate(UPGRADE_PRIORITY)}
            act["pick"] = min(range(len(ch)), key=lambda i: rank.get(ch[i]["id"], 99))

        # ---- events / memory
        for e in obs.get("events", []):
            if e["type"] == "damaged" and e.get("bearing") is not None:
                self.last_dmg = (t, e["bearing"], e.get("by"))
            elif e["type"] == "kill":
                self.my_kills += 1
            elif e["type"] == "take_failed":
                self.bad_pickups[e["id"]] = t
        if self.prev_alive is not None and obs["alive"] < self.prev_alive:
            mine = sum(1 for e in obs.get("events", []) if e["type"] == "kill")
            self.ffa_score += (self.prev_alive - obs["alive"]) - mine
        self.prev_alive = obs["alive"]
        for s in obs.get("sounds", []):
            if s["kind"] in ("gun", "laser", "laser_charge", "lightning", "mortar", "step", "boost", "jet", "reload"):
                self.noise.append((t - s["age"], s["bearing"], s["dist"], s["kind"]))
        self.noise = [n for n in self.noise if t - n[0] < 3.0]

        enemies = [m for m in obs["mechs"] if m["kind"] == "mech"]
        npcs = [m for m in obs["mechs"] if m["kind"] == "npc"]
        for m in enemies:
            self.enemy_seen[m["id"]] = (t, m["pos"], m["vel"], m.get("hp", 1400), m.get("weapons", []))

        # ---- zone
        z = obs["zone"]
        c_now, r_now = self.zone_at(z, t)
        c_soon, r_soon = self.zone_at(z, t + 10.0)
        c_next, r_next = z["next_center"], z["next_radius"]
        d_soon = hdist(p2, c_soon)
        zone_danger = d_soon > r_soon - 8 or not me["in_zone"]

        # ---- stuck detection
        if self.last_pos is not None:
            sp = hdist(p2, self.last_pos) / 0.1
            want = math.hypot(*self.prev_move)
            if want > 0.5 and sp < 1.5 and me["grounded"]:
                self.stuck_t += 0.1
            else:
                self.stuck_t = max(0.0, self.stuck_t - 0.05)
        self.last_pos = p2
        if self.stuck_t > 0.8 and t > self.unstick_until:
            self.unstick_until = t + 1.2
            a = math.atan2(self.prev_move[1], self.prev_move[0]) + self.rng.choice([-1, 1]) * self.rng.uniform(0.6, 1.6)
            self.unstick_dir = (math.cos(a), math.sin(a))
            self.stuck_t = 0.0

        # ---- target selection (mechs)
        target = None
        best = 1e18
        for m in enemies:
            c = self.center_of(m)
            d = math.dist(muzzle, c)
            vis = self.world.los(muzzle, c) or self.world.los(muzzle, [c[0], c[1], m["pos"][2] + 8.5])
            score = d + m.get("hp", 1400) * 0.04 + (0 if vis else 150) + (-40 if m["id"] == self.target_id else 0)
            if self.last_dmg and self.last_dmg[2] == m["id"] and t - self.last_dmg[0] < 3:
                score -= 60
            if score < best:
                best, target = score, (m, c, d, vis)
        self.target_id = target[0]["id"] if target else None

        # secondary targets: NPCs then crates (only when no mech is around)
        side = None
        recent_enemy = any(t - v[0] < 4.0 and hdist(p2, v[1]) < 160 for v in self.enemy_seen.values())
        if target is None:
            for n in sorted(npcs, key=lambda n: hdist(p2, n["pos"])):
                c = self.center_of(n)
                d = math.dist(muzzle, c)
                if d < 140 and self.world.los(muzzle, c):
                    side = (n, c, d, True)
                    break
            if side is None and not recent_enemy:
                for cr in sorted(obs.get("crates", []), key=lambda c: hdist(p2, c["pos"])):
                    c = [cr["pos"][0], cr["pos"][1], cr["pos"][2] + 1.2]
                    d = math.dist(muzzle, c)
                    if d < 90 and self.world.los(muzzle, c):
                        side = ({"id": cr["id"], "kind": "crate", "pos": cr["pos"], "vel": [0, 0, 0]}, c, d, True)
                        break
        shoot = target if (target and target[3]) else side

        # ---- aiming and firing
        fire = [False, False]
        aim = None
        ws = me["weapons"]
        gi, gun = self.weapon(me, "gun")
        li, laser = self.weapon(me, "laser")
        ki, light = self.weapon(me, "lightning")
        mi, mortar = self.weapon(me, "mortar")
        if shoot:
            m, c, d, vis = shoot
            is_mech = m.get("kind") == "mech"
            rad = self.radius_of(m) if m.get("kind") in ("mech", "npc") else 1.4
            hgt = (9.0 * (1 + 0.05 * m.get("cubes", 0))) if is_mech else (3.5 if m.get("kind") == "npc" else 2.4)
            direct_yaw = yaw_to(muzzle, c)
            direct_pitch = math.atan2(c[2] - muzzle[2], max(hdist(muzzle, c), 0.1))
            # gun lead
            lead_yaw, lead_pitch = direct_yaw, direct_pitch
            if gun:
                s = gun["stats"]["speed"]
                v = m.get("vel", [0, 0, 0])
                q = list(c)
                tt = d / s
                for _ in range(3):
                    q = [c[0] + v[0] * tt, c[1] + v[1] * tt, c[2] + max(min(v[2], 6), -6) * tt * 0.5]
                    tt = math.dist(muzzle, q) / s
                lead_yaw = yaw_to(muzzle, q)
                lead_pitch = math.atan2(q[2] - muzzle[2], max(hdist(muzzle, q), 0.1))
            laser_ready = laser is not None and (laser.get("cooldown", 0) < 0.4 or laser.get("charge", 0) > 0) and d < laser["stats"]["range"]
            light_in = light is not None and d < light["stats"]["range"] * 0.95 and me["energy"] > 6
            if light_in or laser_ready:
                aim = [direct_yaw, direct_pitch]
            elif gun:
                aim = [lead_yaw, lead_pitch]
            else:
                aim = [direct_yaw, direct_pitch]
            # gun
            if gun and gun.get("ammo", 0) > 0 and gun.get("reload", 0) == 0 and d < gun["stats"]["range"]:
                if self.aim_err_ok(me, lead_yaw, lead_pitch, d, rad, hgt):
                    fire[gi] = True
            # laser: hold to charge, release when full and on target
            if laser is not None and d < laser["stats"]["range"]:
                ch = laser.get("charge", 0)
                full = laser["stats"].get("charge", 0.75)
                on = self.aim_err_ok(me, direct_yaw, direct_pitch, d, rad, hgt)
                if ch > 0:
                    fire[li] = not (ch >= full * 0.97 and on)
                elif laser.get("cooldown", 0) <= 0.05 and (is_mech or m.get("kind") == "npc"):
                    fire[li] = True
            # lightning: instant, nearest in cone
            if light is not None and d < light["stats"]["range"] * 0.97 and me["energy"] >= light["stats"].get("energy", 3) + 2:
                if abs(wrap(me["aim"][0] - direct_yaw)) < math.radians(light["stats"]["cone_deg"]) * 0.45:
                    fire[ki] = True
            # mortar at mechs 30-220 m
            if mortar is not None and is_mech and 30 < d < 220 and mortar.get("cooldown", 0) <= 0:
                sol = self.mortar_pitch(pos, c, mortar["stats"])
                if sol is not None and not (light_in or laser_ready):
                    aim = [direct_yaw, sol]
                    if abs(wrap(me["aim"][0] - direct_yaw)) < 0.03 and abs(me["aim"][1] - sol) < 0.03:
                        fire[mi] = True
        elif target is not None and mortar is not None and mortar.get("cooldown", 0) <= 0:
            # lob over cover at a mech we know about but can't see
            m, c, d, _ = target
            if 30 < d < 220:
                sol = self.mortar_pitch(pos, c, mortar["stats"], high=True)
                if sol is not None:
                    aim = [yaw_to(muzzle, c), sol]
                    if abs(wrap(me["aim"][0] - aim[0])) < 0.03 and abs(me["aim"][1] - sol) < 0.03:
                        fire[mi] = True
        if aim is None:
            aim = self.look_dir(me, t, p2, target)
        if target is None and gun and gun.get("ammo", 0) < gun["stats"]["mag"] * 0.5 and gun.get("reload", 0) == 0 and not recent_enemy:
            act["reload"] = True
        # a held laser charge with nothing to shoot: keep holding (it auto-fires after hold_s)
        if laser is not None and laser.get("charge", 0) > 0 and not shoot:
            fire[li] = True

        # ---- movement
        try:
            mode, goal, move, boost, jump = self.choose_move(obs, me, t, p2, target, side, zone_danger, c_next, r_next, c_soon, r_soon, hp_frac)
        except Exception as ex:  # never let a movement bug stop us shooting
            self.errors = getattr(self, "errors", 0) + 1
            if self.errors <= 3:
                import traceback
                mf.log(traceback.format_exc())
            u = unit((c_soon[0] - p2[0], c_soon[1] - p2[1]))
            mode, goal, move, boost, jump = "fallback", None, u, not me["in_zone"], False
        if t < self.unstick_until:
            move = self.unstick_dir
            jump = True
            boost = True
            mode = "unstick"
        # dodge incoming mortar shells
        for pr in obs.get("projectiles", []):
            if pr["kind"] == "mortar":
                land = self.shell_landing(pr)
                if land and hdist(land, p2) < 11:
                    away = unit((p2[0] - land[0], p2[1] - land[1]))
                    move = (away[0] + move[0] * 0.3, away[1] + move[1] * 0.3)
                    boost = True
                    mode = "dodge"
        # take a pickup if within reach
        take = self.want_take(obs, me, p2)
        if take:
            act["take"] = take[0]
            if take[1] is not None:
                act["drop"] = take[1]

        self.prev_move = move
        act.update(move=[float(move[0]), float(move[1])], aim=[float(aim[0]), float(max(-0.69, min(1.29, aim[1])))],
                   fire=fire, boost=bool(boost), jump=bool(jump))
        mf.draw.label(f"{mode} hp{me['hp']:.0f} c{me['cubes']} k{self.my_kills} ffa{self.ffa_score:.0f}")
        if goal:
            mf.draw.line([pos[0], pos[1], pos[2] + 2], [goal[0], goal[1], pos[2] + 2], "#40c0ff")
        return act

    # ------------------------------------------------------------------ pieces
    def mortar_pitch(self, pos, c, st, high=False):
        v, g = st["speed"], st["gravity"]
        ox, oy, oz = pos[0], pos[1], pos[2] + 9.5
        d = math.hypot(c[0] - ox, c[1] - oy) - 3.0
        h = (c[2] - 3.0) - oz
        disc = v ** 4 - g * (g * d * d + 2 * h * v * v)
        if disc < 0 or d <= 1:
            return None
        r = math.sqrt(disc)
        th = math.atan2(v * v + r, g * d) if high else math.atan2(v * v - r, g * d)
        if th > 1.29 or th < -0.69:
            return None
        return th

    def shell_landing(self, pr):
        p, v = pr["pos"], pr["vel"]
        g = self.W["mortar"]["gravity"]
        gz = self.world.ground_at(p[0], p[1])
        # solve p.z + v.z t - g/2 t^2 = gz
        a, b, c = -0.5 * g, v[2], p[2] - gz
        disc = b * b - 4 * a * c
        if disc < 0:
            return None
        tt = (-b - math.sqrt(disc)) / (2 * a)
        if tt < 0 or tt > 8:
            return None
        return (p[0] + v[0] * tt, p[1] + v[1] * tt)

    def look_dir(self, me, t, p2, target):
        # someone shot us recently: face them (rear hits do x1.5)
        if self.last_dmg and t - self.last_dmg[0] < 2.5 and self.last_dmg[1] is not None:
            return [self.last_dmg[1], 0.0]
        if target is not None:  # known but not in sight
            c = target[1]
            return [yaw_to(p2, c), 0.0]
        # recently seen enemies (memory)
        recent = [(t - v[0], v[1]) for v in self.enemy_seen.values() if t - v[0] < 6]
        if recent:
            recent.sort()
            return [yaw_to(p2, recent[0][1]), 0.0]
        loud = [n for n in self.noise if n[2] in ("near", "mid") and n[3] != "reload"]
        if loud:
            n = max(loud, key=lambda n: n[0])
            return [n[1], 0.0]
        # scan around our direction of travel
        base = math.atan2(self.prev_move[1], self.prev_move[0]) if math.hypot(*self.prev_move) > 0.3 else me["aim"][0]
        self.scan_phase += 0.12
        return [base + 0.9 * math.sin(self.scan_phase), 0.0]

    def nav_move(self, p2, goal, onroof):
        goal = (float(goal[0]), float(goal[1]))
        if onroof:
            return unit((goal[0] - p2[0], goal[1] - p2[1])), goal
        wp, _ = self.nav.steer(p2, goal)
        return unit((wp[0] - p2[0], wp[1] - p2[1])), wp

    def choose_move(self, obs, me, t, p2, target, side, zone_danger, c_next, r_next, c_soon, r_soon, hp_frac):
        pos = me["pos"]
        onroof = pos[2] - self.world.ground_at(pos[0], pos[1]) > 2.5
        boost = False
        jump = False
        # where we'd like to hang out: inside the next circle, on our side of it
        r_hold = max(r_next * 0.55, 0.0)
        d_next = hdist(p2, c_next)
        if d_next > r_hold and d_next > 1:
            u = unit((p2[0] - c_next[0], p2[1] - c_next[1]))
            hold = (c_next[0] + u[0] * r_hold, c_next[1] + u[1] * r_hold)
        else:
            hold = p2
        # 1. zone
        if zone_danger:
            goal = c_soon if hdist(p2, c_soon) > r_soon * 0.5 else hold
            mv, wp = self.nav_move(p2, goal, onroof)
            boost = not me["in_zone"] or hdist(p2, c_soon) > r_soon - 3
            if target and target[3]:
                return "zone+fight", wp, self.strafed(mv, target, t, 0.35), boost, False
            return "zone", wp, mv, boost, False
        # 2. combat with a mech
        if target is not None:
            m, c, d, vis = target
            enemy_hp = m.get("hp", 1400)
            to = unit((c[0] - p2[0], c[1] - p2[1]))
            threats = [e for e in obs["mechs"] if e["kind"] == "mech" and hdist(p2, e["pos"]) < 200
                       and self.t_seen(e, t)]
            n_close = sum(1 for e in threats if hdist(p2, e["pos"]) < 120)
            # recovering: break line of sight, regen, then come back
            if hp_frac < 0.45 or (n_close >= 2 and hp_frac < 0.7):
                self.recovering = True
            if self.recovering and (hp_frac > 0.85 or (d < 22 and enemy_hp < me["hp"])):
                self.recovering = False
            if self.recovering and not zone_danger:
                cov = self.find_cover(p2, threats or [m], t, c_soon, r_soon)
                if cov is not None:
                    if hdist(p2, cov) < 2.5:
                        return "cover", cov, (0.0, 0.0), False, False
                    mv, wp = self.nav_move(p2, cov, onroof)
                    return "to-cover", wp, mv, hdist(p2, cov) > 6, False
                away = (p2[0] - to[0] * 60, p2[1] - to[1] * 60)
                if hdist(away, c_soon) > r_soon * 0.85:  # don't flee into the storm
                    u = unit((away[0] - c_soon[0], away[1] - c_soon[1]))
                    away = (c_soon[0] + u[0] * r_soon * 0.8, c_soon[1] + u[1] * r_soon * 0.8)
                mv, wp = self.nav_move(p2, away, onroof)
                return "retreat", wp, self.strafed(mv, target, t, 0.4), True, False
            kinds = self.slots(me)
            if "lightning" in kinds and me["energy"] > 25:
                want = 28.0
            elif "laser" in kinds:
                want = 85.0
            else:
                want = 60.0
            if not vis:
                if self.recovering:
                    return "lurk", None, (0.0, 0.0), False, False
                mv, wp = self.nav_move(p2, (c[0], c[1]), onroof)
                return "hunt", wp, mv, False, False
            if d > want + 15:
                mv, wp = self.nav_move(p2, (c[0], c[1]), onroof)
                return "close", wp, self.strafed(mv, target, t, 0.5), False, False
            if d < want - 15:
                return "space", None, self.strafed((-to[0], -to[1]), target, t, 0.6), False, False
            return "strafe", None, self.strafed((0.0, 0.0), target, t, 1.0), False, False
        self.recovering = self.recovering and hp_frac < 0.85
        # 3. loot: weapons we want, then cubes
        pk = self.best_pickup(obs, me, p2, c_soon, r_soon)
        if pk is not None:
            mv, wp = self.nav_move(p2, pk["pos"], onroof)
            return "loot", wp, mv, False, False
        cubes = [c for c in obs.get("cubes", []) if hdist(p2, c["pos"]) < 70 and hdist(c["pos"], c_soon) < r_soon - 10]
        if cubes:
            cb = min(cubes, key=lambda c: hdist(p2, c["pos"]))
            mv, wp = self.nav_move(p2, cb["pos"], onroof)
            return "cube", wp, mv, False, False
        # 4. shooting an NPC or crate: hold still-ish and keep some distance from NPCs
        if side is not None:
            m, c, d, _ = side
            if m.get("kind") == "npc":
                if d < 35:
                    return "npc", None, self.strafed(unit((p2[0] - c[0], p2[1] - c[1])), side, t, 0.7), False, False
                return "npc", None, self.strafed((0.0, 0.0), side, t, 0.6), False, False
            return "crate", None, (0.0, 0.0), False, False
        # 5. supply drop
        for dr in obs.get("drops", []):
            if dr["lands_in"] < 15 and hp_frac > 0.4 and hdist(dr["pos"], c_soon) < r_soon - 10:
                dd = hdist(p2, dr["pos"])
                if dd < 220:
                    if dd < dr["radius"] - 2:
                        return "capture", None, (0.0, 0.0), False, False
                    mv, wp = self.nav_move(p2, dr["pos"], onroof)
                    return "drop", wp, mv, dd > 60, False
        # 6. drift toward the hold point
        if hdist(p2, hold) > 12:
            mv, wp = self.nav_move(p2, hold, onroof)
            return "hold", wp, (mv[0] * 0.8, mv[1] * 0.8), False, False
        return "idle", None, (0.0, 0.0), False, False

    def t_seen(self, e, t):
        v = self.enemy_seen.get(e["id"])
        return v is not None and t - v[0] < 1.0

    def find_cover(self, p2, threats, t, c_soon, r_soon):
        """Nearest walkable spot (<= 34 m) that no threat can see; cached for 1 s."""
        if self.cover is not None and t - self.cover_t < 1.0:
            return self.cover
        eyes = [(e["pos"][0], e["pos"][1], e["pos"][2] + 8.0) for e in threats[:4]]
        best = None
        for r in (7.0, 12.0, 18.0, 25.0, 34.0):
            for k in range(16):
                a = k * TAU / 16 + (r * 0.37)
                q = (p2[0] + math.cos(a) * r, p2[1] + math.sin(a) * r)
                if not self.world.in_bounds(*q) or not self.world.walkable(*q):
                    continue
                if hdist(q, c_soon) > r_soon - 5:
                    continue
                gz = self.world.ground_at(*q)
                if any(self.world.los(ey, (q[0], q[1], gz + 4.5)) or self.world.los(ey, (q[0], q[1], gz + 8.5)) for ey in eyes):
                    continue
                if not self.world.walk_clear(p2, q):
                    continue
                score = r + min(hdist(q, (e[0], e[1])) for e in eyes) * -0.15
                if best is None or score < best[0]:
                    best = (score, q)
            if best is not None:
                break
        self.cover = best[1] if best else None
        self.cover_t = t
        return self.cover

    def strafed(self, mv, target, t, k):
        m, c = target[0], target[1]
        p = self.last_pos
        to = unit((c[0] - p[0], c[1] - p[1]))
        if t > self.strafe_until:
            self.strafe = -self.strafe
            self.strafe_until = t + self.rng.uniform(0.8, 2.2)
        perp = (-to[1] * self.strafe, to[0] * self.strafe)
        # if the enemy laser is charging at us, dodge hard
        if m.get("charging"):
            k = 1.0
        x = mv[0] + perp[0] * k
        y = mv[1] + perp[1] * k
        # don't strafe into walls
        nx, ny = p[0] + x * 4, p[1] + y * 4
        if not self.world.walkable(nx, ny):
            self.strafe = -self.strafe
            x = mv[0] - perp[0] * k
            y = mv[1] - perp[1] * k
        n = math.hypot(x, y)
        return (x / n, y / n) if n > 1 else (x, y)

    def best_pickup(self, obs, me, p2, c_soon, r_soon):
        kinds = self.slots(me)
        best, bestv = None, 0.0
        for pk in obs.get("pickups", []):
            k = pk["kind"]
            if k in kinds or self.bad_pickups.get(pk["id"], -99) > obs["t"] - 5:
                continue
            d = hdist(p2, pk["pos"])
            if d > (160 if None in kinds else 90) or hdist(pk["pos"], c_soon) > r_soon - 8:
                continue
            gain = self.loadout_gain(kinds, k)
            if gain <= 0:
                continue
            v = gain * 100 - d
            if v > bestv:
                best, bestv = pk, v
        return best

    def loadout_gain(self, kinds, k):
        if None in kinds:
            return WEAPON_RANK.get(k, 0)
        worst = min(WEAPON_RANK.get(x, 0) for x in kinds)
        return WEAPON_RANK.get(k, 0) - worst

    def want_take(self, obs, me, p2):
        kinds = self.slots(me)
        for pk in obs.get("pickups", []):
            if pk["kind"] in kinds:
                continue
            if hdist(p2, pk["pos"]) > self.reach - 0.3 or abs(pk["pos"][2] - me["pos"][2]) > 3.8:
                continue
            if self.loadout_gain(kinds, pk["kind"]) <= 0:
                continue
            if None in kinds:
                return pk["id"], None
            # swap out the worst weapon (never a charging laser)
            cand = [(WEAPON_RANK.get(w["kind"], 0), i) for i, w in enumerate(me["weapons"])
                    if w and not (w["kind"] == "laser" and w.get("charge", 0) > 0)]
            if not cand:
                return None
            return pk["id"], min(cand)[1]
        return None


if __name__ == "__main__":
    mf.run(Bot)
