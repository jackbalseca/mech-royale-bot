"""FFA sim: per-weapon shots and hits (all bots are the same file)."""
import sys, collections
sys.path.insert(0, 'tools')
import sim as S
bot = sys.argv[1] if len(sys.argv) > 1 else 'bot.py'
seeds = [int(s) for s in sys.argv[2:]] or [5]
hello = S.load_hello(); pc = S.load_bot_class(bot, 0)
shots = collections.Counter(); hits = collections.Counter(); dmg = collections.Counter(); dist_hist = []
for seed in seeds:
    sim = S.Sim(hello, [{"cls": pc, "label": "b"}] * 16, seed, "ffa")
    fg, fl, fm, fz = sim.fire_gun, sim.fire_laser, sim.fire_mortar, sim.fire_lightning
    def g(m, st, d): shots['gun'] += 1; fg(m, st, d)
    def l(m, st, d, f): shots['laser'] += 1; fl(m, st, d, f)
    def mo(m, st, d): shots['mortar'] += 1; fm(m, st, d)
    def z(m, st, d): shots['lightning'] += 1; fz(m, st, d)
    sim.fire_gun, sim.fire_laser, sim.fire_mortar, sim.fire_lightning = g, l, mo, z
    od = sim.damage
    def dm(v, a, w, src, att, effect=None):
        if att is not None: hits[w] += 1; dmg[w] += a
        od(v, a, w, src, att, effect)
    sim.damage = dm
    res, t = sim.run()
    print('seed', seed, 'end', round(t))
for w in shots:
    print(f"{w:10s} shots {shots[w]:6d}  mech-hits {hits[w]:6d}  rate {hits[w]/max(shots[w],1):.2f}  dmg {dmg[w]:.0f}")
