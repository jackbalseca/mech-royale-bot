"""v24 scenario checks: bot.py vs tools/bots/v19.py on hand-built observations (decisions only, not outcomes).
Usage (repo root): python3 tools/scen_v24.py      exits non-zero if any assertion fails."""
import copy, gzip, json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim as S, mechfight as mf  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
L = [json.loads(l) for l in gzip.open(os.path.join(ROOT, "check", "stream.jsonl.gz"))]
HELLO = L[0]
BASE = [o for o in L if o.get("type") == "obs"][50]  # t=5, one gun, in zone
CFG = HELLO["config"]
NEW = S.load_bot_class(os.path.join(ROOT, "bot.py"), "scen_new")
OLD = S.load_bot_class(os.path.join(ROOT, "tools", "bots", "v19.py"), "scen_v19")
W = S.shared_world()[0]


def wpn(kind):
    w = {"kind": kind, "cooldown": 0, "stats": copy.deepcopy(CFG["weapons"][kind])}
    w.update({"ammo": 12, "reload": 0} if kind == "gun" else {"charge": 0} if kind == "laser" else {})
    return w


def base(hp=1400, weapons=("gun", None)):
    o = copy.deepcopy(BASE)
    for k in ("mechs", "crates", "pickups", "projectiles", "cubes", "events", "sounds", "beams", "drops"):
        o[k] = []
    o["self"]["hp"] = hp
    o["self"]["weapons"] = [wpn(k) if k else None for k in weapons]
    return o


def run(cls, o, seen=None):
    b = cls(HELLO)
    if seen:
        b.enemy_seen.update(seen)
    a = b.act(copy.deepcopy(o))
    lab = (mf.draw.take() or {}).get("label", "")
    a["mode"] = lab.split()[0] if lab else ""
    return a


def me_xy(o):
    return o["self"]["pos"][0], o["self"]["pos"][1]


def aim_at(o, c):
    me = o["self"]
    mz = me["pos"][2] + me["stats"].get("muzzle_height", 7.0)
    me["aim"] = [math.atan2(c[1] - me["pos"][1], c[0] - me["pos"][0]),
                 math.atan2(c[2] - mz, math.hypot(c[0] - me["pos"][0], c[1] - me["pos"][1]))]


def crate_scene(hp):
    """A crate 18-30 m away that v19 actually shoots (searched around us so LOS holds)."""
    x, y = me_xy(BASE)
    for r in (18, 24, 30):
        for k in range(12):
            a = k * math.tau / 12
            q = (x + r * math.cos(a), y + r * math.sin(a))
            if not W.walkable(*q):
                continue
            o = base(hp)
            gz = W.ground_at(*q)
            o["crates"] = [{"id": 1001, "pos": [q[0], q[1], gz], "hp": 300}]
            aim_at(o, (q[0], q[1], gz + 1.2))
            if any(run(OLD, o)["fire"]):
                return o
    raise SystemExit("no crate spot that v19 fires at")


fails = []
rows = []


def check(name, cond, new, old):
    rows.append((name, "PASS" if cond else "FAIL", new["mode"], old["mode"], new["fire"], old["fire"],
                 [round(v, 2) for v in new["move"]], [round(v, 2) for v in old["move"]], new.get("take"), old.get("take")))
    if not cond:
        fails.append(name)


SAME = ("move", "aim", "fire", "boost", "jump", "take", "drop", "reload")


def same(a, b):
    return all(a.get(k) == b.get(k) for k in SAME)


# (i) hurt, no target, crate in view -> no fire, heal; v19 shoots it
o = crate_scene(hp=800)
n, v = run(NEW, o), run(OLD, o)
check("i   hurt+crate: no fire, heal", not any(n["fire"]) and n["mode"] == "heal" and any(v["fire"]), n, v)
# (i-b) same, plus a mech seen 3 s ago 60 m away -> cover against it
x, y = me_xy(o)
seen = {12: (BASE["t"] - 3.0, [x + 60, y, BASE["self"]["pos"][2]], [0, 0, 0], 1400, ["gun"])}
n, v = run(NEW, o, seen), run(OLD, o, seen)
check("i-b hurt+crate+recent mech: cover", not any(n["fire"]) and n["mode"] in ("heal-cover", "heal-to-cover"), n, v)

# (ii) hurt, no target, empty slot, laser pickup ~50 m away -> both go loot it
o = base(hp=800)
x, y = me_xy(o)
spot = next(q for q in ((x + 50 * math.cos(k * math.tau / 16), y + 50 * math.sin(k * math.tau / 16)) for k in range(16)) if W.walkable(*q))
o["pickups"] = [{"id": 8001, "kind": "laser", "pos": [spot[0], spot[1], W.ground_at(*spot)]}]
n, v = run(NEW, o), run(OLD, o)
check("ii  hurt+empty slot+laser 50m: fetch", n["mode"] == "loot" and v["mode"] == "loot" and n["move"] == v["move"], n, v)

# (iii) healthy, gun+laser, lightning in reach -> v19 drops the gun, v24 keeps it
o = base(weapons=("gun", "laser"))
o["pickups"] = [{"id": 8002, "kind": "lightning", "pos": list(o["self"]["pos"])}]
n, v = run(NEW, o), run(OLD, o)
check("iii gun+laser, lightning in reach: keep gun", n.get("take") is None and v.get("take") == 8002 and v.get("drop") == 0, n, v)

# (iv) hurt + visible hostile mech aiming at us, no bullets -> identical action
o = base(hp=800)
x, y = me_xy(o)
for k in range(16):
    a = k * math.tau / 16
    q = (x + 70 * math.cos(a), y + 70 * math.sin(a))
    gz = W.ground_at(*q)
    if W.walkable(*q) and W.los((x, y, o["self"]["pos"][2] + 7), (q[0], q[1], gz + 4.5)):
        break
o["mechs"] = [{"id": 12, "kind": "mech", "pos": [q[0], q[1], gz], "vel": [0, 0, 0], "aim": [math.atan2(y - q[1], x - q[0]), 0],
               "hp": 1400, "max_hp": 1400, "cubes": 0, "weapons": ["gun"], "charging": False}]
n, v = run(NEW, o), run(OLD, o)
check("iv  hurt+hostile mech: same as v19", same(n, v) and n["mode"] == v["mode"] and v["mode"] not in ("idle", ""), n, v)

# (v) zone danger (hurt, outside next circle) -> identical action
o = base(hp=800)
x, y = me_xy(o)
o["self"]["in_zone"] = False
o["zone"].update(center=[x - 400, y], radius=300, next_center=[x - 400, y], next_radius=200, shrink_start=0, shrink_end=1)
n, v = run(NEW, o), run(OLD, o)
check("v   zone danger: same as v19", same(n, v) and n["mode"] == v["mode"] == "zone", n, v)

# (vi) healthy, no target (recorded crates left in) -> identical action
o = copy.deepcopy(BASE)
o["mechs"] = []
n, v = run(NEW, o), run(OLD, o)
check("vi  healthy, no target: same as v19", same(n, v) and n["mode"] == v["mode"], n, v)

# (vii) bullet 60 m out on a collision course -> v24 sidesteps, v19 doesn't
o = base()
x, y = me_xy(o)
cz = o["self"]["pos"][2] + 4.5
for k in range(16):
    a = k * math.tau / 16
    side = (-math.sin(a), math.cos(a))  # sidestep direction for a bullet coming from angle a
    if W.walkable(x + side[0] * 4, y + side[1] * 4) and W.walkable(x - side[0] * 4, y - side[1] * 4):
        break
o["projectiles"] = [{"id": 90, "kind": "gun", "pos": [x + 60 * math.cos(a), y + 60 * math.sin(a), cz],
                     "vel": [-252 * math.cos(a), -252 * math.sin(a), 0]}]
n, v = run(NEW, o), run(OLD, o)
check("vii bullet incoming: sidestep", n["mode"].endswith("+bdodge") and n["move"] != v["move"] and "bdodge" not in v["mode"], n, v)

print(f"{'scenario':40s} {'res':4s} {'v24 mode':16s} {'v19 mode':12s} {'v24 fire':14s} {'v19 fire':14s} {'v24 move':16s} {'v19 move':16s} take(v24/v19)",
      file=sys.stderr)
for r in rows:
    print(f"{r[0]:40s} {r[1]:4s} {r[2]:16s} {r[3]:12s} {str(r[4]):14s} {str(r[5]):14s} {str(r[6]):16s} {str(r[7]):16s} {r[8]}/{r[9]}", file=sys.stderr)
print(f"{len(rows) - len(fails)}/{len(rows)} passed" + (f"; FAILED: {fails}" if fails else ""), file=sys.stderr)
sys.exit(1 if fails else 0)
