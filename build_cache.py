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
