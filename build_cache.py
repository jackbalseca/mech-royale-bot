"""Precompute world grids and the nav graph. Run at image build time: python3 build_cache.py [map_dir]"""
import os
import sys
import time
import numpy as np
import world as W
import nav as N

t0 = time.time()
map_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(W.HERE, "arena")
arr = W.build_arrays(map_dir)
os.makedirs(os.path.dirname(W.CACHE), exist_ok=True)
np.savez(W.CACHE, **arr)
print(f"world grids: {time.time() - t0:.1f}s, walkable {arr['walk'].mean():.1%}", file=sys.stderr)
w = W.World()
g = N.build_graph(w)
np.savez(os.path.join(W.HERE, "cache", "nav.npz"), **g)
print(f"nav graph: {len(g['nodes'])} nodes, {g['edges'].shape[1]} edges, total {time.time() - t0:.1f}s", file=sys.stderr)

# v46: exposure map. For each walkable spot on a 6 m lattice, the fraction of 48 viewpoints (16 directions x 40/80/130 m,
# eye 8 m above ground) that can see a mech's body (5.4 m) there. Used late in practice matches to hold low-exposure spots.
import math
S = 6.0
xs = np.arange(w.minx + 3, w.minx + w.nx * w.step - 3, S)
ys = np.arange(w.miny + 3, w.miny + w.ny * w.step - 3, S)
expo = np.full((len(ys), len(xs)), np.nan, dtype=np.float32)
dirs = [(math.cos(k * math.pi / 8), math.sin(k * math.pi / 8)) for k in range(16)]
for j, y in enumerate(ys):
    for i, x in enumerate(xs):
        if not w.walkable(x, y):
            continue
        gz = w.ground_at(x, y)
        body = (x, y, gz + 5.4)
        vis = tot = 0
        for r in (40.0, 80.0, 130.0):
            for dx, dy in dirs:
                ex, ey = x + dx * r, y + dy * r
                if not w.in_bounds(ex, ey):
                    continue
                tot += 1
                if w.los((ex, ey, w.ground_at(ex, ey) + 8.0), body):
                    vis += 1
        expo[j, i] = vis / max(tot, 1)
np.savez(os.path.join(W.HERE, "cache", "expo.npz"), xs=xs, ys=ys, expo=expo)
print(f"exposure map: {np.isfinite(expo).sum()} spots, total {time.time() - t0:.1f}s", file=sys.stderr)
