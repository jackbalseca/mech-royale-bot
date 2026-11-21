"""Approximate local simulator for Mech Royale (mechfight/1 rules), for comparing bot versions.

It is NOT the official server: physics, vision (no trees) and NPCs are simplified. Use it for
relative comparisons (A vs B), not absolute scores.

Usage (from repo root):
  python3 tools/sim.py --mode ffa --bots bot.py:8,tools/bots/v0.py:8 --matches 4
  python3 tools/sim.py --mode practice --bots bot.py --matches 8
"""
import argparse
import gzip
import importlib.util
import json
import math
import os
import random
import sys
import time
from copy import deepcopy

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import world as W  # noqa: E402
import nav as N  # noqa: E402
import mechfight as mf  # noqa: E402

TAU = 2 * math.pi
DT = 0.05


def wrap(a):
    return (a + math.pi) % TAU - math.pi


def load_hello():
    with gzip.open(os.path.join(ROOT, "check", "stream.jsonl.gz"), "rt") as f:
        return json.loads(f.readline())


# ---------------------------------------------------------------- shared world for all bots
_SHARED = {}


def shared_world():
    if "w" not in _SHARED:
        _SHARED["w"] = W.World()
        _SHARED["g"] = dict(np.load(os.path.join(ROOT, "cache", "nav.npz")))
        _SHARED["nav"] = N.Nav(_SHARED["w"], _SHARED["g"])
    return _SHARED["w"], _SHARED["nav"]


def load_bot_class(path, tag):
    """Import a bot file as its own module, with World/Nav swapped for shared instances."""
    path = os.path.abspath(path)
    d = os.path.dirname(path)
    if d not in sys.path:
        sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location(f"botmod_{tag}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    w, nav = shared_world()
    mod.World = lambda *a, **k: w

    class _NavShim:
        def __new__(cls, *a, **k):
            return nav
    mod.Nav = _NavShim
    _orig_load = mod.np.load if hasattr(mod, "np") else None
    return mod.Bot


# ---------------------------------------------------------------- entities
class Mech:
    def __init__(self, mid, pos, cfg, ctrl, label, extra_spread=0.0):
        self.id = mid
        self.label = label
        self.ctrl = ctrl
        self.pos = np.array(pos, float)
        self.vel = np.zeros(3)
        self.aim = [random.uniform(-math.pi, math.pi), 0.0]
        self.cmd = {"move": [0, 0], "aim": list(self.aim), "fire": [False, False], "boost": False}
        self.ms = deepcopy(cfg["mech"])
        self.ws = deepcopy(cfg["weapons"])
        self.base_hp = self.ms["hp"]
        self.max_hp = self.ms["hp"]
        self.hp = self.max_hp
        self.energy = self.ms["energy"]
        self.weapons = [self.new_weapon("gun"), None]
        self.cubes = 0
        self.upgrades = []
        self.offers = []
        self.next_threshold = 0
        self.alive = True
        self.last_combat = -99.0
        self.last_spend = -99.0
        self.grounded = True
        self.events = []
        self.sounds = []
        self.memory = {}  # id -> last seen t
        self.extra_spread = extra_spread
        self.step_acc = 0.0
        self.kills = 0
        self.death_t = None
        self.offer_seq = 0
        self.charging = False

    def new_weapon(self, kind):
        w = {"kind": kind, "cooldown": 0.0, "equip": 0.0}
        if kind == "gun":
            w["ammo"] = self.ws["gun"]["mag"] if hasattr(self, "ws") else 12
            w["reload"] = 0.0
        if kind == "laser":
            w["charge"] = 0.0
            w["held"] = 0.0
        return w

    def scale(self):
        return 1 + 0.05 * self.cubes

    def dmg_mult(self, cfgc):
        return 1 + cfgc["damage_per_cube"] * min(self.cubes, cfgc["stat_cap"])

    def kinds(self):
        return [w["kind"] for w in self.weapons if w]


class Sim:
    def __init__(self, hello, specs, seed, mode="ffa", verbose=False):
        """specs: list of 16 dicts {cls, label, house:bool, tier}"""
        self.rng = random.Random(seed)
        random.seed(seed)
        self.hello = hello
        self.cfg = cfg = hello["config"]
        self.world, self.nav = shared_world()
        self.mode = mode
        self.t = 0.0
        self.tick = 0
        self.verbose = verbose
        self.proj = []
        self.next_id = {"proj": 1, "crate": 1000, "cube": 5000, "pick": 8000, "npc": 100}
        self.placements = {}
        self.dead_order = []
        self.player_kills = 0
        # zone schedule
        self.zone_phases = []
        c, r = list(cfg["zone"]["start_center"]), cfg["zone"]["start_radius"]
        t0 = 0.0
        for ph in cfg["zone"]["phases"]:
            rn = ph["radius"]
            ang = self.rng.uniform(0, TAU)
            off = self.rng.uniform(0, max(r - rn, 0)) * 0.7
            cn = [c[0] + math.cos(ang) * off, c[1] + math.sin(ang) * off]
            cn = self.clamp_walk(cn)
            self.zone_phases.append(dict(c0=c, r0=r, c1=cn, r1=rn, s0=t0 + ph["hold_s"], s1=t0 + ph["hold_s"] + ph["shrink_s"],
                                         start=t0, dps=ph["dps"]))
            t0 += ph["hold_s"] + ph["shrink_s"]
            c, r = cn, rn
        # spawns
        spawns = []
        tries = 0
        while len(spawns) < 16 and tries < 20000:
            tries += 1
            p = self.rand_point(cfg["zone"]["start_center"], cfg["zone"]["start_radius"] * cfg["match"]["spawn_zone_fraction"])
            if p is None:
                continue
            sep = cfg["match"]["spawn_min_separation"] if tries < 15000 else 60
            if all(math.dist(p, q) >= sep for q in spawns):
                spawns.append(p)
        order = list(range(16))
        self.rng.shuffle(order)
        self.mechs = []
        for slot, spec in enumerate(specs):
            p = spawns[order[slot]]
            z = self.world.ground_at(*p)
            tier_spread = {"easy": 2.5, "medium": 1.5, "hard": 0.8, "expert": 0.35}.get(spec.get("tier"), 0.0)
            m = Mech(slot, [p[0], p[1], z], cfg, None, spec["label"], tier_spread)
            m.house = spec.get("house", False)
            m.tier = spec.get("tier")
            h = deepcopy(hello)
            h["slot"] = slot
            h["seed"] = self.rng.randrange(1 << 31)
            m.ctrl = spec["cls"](h)
            self.mechs.append(m)
        # loot
        self.pickups = []
        weights = cfg["loot"]["weights"]
        kinds = [k for k, v in weights.items() for _ in range(int(v * 10))]
        for _ in range(cfg["loot"]["floor_count"]):
            p = self.rand_point(cfg["zone"]["start_center"], cfg["zone"]["start_radius"] * 0.95)
            if p:
                self.add_pickup(self.rng.choice(kinds), [p[0], p[1], self.world.ground_at(*p)])
        self.crates = []
        for _ in range(cfg["crates"]["count"]):
            p = self.rand_point(cfg["zone"]["start_center"], cfg["zone"]["start_radius"] * 0.95)
            if p:
                self.crates.append({"id": self.nid("crate"), "pos": [p[0], p[1], self.world.ground_at(*p)], "hp": cfg["crates"]["hp"]})
        self.cubes = []
        self.npcs = []
        for _ in range(cfg["npc"]["count"]):
            p = self.rand_point(cfg["zone"]["start_center"], cfg["zone"]["start_radius"] * 0.9)
            if p:
                self.npcs.append({"id": self.nid("npc"), "kind": "npc", "home": p, "pos": np.array([p[0], p[1], self.world.ground_at(*p)]),
                                  "hp": cfg["npc"]["hp"], "cd": 0.0, "target": None, "alive": True})

    # ------------------------------------------------------------ utils
    def nid(self, k):
        self.next_id[k] += 1
        return self.next_id[k]

    def clamp_walk(self, c):
        if self.world.walkable(*c):
            return c
        ids, d = self.nav.near_nodes(c[0], c[1], 60)
        if ids.size:
            return list(self.nav.nodes[ids[0]])
        return c

    def rand_point(self, c, r):
        for _ in range(50):
            a = self.rng.uniform(0, TAU)
            rr = r * math.sqrt(self.rng.random())
            p = (c[0] + math.cos(a) * rr, c[1] + math.sin(a) * rr)
            if self.world.in_bounds(*p) and self.world.walkable(*p):
                ids, _ = self.nav.near_nodes(p[0], p[1], 10)
                if ids.size:
                    return p
        return None

    def add_pickup(self, kind, pos):
        self.pickups.append({"id": self.nid("pick"), "kind": kind, "pos": list(pos)})

    def zone(self):
        for ph in self.zone_phases:
            if self.t < ph["s1"]:
                return ph
        return self.zone_phases[-1]

    def zone_circle(self):
        ph = self.zone()
        if self.t <= ph["s0"]:
            return ph["c0"], ph["r0"], ph["dps"]
        if self.t >= ph["s1"]:
            return ph["c1"], ph["r1"], ph["dps"]
        f = (self.t - ph["s0"]) / (ph["s1"] - ph["s0"])
        return [ph["c0"][0] + (ph["c1"][0] - ph["c0"][0]) * f, ph["c0"][1] + (ph["c1"][1] - ph["c0"][1]) * f], ph["r0"] + (ph["r1"] - ph["r0"]) * f, ph["dps"]

    def surface_at(self, x, y, z):
        """Height of the surface a mech at foot height z stands on."""
        g = self.world.ground_at(x, y)
        i, j = self.world.ij(x, y)
        top = self.world._bt[j, i]
        base = self.world._bb[j, i]
        if top > -1e8 and top <= z + 1.3 and top > g:
            return float(top)
        rt = self.world._rt[j, i]
        if rt > -1e8 and rt <= z + 1.3 and rt > g:
            return float(rt)
        return g

    def blocked(self, x, y, z):
        if not self.world.in_bounds(x, y):
            return True
        i, j = self.world.ij(x, y)
        top, base = self.world._bt[j, i], self.world._bb[j, i]
        h = 9.0
        if top > -1e8 and top > z + 1.2 and base < z + h:
            return True
        rt, rb = self.world._rt[j, i], self.world._rb[j, i]
        if rt > -1e8 and rt > z + 1.2 and rb < z + h:
            return True
        g = self.world.ground_at(x, y)
        if g > z + 1.2:
            return True
        return False

    # ------------------------------------------------------------ damage
    def damage(self, victim, amount, weapon, src_pos, attacker, effect=None):
        if not victim.alive:
            return
        rear = False
        if src_pos is not None and weapon != "zone":
            to_src = math.atan2(src_pos[1] - victim.pos[1], src_pos[0] - victim.pos[0])
            if abs(wrap(to_src - victim.aim[0])) > math.radians(self.cfg["mech"]["front_arc_deg"] / 2):
                rear = True
                amount *= self.cfg["mech"]["rear_mult"]
            amount *= (1 - min(victim.ms.get("armor", 0), 0.9))
        victim.hp -= amount
        victim.last_combat = self.t
        bearing = None if src_pos is None else math.atan2(src_pos[1] - victim.pos[1], src_pos[0] - victim.pos[0])
        victim.events.append({"type": "damaged", "amount": round(amount, 1), "weapon": weapon, "bearing": bearing,
                              "by": attacker.id if attacker else None, "rear": rear})
        if attacker is not None:
            attacker.last_combat = self.t
            attacker.events.append({"type": "hit", "target": victim.id, "amount": round(amount, 1), "weapon": weapon, "rear": rear})
        if victim.hp <= 0:
            self.kill(victim, attacker)

    def kill(self, m, attacker):
        m.alive = False
        m.hp = 0
        m.death_t = self.t
        self.dead_order.append((self.tick, m.id))
        if attacker is not None:
            attacker.kills += 1
            attacker.events.append({"type": "kill", "target": m.id})
            if not attacker.house and m.house:
                self.player_kills += 1
        n = m.cubes + self.cfg["cubes"]["death_drop_extra"]
        for k in range(n):
            a = k * TAU / max(n, 1)
            self.cubes.append({"id": self.nid("cube"), "pos": [m.pos[0] + math.cos(a) * 1.5, m.pos[1] + math.sin(a) * 1.5, m.pos[2]]})
        for w in m.weapons:
            if w and w["kind"] != "gun":
                self.add_pickup(w["kind"], list(m.pos))
        self.sound_all("death", m.pos, None)

    def damage_npc(self, n, amount, attacker):
        if not n["alive"]:
            return
        n["hp"] -= amount
        n["target"] = attacker.id if attacker else n["target"]
        if attacker:
            attacker.events.append({"type": "hit", "target": n["id"], "amount": amount, "weapon": "x"})
            attacker.last_combat = self.t
        if n["hp"] <= 0:
            n["alive"] = False
            for k in range(self.cfg["npc"]["cubes"]):
                self.cubes.append({"id": self.nid("cube"), "pos": [n["pos"][0] + k, n["pos"][1], n["pos"][2]]})

    def damage_crate(self, c, amount):
        c["hp"] -= amount
        if c["hp"] <= 0 and c in self.crates:
            self.crates.remove(c)
            self.cubes.append({"id": self.nid("cube"), "pos": list(c["pos"])})
            if self.rng.random() < self.cfg["loot"]["crate_weapon_chance"]:
                self.add_pickup(self.rng.choice(["laser", "lightning", "mortar"]), [c["pos"][0] + 1.5, c["pos"][1], c["pos"][2]])
            self.sound_all("crate", c["pos"], None)

    def sound_all(self, kind, pos, src):
        rng = self.cfg["sound"]["range"].get(kind, 100)
        for m in self.mechs:
            if not m.alive or m is src:
                continue
            d = math.hypot(pos[0] - m.pos[0], pos[1] - m.pos[1])
            if d <= rng * 1.0:
                b = math.atan2(pos[1] - m.pos[1], pos[0] - m.pos[0]) + self.rng.gauss(0, math.radians(7 * m.ms.get("hearing", 1)))
                cat = "near" if d < 60 else ("mid" if d < 160 else "far")
                m.sounds.append({"kind": kind, "bearing": wrap(b), "dist": cat, "age": 0.0})

    # ------------------------------------------------------------ geometry
    def seg_hit_cyl(self, p0, p1, c, r, h):
        """first t in [0,1] where segment hits the vertical cylinder (feet c, radius r, height h)."""
        d = p1 - p0
        fx, fy = p0[0] - c[0], p0[1] - c[1]
        a = d[0] * d[0] + d[1] * d[1]
        if a < 1e-9:
            inside = fx * fx + fy * fy <= r * r and c[2] <= p0[2] <= c[2] + h
            return 0.0 if inside else None
        b = 2 * (fx * d[0] + fy * d[1])
        cc = fx * fx + fy * fy - r * r
        disc = b * b - 4 * a * cc
        if disc < 0:
            return None
        sq = math.sqrt(disc)
        t0 = (-b - sq) / (2 * a)
        t1 = (-b + sq) / (2 * a)
        lo, hi = max(t0, 0.0), min(t1, 1.0)
        if lo > hi:
            return None
        for t in (lo, (lo + hi) / 2, hi):
            z = p0[2] + d[2] * t
            if c[2] <= z <= c[2] + h:
                return t
        return None

    def ray_targets(self, p0, p1, shooter):
        best = None
        for m in self.mechs:
            if m is shooter or not m.alive:
                continue
            t = self.seg_hit_cyl(p0, p1, m.pos, 2.5 * m.scale() + 0.3, 9 * m.scale())
            if t is not None and (best is None or t < best[0]):
                best = (t, "mech", m)
        for n in self.npcs:
            if not n["alive"]:
                continue
            t = self.seg_hit_cyl(p0, p1, n["pos"], 1.8 + 0.3, 3.5)
            if t is not None and (best is None or t < best[0]):
                best = (t, "npc", n)
        for c in self.crates:
            t = self.seg_hit_cyl(p0, p1, np.array(c["pos"]), 1.4 + 0.3, 2.4)
            if t is not None and (best is None or t < best[0]):
                best = (t, "crate", c)
        return best

    # ------------------------------------------------------------ observations
    def visible(self, m, target_pos, top_h):
        eye = [m.pos[0], m.pos[1], m.pos[2] + 8 * m.scale()]
        dx, dy = target_pos[0] - m.pos[0], target_pos[1] - m.pos[1]
        d = math.hypot(dx, dy)
        near = self.cfg["vision"]["near_range"] + m.ms.get("near_range_bonus", 0)
        far = self.cfg["vision"]["range"] + m.ms.get("vision_bonus", 0)
        if d > far:
            return False
        if d > near and abs(wrap(math.atan2(dy, dx) - m.aim[0])) > math.radians(self.cfg["vision"]["fov_deg"] / 2):
            return False
        c = [target_pos[0], target_pos[1], target_pos[2] + top_h * 0.5]
        if self.world.los(eye, c):
            return True
        return self.world.los(eye, [target_pos[0], target_pos[1], target_pos[2] + top_h])

    def wstats(self, m, kind):
        return m.ws[kind]

    def obs_for(self, m):
        cfg = self.cfg
        c_now, r_now, dps = self.zone_circle()
        ph = self.zone()
        mechs = []
        for o in self.mechs:
            if o is m or not o.alive:
                continue
            if self.visible(m, o.pos, 9 * o.scale()):
                m.memory[o.id] = self.t
            if self.t - m.memory.get(o.id, -99) <= cfg["vision"]["memory_s"]:
                mechs.append({"id": o.id, "kind": "mech", "pos": [round(v, 2) for v in o.pos], "vel": [round(v, 2) for v in o.vel],
                              "aim": list(o.aim), "hp": round(o.hp, 1), "max_hp": round(o.max_hp, 1), "cubes": o.cubes,
                              "weapons": o.kinds(), "charging": o.charging})
        for n in self.npcs:
            if n["alive"] and math.hypot(n["pos"][0] - m.pos[0], n["pos"][1] - m.pos[1]) < 200 and self.visible(m, n["pos"], 3.5):
                mechs.append({"id": n["id"], "kind": "npc", "pos": list(n["pos"]), "vel": [0, 0, 0], "aim": [0, 0], "hp": n["hp"], "max_hp": cfg["npc"]["hp"]})
        def vis_list(items, h):
            out = []
            for it in items:
                if math.hypot(it["pos"][0] - m.pos[0], it["pos"][1] - m.pos[1]) < 200 and self.visible(m, it["pos"], h):
                    out.append(it)
            return out
        crates = [{"id": c["id"], "pos": c["pos"], "hp": c["hp"]} for c in vis_list(self.crates, 2.4)]
        cubes = [{"id": c["id"], "pos": c["pos"]} for c in vis_list(self.cubes, 1.0)]
        picks = [dict(p) for p in vis_list(self.pickups, 1.0)]
        projs = []
        for p in self.proj:
            if p["owner"] is m:
                continue
            if math.hypot(p["pos"][0] - m.pos[0], p["pos"][1] - m.pos[1]) < 200:
                projs.append({"id": p["id"], "kind": p["kind"], "pos": list(p["pos"]), "vel": list(p["vel"])})
        weapons = []
        for w in m.weapons:
            if not w:
                weapons.append(None)
                continue
            d = {"kind": w["kind"], "cooldown": round(max(w["cooldown"], w["equip"]), 3), "stats": dict(m.ws[w["kind"]])}
            if w["kind"] == "gun":
                d["ammo"] = w["ammo"]
                d["reload"] = round(w["reload"], 2)
            if w["kind"] == "laser":
                d["charge"] = round(w["charge"], 3)
            weapons.append(d)
        stats = dict(m.ms)
        stats["eye_height"] = 8 * m.scale()
        stats["muzzle_height"] = 7 * m.scale()
        offer = None
        if m.offers:
            o = m.offers[0]
            offer = {"id": o["id"], "expires": o["expires"], "choices": [{"id": u["id"], "name": u["name"], "desc": u["desc"]} for u in o["choices"]]}
        in_zone = math.hypot(m.pos[0] - c_now[0], m.pos[1] - c_now[1]) <= r_now
        obs = {"type": "obs", "tick": self.tick, "t": round(self.t, 2), "alive": sum(1 for x in self.mechs if x.alive),
               "self": {"id": m.id, "pos": [round(v, 2) for v in m.pos], "vel": [round(v, 2) for v in m.vel], "aim": list(m.aim),
                        "hp": round(m.hp, 1), "max_hp": round(m.max_hp, 1), "energy": round(m.energy, 1), "max_energy": m.ms["energy"],
                        "grounded": m.grounded, "cubes": m.cubes, "upgrades": list(m.upgrades), "in_zone": in_zone,
                        "weapons": weapons, "stats": stats},
               "mechs": mechs, "projectiles": projs, "crates": crates, "cubes": cubes, "pickups": picks,
               "sounds": m.sounds, "beams": [], "events": m.events, "drops": [],
               "zone": {"center": ph["c0"], "radius": ph["r0"], "next_center": ph["c1"], "next_radius": ph["r1"],
                        "shrink_start": ph["s0"], "shrink_end": ph["s1"], "dps": dps},
               "offer": offer}
        m.sounds = []
        m.events = []
        return obs

    # ------------------------------------------------------------ decisions
    def decide(self):
        house_seen = {}
        player = [m for m in self.mechs if m.alive and not m.house]
        if self.mode == "practice":
            for h in self.mechs:
                if h.alive and h.house:
                    for p in player:
                        if self.visible(h, p.pos, 9):
                            house_seen[p.id] = self.t
        n_hunters = 1 + self.player_kills
        if self.t > 300:
            n_hunters = 99
        tier_order = {"easy": 0, "medium": 1, "hard": 2, "expert": 3}
        house_alive = sorted([m for m in self.mechs if m.alive and m.house], key=lambda m: (tier_order.get(m.tier, 0), m.id))
        hunters = set(m.id for m in house_alive[:n_hunters])
        for m in self.mechs:
            if not m.alive:
                continue
            obs = self.obs_for(m)
            if self.mode == "practice" and m.house:
                # squad: never target each other; hunters get the shared sighting of the player
                obs["mechs"] = [x for x in obs["mechs"] if x["kind"] == "npc" or not self.mechs[x["id"]].house]
                for p in player:
                    known = any(x["id"] == p.id for x in obs["mechs"])
                    shared = self.t - house_seen.get(p.id, -99) < 5 or m.id in hunters
                    if not known and shared and m.id in hunters:
                        obs["mechs"].append({"id": p.id, "kind": "mech", "pos": list(p.pos), "vel": list(p.vel), "aim": list(p.aim),
                                             "hp": p.hp, "max_hp": p.max_hp, "cubes": p.cubes, "weapons": p.kinds(), "charging": p.charging})
                    if known and m.id not in hunters and math.hypot(p.pos[0] - m.pos[0], p.pos[1] - m.pos[1]) > 70 and self.t - m.last_combat > 3:
                        obs["mechs"] = [x for x in obs["mechs"] if x["id"] != p.id]
            t0 = time.perf_counter()
            try:
                act = m.ctrl.act(obs) or {}
            except Exception as ex:  # crash = idle
                import traceback
                if self.verbose:
                    traceback.print_exc()
                act = {}
            mf.draw.take()
            el = (time.perf_counter() - t0) * 1000
            m.slow = getattr(m, "slow", 0) + (1 if el > 50 else 0)
            self.apply_action(m, act)

    def apply_action(self, m, act):
        cmd = m.cmd
        for k in ("move", "aim", "boost"):
            if k in act:
                cmd[k] = act[k]
        cmd["fire"] = list(act.get("fire", [False, False]))
        cmd["jump"] = bool(act.get("jump", False))
        cmd["reload"] = bool(act.get("reload", False))
        if "pick" in act and m.offers and act["pick"] is not None:
            self.apply_offer(m, int(act["pick"]))
        if act.get("take") is not None:
            self.do_take(m, act["take"], act.get("drop"))
        elif act.get("drop") is not None:
            s = act["drop"]
            if m.weapons[s] and not (m.weapons[s]["kind"] == "laser" and m.weapons[s]["charge"] > 0):
                self.add_pickup(m.weapons[s]["kind"], list(m.pos))
                m.weapons[s] = None

    def do_take(self, m, pid, drop):
        pk = next((p for p in self.pickups if p["id"] == pid), None)
        if pk is None:
            m.events.append({"type": "take_failed", "id": pid, "reason": "gone"})
            return
        if math.hypot(pk["pos"][0] - m.pos[0], pk["pos"][1] - m.pos[1]) > self.cfg["loot"]["pickup_radius"] or abs(pk["pos"][2] - m.pos[2]) > 4:
            m.events.append({"type": "take_failed", "id": pid, "reason": "range"})
            return
        if pk["kind"] in m.kinds():
            m.events.append({"type": "take_failed", "id": pid, "reason": "have"})
            return
        slot = None
        if None in m.weapons:
            slot = m.weapons.index(None)
        elif drop is not None:
            slot = drop
            old = m.weapons[slot]
            if old["kind"] == "laser" and old["charge"] > 0:
                m.events.append({"type": "take_failed", "id": pid, "reason": "busy"})
                return
            self.add_pickup(old["kind"], list(m.pos))
        else:
            m.events.append({"type": "take_failed", "id": pid, "reason": "full"})
            return
        self.pickups.remove(pk)
        w = m.new_weapon(pk["kind"])
        w["equip"] = max(self.cfg["loot"]["equip_s"], m.ws[pk["kind"]]["cooldown"])
        m.weapons[slot] = w
        m.events.append({"type": "took", "id": pid, "kind": pk["kind"], "slot": slot})

    def apply_offer(self, m, idx):
        o = m.offers.pop(0)
        idx = max(0, min(idx, len(o["choices"]) - 1))
        u = o["choices"][idx]
        m.upgrades.append(u["id"])
        for e in u["effects"]:
            parts = e["path"].split(".")
            d = m.ms if parts[0] == "mech" else m.ws[parts[1]]
            key = parts[-1]
            if "mul" in e:
                d[key] = d[key] * e["mul"]
            else:
                d[key] = d[key] + e["add"]
        if any(e["path"] == "mech.hp" for e in u["effects"]):
            self.recompute_hp(m)
        m.events.append({"type": "upgrade", "id": u["id"]})

    def recompute_hp(self, m):
        old = m.max_hp
        m.max_hp = m.ms["hp"] * (1 + self.cfg["cubes"]["hp_per_cube"] * min(m.cubes, self.cfg["cubes"]["stat_cap"]))
        if m.max_hp > old:
            m.hp += m.max_hp - old

    def gain_cube(self, m):
        m.cubes += 1
        self.recompute_hp(m)
        m.events.append({"type": "pickup", "cubes": m.cubes})
        th = self.cfg["cubes"]["upgrade_thresholds"]
        while m.next_threshold < len(th) and m.cubes >= th[m.next_threshold]:
            m.next_threshold += 1
            held = set(m.kinds())
            cands = []
            for u in self.cfg["upgrades"]:
                if m.upgrades.count(u["id"]) >= u["max"]:
                    continue
                wk = [e["path"].split(".")[1] for e in u["effects"] if e["path"].startswith("weapons.")]
                if wk and wk[0] not in held:
                    continue
                cands.append(u)
            self.rng.shuffle(cands)
            if cands:
                m.offer_seq += 1
                m.offers.append({"id": m.offer_seq, "expires": self.t + 5, "choices": cands[:3]})

    # ------------------------------------------------------------ physics step
    def step(self):
        cfg = self.cfg
        c_now, r_now, dps = self.zone_circle()
        for m in self.mechs:
            if not m.alive:
                continue
            ms = m.ms
            cmd = m.cmd
            # offers timeout
            if m.offers and self.t > m.offers[0]["expires"]:
                self.apply_offer(m, 0)
            # aim slew
            ty, tp = cmd["aim"][0], max(ms["min_pitch"], min(ms["max_pitch"], cmd["aim"][1]))
            dy = wrap(ty - m.aim[0])
            m.aim[0] = wrap(m.aim[0] + max(-ms["turn_rate"] * DT, min(ms["turn_rate"] * DT, dy)))
            dp = tp - m.aim[1]
            m.aim[1] += max(-ms["pitch_rate"] * DT, min(ms["pitch_rate"] * DT, dp))
            # movement
            mv = cmd["move"]
            L = math.hypot(mv[0], mv[1])
            if L > 1:
                mv = [mv[0] / L, mv[1] / L]
                L = 1
            spend = False
            speed = ms["walk_speed"]
            if cmd.get("boost") and m.grounded and L > 0.1 and m.energy > 0:
                speed = ms["boost_speed"]
                m.energy -= ms["boost_drain"] * DT
                spend = True
            if m.charging:
                speed *= cfg["mech"]["charge_move_mult"]
            want = [mv[0] * speed, mv[1] * speed]
            acc = ms["ground_accel"] if m.grounded else ms["air_accel"]
            for k in (0, 1):
                dv = want[k] - m.vel[k]
                m.vel[k] += max(-acc * DT, min(acc * DT, dv))
            if cmd.get("jump") and m.grounded:
                m.vel[2] = ms["jump_speed"]
                m.grounded = False
            if not m.grounded:
                m.vel[2] -= ms["gravity"] * DT
                if cmd.get("boost") and m.energy > 0:
                    m.vel[2] = min(m.vel[2] + ms["jet_accel"] * DT, ms["max_rise_speed"])
                    m.energy -= ms["jet_drain"] * DT
                    spend = True
                    m.step_acc += DT
            if spend:
                m.last_spend = self.t
            elif self.t - m.last_spend > ms["energy_regen_delay"]:
                m.energy = min(ms["energy"], m.energy + ms["energy_regen"] * DT)
            m.energy = max(0.0, m.energy)
            nx = m.pos[0] + m.vel[0] * DT
            ny = m.pos[1] + m.vel[1] * DT
            nz = m.pos[2] + m.vel[2] * DT
            if self.blocked(nx, ny, max(nz, m.pos[2])):
                if not self.blocked(nx, m.pos[1], max(nz, m.pos[2])):
                    ny = m.pos[1]
                    m.vel[1] = 0
                elif not self.blocked(m.pos[0], ny, max(nz, m.pos[2])):
                    nx = m.pos[0]
                    m.vel[0] = 0
                else:
                    nx, ny = m.pos[0], m.pos[1]
                    m.vel[0] = m.vel[1] = 0
            surf = self.surface_at(nx, ny, max(nz, m.pos[2]))
            if nz <= surf:
                nz = surf
                if m.vel[2] <= 0:
                    m.vel[2] = 0
                    m.grounded = True
            elif m.grounded and nz - surf < 1.3 and m.vel[2] <= 0:
                nz = surf  # walk down small steps / slopes
            else:
                m.grounded = False
            m.pos[:] = (nx, ny, nz)
            sp = math.hypot(m.vel[0], m.vel[1])
            if m.grounded and sp > cfg["sound"]["step_speed"]:
                m.step_acc += DT
                if m.step_acc >= cfg["sound"]["step_every"]:
                    m.step_acc = 0
                    self.sound_all("boost" if speed > ms["walk_speed"] + 1 else "step", m.pos, m)
            # pushing apart
            # weapons
            dmult = m.dmg_mult(cfg["cubes"])
            m.charging = False
            for s, w in enumerate(m.weapons):
                if not w:
                    continue
                w["cooldown"] = max(0.0, w["cooldown"] - DT)
                w["equip"] = max(0.0, w["equip"] - DT)
                k = w["kind"]
                st = m.ws[k]
                trig = cmd["fire"][s] if s < len(cmd["fire"]) else False
                if k == "gun":
                    if w["reload"] > 0:
                        w["reload"] -= DT
                        if w["reload"] <= 0:
                            w["reload"] = 0.0
                            w["ammo"] = int(st["mag"])
                    elif cmd.get("reload") and w["ammo"] < st["mag"]:
                        w["reload"] = st["reload"]
                    if trig and w["reload"] == 0 and w["ammo"] > 0 and w["cooldown"] <= 0 and w["equip"] <= 0:
                        self.fire_gun(m, st, dmult)
                        w["ammo"] -= 1
                        w["cooldown"] += st["cooldown"]
                        if w["ammo"] <= 0:
                            w["reload"] = st["reload"]
                elif k == "laser":
                    if w.get("short", 0) > 0:
                        w["short"] -= DT
                        w["charge"] = 0.0
                        continue
                    if w["charge"] > 0:
                        w["charge"] = min(st["charge"], w["charge"] + DT)
                        if w["charge"] >= st["charge"]:
                            w["held"] += DT
                        release = (not trig and w["charge"] >= st["min_charge"]) or w["held"] >= st["hold_s"]
                        if release:
                            self.fire_laser(m, st, dmult, w["charge"] / st["charge"])
                            w["charge"] = 0.0
                            w["held"] = 0.0
                            w["cooldown"] = st["cooldown"]
                        else:
                            m.charging = True
                    elif trig and w["cooldown"] <= 0 and w["equip"] <= 0:
                        w["charge"] = DT
                        m.charging = True
                        if self.tick % 10 == 0:
                            self.sound_all("laser_charge", m.pos, m)
                elif k == "lightning":
                    if trig and w["cooldown"] <= 0 and w["equip"] <= 0 and m.energy >= st["energy"]:
                        m.energy -= st["energy"]
                        m.last_spend = self.t
                        w["cooldown"] = st["cooldown"]
                        self.fire_lightning(m, st, dmult)
                elif k == "mortar":
                    if trig and w["cooldown"] <= 0 and w["equip"] <= 0:
                        w["cooldown"] = st["cooldown"]
                        self.fire_mortar(m, st, dmult)
            # zone / regen
            inz = math.hypot(m.pos[0] - c_now[0], m.pos[1] - c_now[1]) <= r_now
            if not inz:
                m.hp -= dps * DT
                m.last_combat = self.t
                if m.hp <= 0:
                    self.kill(m, None)
                    continue
            elif self.t - m.last_combat > ms["regen_delay"]:
                m.hp = min(m.max_hp, m.hp + ms["regen_per_s"] * DT)
            # cubes
            for c in list(self.cubes):
                if math.hypot(c["pos"][0] - m.pos[0], c["pos"][1] - m.pos[1]) <= cfg["cubes"]["pickup_radius"] and abs(c["pos"][2] - m.pos[2]) < 4:
                    self.cubes.remove(c)
                    self.gain_cube(m)
        # separation
        alive = [m for m in self.mechs if m.alive]
        for i in range(len(alive)):
            for j in range(i + 1, len(alive)):
                a, b = alive[i], alive[j]
                d = math.hypot(a.pos[0] - b.pos[0], a.pos[1] - b.pos[1])
                rr = 2.5 * (a.scale() + b.scale())
                if 1e-6 < d < rr and abs(a.pos[2] - b.pos[2]) < 9:
                    push = (rr - d) / 2 / d
                    dx, dy = (a.pos[0] - b.pos[0]) * push, (a.pos[1] - b.pos[1]) * push
                    if not self.blocked(a.pos[0] + dx, a.pos[1] + dy, a.pos[2]):
                        a.pos[0] += dx
                        a.pos[1] += dy
                    if not self.blocked(b.pos[0] - dx, b.pos[1] - dy, b.pos[2]):
                        b.pos[0] -= dx
                        b.pos[1] -= dy
        self.step_projectiles()
        self.step_npcs()

    def muzzle(self, m):
        return np.array([m.pos[0], m.pos[1], m.pos[2] + 7 * m.scale()])

    def dirvec(self, yaw, pitch):
        return np.array([math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)])

    def fire_gun(self, m, st, dmult):
        sp = math.radians(st["spread_deg"] + m.extra_spread)
        yaw = m.aim[0] + self.rng.gauss(0, sp)
        pitch = m.aim[1] + self.rng.gauss(0, sp)
        d = self.dirvec(yaw, pitch)
        o = self.muzzle(m) + d * 3.0
        self.proj.append({"id": self.nid("proj"), "kind": "gun", "owner": m, "pos": o, "vel": d * st["speed"], "dmg": st["damage"] * dmult,
                          "range": st["range"], "trav": 0.0, "origin": o.copy()})
        self.sound_all("gun", m.pos, m)

    def fire_mortar(self, m, st, dmult):
        sp = math.radians(m.extra_spread * 0.5)
        d = self.dirvec(m.aim[0] + self.rng.gauss(0, sp), m.aim[1] + self.rng.gauss(0, sp))
        o = np.array([m.pos[0], m.pos[1], m.pos[2] + 9.5 * m.scale()]) + d * 3.0
        self.proj.append({"id": self.nid("proj"), "kind": "mortar", "owner": m, "pos": o, "vel": d * st["speed"], "dmg": st["damage"] * dmult,
                          "st": st, "ttl": st["ttl"], "dmult": dmult})
        self.sound_all("mortar", m.pos, m)

    def fire_laser(self, m, st, dmult, frac):
        sp = math.radians(m.extra_spread * 0.5)
        d = self.dirvec(m.aim[0] + self.rng.gauss(0, sp), m.aim[1] + self.rng.gauss(0, sp))
        o = self.muzzle(m) + d * 3.0
        end = o + d * st["range"]
        wf = self.world.los_blocked_at(o, end, spacing=1.0)
        if wf is not None:
            end = o + (end - o) * wf
        hit = self.ray_targets(o, end, m)
        dmg = st["damage"] * (st["min_frac"] + (1 - st["min_frac"]) * frac) * dmult
        if hit:
            t, kind, tgt = hit
            if kind == "mech":
                if "mortar" in tgt.kinds():
                    dmg *= 1 + st["cookoff"]
                self.damage(tgt, dmg, "laser", m.pos, m)
            elif kind == "npc":
                self.damage_npc(tgt, dmg, m)
            else:
                self.damage_crate(tgt, dmg)
        self.sound_all("laser", m.pos, m)

    def fire_lightning(self, m, st, dmult):
        cands = []
        half = math.radians(st["cone_deg"] / 2)
        mz = self.muzzle(m)
        for o in self.mechs:
            if o is m or not o.alive:
                continue
            c = [o.pos[0], o.pos[1], o.pos[2] + 4.5 * o.scale()]
            cands.append((o, c, "mech"))
        for n in self.npcs:
            if n["alive"]:
                cands.append((n, [n["pos"][0], n["pos"][1], n["pos"][2] + 1.75], "npc"))
        for cr in self.crates:
            cands.append((cr, [cr["pos"][0], cr["pos"][1], cr["pos"][2] + 1.2], "crate"))
        best = None
        for o, c, k in cands:
            d = math.hypot(c[0] - m.pos[0], c[1] - m.pos[1])
            if d > st["range"] or abs(wrap(math.atan2(c[1] - m.pos[1], c[0] - m.pos[0]) - m.aim[0])) > half:
                continue
            if not self.world.los(mz, c):
                continue
            if best is None or d < best[0]:
                best = (d, o, c, k)
        self.sound_all("lightning", m.pos, m)
        if best is None:
            return
        chain = [best[1:]]
        hitset = {id(best[1])}
        dmg = st["damage"] * dmult
        cur = best
        for _ in range(int(st["chain"])):
            nxt = None
            for o, c, k in cands:
                if id(o) in hitset:
                    continue
                d = math.dist(c, cur[2])
                if d <= st["chain_range"] and (nxt is None or d < nxt[0]):
                    nxt = (d, o, c, k)
            if nxt is None:
                break
            hitset.add(id(nxt[1]))
            chain.append(nxt[1:])
            cur = nxt
        for i, (o, c, k) in enumerate(chain):
            dd = dmg * (st["chain_falloff"] ** i)
            if k == "mech":
                if "laser" in o.kinds():
                    for w in o.weapons:
                        if w and w["kind"] == "laser":
                            w["charge"] = 0.0
                            w["short"] = st["short_s"]
                self.damage(o, dd, "lightning", m.pos, m)
            elif k == "npc":
                self.damage_npc(o, dd, m)
            else:
                self.damage_crate(o, dd)

    def explode(self, p, st, owner, dmult, direct):
        if direct is not None and direct[1] == "mech":
            self.damage(direct[2], st["damage"] * dmult, "mortar", p, owner)
        elif direct is not None and direct[1] == "npc":
            self.damage_npc(direct[2], st["damage"] * dmult, owner)
        elif direct is not None and direct[1] == "crate":
            self.damage_crate(direct[2], st["damage"] * dmult)
        R = st["splash_radius"]
        for m in self.mechs:
            if not m.alive:
                continue
            c = np.array([m.pos[0], m.pos[1], m.pos[2] + 4.5 * m.scale()])
            d = max(0.0, float(np.linalg.norm(c - p)) - 2.5 * m.scale())
            if d > R or not self.world.los(p + np.array([0, 0, 0.5]), c):
                continue
            f = 1 - (1 - st["splash_edge"]) * (d / R)
            dmg = st["splash"] * dmult * f * (self.cfg["mech"]["self_damage_mult"] if m is owner else 1)
            if direct is None or direct[2] is not m:
                self.damage(m, dmg, "mortar", list(p), owner if m is not owner else None)
            away = np.array([m.pos[0] - p[0], m.pos[1] - p[1]])
            n = np.linalg.norm(away)
            away = away / n if n > 1e-6 else np.array([1.0, 0.0])
            m.vel[0] += away[0] * st["knock"] * f
            m.vel[1] += away[1] * st["knock"] * f
            m.vel[2] += st["knock_up"] * f
            m.grounded = False
            m.energy = max(0.0, m.energy - st["drain"] * f)
            m.events.append({"type": "effect", "effect": "concuss", "by": owner.id})
        self.sound_all("explosion", p, None)

    def step_projectiles(self):
        keep = []
        for p in self.proj:
            p0 = p["pos"].copy()
            if p["kind"] == "mortar":
                p["vel"][2] -= p["st"]["gravity"] * DT
            p1 = p0 + p["vel"] * DT
            wf = self.world.los_blocked_at(p0, p1, spacing=1.0)
            end = p1 if wf is None else p0 + (p1 - p0) * wf
            hit = self.ray_targets(p0, end, p["owner"])
            if p["kind"] == "gun":
                p["trav"] += float(np.linalg.norm(p1 - p0))
                if hit:
                    t, kind, tgt = hit
                    if kind == "mech":
                        self.damage(tgt, p["dmg"], "gun", p["origin"], p["owner"])
                    elif kind == "npc":
                        self.damage_npc(tgt, p["dmg"], p["owner"])
                    else:
                        self.damage_crate(tgt, p["dmg"])
                    continue
                if wf is not None or p["trav"] > p["range"]:
                    continue
            else:
                p["ttl"] -= DT
                if hit:
                    self.explode(p0 + (end - p0) * hit[0], p["st"], p["owner"], p["dmult"], hit)
                    continue
                if wf is not None:
                    self.explode(end, p["st"], p["owner"], p["dmult"], None)
                    continue
                if p["ttl"] <= 0:
                    continue
            p["pos"] = p1
            keep.append(p)
        self.proj = keep

    def step_npcs(self):
        cfgn = self.cfg["npc"]
        for n in self.npcs:
            if not n["alive"]:
                continue
            n["cd"] = max(0.0, n["cd"] - DT)
            tgt = None
            if n["target"] is not None:
                m = self.mechs[n["target"]] if n["target"] < 16 else None
                if m and m.alive and math.hypot(m.pos[0] - n["pos"][0], m.pos[1] - n["pos"][1]) < cfgn["deaggro_range"]:
                    tgt = m
                else:
                    n["target"] = None
            if tgt is None:
                for m in self.mechs:
                    if m.alive and math.hypot(m.pos[0] - n["pos"][0], m.pos[1] - n["pos"][1]) < cfgn["aggro_range"]:
                        tgt = m
                        break
            if tgt is not None and n["cd"] <= 0:
                eye = [n["pos"][0], n["pos"][1], n["pos"][2] + 3]
                c = [tgt.pos[0], tgt.pos[1], tgt.pos[2] + 4.5]
                if self.world.los(eye, c):
                    n["cd"] = cfgn["cooldown"]
                    if self.rng.random() < 0.6:
                        self.damage(tgt, cfgn["damage"], "npc", list(n["pos"]), None)
                    self.sound_all("npc_gun", n["pos"], None)

    # ------------------------------------------------------------ run
    def run(self):
        cfg = self.cfg
        dur = cfg["match"]["duration_s"]
        while True:
            alive = [m for m in self.mechs if m.alive]
            if len(alive) <= 1 or self.t >= dur:
                break
            if self.mode == "practice" and not any(not m.house for m in alive):
                break
            if self.tick % 2 == 0:
                self.decide()
            self.step()
            self.t += DT
            self.tick += 1
        # placements
        alive = [m for m in self.mechs if m.alive]
        alive.sort(key=lambda m: -m.hp)
        place = {}
        for i, m in enumerate(alive):
            place[m.id] = i + 1
        n_alive = len(alive)
        # dead: later death = better place; same tick share
        dead = sorted(self.dead_order, key=lambda x: -x[0])
        rank = n_alive
        i = 0
        while i < len(dead):
            tk = dead[i][0]
            group = [d for d in dead[i:] if d[0] == tk]
            for _, mid in group:
                place[mid] = rank + 1
            rank += len(group)
            i += len(group)
        return [{"slot": m.id, "label": m.label, "place": place[m.id], "kills": m.kills, "cubes": m.cubes,
                 "death_t": m.death_t, "slow": getattr(m, "slow", 0)} for m in self.mechs], self.t


def run_one(args):
    mode, bot_specs, seed = args
    hello = load_hello()
    classes = {}
    specs = []
    if mode == "ffa":
        for path, label, count in bot_specs:
            if path not in classes:
                classes[path] = load_bot_class(path, len(classes))
            specs += [{"cls": classes[path], "label": label} for _ in range(count)]
        random.Random(seed).shuffle(specs)
    else:
        path, label, _ = bot_specs[0]
        house_path = bot_specs[1][0] if len(bot_specs) > 1 else path
        pc = load_bot_class(path, 0)
        hc = load_bot_class(house_path, 1) if house_path != path else pc
        tiers = ["easy"] * 4 + ["medium"] * 4 + ["hard"] * 4 + ["expert"] * 3
        specs = [{"cls": pc, "label": label}] + [{"cls": hc, "label": "house-" + t, "house": True, "tier": t} for t in tiers]
    sim = Sim(hello, specs, seed, mode)
    t0 = time.time()
    res, t_end = sim.run()
    return res, t_end, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="ffa", choices=["ffa", "practice"])
    ap.add_argument("--bots", required=True, help="path[:count],... (ffa) or player_path[,house_path] (practice)")
    ap.add_argument("--matches", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    a = ap.parse_args()
    specs = []
    for part in a.bots.split(","):
        bits = part.split(":")
        path = bits[0]
        cnt = int(bits[1]) if len(bits) > 1 else 16
        specs.append((path, os.path.relpath(path, ROOT), cnt))
    jobs = [(a.mode, specs, a.seed + i) for i in range(a.matches)]
    from multiprocessing import Pool
    t0 = time.time()
    if a.jobs > 1:
        with Pool(a.jobs) as pool:
            outs = pool.map(run_one, jobs)
    else:
        outs = [run_one(j) for j in jobs]
    agg = {}
    for res, t_end, wall in outs:
        print(f"match: {t_end:.0f}s sim, {wall:.0f}s wall", file=sys.stderr)
        for r in res:
            if a.mode == "practice" and r["label"].startswith("house"):
                continue
            g = agg.setdefault(r["label"], {"pts": [], "kills": [], "slow": 0, "death": []})
            g["pts"].append(16 - r["place"])
            g["kills"].append(r["kills"])
            g["slow"] += r["slow"]
            g["death"].append(r["death_t"] or t_end)
    for label, g in agg.items():
        p = np.array(g["pts"], float)
        se = p.std(ddof=1) / math.sqrt(len(p)) if len(p) > 1 else 0
        print(f"{label:30s} score {p.mean():5.2f} ± {se:.2f}  (n={len(p)})  kills {np.mean(g['kills']):.2f}  "
              f"survive {np.mean(g['death']):.0f}s  slow {g['slow']}")
    print(f"total wall {time.time() - t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
