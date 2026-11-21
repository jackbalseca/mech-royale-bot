"""Run sim matches and report any exceptions raised inside bot act()/choose_move."""
import sys, traceback, collections
sys.path.insert(0, 'tools')
import sim as S, mechfight as mf
seeds = [int(s) for s in sys.argv[1:]] or [1]
hello = S.load_hello(); pc = S.load_bot_class('bot.py', 0)
errs = collections.Counter(); first = {}
_log = mf.log
def log(*a):
    msg = ' '.join(map(str, a))
    if 'Traceback' in msg:
        key = msg.strip().splitlines()[-1]
        errs[key] += 1; first.setdefault(key, msg)
mf.log = log
import builtins
for seed in seeds:
    tiers = ["easy"]*4+["medium"]*4+["hard"]*4+["expert"]*3
    specs = [{"cls": pc, "label": "me"}]+[{"cls": pc, "label": "h", "house": True, "tier": t} for t in tiers]
    sim = S.Sim(hello, specs, seed, "ffa")
    for m in sim.mechs:
        oa = m.ctrl.act
        def w(o, oa=oa):
            try: return oa(o)
            except Exception:
                tb = traceback.format_exc(); key = tb.strip().splitlines()[-1]
                errs[key] += 1; first.setdefault(key, tb); raise
        m.ctrl.act = w
    res, t = sim.run()
    print('seed', seed, 'ended', round(t), 'places', sorted((r['place'], r['kills']) for r in res)[:4])
for k, v in errs.most_common(8):
    print(v, k); print(first[k][-900:])
print('errors total', sum(errs.values()))
