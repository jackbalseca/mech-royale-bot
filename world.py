"""Static world model: terrain, buildings, bridges, line-of-sight and a walkability grid.

Everything is rasterized onto the terrain's 1 m vertex grid. Building the grids takes a few
seconds, so the Dockerfile runs `python3 build_cache.py` once at image build time and the bot
loads the result from cache/world.npz (falling back to building from /arena if it's missing).
"""
import json
import os
import math
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache", "world.npz")

MECH_H = 9.0
STEP_UP = 1.2
MAX_SLOPE_DEG = 50.0
CLEAR_R = 3.2  # mech radius 2.5 + margin, used to erode the walk grid


def _poly_mask(xs, ys, ring):
    """Even-odd point-in-polygon for grid points (xs: (W,), ys: (H,)) -> bool (H, W)."""
    pts = np.asarray(ring, dtype=np.float64).reshape(-1, 2)
    X = xs[None, :]
    Y = ys[:, None]
    inside = np.zeros((ys.size, xs.size), dtype=bool)
    n = len(pts)
    for k in range(n):
        x1, y1 = pts[k]
        x2, y2 = pts[(k + 1) % n]
        if y1 == y2:
            continue
        cond = (y1 > Y) != (y2 > Y)
        xint = x1 + (Y - y1) * (x2 - x1) / (y2 - y1)
        inside ^= cond & (X < xint)
    return inside


def build_arrays(map_dir):
    w = json.load(open(os.path.join(map_dir, "v2", "world.json")))
    t = w["terrain"]
    nx, ny, step = t["nx"], t["ny"], t["step"]
    minx, miny = t["minX"], t["minY"]
    ground = (np.fromfile(os.path.join(map_dir, "v2", t["file"]), dtype="<i2").reshape(ny, nx).astype(np.float32)
              * np.float32(t.get("scale", 0.01)))
    xs = minx + np.arange(nx) * step
    ys = miny + np.arange(ny) * step
    nan = np.float32(np.nan)
    bld_base = np.full((ny, nx), nan, np.float32)
    bld_top = np.full((ny, nx), nan, np.float32)
    brg_base = np.full((ny, nx), nan, np.float32)
    brg_top = np.full((ny, nx), nan, np.float32)
    move_block = np.zeros((ny, nx), bool)
    for p in w["prisms"]:
        ring = np.asarray(p["ring"]).reshape(-1, 2)
        x0, y0 = ring.min(0)
        x1, y1 = ring.max(0)
        i0 = max(0, int(math.floor((x0 - minx) / step)))
        i1 = min(nx, int(math.ceil((x1 - minx) / step)) + 1)
        j0 = max(0, int(math.floor((y0 - miny) / step)))
        j1 = min(ny, int(math.ceil((y1 - miny) / step)) + 1)
        if i1 <= i0 or j1 <= j0:
            continue
        sx, sy = xs[i0:i1], ys[j0:j1]
        m = _poly_mask(sx, sy, p["ring"])
        for h in p.get("holes") or []:
            m &= ~_poly_mask(sx, sy, h)
        if not m.any():
            continue
        base, top = np.float32(p["base"]), np.float32(p["top"])
        g = ground[j0:j1, i0:i1]
        if p["kind"] == "bridge":
            bb, bt = brg_base[j0:j1, i0:i1], brg_top[j0:j1, i0:i1]
            bb[m] = np.fmin(bb[m], base)
            bt[m] = np.fmax(bt[m], top)
        else:
            bb, bt = bld_base[j0:j1, i0:i1], bld_top[j0:j1, i0:i1]
            bb[m] = np.fmin(bb[m], base)
            bt[m] = np.fmax(bt[m], top)
        # blocks a mech walking on the ground: rises above a step and the mech can't pass under
        blk = m & (top - g > STEP_UP) & (base - g < MECH_H)
        move_block[j0:j1, i0:i1] |= blk
    # terrain too steep to walk
    gy, gx = np.gradient(ground.astype(np.float64), step)
    steep = np.hypot(gx, gy) > math.tan(math.radians(MAX_SLOPE_DEG))
    blocked = move_block | steep
    # map edge margin
    blocked[:3, :] = blocked[-3:, :] = True
    blocked[:, :3] = blocked[:, -3:] = True
    walk = ~_dilate(blocked, CLEAR_R / step)
    return dict(ground=ground, bld_base=bld_base, bld_top=bld_top, brg_base=brg_base, brg_top=brg_top,
                walk=walk, blocked=blocked,
                meta=np.array([minx, miny, step, nx, ny], np.float64))


def _dilate(mask, r):
    try:
        from scipy import ndimage
        R = int(math.ceil(r))
        yy, xx = np.mgrid[-R:R + 1, -R:R + 1]
        return ndimage.binary_dilation(mask, structure=(xx * xx + yy * yy) <= r * r)
    except Exception:
        out = mask.copy()
        R = int(math.ceil(r))
        for dy in range(-R, R + 1):
            for dx in range(-R, R + 1):
                if dx * dx + dy * dy <= r * r:
                    out |= np.roll(np.roll(mask, dy, 0), dx, 1)
        return out


class World:
    def __init__(self, map_dir=None):
        arr = None
        if os.path.exists(CACHE):
            try:
                arr = dict(np.load(CACHE))
            except Exception:
                arr = None
        if arr is None:
            arr = build_arrays(map_dir or "/arena")
        self.__dict__.update(arr)
        self.minx, self.miny, self.step, nx, ny = arr["meta"]
        self.nx, self.ny = int(nx), int(ny)
        # NaN-free versions for fast vector tests
        self._bb = np.where(np.isnan(self.bld_base), np.float32(1e9), self.bld_base)
        self._bt = np.where(np.isnan(self.bld_top), np.float32(-1e9), self.bld_top)
        self._rb = np.where(np.isnan(self.brg_base), np.float32(1e9), self.brg_base)
        self._rt = np.where(np.isnan(self.brg_top), np.float32(-1e9), self.brg_top)

    # ---- indexing -------------------------------------------------------
    def ij(self, x, y):
        i = np.clip(np.rint((np.asarray(x) - self.minx) / self.step).astype(np.int64), 0, self.nx - 1)
        j = np.clip(np.rint((np.asarray(y) - self.miny) / self.step).astype(np.int64), 0, self.ny - 1)
        return i, j

    def ground_at(self, x, y):
        fx = (x - self.minx) / self.step
        fy = (y - self.miny) / self.step
        i = int(min(max(math.floor(fx), 0), self.nx - 2))
        j = int(min(max(math.floor(fy), 0), self.ny - 2))
        tx, ty = min(max(fx - i, 0.0), 1.0), min(max(fy - j, 0.0), 1.0)
        g = self.ground
        return float((g[j, i] * (1 - tx) + g[j, i + 1] * tx) * (1 - ty) + (g[j + 1, i] * (1 - tx) + g[j + 1, i + 1] * tx) * ty)

    def walkable(self, x, y):
        i, j = self.ij(x, y)
        return bool(self.walk[j, i])

    def in_bounds(self, x, y):
        return self.minx + 5 < x < self.minx + self.step * (self.nx - 5) and self.miny + 5 < y < self.miny + self.step * (self.ny - 5)

    # ---- queries --------------------------------------------------------
    def los(self, a, b, spacing=1.0):
        """True if the straight segment a->b (3D points) misses terrain, buildings and bridges.
        Trees are ignored (they don't stop shots)."""
        a = np.asarray(a, np.float64)
        b = np.asarray(b, np.float64)
        d = b - a
        L = math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
        n = max(2, int(L / spacing))
        t = np.linspace(0.0, 1.0, n)[1:-1]
        if t.size == 0:
            return True
        p = a[None, :] + t[:, None] * d[None, :]
        i, j = self.ij(p[:, 0], p[:, 1])
        z = p[:, 2]
        if np.any(z < self.ground[j, i] - 0.3):
            return False
        if np.any((z >= self._bb[j, i]) & (z <= self._bt[j, i])):
            return False
        if np.any((z >= self._rb[j, i]) & (z <= self._rt[j, i])):
            return False
        return True

    def los_blocked_at(self, a, b, spacing=1.0):
        """Fraction along a->b of the first obstruction, or None if clear."""
        a = np.asarray(a, np.float64)
        b = np.asarray(b, np.float64)
        d = b - a
        L = float(np.linalg.norm(d))
        n = max(2, int(L / spacing))
        t = np.linspace(0.0, 1.0, n)
        p = a[None, :] + t[:, None] * d[None, :]
        i, j = self.ij(p[:, 0], p[:, 1])
        z = p[:, 2]
        hit = (z < self.ground[j, i] - 0.3) | ((z >= self._bb[j, i]) & (z <= self._bt[j, i])) | ((z >= self._rb[j, i]) & (z <= self._rt[j, i]))
        k = np.flatnonzero(hit)
        return None if k.size == 0 else float(t[k[0]])

    def walk_clear(self, a, b, spacing=0.8):
        """True if a mech can walk the straight ground segment a->b (2D) on the eroded grid."""
        ax, ay = a[0], a[1]
        dx, dy = b[0] - ax, b[1] - ay
        L = math.hypot(dx, dy)
        n = max(2, int(L / spacing))
        t = np.linspace(0.0, 1.0, n)
        i, j = self.ij(ax + t * dx, ay + t * dy)
        return bool(self.walk[j, i].all())

    def solid_top_at(self, x, y):
        i, j = self.ij(x, y)
        v = self.bld_top[j, i]
        return None if np.isnan(v) else float(v)
