"""Stand-in house bots for the local sim's practice mode.

Our own model, written from public observations of the real house squad (behaviour notes in
jklein07/mech-royale-bot, MIT): skill-dependent aim error resampled every ~0.3 s, a reaction delay
when switching targets, partial target leading for weaker tiers, poor laser accuracy, and passive
non-hunters that leave the prey alone unless it hurts them. Hunters always know the prey's position.
"""
import math
import random

SIGMA_DEG = {"easy": 3.5, "medium": 2.0, "hard": 1.3, "expert": 0.8}
REACT_S = {"easy": 0.7, "medium": 0.45, "hard": 0.3, "expert": 0.15}
LEAD = {"easy": 0.4, "medium": 0.75, "hard": 1.0, "expert": 1.0}
STRAFE = {"easy": 0.3, "medium": 0.6, "hard": 0.9, "expert": 0.9}
LASER_ERR_DEG = 2.5


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def unit(x, y):
    n = math.hypot(x, y)
    return (x / n, y / n) if n > 1e-9 else (0.0, 0.0)


class HouseBot:
    """Constructed by the sim with (hello, sim, mech). sim.intel gives hunters + prey."""

    def __init__(self, hello, tier, sim_ref):
        self.tier = tier
        self.sim = sim_ref
        self.cfg = hello["config"]
        self.rng = random.Random(hello.get("seed", 0))
        self.world, self.nav = sim_ref.world, sim_ref.nav
        self.err = (0.0, 0.0)
        self.err_t = -1.0
        self.lerr = 0.0
        self.react_t = 0.0
        self.target_id = None
        self.strafe = 1.0
        self.strafe_t = 0.0
        self.last_hurt = -99.0
        self.roam = None

    def go(self, me, gx, gy):
        p = (me["pos"][0], me["pos"][1])
        if math.hypot(gx - p[0], gy - p[1]) < 2:
            return [0.0, 0.0]
        wp, _ = self.nav.steer(p, (gx, gy))
        return list(unit(wp[0] - p[0], wp[1] - p[1]))

    def act(self, o):
        me = o["self"]
        t = o["t"]
        a = {"tick": o["tick"], "fire": [False, False]}
        if o.get("offer"):
            a["pick"] = 0
        for e in o["events"]:
            if e["type"] == "damaged" and e.get("by") is not None:
                self.last_hurt = t
        hunting = me["id"] in self.sim.hunters
        prey = [m for m in o["mechs"] if m["kind"] == "mech"]  # sim already filtered out squad mates
        passive = not hunting and t - self.last_hurt > 6.0
        target = None
        if not passive:
            for m in prey:
                d = math.dist(m["pos"], me["pos"])
                if target is None or d < target[1]:
                    target = (m, d, True)
        if target is None and hunting and self.sim.prey_info is not None:
            pm = self.sim.prey_info
            target = (pm, math.dist(pm["pos"], me["pos"]), False)
        muz = [me["pos"][0], me["pos"][1], me["pos"][2] + me["stats"]["muzzle_height"]]
        z = o["zone"]
        zc, zr = z["next_center"], z["next_radius"]
        dz = math.hypot(me["pos"][0] - zc[0], me["pos"][1] - zc[1])
        # movement
        if not me["in_zone"] or (t > z["shrink_start"] - 10 and dz > zr * 0.9):
            a["move"] = self.go(me, zc[0], zc[1])
            a["boost"] = not me["in_zone"]
        elif target is not None and (hunting or (target[2] and target[1] < 120)):
            m, d, vis = target
            pref = 25.0 if "lightning" in [w["kind"] for w in me["weapons"] if w] else 55.0
            tc = [m["pos"][0], m["pos"][1], m["pos"][2] + 4.5]
            los = self.world.los(muz, tc)
            if not los or d > pref + 50:
                a["move"] = self.go(me, m["pos"][0], m["pos"][1])
                a["boost"] = d > 150 and me["energy"] > 50
            else:
                rx, ry = unit(m["pos"][0] - me["pos"][0], m["pos"][1] - me["pos"][1])
                if t > self.strafe_t:
                    self.strafe = self.rng.choice([-1.0, 1.0])
                    self.strafe_t = t + self.rng.uniform(0.5, 1.5)
                rad = max(-1.0, min(1.0, (d - pref) / 30.0))
                s = STRAFE[self.tier]
                a["move"] = list(unit(-ry * self.strafe * s + rx * rad, rx * self.strafe * s + ry * rad))
        else:
            a["move"] = self.loot_or_roam(o, me, zc, zr)
        # aim / fire
        if target is not None:
            m, d, vis = target
            if m["id"] != self.target_id:
                self.target_id = m["id"]
                self.react_t = t + REACT_S[self.tier]
            if t > self.err_t:
                s = math.radians(SIGMA_DEG[self.tier])
                self.err = (self.rng.gauss(0, s), self.rng.gauss(0, s * 0.6))
                self.lerr = self.rng.gauss(0, math.radians(LASER_ERR_DEG))
                self.err_t = t + 0.3
            tc = [m["pos"][0], m["pos"][1], m["pos"][2] + 4.5]
            v = m.get("vel", [0, 0, 0])
            gun = next((w for w in me["weapons"] if w and w["kind"] == "gun"), None)
            sp = gun["stats"]["speed"] if gun else 252.0
            ti = d / sp
            for _ in range(2):
                q = [tc[0] + v[0] * ti * LEAD[self.tier], tc[1] + v[1] * ti * LEAD[self.tier], tc[2]]
                ti = math.dist(muz, q) / sp
            ay = math.atan2(q[1] - muz[1], q[0] - muz[0])
            ap = math.atan2(q[2] - muz[2], math.hypot(q[0] - muz[0], q[1] - muz[1]))
            charging = any(w and w["kind"] == "laser" and w.get("charge", 0) > 0 for w in me["weapons"])
            aim = [ay + self.err[0] + (self.lerr if charging else 0.0), ap + self.err[1]]
            a["aim"] = aim
            los = self.world.los(muz, tc)
            if vis and los and t >= self.react_t:
                err = abs(wrap(aim[0] - me["aim"][0]))
                for s_, w in enumerate(me["weapons"]):
                    if not w:
                        continue
                    k = w["kind"]
                    if k == "gun":
                        if err < 0.06 and d < w["stats"]["range"] and w.get("ammo", 0) > 0:
                            a["fire"][s_] = True
                        if w.get("ammo", 0) <= 0:
                            a["reload"] = True
                    elif k == "laser" and d < w["stats"]["range"]:
                        if w.get("charge", 0) <= 0:
                            a["fire"][s_] = w["cooldown"] <= 0 and err < 0.3
                        elif w["charge"] < w["stats"]["charge"]:
                            a["fire"][s_] = True
                        else:
                            a["fire"][s_] = err > 0.02
                    elif k == "lightning" and d < w["stats"]["range"] and err < 0.25:
                        a["fire"][s_] = True
        else:
            mv = a.get("move", [0, 0])
            if abs(mv[0]) + abs(mv[1]) > 0.1:
                a["aim"] = [math.atan2(mv[1], mv[0]), 0.0]
            best = None
            for c in o.get("crates", []):
                dd = math.dist(c["pos"], me["pos"])
                if dd < 50 and (best is None or dd < best[1]):
                    best = (c, dd)
            if best:
                c = best[0]
                p = [c["pos"][0], c["pos"][1], c["pos"][2] + 1.2]
                if self.world.los(muz, p):
                    ay = math.atan2(p[1] - muz[1], p[0] - muz[0])
                    a["aim"] = [ay, math.atan2(p[2] - muz[2], math.hypot(p[0] - muz[0], p[1] - muz[1]))]
                    if abs(wrap(ay - me["aim"][0])) < 0.03 and me["weapons"][0] and me["weapons"][0]["kind"] == "gun":
                        a["fire"][0] = True
        # take weapons into an empty slot
        if me["weapons"][1] is None:
            kinds = [w["kind"] for w in me["weapons"] if w]
            for pk in o.get("pickups", []):
                if math.hypot(pk["pos"][0] - me["pos"][0], pk["pos"][1] - me["pos"][1]) < 3.8 and pk["kind"] not in kinds:
                    a["take"] = pk["id"]
                    break
        return a

    def loot_or_roam(self, o, me, zc, zr):
        p = me["pos"]
        if me["weapons"][1] is None:
            picks = [pk for pk in o.get("pickups", []) if math.dist(pk["pos"], p) < 120]
            if picks:
                pk = min(picks, key=lambda q: math.dist(q["pos"], p))
                return self.go(me, pk["pos"][0], pk["pos"][1])
        cubes = [c for c in o.get("cubes", []) if math.dist(c["pos"], p) < 60]
        if cubes:
            c = min(cubes, key=lambda q: math.dist(q["pos"], p))
            return self.go(me, c["pos"][0], c["pos"][1])
        if self.roam is None or math.hypot(self.roam[0] - p[0], self.roam[1] - p[1]) < 8 or self.rng.random() < 0.004:
            for _ in range(20):
                ang = self.rng.uniform(0, 2 * math.pi)
                r = zr * 0.7 * math.sqrt(self.rng.random())
                q = (zc[0] + math.cos(ang) * r, zc[1] + math.sin(ang) * r)
                if self.world.in_bounds(*q) and self.world.walkable(*q):
                    self.roam = q
                    break
        if self.roam is None:
            return [0.0, 0.0]
        return self.go(me, self.roam[0], self.roam[1])
