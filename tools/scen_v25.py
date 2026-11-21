"""v25 scenario checks: bot.py vs tools/bots/v24b.py (baseline) on hand-built observations (decisions only).
Usage (repo root): python3 tools/scen_v25.py      exits non-zero if any assertion fails."""
import copy, gzip, json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim as S, mechfight as mf  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
L = [json.loads(l) for l in gzip.open(os.path.join(ROOT, "check", "stream.jsonl.gz"))]
HELLO = L[0]
BASE = [o for o in L if o.get("type") == "obs"][50]  # t=5, one gun, in zone
CFG = HELLO["config"]
NEW = S.load_bot_class(os.path.join(ROOT, "bot.py"), "scen_new")
OLD = S.load_bot_class(os.path.join(ROOT, "tools", "bots", "v24b.py"), "scen_v24b")
W = S.shared_world()[0]
X, Y, Z = BASE["self"]["pos"]
SAME = ("move", "aim", "fire", "boost", "jump", "take", "drop", "reload")


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


def spot(r, toward=None, los=False, skip=()):
    """Walkable point r m from us (in LOS if asked); bearings ordered by closeness to `toward`."""
    angs = [k * math.tau / 32 for k in range(32)]
    if toward is not None:
        angs.sort(key=lambda a: abs(math.remainder(a - toward, math.tau)))
    for a in angs:
        if any(abs(math.remainder(a - s, math.tau)) < 0.6 for s in skip):
            continue
        q = (X + r * math.cos(a), Y + r * math.sin(a))
        if W.walkable(*q) and (not los or W.los((X, Y, Z + 8), (q[0], q[1], W.ground_at(*q) + 4.5))):
            return q, a
    raise SystemExit(f"no spot at {r} m")


def mech(mid, q, at_us=True, charging=True, off=1.2):
    yaw = math.atan2(Y - q[1], X - q[0]) + (0 if at_us else off)
    return {"id": mid, "kind": "mech", "pos": [q[0], q[1], W.ground_at(*q)], "vel": [0, 0, 0], "aim": [yaw, 0],
            "hp": 1400, "max_hp": 1400, "cubes": 0, "weapons": ["gun", "laser"], "charging": charging}


def run(cls, o, prep=None):
    b = cls(HELLO)
    if prep:
        prep(b)
    a = b.act(copy.deepcopy(o))
    lab = (mf.draw.take() or {}).get("label", "")
    a["mode"] = lab.split()[0] if lab else ""
    return a


rows, fails = [], []


def check(name, cond, n, v):
    rows.append((name, "PASS" if cond else "FAIL", n["mode"], v["mode"], [round(x, 2) for x in n["move"]],
                 [round(x, 2) for x in v["move"]], n["boost"], v["boost"], n.get("take"), v.get("take")))
    if not cond:
        fails.append(name)


def same(a, b):
    return all(a.get(k) == b.get(k) for k in SAME) and a["mode"] == b["mode"]


q80, a80 = spot(80, los=True)

# (1) a mech 80 m away charges a laser at us -> v25 hard sidestep (it is also our target)
o = base()
o["mechs"] = [mech(12, q80)]
n, v = run(NEW, o), run(OLD, o)
check("1 laser charging at us: sidestep", n["mode"].endswith("+ldodge") and n["move"] != v["move"] and "ldodge" not in v["mode"], n, v)

# (2) our target is a different (closer, hostile, not charging) mech; a second mech charges at us -> sidestep
o = base()
q40, _ = spot(40, los=True, skip=(a80,))
tgt = mech(13, q40, charging=False)
o["mechs"] = [tgt, mech(12, q80)]
o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": math.atan2(q40[1] - Y, q40[0] - X), "by": 13}]
n, v = run(NEW, o), run(OLD, o)
check("2 non-target charging at us: sidestep", n["mode"].endswith("+ldodge") and n["move"] != v["move"], n, v)

# (3) a mech charges at someone else (aim 1.2 rad off us) -> same as v24b
o = base()
o["mechs"] = [mech(12, q80, at_us=False)]
n, v = run(NEW, o), run(OLD, o)
check("3 charging at someone else: same", same(n, v), n, v)

# (4) first laser 200 m away (inside the zone), gun + empty slot -> v25 goes, v24b (160 m cap) doesn't
o = base()
zc = o["zone"]["center"]
q200, _ = spot(200, toward=math.atan2(zc[1] - Y, zc[0] - X))
o["pickups"] = [{"id": 8001, "kind": "laser", "pos": [q200[0], q200[1], W.ground_at(*q200)]}]
n, v = run(NEW, o), run(OLD, o)
check("4 first laser 200 m: go", n["mode"] == "loot" and v["mode"] != "loot", n, v)

# (5) mortar pickup at our feet, empty slot -> v24b takes it, v25 skips
o = base()
o["pickups"] = [{"id": 8002, "kind": "mortar", "pos": [X, Y, Z]}]
n, v = run(NEW, o), run(OLD, o)
check("5 mortar in reach: skip", n.get("take") is None and v.get("take") == 8002, n, v)

# (6) zone danger while a mech charges at us -> same as v24b (no laser dodge over zone)
o = base()
o["mechs"] = [mech(12, q80)]
o["self"]["in_zone"] = False
o["zone"].update(center=[X - 400, Y], radius=300, next_center=[X - 400, Y], next_radius=200, shrink_start=0, shrink_end=1)
n, v = run(NEW, o), run(OLD, o)
check("6 zone danger + charger: same", same(n, v) and n["mode"].startswith("zone"), n, v)


def stuck(b):
    b.unstick_until, b.unstick_dir = BASE["t"] + 1.0, (0.0, 1.0)


# (7) unsticking while a mech charges at us -> same as v24b
o = base()
o["mechs"] = [mech(12, q80)]
n, v = run(NEW, o, stuck), run(OLD, o, stuck)
check("7 unstick + charger: same", same(n, v) and n["mode"].startswith("unstick"), n, v)

# (8) bullet on a collision course while a mech charges at us -> bullet dodge as in v24b
o = base()
o["mechs"] = [mech(12, q80)]
cz = Z + 4.5
for k in range(16):
    a = k * math.tau / 16
    if W.walkable(X - math.sin(a) * 4, Y + math.cos(a) * 4) and W.walkable(X + math.sin(a) * 4, Y - math.cos(a) * 4):
        break
o["projectiles"] = [{"id": 90, "kind": "gun", "pos": [X + 60 * math.cos(a), Y + 60 * math.sin(a), cz], "vel": [-252 * math.cos(a), -252 * math.sin(a), 0]}]
n, v = run(NEW, o), run(OLD, o)
check("8 bullet + charger: bullet dodge, same", same(n, v) and n["mode"].endswith("+bdodge"), n, v)

print(f"{'scenario':38s} {'res':4s} {'v25 mode':18s} {'v24b mode':14s} {'v25 move':16s} {'v24b move':16s} boost(v25/v24b) take(v25/v24b)", file=sys.stderr)
for r in rows:
    print(f"{r[0]:38s} {r[1]:4s} {r[2]:18s} {r[3]:14s} {str(r[4]):16s} {str(r[5]):16s} {r[6]}/{r[7]}  {r[8]}/{r[9]}", file=sys.stderr)
print(f"{len(rows) - len(fails)}/{len(rows)} passed" + (f"; FAILED: {fails}" if fails else ""), file=sys.stderr)
sys.exit(1 if fails else 0)
