"""Mega Drive graphics conversion: colour reduction, palette fitting, tile packing."""

def to_md(rgb):
    """8-bit RGB -> Mega Drive 3-bit-per-channel tuple."""
    return tuple((c * 7 + 127) // 255 for c in rgb)

def md_word(c):
    """(r,g,b) 0..7 -> CRAM word 0000BBB0GGG0RRR0."""
    r, g, b = c
    return (b << 9) | (g << 5) | (r << 1)

def _d(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2

def nearest(pal, c):
    best, bi = 1 << 30, 0
    for i, p in enumerate(pal):
        d = _d(p, c)
        if d < best:
            best, bi = d, i
    return bi, best

def kmeans_colors(hist, k, iters=12):
    """Weighted k-means over a {color: count} histogram -> up to k colors."""
    cols = sorted(hist, key=lambda c: -hist[c])
    if len(cols) <= k:
        return cols
    # farthest-point init seeded with most frequent colour
    cent = [cols[0]]
    while len(cent) < k:
        cent.append(max(cols, key=lambda c: min(_d(c, x) for x in cent) * (hist[c] ** 0.5)))
    for _ in range(iters):
        acc = [[0, 0, 0, 0] for _ in cent]
        for c, n in hist.items():
            i, _ = nearest(cent, c)
            a = acc[i]; a[0] += c[0] * n; a[1] += c[1] * n; a[2] += c[2] * n; a[3] += n
        new = []
        for a, old in zip(acc, cent):
            new.append(tuple(round(a[j] / a[3]) for j in range(3)) if a[3] else old)
        if new == cent:
            break
        cent = new
    return list(dict.fromkeys(cent))

def tile_error(hist, pal):
    return sum(nearest(pal, c)[1] * n for c, n in hist.items())

def fit_palettes(tiles, npal, ncol=15, iters=6):
    """tiles: list of {color: count}. Returns (palettes, assignment) minimising total error.
    ncol may be a list giving the colour budget of each palette."""
    if isinstance(ncol, int):
        ncol = [ncol] * npal
    # initial split: sort tiles by average hue-ish key and cut into npal groups
    def avg(h):
        n = sum(h.values()) or 1
        return tuple(sum(c[j] * m for c, m in h.items()) / n for j in range(3))
    order = sorted(range(len(tiles)), key=lambda i: avg(tiles[i]))
    assign = [0] * len(tiles)
    for rank, i in enumerate(order):
        assign[i] = rank * npal // max(1, len(tiles))
    pals = []
    for _ in range(iters):
        pals = []
        for p in range(npal):
            hist = {}
            for t, a in zip(tiles, assign):
                if a == p:
                    for c, n in t.items():
                        hist[c] = hist.get(c, 0) + n
            pals.append(kmeans_colors(hist, ncol[p]) if hist else [(0, 0, 0)])
        changed = False
        for i, t in enumerate(tiles):
            best = min(range(npal), key=lambda p: tile_error(t, pals[p]))
            if best != assign[i]:
                assign[i] = best; changed = True
        if not changed:
            break
    return pals, assign

def pack_tile(px):
    """64 indexes (row major) -> 32 bytes MD 4bpp."""
    out = bytearray()
    for y in range(8):
        for x in range(0, 8, 2):
            out.append((px[y * 8 + x] << 4) | px[y * 8 + x + 1])
    return bytes(out)

def flip_variants(px):
    h = [px[y * 8 + (7 - x)] for y in range(8) for x in range(8)]
    v = [px[(7 - y) * 8 + x] for y in range(8) for x in range(8)]
    hv = [px[(7 - y) * 8 + (7 - x)] for y in range(8) for x in range(8)]
    return ((px, 0), (h, 1), (v, 2), (hv, 3))

class TileBank:
    """Deduplicating tile store (matches flipped copies)."""
    def __init__(self, base=0):
        self.tiles = []; self.index = {}; self.base = base
    def add(self, px):
        for var, flip in flip_variants(px):
            k = bytes(var)
            if k in self.index:
                return self.index[k], flip
        self.index[bytes(px)] = len(self.tiles) + self.base
        self.tiles.append(pack_tile(px))
        return len(self.tiles) - 1 + self.base, 0
    def data(self):
        return b''.join(self.tiles)
