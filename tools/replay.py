"""Feed the recorded stream to the bot in-process and print decisions + timing."""
import sys, json, gzip, time, collections
sys.path.insert(0, sys.argv[1])
import mechfight as mf
import bot as B
L = [json.loads(l) for l in gzip.open(sys.argv[2])]
b = B.Bot(L[0])
modes = collections.Counter(); times = []
for o in L[1:]:
    if o.get('type') != 'obs': continue
    t0 = time.perf_counter(); a = b.act(o); times.append((time.perf_counter()-t0)*1000)
    d = mf.draw.take() or {}
    modes[d.get('label','').split()[0]] += 1
    if o['tick'] % 40 == 0 or any(a['fire']):
        me=o['self']
        print(o['t'], d.get('label'), 'pos', [round(v) for v in me['pos']], 'aim', [round(v,2) for v in me['aim']], 'cmd', [round(v,2) for v in a['aim']], 'mv', [round(v,2) for v in a['move']], 'fire', a['fire'], 'take', a.get('take'), 'nm', len([m for m in o['mechs'] if m['kind']=='mech']))
import statistics
print(modes); print('ms p50 %.2f p99 %.2f max %.2f' % (statistics.median(times), sorted(times)[int(len(times)*.99)], max(times)))
