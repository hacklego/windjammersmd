#!/usr/bin/env python3
"""Neo Geo screen recording (tools/ngrec) -> Mega Drive "tile movie".

A movie plays on plane A with two name tables (page flipping): every frame lists the tiles to
upload into free VRAM slots, the name table cells to change in the back buffer, an optional
palette and sound events. Colours: every Neo Geo colour used in the scene ("source") is
clustered on its whole trajectory over the scene (so fades and colour cycling survive), each
8x8 cell picks one of the MD palettes, and every frame's CRAM is computed from that frame's
Neo Geo palette RAM.

Movie blob layout (big endian):
  u16 nframes, u16 loop frame (0xFFFF = none), u32 offset of the tile data
  frame: u16 duration (60 Hz ticks), u16 flags (bit0 palette, bit1 cut, bit2 sound)
         [64 u16 CRAM] [u16 n, n x u16 sound id]
         u16 nloads, nloads x (u16 first slot, u16 count, u32 offset into the tile data)
         u16 nruns, nruns x (u16 cell = row * 64 + col, u16 count, count x u16 name table words)
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from array import array
from neogeo import ng_color
from mdgfx import to_md, md_word, TileBank

W, H = 320, 224
CW, CH = W // 8, H // 8
PLANE_W = 64
# VRAM tile slots a movie may use (src/vram.h): everything except the font, disc, shadows,
# the name tables, sprite and scroll tables, and 1408-1471 (sprites shown over still images)
MD_SLOTS = list(range(1, 1080)) + list(range(1152, 1408)) + list(range(1920, 2048))

def read_frames(path, first, last):
    """Yield (frame number, pixels array('H'), palette array('H')) for first <= n <= last from an
    ngrec recording (frames equal to the previous one are stored as a flag only)."""
    size = W * H * 2
    px_off = pal_off = None
    cache = {}
    def load(f, off, n):
        if off not in cache:
            here = f.tell(); f.seek(off)
            a = array('H'); a.frombytes(f.read(n))
            if sys.byteorder == 'big':
                a.byteswap()
            f.seek(here)
            cache.clear(); cache[off] = a
        return cache[off]
    with open(path, 'rb') as f:
        while True:
            hdr = f.read(6)
            if len(hdr) < 6:
                break
            fn, fl = struct.unpack('<IH', hdr)
            if not fl & 0x4000:
                px_off = f.tell(); f.seek(size, 1)
            if not fl & 0x8000:
                pal_off = f.tell(); f.seek(0x2000, 1)
            if fn > last:
                break
            if fn >= first:
                px = array('H', load(f, px_off, size))
                pal = array('H'); pal.frombytes(_read_at(f, pal_off, 0x2000))
                if sys.byteorder == 'big':
                    pal.byteswap()
                yield fn, px, pal

def _read_at(f, off, n):
    here = f.tell(); f.seek(off)
    d = f.read(n)
    f.seek(here)
    return d

def _d(a, b):
    return sum((x - y) * (x - y) for x, y in zip(a, b))

def kmeans(items, k, iters=10):
    """items: {vector: weight} -> up to k centroid vectors (weighted k-means, farthest-point init)."""
    vs = sorted(items, key=lambda v: -items[v])
    if len(vs) <= k:
        return list(vs)
    cent = [vs[0]]
    mind = {v: _d(v, cent[0]) for v in vs}
    while len(cent) < k:
        c = max(vs, key=lambda v: mind[v] * (items[v] ** 0.5))
        if mind[c] == 0:
            break
        cent.append(c)
        for v in vs:
            d = _d(v, c)
            if d < mind[v]:
                mind[v] = d
    dim = len(vs[0])
    for _ in range(iters):
        acc = [[0.0] * (dim + 1) for _ in cent]
        for v, n in items.items():
            i = min(range(len(cent)), key=lambda j: _d(v, cent[j]))
            a = acc[i]
            for j in range(dim):
                a[j] += v[j] * n
            a[dim] += n
        new = [tuple(a[j] / a[dim] for j in range(dim)) if a[dim] else c for a, c in zip(acc, cent)]
        if new == cent:
            break
        cent = new
    return cent

class Movie:
    def __init__(self, frames, npal=4, pal_base=0, drop_fix=(), slots=None, max_states=24, step=1):
        """step: keep every step-th frame, each shown step ticks (frame and sound indexes given to
        encode() are then output frame indexes, source index // step)."""
        self.npal, self.pal_base, self.step = npal, pal_base, step
        frames = (f for k, f in enumerate(frames) if k % step == 0)
        self.slots = slots or MD_SLOTS
        # ---- cells per frame, unique cells, palette states
        cell_ids, self.cells, cell_index = [], [], {}
        state_ids, self.states, state_index = [], [], {}
        self.numbers = []
        for fn, px, pal in frames:
            for (x0, y0, x1, y1) in drop_fix:
                for y in range(y0, y1):
                    for x in range(x0, x1):
                        if px[y * W + x] & 0x1000:
                            px[y * W + x] = 0
            b = px.tobytes()
            ids = []
            for cy in range(CH):
                for cx in range(CW):
                    o = (cy * 8 * W + cx * 8) * 2
                    key = b''.join(b[o + r * W * 2: o + r * W * 2 + 16] for r in range(8))
                    i = cell_index.get(key)
                    if i is None:
                        i = cell_index[key] = len(self.cells)
                        a = array('H'); a.frombytes(key)
                        if sys.byteorder == 'big':
                            a.byteswap()
                        self.cells.append(tuple(v & 0xFFF for v in a))
                    ids.append(i)
            pk = pal.tobytes()
            si = state_index.get(pk)
            if si is None:
                si = state_index[pk] = len(self.states)
                self.states.append(pal)
            cell_ids.append(ids); state_ids.append(si); self.numbers.append(fn)
        self.cell_ids, self.state_ids = cell_ids, state_ids
        # ---- weights: how long each unique cell is visible
        weight = [0] * len(self.cells)
        for ids in cell_ids:
            for i in ids:
                weight[i] += 1
        # ---- source trajectories (MD colour space, sampled palette states)
        ns = len(self.states)
        sample = sorted(set(round(i * (ns - 1) / max(1, max_states - 1)) for i in range(min(ns, max_states))))
        traj = {}
        def trajectory(s):
            t = traj.get(s)
            if t is None:
                t = traj[s] = tuple(c for k in sample for c in to_md(ng_color(self.states[k][s])))
            return t
        # cell groups: identical source histograms
        groups, gindex, cell_group = [], {}, []
        for i, c in enumerate(self.cells):
            h = {}
            for s in c:
                if s:
                    h[s] = h.get(s, 0) + 1
            key = tuple(sorted(h.items()))
            g = gindex.get(key)
            if g is None:
                g = gindex[key] = len(groups)
                groups.append([dict(h), 0])
            groups[g][1] += weight[i]
            cell_group.append(g)
        # ---- palette fitting over groups
        ghist = []
        for h, wgt in groups:
            hv = {}
            for s, n in h.items():
                v = trajectory(s)
                hv[v] = hv.get(v, 0) + n * wgt
            ghist.append(hv)
        assign = self._fit(ghist)
        # ---- source -> (palette, entry), and per palette entry the sources merged into it
        self.entry_of = {}             # (palette, source) -> entry 0..14
        members = [[{} for _ in range(15)] for _ in range(npal)]
        for gi, (h, wgt) in enumerate(groups):
            p = assign[gi]
            for s, n in h.items():
                e = self.entry_of.get((p, s))
                if e is None:
                    v = trajectory(s)
                    e = self.entry_of[(p, s)] = min(range(len(self.cent[p])), key=lambda j: _d(v, self.cent[p][j]))
                members[p][e][s] = members[p][e].get(s, 0) + n * wgt
        self.members = members
        # ---- tiles
        self.bank = TileBank(0)
        self.cell_tile = []            # unique cell -> (bank tile, flip, palette)
        for i, c in enumerate(self.cells):
            p = assign[cell_group[i]]
            idx = [0 if s == 0 else 1 + self.entry_of[(p, s)] for s in c]
            t, flip = self.bank.add(idx)
            self.cell_tile.append((t, flip, p))

    def _fit(self, ghist, iters=6):
        npal = self.npal
        def mean(h):
            n = sum(h.values()) or 1
            dim = len(next(iter(h))) if h else 3
            return tuple(sum(v[j] * m for v, m in h.items()) / n for j in range(dim))
        order = sorted(range(len(ghist)), key=lambda i: sum(mean(ghist[i])) if ghist[i] else -1)
        assign = [0] * len(ghist)
        for rank, i in enumerate(order):
            assign[i] = rank * npal // max(1, len(ghist))
        def err(h, cent):
            return sum(min(_d(v, c) for c in cent) * n for v, n in h.items())
        for _ in range(iters):
            cent = []
            for p in range(npal):
                hist = {}
                for h, a in zip(ghist, assign):
                    if a == p:
                        for v, n in h.items():
                            hist[v] = hist.get(v, 0) + n
                cent.append(kmeans(hist, 15) if hist else [(0,) * 3])
            changed = False
            for i, h in enumerate(ghist):
                if not h:
                    continue
                best = min(range(npal), key=lambda p: err(h, cent[p]))
                if best != assign[i]:
                    assign[i] = best; changed = True
            self.cent = cent
            if not changed:
                break
        return assign

    def cram(self, state):
        """CRAM words for palettes pal_base.. for one palette state (entry 0 of the first palette
        is the backdrop)."""
        pal = self.states[state]
        out = []
        for p in range(self.npal):
            words = [md_word(to_md(ng_color(pal[0xFFF])))] if p == 0 else [0]
            for e in range(15):
                m = self.members[p][e]
                if not m:
                    words.append(0); continue
                tot = sum(m.values())
                rgb = [0.0, 0.0, 0.0]
                for s, n in m.items():
                    c = ng_color(pal[s])
                    for j in range(3):
                        rgb[j] += c[j] * n / tot
                words.append(md_word(to_md(tuple(int(round(x)) for x in rgb))))
            out.append(words)
        return out

    def encode(self, sound=None, loop_from=None):
        """-> (blob, stats). sound: {frame index: [ids]}. loop_from: frame index the movie loops to."""
        frames = []                       # merged frames: [first index, duration]
        for i in range(len(self.cell_ids)):
            if frames and self.cell_ids[i] == self.cell_ids[frames[-1][0]] \
                    and self.state_ids[i] == self.state_ids[frames[-1][0]] \
                    and not (sound and i in sound) and i != loop_from:
                frames[-1][1] += self.step
            else:
                frames.append([i, self.step])
        st = dict(resident={}, slot_tile=[None] * len(self.slots), last_use=[0] * len(self.slots),
                  bufs=[[None] * (CW * CH), [None] * (CW * CH)], cram=None, n=0)
        self.cuts = self.loads_total = 0
        self.out_src = []                 # source frame index of each output frame
        out = []
        if loop_from is None:
            for i, dur in frames:
                out.append(self._frame(st, i, dur, sound))
            loop_out = 0xFFFF
        else:
            k0 = next(k for k, (i, d) in enumerate(frames) if i == loop_from)
            for i, dur in frames[:k0]:
                out.append(self._frame(st, i, dur, sound))
            def snap():
                return (repr(st['bufs']), repr(sorted(st['resident'].items())), st['cram'], st['n'] & 1)
            starts = []
            for _ in range(4):           # repeat the loop body until the VRAM state converges
                starts.append((len(out), snap()))
                for i, dur in frames[k0:]:
                    out.append(self._frame(st, i, dur, sound if len(starts) == 1 else None))
                if snap() == starts[-1][1]:
                    break
            else:
                raise ValueError('loop does not converge')
            loop_out = starts[-1][0]
        tiles = self.bank.data()
        body = b''.join(out)
        blob = struct.pack('>HHI', len(out), loop_out, 8 + len(body)) + body
        return blob + tiles, dict(frames=len(out), tiles=len(self.bank.tiles), loads=self.loads_total,
                                  cuts=self.cuts, states=len(self.states), cells=len(self.cells),
                                  bytes=len(blob) + len(tiles))

    def _frame(self, st, i, dur, sound):
        self.out_src.append(i)
        nslots = len(self.slots)
        resident, slot_tile, last_use, bufs = st['resident'], st['slot_tile'], st['last_use'], st['bufs']
        back = st['n'] & 1
        ids = self.cell_ids[i]
        needed = {self.cell_tile[c][0] for c in ids}
        front_slots = {w & 0x7FF for w in bufs[back ^ 1] if w is not None}
        missing = sorted(t for t in needed if t not in resident)
        keep = {resident[t] for t in needed if t in resident}
        free = [s for s in range(nslots) if s not in keep and self.slots[s] not in front_slots]
        cut = len(free) < len(missing)
        if cut:                            # not enough room beside the shown frame: blank while loading
            free = [s for s in range(nslots) if s not in keep]
            if len(free) < len(missing):
                raise ValueError('frame %d needs %d tiles, VRAM has %d slots' % (i, len(needed), nslots))
        free.sort(key=lambda s: (slot_tile[s] is not None, last_use[s], s))
        chosen = sorted(free[:len(missing)])
        loads = []
        for t, s in zip(missing, chosen):
            if slot_tile[s] is not None:
                del resident[slot_tile[s]]
            slot_tile[s] = t; resident[t] = s
            if loads and self.slots[loads[-1][0]] + loads[-1][1] == self.slots[s] and loads[-1][2] + loads[-1][1] == t:
                loads[-1][1] += 1
            else:
                loads.append([s, 1, t])
        for t in needed:
            last_use[resident[t]] = st['n']
        self.loads_total += len(missing)
        words = []
        for c in ids:
            t, flip, p = self.cell_tile[c]
            words.append(((self.pal_base + p) << 13) | (flip << 11) | self.slots[resident[t]])
        runs = []
        bb = bufs[back]
        for cy in range(CH):
            cx = 0
            while cx < CW:
                o = cy * CW + cx
                if bb[o] == words[o] and not cut:
                    cx += 1; continue
                start = cx
                while cx < CW and (cut or bb[cy * CW + cx] != words[cy * CW + cx]):
                    cx += 1
                runs.append((cy * PLANE_W + start, words[cy * CW + start: cy * CW + cx]))
        bufs[back] = list(words)
        flat = [0] * (16 * self.pal_base) + [w for p in self.cram(self.state_ids[i]) for w in p]   # at palette pal_base
        fl = 0
        rec = bytearray()
        if flat != st['cram']:
            fl |= 1; rec += struct.pack('>%dH' % len(flat), *flat) + bytes(2 * (64 - len(flat)))
            st['cram'] = flat
        snd = (sound or {}).get(i, [])
        if snd:
            fl |= 4; rec += struct.pack('>H%dH' % len(snd), len(snd), *snd)
        if cut:
            fl |= 2; self.cuts += 1
        rec += struct.pack('>H', len(loads))
        for s, n, t in loads:
            rec += struct.pack('>HHI', self.slots[s], n, t * 32)
        rec += struct.pack('>H', len(runs))
        for cell, ws in runs:
            rec += struct.pack('>HH%dH' % len(ws), cell, len(ws), *ws)
        st['n'] += 1
        return struct.pack('>HH', dur, fl) + bytes(rec)

if __name__ == '__main__':
    import argparse, time
    ap = argparse.ArgumentParser()
    ap.add_argument('frames'); ap.add_argument('first', type=int); ap.add_argument('last', type=int)
    ap.add_argument('out'); ap.add_argument('--loop', type=int)
    a = ap.parse_args()
    t0 = time.time()
    fr = read_frames(a.frames, a.first, a.last)
    m = Movie(fr)
    blob, st = m.encode(loop_from=None if a.loop is None else a.loop - a.first)
    open(a.out, 'wb').write(blob)
    print(st, '%.1fs' % (time.time() - t0))
