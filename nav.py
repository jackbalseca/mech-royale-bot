"""Waypoint graph over the walk grid + per-goal Dijkstra (cached).

Nodes sit on an 8 m lattice (snapped to the nearest walkable cell), linked to lattice neighbours
when a mech can walk the straight line between them. Built once at image build time.
"""
import math
import numpy as np

LATTICE = 8.0
NEIGH = [(dx, dy) for dx in range(-2, 3) for dy in range(-2, 3)
         if (dx, dy) != (0, 0) and math.gcd(abs(dx), abs(dy)) == 1]


def build_graph(world):
    minx, miny = world.minx, world.miny
    maxx = minx + world.step * (world.nx - 1)
    maxy = miny + world.step * (world.ny - 1)
    gw = int((maxx - minx) // LATTICE) + 1
    gh = int((maxy - miny) // LATTICE) + 1
    cell = -np.ones((gh, gw), np.int32)
    nodes = []
    offs = [(0, 0)] + sorted(((dx, dy) for dx in range(-4, 5) for dy in range(-4, 5) if (dx, dy) != (0, 0)),
                             key=lambda o: o[0] * o[0] + o[1] * o[1])
    for gy in range(gh):
        for gx in range(gw):
            cx, cy = minx + gx * LATTICE, miny + gy * LATTICE
            for dx, dy in offs:
                x, y = cx + dx, cy + dy
                if world.walkable(x, y):
                    cell[gy, gx] = len(nodes)
                    nodes.append((x, y))
                    break
    nodes = np.asarray(nodes, np.float32)
    ei, ej, ew = [], [], []
    for gy in range(gh):
        for gx in range(gw):
            a = cell[gy, gx]
            if a < 0:
                continue
            for dx, dy in NEIGH:
                if dx < 0 or (dx == 0 and dy < 0):
                    continue  # each undirected pair once
                hx, hy = gx + dx, gy + dy
                if not (0 <= hx < gw and 0 <= hy < gh):
                    continue
                b = cell[hy, hx]
                if b < 0:
                    continue
                if world.walk_clear(nodes[a], nodes[b]):
                    ei.append(a)
                    ej.append(b)
                    ew.append(float(np.hypot(*(nodes[a] - nodes[b]))))
    return dict(nodes=nodes, cell=cell, edges=np.array([ei, ej], np.int32),
                weights=np.array(ew, np.float32), gmeta=np.array([minx, miny, LATTICE], np.float64))


class Nav:
    def __init__(self, world, g):
        from scipy.sparse import csr_matrix
        self.w = world
        self.nodes = g["nodes"].astype(np.float64)
        self.cell = g["cell"]
        self.gminx, self.gminy, self.lat = g["gmeta"]
        n = len(self.nodes)
        e = g["edges"]
        wts = g["weights"]
        self.mat = csr_matrix((np.concatenate([wts, wts]), (np.concatenate([e[0], e[1]]), np.concatenate([e[1], e[0]]))),
                              shape=(n, n))
        self._cache = {}

    def near_nodes(self, x, y, r=20.0):
        gx = int(round((x - self.gminx) / self.lat))
        gy = int(round((y - self.gminy) / self.lat))
        k = int(math.ceil(r / self.lat))
        gh, gw = self.cell.shape
        sl = self.cell[max(0, gy - k):min(gh, gy + k + 1), max(0, gx - k):min(gw, gx + k + 1)].ravel()
        sl = sl[sl >= 0]
        if sl.size == 0:
            return sl, np.zeros(0)
        d = np.hypot(self.nodes[sl, 0] - x, self.nodes[sl, 1] - y)
        o = np.argsort(d)
        return sl[o], d[o]

    def _field(self, goal_node):
        f = self._cache.get(goal_node)
        if f is None:
            from scipy.sparse.csgraph import dijkstra
            dist, pred = dijkstra(self.mat, directed=False, indices=goal_node, return_predecessors=True)
            f = (dist, pred)
            if len(self._cache) > 24:
                self._cache.clear()
            self._cache[goal_node] = f
        return f

    def goal_node(self, x, y):
        for r in (12.0, 24.0, 48.0):
            ids, d = self.near_nodes(x, y, r)
            for k in ids[:6]:
                if self.w.walk_clear((x, y), self.nodes[k]):
                    return int(k)
            if ids.size:
                return int(ids[0])
        return None

    def steer(self, me, goal):
        """Point to walk toward next on the way from `me` (x, y) to `goal` (x, y)."""
        me = (float(me[0]), float(me[1]))
        goal = (float(goal[0]), float(goal[1]))
        if math.dist(me, goal) < 80 and self.w.walk_clear(me, goal):
            return tuple(goal), math.dist(me, goal)
        gn = self.goal_node(goal[0], goal[1])
        if gn is None:
            return tuple(goal), math.dist(me, goal)
        dist, pred = self._field(gn)
        ids, d = self.near_nodes(me[0], me[1], 24.0)
        if ids.size == 0:
            return tuple(goal), math.dist(me, goal)
        cost = d + dist[ids]
        best = None
        for k in np.argsort(cost)[:8]:
            n = int(ids[k])
            if not np.isfinite(dist[n]):
                continue
            if self.w.walk_clear(me, self.nodes[n]):
                best = n
                break
        if best is None:  # nothing reachable in a straight line: head to the nearest node anyway
            best = int(ids[0])
            return tuple(self.nodes[best]), float(d[0]) + float(dist[best] if np.isfinite(dist[best]) else 1e4)
        total = float(math.dist(me, self.nodes[best]) + dist[best])
        # look ahead along the path for the furthest node still in a straight walkable line
        cur = best
        for _ in range(5):
            nxt = pred[cur]
            if nxt < 0:
                break
            if self.w.walk_clear(me, self.nodes[nxt]):
                cur = int(nxt)
            else:
                break
        if pred[cur] < 0 and self.w.walk_clear(me, goal):
            return tuple(goal), total
        return tuple(self.nodes[cur]), total

    def path_len(self, a, b):
        gn = self.goal_node(b[0], b[1])
        if gn is None:
            return math.dist(a, b)
        dist, _ = self._field(gn)
        ids, d = self.near_nodes(a[0], a[1], 24.0)
        if ids.size == 0:
            return math.dist(a, b) * 1.5
        c = d + dist[ids]
        return float(np.min(c)) if np.isfinite(np.min(c)) else math.dist(a, b) * 2
