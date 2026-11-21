"""v26 scenario checks: bot.py (one v26 variant) vs tools/bots/v24b.py on hand-built observations (decisions only).
The active variant is read from bot.py's V26_* flag. Usage (repo root): python3 tools/scen_v26.py   (non-zero exit on failure)"""
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
G = NEW.__init__.__globals__
VAR = [k for k in ("V26_DODGEHOLD", "V26_DODGENOBOOST", "V26_DODGEREACH", "V26_DROPS") if G.get(k)]
assert len(VAR) == 1, f"expected exactly one active V26 flag, got {VAR}"
VAR = {"V26_DODGEHOLD": "a", "V26_DODGENOBOOST": "b", "V26_DODGEREACH": "c", "V26_DROPS": "d"}[VAR[0]]
W = S.shared_world()[0]
X, Y, Z = BASE["self"]["pos"]
SAME = ("move", "aim", "fire", "boost", "jump", "take", "drop", "reload")
LOGS = []
mf.log = lambda *a: LOGS.append(" ".join(map(str, a)))


def wpn(kind):
    w = {"kind": kind, "cooldown": 0, "stats": copy.deepcopy(CFG["weapons"][kind])}
    w.update({"ammo": 12, "reload": 0} if kind == "gun" else {"charge": 0} if kind == "laser" else {})
    return w


def base(hp=1400):
    o = copy.deepcopy(BASE)
    for k in ("mechs", "crates", "pickups", "projectiles", "cubes", "events", "sounds", "beams", "drops"):
        o[k] = []
    o["self"]["hp"] = hp
    o["self"]["weapons"] = [wpn("gun"), None]
    return o


def label():
    lab = (mf.draw.take() or {}).get("label", "")
    return lab.split()[0] if lab else ""


def step(b, o):
    a = b.act(copy.deepcopy(o))
    a["mode"] = label()
    return a


def seq(cls, obs_list, prep=None):
    b = cls(HELLO)
    if prep:
        prep(b)
    return [step(b, o) for o in obs_list]


def later(o, k):
    o = copy.deepcopy(o)
    o["t"] = round(o["t"] + 0.1 * k, 3)
    o["tick"] += 2 * k
    return o


def same(a, b, skip=()):
    return all(a.get(k) == b.get(k) for k in SAME if k not in skip) and a["mode"] == b["mode"]


def dot(u, v):
    return u[0] * v[0] + u[1] * v[1]


def mech(mid, q, charging=False):
    return {"id": mid, "kind": "mech", "pos": [q[0], q[1], W.ground_at(*q)], "vel": [0, 0, 0],
            "aim": [math.atan2(Y - q[1], X - q[0]), 0], "hp": 1400, "max_hp": 1400, "cubes": 0, "weapons": ["gun"], "charging": charging}


def spot(r, toward=None, los=False):
    angs = [k * math.tau / 32 for k in range(32)]
    if toward is not None:
        angs.sort(key=lambda a: abs(math.remainder(a - toward, math.tau)))
    for a in angs:
        q = (X + r * math.cos(a), Y + r * math.sin(a))
        if W.walkable(*q) and (not los or W.los((X, Y, Z + 8), (q[0], q[1], W.ground_at(*q) + 4.5))):
            return q, a
    raise SystemExit(f"no spot at {r} m")


rows, fails = [], []


def check(name, cond, detail=""):
    rows.append((name, "PASS" if cond else "FAIL", detail))
    if not cond:
        fails.append(name)


def mv(a):
    return [round(x, 2) for x in a["move"]]


# ---- bullets: direction a with both sidestep sides walkable
cz = Z + 4.5
for k in range(16):
    ang = k * math.tau / 16
    if W.walkable(X - math.sin(ang) * 4, Y + math.cos(ang) * 4) and W.walkable(X + math.sin(ang) * 4, Y - math.cos(ang) * 4):
        break


def bullet(o, a, off=0.0):
    """Gun bullet 60 m out, flying at us from bearing a, passing `off` m to the side of our centre."""
    sx, sy = -math.sin(a) * off, math.cos(a) * off
    o["projectiles"] = [{"id": 90, "kind": "gun", "pos": [X + 60 * math.cos(a) + sx, Y + 60 * math.sin(a) + sy, cz],
                         "vel": [-252 * math.cos(a), -252 * math.sin(a), 0]}]
    return o


b1 = bullet(base(), ang)
# B1 direct bullet, one tick
n, v = seq(NEW, [b1])[0], seq(OLD, [b1])[0]
if VAR == "b":
    check("B1 direct bullet: dodge, no boost", n["mode"].endswith("+bdodge") and same(n, v, skip=("boost",)) and v["boost"] and not n["boost"],
          f"move {mv(n)} vs {mv(v)}  boost {n['boost']}/{v['boost']}")
else:
    check("B1 direct bullet: same as v24b", same(n, v) and n["mode"].endswith("+bdodge"), f"move {mv(n)} vs {mv(v)}")

# B2 direct bullet, then 2 ticks with a bullet from the opposite side (would flip the sidestep)
opp = [b1, bullet(later(base(), 1), ang + math.pi), bullet(later(base(), 2), ang + math.pi)]
ns, vs = seq(NEW, opp), seq(OLD, opp)
if VAR == "a":
    check("B2 opposite bullet ticks 2-3: hold direction",
          all(x["mode"].endswith("+bdodge") and x["move"] == ns[0]["move"] for x in ns[1:]) and all(dot(x["move"], vs[0]["move"]) < 0 for x in vs[1:]),
          f"v26a {[mv(x) for x in ns]} | v24b {[mv(x) for x in vs]}")
else:
    check("B2 opposite bullet: same as v24b", all(same(x, y, skip=("boost",) if VAR == "b" else ()) for x, y in zip(ns, vs)),
          f"{[mv(x) for x in ns]} vs {[mv(x) for x in vs]}")

# B3 direct bullet, then 2 ticks with no bullet
gone = [b1, later(base(), 1), later(base(), 2)]
ns, vs = seq(NEW, gone), seq(OLD, gone)
if VAR == "a":
    check("B3 bullet gone ticks 2-3: keep sidestepping",
          all(x["mode"].endswith("+bdodge") and x["move"] == ns[0]["move"] for x in ns[1:]) and all(x["move"] == [0.0, 0.0] for x in vs[1:]),
          f"v26a {[mv(x) for x in ns]} | v24b {[mv(x) for x in vs]}")
else:
    check("B3 bullet gone: same as v24b", all(same(x, y, skip=("boost",) if VAR == "b" else ()) for x, y in zip(ns, vs)),
          f"{[mv(x) for x in ns]} vs {[mv(x) for x in vs]}")

# B4 bullet that would pass 4.3 m from our centre (graze; v24b reach 3.6 m, v26c 5.0 m)
g = bullet(base(), ang, off=4.3)
n, v = seq(NEW, [g])[0], seq(OLD, [g])[0]
if VAR == "c":
    check("B4 graze bullet 4.3 m: dodge", n["mode"].endswith("+bdodge") and "bdodge" not in v["mode"], f"{n['mode']} vs {v['mode']}")
else:
    check("B4 graze bullet 4.3 m: same as v24b", same(n, v) and "bdodge" not in n["mode"], f"{n['mode']} vs {v['mode']}")

# ---- D1 drop landing in 20 s, 250 m away (inside the next circle), hurt
o = base(hp=800)
zn = o["zone"]["next_center"]
q250, _ = spot(250, toward=math.atan2(zn[1] - Y, zn[0] - X))
o["drops"] = [{"id": 20000, "pos": [q250[0], q250[1], W.ground_at(*q250)], "radius": 8, "lands_in": 20.0, "capture_s": 4, "progress": 0, "holder": None}]
n, v = seq(NEW, [o])[0], seq(OLD, [o])[0]
if VAR == "d":
    check("D1 drop 250 m / 20 s, hurt: go", n["mode"] == "drop" and v["mode"] != "drop", f"{n['mode']} vs {v['mode']}")
else:
    check("D1 drop 250 m / 20 s, hurt: same as v24b", same(n, v), f"{n['mode']} vs {v['mode']}")

# ---- invariants: identical to v24b
q80, _ = spot(80, los=True)
o = base(hp=800)
o["self"]["in_zone"] = False
o["zone"].update(center=[X - 400, Y], radius=300, next_center=[X - 400, Y], next_radius=200, shrink_start=0, shrink_end=1)
n, v = seq(NEW, [o])[0], seq(OLD, [o])[0]
check("I1 zone danger: same as v24b", same(n, v) and n["mode"] == "zone", n["mode"])


def stuck(b):
    b.unstick_until, b.unstick_dir = BASE["t"] + 1.0, (0.0, 1.0)


o = base()
n, v = seq(NEW, [o], stuck)[0], seq(OLD, [o], stuck)[0]
check("I2 unstick: same as v24b", same(n, v) and n["mode"] == "unstick", n["mode"])
o = base(hp=800)
o["mechs"] = [mech(12, q80)]
n, v = seq(NEW, [o])[0], seq(OLD, [o])[0]
check("I3 visible hostile mech: same as v24b", same(n, v) and n["mode"] not in ("idle", ""), n["mode"])

# ---- D2 full drive: a drop is called, falls, lands, we walk in, capture, then a mech shows up
COMBAT = ("close", "space", "strafe", "hunt", "lurk", "cover", "to-cover", "retreat")
qd, _ = spot(18)
o = base(hp=800)
o["zone"].update(next_center=[X, Y], next_radius=200)  # we and the drop are inside the next circle
b = NEW(HELLO)
nav = b.nav
steer0 = nav.steer
bad2d = []


def steer(p, g, *a, **k):
    if len(p) != 2 or len(g) != 2:
        bad2d.append((p, g))
    return steer0(p, g, *a, **k)


nav.steer = steer
LOGS.clear()
pos = [X, Y, Z]
drop = {"id": 20001, "pos": [qd[0], qd[1], W.ground_at(*qd)], "radius": 8, "lands_in": 2.0, "capture_s": 4, "progress": 0.0, "holder": None}
modes, outside, captured_at, mech_at = [], 0, None, None
try:
    for k in range(80):
        ok = later(o, k)
        ok["self"]["pos"] = list(pos)
        ok["drops"] = [dict(drop)] if captured_at is None else []
        if mech_at is not None:
            ok["mechs"] = [mech(12, q80)]
        a = step(b, ok)
        modes.append(a["mode"])
        c_now, r_now = b.zone_at(ok["zone"], ok["t"])
        if a["mode"] in ("drop", "capture") and math.hypot(pos[0] - c_now[0], pos[1] - c_now[1]) > r_now:
            outside += 1
        sp = CFG["mech"]["boost_speed"] if a["boost"] else CFG["mech"]["walk_speed"]
        nx, ny = pos[0] + a["move"][0] * sp * 0.1, pos[1] + a["move"][1] * sp * 0.1
        if W.walkable(nx, ny):
            pos = [nx, ny, W.ground_at(nx, ny)]
        ok["self"]["vel"] = [a["move"][0] * sp, a["move"][1] * sp, 0]
        drop["lands_in"] = max(0.0, round(drop["lands_in"] - 0.1, 3))
        if captured_at is None and drop["lands_in"] == 0 and math.hypot(pos[0] - qd[0], pos[1] - qd[1]) < drop["radius"]:
            drop["holder"] = BASE["self"]["id"]
            drop["progress"] = round(drop["progress"] + 0.1, 3)
            if drop["progress"] >= drop["capture_s"]:
                captured_at = k
                o["self"].update(hp=o["self"]["max_hp"], energy=100, cubes=o["self"]["cubes"] + 3)
        if captured_at is not None and mech_at is None and k >= captured_at + 3:
            mech_at = k + 1
        if mech_at is not None and k >= mech_at + 4:
            break
finally:
    del nav.steer
first = lambda m: next((i for i, x in enumerate(modes) if x.split("+")[0] == m), None)  # noqa: E731
i_drop, i_cap = first("drop"), first("capture")
after = [m.split("+")[0] for m in modes[mech_at:]] if mech_at is not None else []
tb = sum("Traceback" in x for x in LOGS)
check("D2 drive: drop -> capture -> fight", i_drop is not None and i_cap is not None and i_drop < i_cap and captured_at is not None
      and after and all(m in COMBAT for m in after), f"ticks {len(modes)}, drop@{i_drop} capture@{i_cap} captured@{captured_at} mech@{mech_at} after={after}")
check("D2 drive: no exceptions", getattr(b, "errors", 0) == 0 and tb == 0, f"errors={getattr(b, 'errors', 0)} tracebacks={tb}")
check("D2 drive: nav goals 2D", not bad2d, f"bad={bad2d[:2]}")
check("D2 drive: never outside zone in drop mode", outside == 0, f"outside={outside}")

# D3 a drop outside the next circle is never chased (v26d)
o = base(hp=800)
o["zone"].update(next_center=[X + 300, Y], next_radius=150)
o["drops"] = [dict(drop, id=20002, lands_in=5.0, progress=0.0, holder=None, pos=[qd[0], qd[1], W.ground_at(*qd)])]
ms = [x["mode"] for x in seq(NEW, [later(o, k) for k in range(10)])]
if VAR == "d":
    check("D3 drop outside next circle: never chased", not any(m.startswith(("drop", "capture")) for m in ms), str(sorted(set(ms))))

print(f"variant v26{VAR}", file=sys.stderr)
for r in rows:
    print(f"{r[0]:48s} {r[1]:4s} {r[2]}", file=sys.stderr)
print(f"{len(rows) - len(fails)}/{len(rows)} passed" + (f"; FAILED: {fails}" if fails else ""), file=sys.stderr)
sys.exit(1 if fails else 0)
