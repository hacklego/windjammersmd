#!/usr/bin/env python3
"""Record scenes of the original game and convert them into Mega Drive movies.

usage: mkmovies.py <rom dir or zip> <bios dir or neogeo.zip> <build dir>

Runs tools/ngrec (BUILD/ngrec) once per recording in the manifest to get the sound command log,
works out each movie's frame range from its markers, records those frames, converts them with
tools/mkmovie.py and writes BUILD/movies.s/.c/.h and BUILD/banked_movies.txt.
"""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neogeo import RomSet
from mkmovie import Movie, read_frames
import manifest_wjammers as M

def parse_commands(path):
    """ngrec sound log -> [(frame, (bytes...))]: 0x16-0x1F take one parameter byte."""
    out, pending = [], None
    for line in open(path):
        fr, b = line.split()
        fr, b = int(fr), int(b, 16)
        if pending is not None:
            out.append((pending[0], (pending[1], b)))
            pending = None
        elif 0x16 <= b <= 0x1F:
            pending = (fr, b)
        else:
            out.append((fr, (b,)))
    return out

def normalize(cmd):
    return (0x17, cmd[1]) if len(cmd) == 2 and cmd[0] == 0x16 else cmd

def marker_frame(cmds, marker):
    if isinstance(marker, int):
        return marker                   # absolute frame number
    code, occurrence, offset = marker
    hits = [fr for fr, c in cmds if normalize(c) == normalize(tuple(code))]
    if occurrence >= len(hits):
        raise SystemExit('marker %s #%d not found in the recording' % (code, occurrence))
    return hits[occurrence] + offset

def read_vram(path):
    """First frame of an ngrec -V dump -> (VRAM words, palette words)."""
    import struct
    with open(path, 'rb') as f:
        f.read(4)
        v = struct.unpack('<%dH' % 0x8800, f.read(0x8800 * 2))
        p = struct.unpack('<%dH' % 0x1000, f.read(0x2000))
    return v, p

_game = None
def sprite_chains(vram):
    """-> [(first sprite, last sprite, x, y)] for the visible sprite chains of a VRAM image."""
    out = []
    for n in range(1, 381):
        yc = vram[0x8200 + n]
        if yc & 0x40 and out:
            out[-1][1] = n
            continue
        x = vram[0x8400 + n] >> 7
        out.append([n, n, x - 0x200 if x >= 0x1F0 else x, (0x200 - (yc >> 7)) - 16, yc & 0x3F])
    return [tuple(c[:4]) for c in out if c[4]]

def fit_palette(img):
    """15-colour MD palette for an image (index 0 transparent) -> 16 CRAM words."""
    from mdgfx import to_md, md_word, kmeans_colors
    hist = {}
    for row in img:
        for c in row:
            if c:
                m = to_md(c)
                hist[m] = hist.get(m, 0) + 1
    cols = kmeans_colors(hist, 15)
    return [0] + [md_word(c) for c in cols] + [0] * (15 - len(cols))

def render_chain(vram, pal, ranges):
    """Draw Neo Geo sprite ranges [(a, b)] (unscaled) -> (rows of RGB or None, screen x, screen y)."""
    from neogeo import ng_color
    cols = []
    x = y = 0
    for n in [n for a, b in ranges for n in range(a, b + 1)]:
        yc = vram[0x8200 + n]
        if yc & 0x40 and cols:
            x += 16
        else:
            y = (0x200 - (yc >> 7)) - 16; x = vram[0x8400 + n] >> 7
            if x >= 0x1F0: x -= 0x200
            hgt = yc & 0x3F
        cols.append((n, x, y, hgt))
    xs = min(c[1] for c in cols); ys = min(c[2] for c in cols)
    W = max(c[1] for c in cols) + 16 - xs; Hh = max(c[2] + 16 * c[3] for c in cols) - ys
    img = [[None] * W for _ in range(Hh)]
    for n, cx, cy, hgt in cols:
        for r in range(hgt):
            t = vram[n * 64 + 2 * r]; at = vram[n * 64 + 2 * r + 1]
            code = t | ((at << 12) & 0xF0000)
            px = _game.tile(code); pl = at >> 8
            for yy in range(16):
                for xx in range(16):
                    v = px[(15 - yy if at & 2 else yy) * 16 + (15 - xx if at & 1 else xx)]
                    if v:
                        img[cy - ys + r * 16 + yy][cx - xs + xx] = ng_color(pal[pl * 16 + v])
    return img, xs, ys

def sprite_frame(img, cram, only=None):
    """RGB image -> (MD tiles, pieces (dx, dy, size, tile)) using the screen's CRAM palettes;
    each 32x32 piece picks the palette that fits it best (size bit 0x20, palette in bits 6-7)."""
    from mdgfx import to_md, pack_tile
    cram = list(cram) + [0] * (64 - len(cram))
    pals = [[((w >> 1) & 7, (w >> 5) & 7, (w >> 9) & 7) for w in cram[p * 16:p * 16 + 16]] for p in range(4)]
    usable = [p for p in range(4) if any(cram[p * 16 + 1:p * 16 + 16])]
    H, W = len(img), len(img[0])
    tw, th = (W + 7) // 8, (H + 7) // 8
    def px(x, y):
        return img[y][x] if y < H and x < W else None
    data, pieces = bytearray(), []
    for by in range(0, th, 4):
        for bx in range(0, tw, 4):
            w, h = min(4, tw - bx), min(4, th - by)
            cells = [[px(bx * 8 + x, by * 8 + y) for y in range(h * 8) for x in range(w * 8)]]
            colors = [to_md(c) for c in cells[0] if c]
            if not colors:
                continue
            def err(p):
                return sum(min(sum((a - b) ** 2 for a, b in zip(c, q)) for q in pals[p][1:]) for c in colors)
            best = only if only is not None else min(usable, key=err)
            pl = pals[best]
            def idx(c):
                if c is None:
                    return 0
                m = to_md(c)
                return 1 + min(range(15), key=lambda i: sum((a - b) ** 2 for a, b in zip(m, pl[i + 1])))
            start = len(data) // 32
            for tx in range(w):                    # MD sprite tiles run down each column
                for ty in range(h):
                    data += pack_tile([idx(px((bx + tx) * 8 + x, (by + ty) * 8 + y)) for y in range(8) for x in range(8)])
            pieces.append((bx * 8, by * 8, ((w - 1) << 2) | (h - 1) | 0x20 | (best << 6), start))
    return bytes(data), pieces

def make_hud(pal, rs):
    """Match HUD from the game's own tiles: big score digits and TIME boxes (C-ROM, scoreboard
    palette) as sprites in palette 1, HUD font and flags (S-ROM) as plane tiles. Palette 1 entries
    8-15 are fixed in a match: 8, 9 HUD colours, 10-13 disc, 14 black, 15 white."""
    from neogeo import ng_color, decode_fix
    from mdgfx import to_md, md_word, pack_tile
    import struct as _st
    srom = rs.get(*M.FILES['s1'])
    hud = [to_md(ng_color(pal[M.HUD_COLOR_ENTRIES[0]])), to_md(ng_color(pal[M.HUD_COLOR_ENTRIES[1]]))]
    disc = [((w >> 1) & 7, (w >> 5) & 7, (w >> 9) & 7) for w in _st.unpack('>4H', open(os.path.join(sys.argv[3], 'disc_colors.bin'), 'rb').read()[:8])]
    # only the entries that never change: 10-13 are recoloured for the disc, supers and banners
    fixed = {8: hud[0], 9: hud[1], 14: (0, 0, 0), 15: (7, 7, 7)}
    def near(c, choices):
        c = to_md(c)
        return min(choices, key=lambda i: sum((a - b) ** 2 for a, b in zip(c, choices[i])))
    def sprite16(tile, palno):
        px = _game.tile(tile)
        out = bytearray()
        for tx in range(2):
            for ty in range(2):
                out += pack_tile([near(ng_color(pal[palno * 16 + v]), fixed) if v else 0
                                  for y in range(8) for v in [px[(ty * 8 + y) * 16 + tx * 8 + x] for x in range(8)]])
        return bytes(out)
    data, c = bytearray(), []
    for d in range(10):
        data += sprite16(M.HUD_DIGIT_TILE + d, M.HUD_SPRITE_PAL)
    for k in range(31):         # TIME boxes for 30..0 seconds (tile HUD_TIME_TILE + k shows 45 - k)
        data += sprite16(M.HUD_TIME_TILE + 15 + k, M.HUD_SPRITE_PAL)
    data += sprite16(M.HUD_TIME_UP_TILE, M.HUD_SPRITE_PAL)      # TIME UP
    def fix8(code, palno, choices):
        px = decode_fix(srom, code)
        return pack_tile([near(ng_color(pal[palno * 16 + v]), choices) if v else 0 for v in px])
    for ch in 'P120123456789'[:3] + '0123456789':
        data += fix8(0x300 + ord(ch), M.HUD_FONT_PAL, fixed)
    import extract
    flag_pal = []
    for ci in range(6):
        sides = []
        for side in range(2):
            # the side's player palette from the character data, plus palette 1's fixed colours
            cp = [to_md(_game.color(M.CHARACTERS[ci]['palette'] + side, i)) for i in range(16)]
            pals = []
            for k, off in enumerate((0, 1, 2, 3)):
                code = M.HUD_FLAG_TILES[ci] + off
                px = decode_fix(srom, code)
                cols = [ng_color(pal[M.HUD_FLAG_PAL * 16 + v]) for v in px if v]
                own = {i: cp[i] for i in range(1, 16)}
                e_own = sum(min(sum((a - b) ** 2 for a, b in zip(to_md(c), q)) for q in own.values()) for c in cols)
                e_fix = sum(min(sum((a - b) ** 2 for a, b in zip(to_md(c), q)) for q in fixed.values()) for c in cols)
                use = (own, 2 + side) if e_own < e_fix else (fixed, 1)
                data += fix8(code, M.HUD_FLAG_PAL, use[0])
                pals.append(use[1])
            sides.append(pals)
        flag_pal.append(sides)
    # set lamp: lit bar over a score once that player has a set (C-ROM HUD_SET_BAR_TILES, left and
    # right halves; only rows 8-15 are drawn): its three different 8x8 pieces, end-middle-end
    def bar8(tile, tx):
        px = _game.tile(tile)
        return pack_tile([near(ng_color(pal[M.HUD_SPRITE_PAL * 16 + v]), fixed) if v else 0
                          for y in range(8, 16) for v in [px[y * 16 + tx * 8 + x] for x in range(8)]])
    left, right = M.HUD_SET_BAR_TILES
    data += bar8(left, 0) + bar8(left, 1) + bar8(right, 1)
    # last seconds: the big TIME box (fix layer), halves of 2x4 fix tiles: the tens (0, 1, 3, U of UP)
    # then the units (0-9, P of UP), with the box palette's own colour indexes (the match maps them
    # to palette 1 at run time, by court: src/match.c box_lut)
    box_pal = [md_word(to_md(ng_color(pal[M.HUD_BOX_PAL * 16 + i]))) for i in range(16)]
    print('time box palette', ['%03X' % w for w in box_pal])
    for code in M.HUD_BOX_TENS + M.HUD_BOX_UNITS:
        for k in range(8):
            data += pack_tile(decode_fix(srom, code + k))
    c.append('const u16 hud_box_src[16] = {%s};' % ', '.join('0x%03X' % w for w in box_pal))
    # the game's fix-layer font in the HUD colours: text drawn during a match looks like the original
    font = bytearray()
    for ch in range(0x20, 0x60):        # ('^' unused: the 'm' of the DOG DISTANCE metres there)
        font += fix8(M.FONT_BASE + (ord('m') if ch == ord('^') else ch), M.HUD_FONT_PAL, fixed)
    open(os.path.join(sys.argv[3], 'fixfont.bin'), 'wb').write(bytes(font))
    # the ranking's score font: 8 x 16 (fix tiles 0xE00 / 0xF00 + ASCII), space then 0-9, top and bottom
    rfont = bytearray()
    for ch in ' 0123456789':
        rfont += fix8(0xE00 + ord(ch), M.HUD_FONT_PAL, fixed) + fix8(0xF00 + ord(ch), M.HUD_FONT_PAL, fixed)
    open(os.path.join(sys.argv[3], 'rankfont.bin'), 'wb').write(bytes(rfont))
    c += ['const u16 hud_flag_pal[6][2][4] = {%s};' % ', '.join(
            '{%s}' % ', '.join('{%s}' % ', '.join(map(str, p)) for p in sides) for sides in flag_pal),
         'const u16 hud_colors[2] = {0x%03X, 0x%03X};' % (md_word(hud[0]), md_word(hud[1]))]
    return c, bytes(data)

def make_bonus(run, cmds, sound_id, build):
    """The frisbee dog bonus demo: the beach (one repeating 512 px sprite chain) for plane B with its
    scroll per frame, and every other sprite as an object replayed at its recorded position."""
    import struct as _st
    from extract import convert_plane
    from mdgfx import TileBank, to_md, md_word, pack_tile, fit_palettes, nearest
    bd = M.BONUS_DEMO
    first, last = marker_frame(cmds, bd['start']), marker_frame(cmds, bd['end'])
    base = os.path.join(build, 'bonus')
    run(bd['rec'], M.RECORDINGS[bd['rec']], [(first, last)], base, ['-N', '-V', base + '.vram'])
    frames = []
    with open(base + '.vram', 'rb') as f:
        while True:
            h = f.read(4)
            if not h:
                break
            fn = _st.unpack('<I', h)[0]
            v = _st.unpack('<%dH' % 0x8800, f.read(0x8800 * 2)); p = _st.unpack('<%dH' % 0x1000, f.read(0x2000))
            if (fn - first) % bd['step'] == 0:
                frames.append((fn, v, p))
    os.remove(base + '.vram')
    def bg_chain(v):
        for a_, b_, x_, y_ in sprite_chains(v):
            if b_ - a_ == 31 and (v[0x8200 + a_] & 0x3F) == 14:
                return a_, b_, x_
    ref = next(fr for fr in frames if bg_chain(fr[1]))
    a0, b0, _ = bg_chain(ref[1])
    img, _, _ = render_chain(ref[1], ref[2], [(a0, b0)])
    img = [row + [None] * (512 - len(row)) for row in img[:224]] + [[None] * 512] * max(0, 224 - len(img))
    bank = TileBank(1)
    words, cram = convert_plane(img, 0, 0, 64, 28, 2, 0, bank)
    # objects
    # the shadows and the sand puffs: the original draws them every other frame only (see bonus.c)
    dg, DUST_PAL, flicker = M.DOG_GAME, 0x11, set()
    uniq, recs, events = {}, [], []
    for fn, v, p in frames:
        bg = bg_chain(v)
        objs = []
        for a_, b_, x_, y_ in sprite_chains(v):
            if bg and a_ == bg[0]:
                continue
            if y_ >= 224 or y_ < -64 or x_ >= 320 or x_ < -64:
                continue
            z = v[0x8000 + a_]
            zx, zy = ((z >> 8) & 15) >> 1, (z & 0xFF) >> 5      # quantised shrink
            sig = (tuple((v[n * 64 + 2 * r], v[n * 64 + 2 * r + 1]) for n in range(a_, b_ + 1)
                         for r in range(v[0x8200 + a_] & 0x3F)), zx, zy, b_ - a_)
            if sig not in uniq:
                pl_, t_ = v[a_ * 64 + 1] >> 8, v[a_ * 64] | ((v[a_ * 64 + 1] << 12) & 0xF0000)
                if pl_ in (dg['shadow'][0], DUST_PAL) or (pl_, t_) == (dg['disc'], dg['shadow_tile']):
                    flicker.add(len(uniq))
                im, _, _ = render_chain(v, p, [(a_, b_)])
                sx, sy = (zx * 2 + 2) / 16.0, (zy * 32 + 32) / 256.0
                H, W_ = len(im), len(im[0])
                nh, nw = max(1, int(H * sy + 0.5)), max(1, int(W_ * sx + 0.5))
                uniq[sig] = (len(uniq), [[im[min(H - 1, int(y / sy))][min(W_ - 1, int(x / sx))] for x in range(nw)] for y in range(nh)])
            objs.append((a_, uniq[sig][0], x_, y_))
        objs.reverse()        # the Neo Geo draws later sprites on top, the Mega Drive earlier ones
        recs.append((bg[2] if bg else 0, objs))
        for fr, c_ in cmds:
            if fn <= fr < fn + bd['step']:
                sid = sound_id(normalize(c_))
                if sid is not None:
                    events.append((len(recs) - 1, sid))
    images = [im for _, (k, im) in sorted(uniq.items(), key=lambda kv: kv[1][0])]
    hists = []
    for im in images:
        h_ = {}
        for row in im:
            for c_ in row:
                if c_:
                    m = to_md(c_); h_[m] = h_.get(m, 0) + 1
        hists.append(h_ or {(0, 0, 0): 1})
    # palette 3 leaves 8, 9, 14, 15 to the HUD text (the game font's colours, as src/bonus.c sets them)
    slots = [list(range(1, 16)), [1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13]]
    pals, assign = fit_palettes(hists, 2, [15, 11])
    data, fr_c, c = bytearray(), [], []
    maxt = 0
    for k, im in enumerate(images):
        pl, sl = pals[assign[k]], slots[assign[k]]
        def idx(c_):
            return 0 if c_ is None else sl[nearest(pl, to_md(c_))[0]]
        H, W_ = len(im), len(im[0])
        pieces, start = [], len(data) // 32
        for by in range(0, (H + 7) // 8, 4):
            for bx in range(0, (W_ + 7) // 8, 4):
                w, h = min(4, (W_ + 7) // 8 - bx), min(4, (H + 7) // 8 - by)
                px = lambda x, y: im[y][x] if y < H and x < W_ else None
                if not any(px(bx * 8 + x, by * 8 + y) for y in range(h * 8) for x in range(w * 8)):
                    continue
                t0 = len(data) // 32 - start
                for tx in range(w):
                    for ty in range(h):
                        data.extend(pack_tile([idx(px((bx + tx) * 8 + x, (by + ty) * 8 + y)) for y in range(8) for x in range(8)]))
                pieces.append('{%d, %d, %d, %d}' % (bx * 8, by * 8, ((w - 1) << 2) | (h - 1) | 0x20 | ((2 + assign[k]) << 6), t0))
        maxt = max(maxt, len(data) // 32 - start)
        c.append('static const SprPiece bo%d_p[] = {%s};' % (k, ', '.join(pieces) or '{0, 0, 0, 0}'))
        fr_c.append('{bonus_data + %d, %d, %d, bo%d_p}' % (len(bank.tiles) * 32 + start * 32, len(data) // 32 - start, len(pieces), k))
    c.append('const Frame bonus_objects[] = {%s};' % ', '.join(fr_c))
    c.append('const u8 bonus_flicker[%d] = {%s};' % (len(images) + (len(images) & 1), ', '.join('1' if k in flicker else '0' for k in range(len(images) + (len(images) & 1)))))
    rec_words = []
    for scroll, objs in recs:
        rec_words += [scroll, len(objs)] + [w_ for a_, k, x_, y_ in objs for w_ in (a_, k, x_ & 0xFFFF, y_ & 0xFFFF)]
    c.append('const u16 bonus_frames[] = {%s};' % ', '.join(map(str, rec_words)))
    c.append('const u16 bonus_sounds[] = {%s};' % ', '.join('%d, %d' % e for e in events + [(0xFFFF, 0)]))
    c.append('const u16 bonus_pal[64] = {%s};' % ', '.join('0x%03X' % w_ for w_ in (cram[0] + cram[1] +
        [w_ for pl, sl in zip(pals, slots) for w_ in [0] + [md_word(pl[sl.index(i)]) if i in sl and sl.index(i) < len(pl) else 0
                                                         for i in range(1, 16)]])))
    c.append('const u16 bonus_map[64 * 28] = {%s};' % ', '.join('0x%04X' % w_ for w_ in words))
    c.append('const u16 bonus_count = %d, bonus_step = %d, bonus_bg_tiles = %d;' % (len(recs), bd['step'], len(bank.tiles)))
    print('bonus demo: %d frames, %d objects images (%d KB, max %d tiles), beach %d tiles' % (
        len(recs), len(images), len(data) // 1024, maxt, len(bank.tiles)))
    return c, bank.data() + bytes(data)

def vram_shots(run, wanted):
    """{(recording, frame)} -> {(recording, frame): (VRAM words, palette words)}, one ngrec run
    per recording."""
    import struct as _st
    out = {}
    for rname in sorted(set(r for r, _ in wanted)):
        frames = sorted(f for r, f in wanted if r == rname)
        rec = M.RECORDINGS[rname]
        rec = dict(rec, frames=max(rec['frames'], frames[-1] + 1))
        base = os.path.join(sys.argv[3], 'shots_' + rname)
        run(rname, rec, [(f, f) for f in frames], base, ['-N', '-V', base + '.vram'])
        with open(base + '.vram', 'rb') as f:
            while True:
                h = f.read(4)
                if len(h) < 4:
                    break
                fn = _st.unpack('<I', h)[0]
                v = _st.unpack('<%dH' % 0x8800, f.read(0x8800 * 2))
                out[(rname, fn)] = (v, _st.unpack('<%dH' % 0x1000, f.read(0x2000)))
        os.remove(base + '.vram')
    return out

def chain_image(shot, x, y, pl, what):
    """The sprite chain starting at (x, y) in palette pl of a VRAM shot, rendered."""
    vram, pal = shot
    ch = [c for c in sprite_chains(vram) if c[2] == x and c[3] == y and (vram[c[0] * 64 + 1] >> 8) == pl]
    if not ch:
        raise SystemExit('%s: no sprite chain at %d,%d in palette %X' % (what, x, y, pl))
    return render_chain(vram, pal, [(ch[0][0], ch[0][1])])[0]

def fit4(images, pal):
    """4 colours (palette 1 entries 10-13) fitted to images, next to the fixed entries 8, 9 (HUD),
    14 (black) and 15 (white) -> (md colours, RGB -> palette 1 index)."""
    from neogeo import ng_color
    from mdgfx import to_md, kmeans_colors
    hist = {}
    for img in images:
        for row in img:
            for c_ in row:
                if c_:
                    m = to_md(c_); hist[m] = hist.get(m, 0) + 1
    hud = [to_md(ng_color(pal[M.HUD_COLOR_ENTRIES[0]])), to_md(ng_color(pal[M.HUD_COLOR_ENTRIES[1]]))]
    fixed = {8: hud[0], 9: hud[1], 14: (0, 0, 0), 15: (7, 7, 7)}
    rest = {c_: n for c_, n in hist.items() if min(sum((a - b) ** 2 for a, b in zip(c_, q)) for q in fixed.values()) > 1}
    cols = kmeans_colors(rest, 4) if rest else []
    cols += [(0, 0, 0)] * (4 - len(cols))
    slots = dict(fixed); slots.update({10 + i: cols[i] for i in range(4)})
    def idx(c_):
        if c_ is None:
            return 0
        m = to_md(c_)
        return min(slots, key=lambda k: sum((a - b) ** 2 for a, b in zip(m, slots[k])))
    return cols, idx

def fitted_parts(images, pal, out_tiles, symbol):
    """Plane A parts in palette 1 with 4 colours fitted to them (fit4). images: [(name, rows of
    RGB)] -> (md colours, [(name, C initializer of a BannerPart, C map)]); the tiles are appended
    to out_tiles."""
    from mdgfx import TileBank
    cols, idx = fit4([img for _, img in images], pal)
    parts = []
    for name, img in images:
        H, W = len(img), len(img[0])
        bank = TileBank(0)
        cells = []
        for cy in range((H + 7) // 8):
            for cx in range((W + 7) // 8):
                px = [idx(img[cy * 8 + yy][cx * 8 + xx]) if cy * 8 + yy < H and cx * 8 + xx < W else 0 for yy in range(8) for xx in range(8)]
                if not any(px):
                    cells.append(0xFFFF); continue
                t, flip = bank.add(px)
                cells.append((flip << 11) | t)
        start = len(out_tiles) // 32
        out_tiles += bank.data()
        parts.append((name, '{%s + %d, %d, %d, %d, %s_map}' % (symbol, start * 32, len(bank.tiles), (W + 7) // 8, (H + 7) // 8, name),
                       'static const u16 %s_map[] = {%s};' % (name, ', '.join('0x%04X' % w for w in cells))))
    return cols, parts

def hud_glyphs(srom, pal):
    """The bonus rounds' HUD glyphs as colour images (8 x 8, None = clear): each character's flag
    (4 fix tiles: TL, BL, TR, BR), then the timer's big digits 0-9 (4 each, the same order)."""
    from neogeo import ng_color, decode_fix
    g = []
    for ci in range(6):
        g += [[ng_color(pal[M.HUD_FLAG_PAL * 16 + v]) if v else None for v in decode_fix(srom, M.HUD_FLAG_TILES[ci] + k)] for k in range(4)]
    g += [[ng_color(pal[M.BOWL['digit_pal'] * 16 + v]) if v else None for v in decode_fix(srom, M.BOWL['digits'] + k)] for k in range(40)]
    return g

def make_bowl(run, banked, srom, match_pal):
    """FLYING DISC BOWLING pictures (manifest BOWL): the lane for plane B; sprites, the sheet's marks
    and the timer digits in one palette (3; 8/9 HUD colours, 14 black, 15 white)."""
    import struct as _st
    from extract import convert_plane
    from mdgfx import TileBank, to_md, md_word, kmeans_colors, pack_tile
    from neogeo import ng_color, decode_fix
    bw = M.BOWL
    build = sys.argv[3]
    rec = M.RECORDINGS[bw['rec']]
    base = os.path.join(build, 'bowl')
    fr = bw['frame']
    shots = vram_shots(run, set([(bw['rec'], fr), (bw['rec'], bw['machine'][0]), (bw['rec'], bw['logo'][0])]))
    vram, pal = shots[(bw['rec'], fr)]
    extra = []
    for b in bw['blank']:
        extra += ['-B', b]
    for a_, b_, x_, y_ in sprite_chains(vram):
        if (vram[a_ * 64 + 1] >> 8) in bw['hide_palettes']:
            extra += ['-H', '%d-%d' % (a_, b_)]
    run(bw['rec'], rec, [(fr, fr)], base, extra)
    (_, px, npal_), = list(read_frames(base + '.frames', fr, fr))
    os.remove(base + '.frames')
    img = [[ng_color(npal_[px[y * 320 + x] & 0xFFF]) if px[y * 320 + x] else ng_color(npal_[0xFFF]) for x in range(320)] for y in range(224)]
    bank = TileBank(1)
    words, cram = convert_plane(img, 0, 0, 40, 28, 2, 0, bank, ncol=M.COURT_COLORS)
    for kind, data in (('tiles', bank.data()), ('map', _st.pack('>%dH' % len(words), *words)),
                       ('pal', _st.pack('>32H', *(cram[0] + cram[1])))):
        open(os.path.join(build, 'bowlshot_%s.bin' % kind), 'wb').write(data)
    banked.append('V bowlshot_tiles %s' % os.path.abspath(os.path.join(build, 'bowlshot_tiles.bin')))
    # sprites
    def tile_img(code, palno):
        t = _game.tile(code)
        return [[ng_color(pal[palno * 16 + t[y * 16 + x]]) if t[y * 16 + x] else None for x in range(16)] for y in range(16)]
    pt = bw['pin_tiles']
    images = [tile_img(pt['stand'], bw['pin_pal']), tile_img(pt['shadow'], bw['pin_pal'])] + \
             [tile_img(t, bw['pin_pal']) for t in pt['tumble']]
    mv, mpl = shots[(bw['rec'], bw['machine'][0])], bw['machine'][1]
    mch = [c for c in sprite_chains(mv[0]) if (mv[0][c[0] * 64 + 1] >> 8) == mpl]
    images.append(render_chain(mv[0], mv[1], [(mch[0][0], mch[0][1])])[0])
    lv = shots[(bw['rec'], bw['logo'][0])]
    lch = [(c[0], c[1]) for c in sprite_chains(lv[0]) if (lv[0][c[0] * 64 + 1] >> 8) == bw['logo'][1]]
    limg, lx, ly = render_chain(lv[0], lv[1], lch)
    images.append(limg)
    # fix glyphs: marks (2 tiles each) and big digits (2 x 2), in this palette too
    mcode, mn, mpal = bw['marks']
    fixg = [[ng_color(pal[mpal * 16 + v]) if v else None for v in decode_fix(srom, mcode + k)] for k in range(mn * 2)]
    fixg += [[ng_color(pal[bw['digit_pal'] * 16 + v]) if v else None for v in decode_fix(srom, bw['digits'] + k)] for k in range(40)]
    fixg += hud_glyphs(srom, match_pal)[:24]                    # the flags (weighed: small but seen)
    hist = {}
    for im in images:
        for row in im:
            for c_ in row:
                if c_:
                    m = to_md(c_); hist[m] = hist.get(m, 0) + 1
    for g_ in fixg:
        for c_ in g_:
            if c_:
                m = to_md(c_); hist[m] = hist.get(m, 0) + 8
    hud = [to_md(ng_color(match_pal[M.HUD_COLOR_ENTRIES[0]])), to_md(ng_color(match_pal[M.HUD_COLOR_ENTRIES[1]]))]
    fixed = {8: hud[0], 9: hud[1], 14: (0, 0, 0), 15: (7, 7, 7)}
    rest = {c_: n for c_, n in hist.items() if min(sum((a - b) ** 2 for a, b in zip(c_, q)) for q in fixed.values()) > 1}
    free = [i for i in range(1, 16) if i not in fixed]
    cols = kmeans_colors(rest, len(free))
    slots = dict(fixed); slots.update({free[i]: cols[i] for i in range(len(cols))})
    def idx(c_):
        if c_ is None:
            return 0
        m = to_md(c_)
        return min(slots, key=lambda k: sum((a - b) ** 2 for a, b in zip(m, slots[k])))
    bpal = [0] * 16
    for k, c_ in slots.items():
        bpal[k] = md_word(c_)
    data, c = bytearray(), ['const u16 bowl_pal[16] = {%s};' % ', '.join('0x%03X' % w for w in bpal)]
    inits = []
    for n, im in enumerate(images):
        H, W = len(im), len(im[0])
        th, tw = (H + 7) // 8, (W + 7) // 8
        pieces, start = [], len(data) // 32
        for by in range(0, th, 4):
            for bx in range(0, tw, 4):
                w, h = min(4, tw - bx), min(4, th - by)
                t0 = len(data) // 32 - start
                for tx in range(w):
                    for ty in range(h):
                        data.extend(pack_tile([idx(im[(by + ty) * 8 + y][(bx + tx) * 8 + x] if (by + ty) * 8 + y < H and (bx + tx) * 8 + x < W else None) for y in range(8) for x in range(8)]))
                pieces.append('{%d, %d, %d, %d}' % (bx * 8, by * 8, ((w - 1) << 2) | (h - 1), t0))
        c.append('static const SprPiece bw%d_p[] = {%s};' % (n, ', '.join(pieces)))
        inits.append('{bowl_tiles + %d, %d, %d, bw%d_p}' % (start * 32, len(data) // 32 - start, len(pieces), n))
    c.append('const Frame bowl_img[%d] = {%s};' % (len(images), ', '.join(inits)))
    c.append('const s16 bowl_logo_pos[2] = {%d, %d};' % (lx, ly))
    c.append('const s16 bowl_machine_pos[2] = {%d, %d};' % (mch[0][2], mch[0][3]))
    c.append('const s16 bowl_pins[10][2] = {%s};' % ', '.join('{%d, %d}' % p_ for p_ in bw['pins']))
    gl = bytearray()
    for g_ in fixg:
        gl += pack_tile([idx(c_) for c_ in g_])
    open(os.path.join(build, 'bowl_tiles.bin'), 'wb').write(bytes(data))
    banked.append('V:chars bowl_tiles %s' % os.path.abspath(os.path.join(build, 'bowl_tiles.bin')))
    open(os.path.join(build, 'bowl_glyphs.bin'), 'wb').write(bytes(gl))
    c = ['extern const u8 bowlshot_tiles[], bowlshot_tiles_page[], bowlshot_map[], bowlshot_pal[];',
         'const BgAsset bg_bowlshot = {bowlshot_tiles, %d, bowlshot_map, bowlshot_pal};' % (len(bank.tiles) * 32)] + c
    a = []
    for kind, path in (('bowlshot_map', 'bowlshot_map.bin'), ('bowlshot_pal', 'bowlshot_pal.bin'), ('bowl_glyphs', 'bowl_glyphs.bin')):
        a += ['    .balign 2', '    .globl %s' % kind, '%s:' % kind, '    .incbin "%s"' % os.path.abspath(os.path.join(build, path))]
    h = ['/* FLYING DISC BOWLING (make_bowl): the lane for plane B (tiles banked); sprites (palette 3 =',
         '   bowl_pal, tiles banked with char_tiles): 0 pin, 1 its shadow, 2-4 tumbling, 5 pinsetter,',
         '   6 title; glyphs (palette 3): marks (spare, strike, G, -, /, 0-9; 2 tiles each, top then',
         '   bottom) then the big digits 0-9, then the flags of the characters (4 tiles each: TL, BL, TR, BR) */',
         'extern const BgAsset bg_bowlshot;', 'extern const u8 bowlshot_tiles_page[], bowl_tiles[], bowl_glyphs[];',
         'extern const u16 bowl_pal[16];', 'extern const Frame bowl_img[];',
         'extern const s16 bowl_logo_pos[2], bowl_machine_pos[2], bowl_pins[10][2];']
    print('bowling: %d lane tiles, %d KB of sprites' % (len(bank.tiles), len(data) // 1024))
    return c, a, h

def make_menu(run, banked, srom):
    """GAME MODE SELECT: the original's screen (plane B, palettes 0/1 with 1:8-15 free) and the
    arrow and digits as plane tiles coloured with palette 1 entries 8-15."""
    import struct as _st
    from extract import convert_plane
    from mdgfx import TileBank, to_md, md_word, kmeans_colors, pack_tile
    from neogeo import ng_color, decode_fix
    build = sys.argv[3]
    rec = M.RECORDINGS['select']
    base = os.path.join(build, 'menu')
    fr = M.MENU_FRAME
    extra = []
    for b in M.MENU_BLANK:
        extra += ['-B', b]
    run('select', rec, [(fr, fr)], base, extra)
    (_, px, npal_), = list(read_frames(base + '.frames', fr, fr))
    os.remove(base + '.frames')
    img = [[ng_color(npal_[px[y * 320 + x] & 0xFFF]) if px[y * 320 + x] else ng_color(npal_[0xFFF]) for x in range(320)] for y in range(224)]
    bank = TileBank(1)
    words, cram = convert_plane(img, 0, 0, 40, 28, 2, 0, bank, ncol=M.COURT_COLORS)
    for kind, data in (('tiles', bank.data()), ('map', _st.pack('>%dH' % len(words), *words)),
                       ('pal', _st.pack('>32H', *(cram[0] + cram[1])))):
        open(os.path.join(build, 'menushot_%s.bin' % kind), 'wb').write(data)
    banked.append('V menushot_tiles %s' % os.path.abspath(os.path.join(build, 'menushot_tiles.bin')))
    codes = [M.MENU_ARROW + k for k in range(4)] + [M.MENU_DIGITS + k for k in range(40)] + \
            [M.MENU_LETTERS + k for k in range(26 * 4)] + \
            [M.MENU_DIGITS + k for k in range(40, 64)] + [M.MENU_LETTERS + k for k in range(104, 136)]   # symbols
    # the same screen with every text blanked: options, extra instruction pages
    run('select', rec, [(fr, fr)], base, ['-B', '0-39,0-31'])
    (_, px2, _), = list(read_frames(base + '.frames', fr, fr))
    os.remove(base + '.frames')
    img2 = [[ng_color(npal_[px2[y * 320 + x] & 0xFFF]) if px2[y * 320 + x] else ng_color(npal_[0xFFF]) for x in range(320)] for y in range(224)]
    bank2 = TileBank(1)
    words2, cram2 = convert_plane(img2, 0, 0, 40, 28, 1, 0, bank2, ncol=[15])   # one palette: 0
    for kind, data in (('tiles', bank2.data()), ('map', _st.pack('>%dH' % len(words2), *words2)),
                       ('pal', _st.pack('>32H', *(cram2[0] + [0] * 16)))):
        open(os.path.join(build, 'menublank_%s.bin' % kind), 'wb').write(data)
    glyphs = [[ng_color(npal_[M.MENU_FIX_PAL * 16 + v]) if v else None for v in decode_fix(srom, c)] for c in codes]
    hist = {}
    for g in glyphs:
        for c_ in g:
            if c_:
                m = to_md(c_); hist[m] = hist.get(m, 0) + 1
    cols = kmeans_colors(hist, 8)
    cols += [(0, 0, 0)] * (8 - len(cols))
    data = bytearray()
    for g in glyphs:
        data += pack_tile([0 if c_ is None else 8 + min(range(8), key=lambda i: sum((a - b) ** 2 for a, b in zip(to_md(c_), cols[i]))) for c_ in g])
    open(os.path.join(build, 'menu_glyphs.bin'), 'wb').write(bytes(data))
    c = ['extern const u8 menushot_tiles[], menushot_tiles_page[], menushot_map[], menushot_pal[];',
         'const BgAsset bg_menushot = {menushot_tiles, %d, menushot_map, menushot_pal};' % (len(bank.tiles) * 32),
         'extern const u8 menublank_tiles[], menublank_map[], menublank_pal[];',
         'const BgAsset bg_menublank = {menublank_tiles, %d, menublank_map, menublank_pal};' % (len(bank2.tiles) * 32),
         'const u16 menu_glyph_pal[8] = {%s};' % ', '.join('0x%03X' % md_word(x) for x in cols),
         # (fix rows 0-1 are above the screen)
         'const u16 menu_arrow_rows[2] = {%d, %d};' % tuple(r - 2 for r in M.MENU_ARROW_ROWS),
         'const u16 menu_arrow_col = %d, menu_timer_cell[2] = {%d, %d};' % (M.MENU_ARROW_COL, M.MENU_TIMER_CELL[0], M.MENU_TIMER_CELL[1] - 2)]
    a = []
    for kind, path in (('menushot_map', 'menushot_map.bin'), ('menushot_pal', 'menushot_pal.bin'), ('menu_glyphs', 'menu_glyphs.bin'),
                       ('menublank_tiles', 'menublank_tiles.bin'), ('menublank_map', 'menublank_map.bin'), ('menublank_pal', 'menublank_pal.bin')):
        a += ['    .balign 2', '    .globl %s' % kind, '%s:' % kind, '    .incbin "%s"' % os.path.abspath(os.path.join(build, path))]
    h = ['/* GAME MODE SELECT (make_menu): the screen for plane B (tiles banked); glyphs: arrow then digits',
         '   0-9, 4 tiles each (TL, BL, TR, BR), palette 1 entries 8-15 = menu_glyph_pal,'
         '   then the letters A-Z; bg_menublank: the screen without its texts (tiles in fixed ROM) */',
         'extern const BgAsset bg_menushot, bg_menublank;', 'extern const u8 menushot_tiles_page[], menu_glyphs[];',
         '#define MENU_GLYPHS (4 + 40 + 104 + 24 + 32)   /* + the symbols: big-font codes 0x28-0x3F, 0xA8-0xC7 */',
         'extern const u16 menu_glyph_pal[8], menu_arrow_rows[2], menu_arrow_col, menu_timer_cell[2];']
    print('menu: %d tiles, without its texts %d' % (len(bank.tiles), len(bank2.tiles)))
    return c, a, h

def make_ending(run, banked):
    """The ending picture (manifest ENDING) for plane B, palettes 0 and 1 (palette 1 entries 8-15
    left to the game font), and the staff pages' text from the fix layer."""
    import struct as _st
    from extract import convert_plane
    from mdgfx import TileBank
    from neogeo import ng_color
    en = M.ENDING
    build = sys.argv[3]
    rec = M.RECORDINGS[en['rec']]
    base = os.path.join(build, 'ending')
    fr = en['picture']
    run(en['rec'], rec, [(fr, fr)], base, ['-B', en['blank']])
    (_, px, npal_), = list(read_frames(base + '.frames', fr, fr))
    img = [[ng_color(npal_[px[y * 320 + x] & 0xFFF]) if px[y * 320 + x] else ng_color(npal_[0xFFF]) for x in range(320)] for y in range(224)]
    bank = TileBank(1)
    words, cram = convert_plane(img, 0, 0, 40, 28, 2, 0, bank, ncol=M.COURT_COLORS)
    for kind, data in (('tiles', bank.data()), ('map', _st.pack('>%dH' % len(words), *words)),
                       ('pal', _st.pack('>32H', *(cram[0] + cram[1])))):
        open(os.path.join(build, 'endshot_%s.bin' % kind), 'wb').write(data)
    banked.append('V endshot_tiles %s' % os.path.abspath(os.path.join(build, 'endshot_tiles.bin')))
    # pages: the fix layer's text rows at each page's frame
    run(en['rec'], rec, [(f, f) for f in en['pages']], base, ['-N', '-F', base + '.fix'])
    pages, cur = {}, None
    for line in open(base + '.fix'):
        if line.startswith('frame'):
            cur = int(line.split()[1]); pages[cur] = {}
            continue
        row, cells = line.split(':', 1)
        row = int(row)
        if en['rows'][0] <= row <= en['rows'][1]:
            txt = ''.join(chr(c & 0xFF) if (c & 0xF00) == 0x300 and 0x20 <= (c & 0xFF) < 0x7F else ' '
                          for c in (int(w, 16) for w in cells.split()))
            pages[cur][row] = txt.rstrip()
    os.remove(base + '.frames'); os.remove(base + '.fix')
    lines = []
    for f in en['pages']:
        for row, txt in sorted(pages.get(f, {}).items()):
            if txt.strip():
                lines.append('{%d, %d, "%s"}' % (en['pages'].index(f), row, txt.replace('\\', '\\\\').replace('"', '\\"')))
    c = ['extern const u8 endshot_tiles[], endshot_tiles_page[], endshot_map[], endshot_pal[];',
         'const BgAsset bg_endshot = {endshot_tiles, %d, endshot_map, endshot_pal};' % (len(bank.tiles) * 32),
         'const EndLine ending_lines[] = {%s, {0xFF, 0, 0}};' % ', '.join(lines)]
    a = []
    for kind in ('map', 'pal'):
        a += ['    .balign 2', '    .globl endshot_%s' % kind, 'endshot_%s:' % kind,
              '    .incbin "%s"' % os.path.abspath(os.path.join(build, 'endshot_%s.bin' % kind))]
    h = ['/* ending (make_ending): picture for plane B (tiles banked), staff pages: lines of text',
         '   (page, row, text), the list ends with page 0xFF; ENDING_PAGES pages of ENDING_PAGE_FRAMES */',
         'typedef struct { u8 page, row; const char *text; } EndLine;',
         'extern const BgAsset bg_endshot;', 'extern const u8 endshot_tiles_page[];', 'extern const EndLine ending_lines[];',
         '#define ENDING_PAGES %d' % len(en['pages']), '#define ENDING_PAGE_FRAMES %d' % en['page_frames']]
    print('ending: %d tiles, %d lines of text' % (len(bank.tiles), len(lines)))
    return c, a, h

def cut_dog_play(run, images):
    """DOG DISTANCE objects as the game draws them (manifest DOG_PLAY): for every animation frame
    (and zoom) the most complete picture seen, appended to images -> [(key, image, dx, dy)], key =
    frame << 4 | zoom, (dx, dy) from the object's anchor: the dog and the disc it holds (x, y + h / 2),
    the flying disc (x, y + 48 - 3 z / 8, z = 63 + 2 h at most 255), an obstacle (x, y). Sprites are
    drawn from the positions of the frame before and the camera of the one before that."""
    import struct as _st
    from array import array
    from PIL import Image
    from neogeo import ng_color
    dp = M.DOG_PLAY
    lut = bytes(255 if v & 15 else 0 for v in range(256))
    best = {}                                       # key -> {(w, h): (pixels, image, dx, dy)}
    def W(r, a): return _st.unpack('>H', r[a:a + 2])[0]
    def SW(r, a): return _st.unpack('>h', r[a:a + 2])[0]
    for rec, (first, last) in dp['recs'].items():
        for kind, opts in dp['passes'].items():
            if rec == 'dog' and kind not in ('dog', 'obst') or rec == 'dogpow' and kind == 'shadow':
                continue
            base = os.path.join(sys.argv[3], 'dogcut')
            run(rec, M.RECORDINGS[rec], [(first - 2, last)], base, list(opts) + ['-R', base + '.ram'])
            rams = {}
            with open(base + '.ram', 'rb') as f:
                while True:
                    h = f.read(4)
                    if not h:
                        break
                    rams[_st.unpack('<I', h)[0]] = f.read(65536)
            px = pal = None
            with open(base + '.frames', 'rb') as f:
                while True:
                    hdr = f.read(6)
                    if len(hdr) < 6:
                        break
                    fn, fl = _st.unpack('<IH', hdr)
                    if not fl & 0x4000:
                        px = f.read(320 * 224 * 2)
                    if not fl & 0x8000:
                        pal = _st.unpack('<4096H', f.read(0x2000))
                    if fn < first or fn - 2 not in rams:
                        continue
                    r, rc = rams[fn - 1], rams[fn - 2]
                    cam = W(rc, 0x2E0)
                    dog_st, holding = r[0xC02], r[0xC1A]
                    win = None
                    if kind == 'shadow':            # the dog's, on the ground under it
                        if dog_st not in (4, 8, 0xC, 0x10):
                            continue
                        key = 0xA00 << 4 | (r[0xC0E] if dog_st == 8 else 15)
                        ax, ay = W(r, 0xC06) - cam, W(r, 0xC0A)
                        win = (max(0, ax - 40), max(1, ay - 60), min(319, ax + 40), min(223, ay + 10))
                    elif kind in ('dog', 'held'):
                        if dog_st not in (4, 8, 0xC, 0x10) or (kind == 'held' and not holding):
                            continue
                        fr = W(r, 0xC04) if kind == 'dog' else W(r, 0xA04)
                        if W(rams[fn], 0xC04) != W(r, 0xC04):
                            continue                # the frame changes: positions not settled
                        key = fr << 4 | (r[0xC0E] if dog_st == 8 else 15)
                        ax, ay = W(r, 0xC06) - cam, W(r, 0xC0A) + (SW(r, 0xC20) >> 1)
                    elif kind == 'fly':
                        h = SW(r, 0xA44)
                        if not r[0xA18] & 0x80 or holding or h <= 0:
                            continue
                        e, fr = r[0xA0E], W(r, 0xA04)
                        key = fr << 4 | e
                        ax, ay = W(r, 0xA06) - cam, W(r, 0xA0A) + 48 - 3 * min(255, 63 + 2 * h) // 8
                    else:
                        if not r[0xC78] & 0x80:
                            continue
                        key = W(r, 0xC7C) << 4
                        ax, ay = W(r, 0xC7E) - cam, W(r, 0xC82)
                    mask = Image.frombytes('L', (320, 224), px[0::2]).point(lut)
                    if win:
                        if win[2] <= win[0] or win[3] <= win[1]:
                            continue
                        m2 = Image.new('L', (320, 224))
                        m2.paste(mask.crop(win), win[:2])
                        mask = m2
                    bb = mask.getbbox()
                    if not bb or bb[0] == 0 or bb[1] == 0 or bb[2] == 320 or bb[3] == 224:
                        continue
                    n = mask.histogram()[255]
                    size = (bb[2] - bb[0], bb[3] - bb[1])
                    if kind == 'fly' and size[0] > 4 * (key & 15) + 5:
                        continue                    # something else drawn with the disc's tiles
                    slot = best.setdefault(key, {})
                    if size in slot and slot[size][0] >= n:
                        slot[size] = (slot[size][0], slot[size][1], slot[size][2], slot[size][3], slot[size][4] + 1)
                        continue
                    img = []
                    for y in range(bb[1], bb[3]):
                        row = []
                        for x in range(bb[0], bb[2]):
                            v = px[2 * (y * 320 + x)] | px[2 * (y * 320 + x) + 1] << 8
                            row.append(ng_color(pal[v & 0xFFF]) if v & 15 and mask.getpixel((x, y)) else None)
                        img.append(row)
                    seen = slot[size][4] + 1 if size in slot else 1
                    slot[size] = (n, img, bb[0] - ax, bb[1] - ay, seen)
            for ext in ('.frames', '.ram', '.snd'):
                if os.path.exists(base + ext):
                    os.remove(base + ext)
    pics = []
    fly = {}                                        # flying disc: (turn, size) -> nearest zoom seen
    for key, slot in sorted(best.items()):
        # the picture of the size seen most often (others are cut short by the screen or mixed up)
        n, img, dx, dy, _ = max(slot.values(), key=lambda s: (s[4], s[0]))
        fr, e = key >> 4, key & 15
        if fr < 0x20:                               # flying disc: keep some sizes
            for size in dp['fly_sizes']:
                if size != 15 and fr & 1:
                    continue
                k = (fr, size)
                if k not in fly or abs(e - size) < abs(fly[k][0] - size):
                    fly[k] = (e, img, dx, dy)
            continue
        images.append(img)
        pics.append((key, len(images) - 1, dx, dy))
    for (fr, size), (e, img, dx, dy) in sorted(fly.items()):
        images.append(img)
        pics.append((fr << 4 | size, len(images) - 1, dx, dy))
    print('dog game as played: %d pictures' % len(pics))
    return sorted(pics)

def make_ranking(run):
    """RANKING TOP5 faces (manifest RANK_SHOTS): one 48 x 32 picture per game character id, cut
    from the ranking screens; they share palettes 2 (entries 1-7: 8-15 are the big font) and 3
    (1-7, 10-13: 8, 9, 14, 15 are the HUD font) -> (C lines, header lines, tiles)."""
    from mdgfx import to_md, md_word, pack_tile, fit_palettes, nearest
    faces = {}
    for rec, fr, ids in M.RANK_SHOTS:
        base = os.path.join(sys.argv[3], 'rankshot')
        run(rec, M.RECORDINGS[rec], [(fr, fr)], base, ['-N', '-V', base + '.vram'])
        vram, pal = read_vram(base + '.vram')
        os.remove(base + '.vram')
        for row, gid in enumerate(ids):
            y = M.RANK_ROW_Y + 32 * row
            ch = [(c[0], c[1]) for c in sprite_chains(vram) if c[2] == M.RANK_FACE_X and c[3] == y]
            if not ch:
                raise SystemExit('ranking: no face at row %d of %s %d' % (row, rec, fr))
            faces[gid] = render_chain(vram, pal, ch)[0]
    images = [faces[g] for g in range(6)]
    hists = []
    for im in images:
        h_ = {}
        for row in im:
            for c_ in row:
                if c_:
                    m = to_md(c_); h_[m] = h_.get(m, 0) + 1
        hists.append(h_)
    slots = [[1, 2, 3, 4, 5, 6, 7], [1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13]]
    pals, assign = fit_palettes(hists, 2, [7, 11])
    data, c, inits = bytearray(), [], []
    for k, im in enumerate(images):
        pl, sl = pals[assign[k]], slots[assign[k]]
        H, W = len(im), len(im[0])
        start = len(data) // 32
        pieces = []
        for bx in range(0, (W + 7) // 8, 4):
            w, h = min(4, (W + 7) // 8 - bx), (H + 7) // 8
            for tx in range(w):
                for ty in range(h):
                    data.extend(pack_tile([0 if (ty * 8 + y >= H or (bx + tx) * 8 + x >= W or not im[ty * 8 + y][(bx + tx) * 8 + x])
                                           else sl[nearest(pl, to_md(im[ty * 8 + y][(bx + tx) * 8 + x]))[0]]
                                           for y in range(8) for x in range(8)]))
            pieces.append('{%d, 0, %d, %d}' % (bx * 8, ((w - 1) << 2) | (h - 1) | 0x20 | ((2 + assign[k]) << 6),
                                               (len(data) // 32 - start) - w * h))
        c.append('static const SprPiece rf%d_p[] = {%s};' % (k, ', '.join(pieces)))
        inits.append('{rank_face_tiles + %d, %d, %d, rf%d_p}' % (start * 32, len(data) // 32 - start, len(pieces), k))
    c.append('const Frame rank_faces[6] = {%s};' % ', '.join(inits))
    words = []
    for p_, sl in zip(pals, slots):
        words.append([0] + [md_word(p_[sl.index(i)]) if i in sl and sl.index(i) < len(p_) else 0 for i in range(1, 16)])
    c.append('const u16 rank_face_pal[2][16] = {%s};' % ', '.join('{%s}' % ', '.join('0x%03X' % w for w in p_) for p_ in words))
    d = M.RANK_DEFAULT
    c.append('const u32 rank_default_score[5] = {%s};' % ', '.join(str(e[0]) for e in d))
    code = {ch: 0x40 + 4 * (ord(ch) - ord('A')) for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'}
    code['.'] = 0x34
    c.append('const u8 rank_default_name[5][4] = {%s};' % ', '.join('{%s, 0}' % ', '.join('0x%02X' % code[ch] for ch in e[1]) for e in d))
    c.append('const u8 rank_default_gid[6] = {%s};' % ', '.join(str(e[2]) for e in d))
    c.append('const u8 rank_gid_of_char[6] = {%s};' % ', '.join(str(g) for g in M.GAME_ID))
    c.append('const u8 rank_letters[%d] = {%s};' % (len(M.RANK_LETTERS), ', '.join('0x%02X' % x for x in M.RANK_LETTERS)))
    h = ['/* RANKING TOP5 (make_ranking): faces by game character id (palettes rank_face_pal, the',
         '   sprite pieces say 2 or 3), the power-on table, the name letters (big-font codes) */',
         'extern const u8 rank_face_tiles[];', 'extern const Frame rank_faces[6];', 'extern const u16 rank_face_pal[2][16];',
         'extern const u32 rank_default_score[5];', 'extern const u8 rank_default_name[5][4], rank_default_gid[6], rank_gid_of_char[6];',
         'extern const u8 rank_letters[%d];' % len(M.RANK_LETTERS), '#define RANK_LETTERS %d' % len(M.RANK_LETTERS),
         '#define RANK_BLANK 0x%02X' % M.RANK_BLANK, '#define RANK_END 0x%02X' % M.RANK_END,
         '#define RANK_FACE_X %d' % M.RANK_FACE_X, '#define RANK_ROW_Y %d' % M.RANK_ROW_Y]
    print('ranking: %d tiles of faces' % (len(data) // 32))
    return c, h, bytes(data)

def make_dog(run, match_pal, srom):
    """DOG DISTANCE sprites (manifest DOG_GAME) cut from the recording, in one sprite palette
    (palette 3: 11 fitted colours, 8/9 the HUD colours, 14 black, 15 white so the game font can be
    drawn with it). -> (C lines, tile data)."""
    import struct as _st
    from neogeo import ng_color
    from mdgfx import to_md, md_word, kmeans_colors, pack_tile
    dg = M.DOG_GAME
    first, last = dg['frames']
    base = os.path.join(sys.argv[3], 'dog')
    run(dg['rec'], M.RECORDINGS[dg['rec']], [(first, last)], base, ['-N', '-V', base + '.vram'])
    images, keys = [], {}
    def image(v, p, c):
        k = (v[c[0] * 64 + 1] >> 8, v[c[0] * 64] | ((v[c[0] * 64 + 1] << 12) & 0xF0000), c[1] - c[0])
        if k not in keys:
            keys[k] = len(images)
            images.append(render_chain(v, p, [(c[0], c[1])])[0])
        return keys[k]
    def pal_tile(v, c):
        return v[c[0] * 64 + 1] >> 8, v[c[0] * 64] | ((v[c[0] * 64 + 1] << 12) & 0xF0000)
    seqs = {'wag': [], 'girl': []}
    singles = {}
    want = {('roll', t): None for t in dg['roll']}
    want.update({('flag', t): None for t in dg['flags']})
    with open(base + '.vram', 'rb') as f:
        while True:
            h = f.read(4)
            if len(h) < 4:
                break
            fn = _st.unpack('<I', h)[0]
            v = _st.unpack('<%dH' % 0x8800, f.read(0x8800 * 2)); p = _st.unpack('<%dH' % 0x1000, f.read(0x2000))
            chains = sprite_chains(v)
            for c in chains:
                pl, t = pal_tile(v, c)
                a_, b_ = dg['wag']
                if a_ <= fn <= b_ and pl == dg['dog']:
                    seqs['wag'].append((image(v, p, c), c[2], c[3]))
                if dg['girl'][1] <= fn <= dg['girl'][2] and pl == dg['girl'][0] and len(seqs['girl']) <= fn - dg['girl'][1]:
                    seqs['girl'].append((image(v, p, c), c[2], c[3]))
                if pl == dg['disc'] and ('roll', t) in want and want[('roll', t)] is None:
                    want[('roll', t)] = image(v, p, c)
                if pl == dg['flag'] and ('flag', t) in want and want[('flag', t)] is None:
                    want[('flag', t)] = image(v, p, c)
                if pl == dg['disc'] and t == dg['shadow_tile'] and 'dshadow' not in singles:
                    singles['dshadow'] = (image(v, p, c), c[2], c[3])
                if (pl, t) == dg['shadow'] and 'shadow' not in singles:
                    singles['shadow'] = (image(v, p, c), c[2], c[3])
                if fn == dg['pole'][1] and pl == dg['pole'][0]:
                    singles['pole'] = (image(v, p, c), c[2], c[3])
            if fn == dg['logo'][1]:                 # the DOG DISTANCE title: all its chains in one image
                rng = [(c[0], c[1]) for c in chains if pal_tile(v, c)[0] == dg['logo'][0]]
                img, x0, y0 = render_chain(v, p, rng)
                images.append(img)
                singles['logo'] = (len(images) - 1, x0, y0)
    os.remove(base + '.vram')
    pics = cut_dog_play(run, images)
    glyphs = hud_glyphs(srom, match_pal)
    missing = [k for k, i in want.items() if i is None]
    if missing or any(not v_ for v_ in seqs.values()):
        raise SystemExit('dog game: sprites not found: %s %s' % (missing, [k for k, v_ in seqs.items() if not v_]))
    # one palette for all of them
    hist = {}
    for im in images:
        for row in im:
            for c_ in row:
                if c_:
                    m = to_md(c_); hist[m] = hist.get(m, 0) + 1
    for g_ in glyphs:                       # the HUD's flags and timer digits (weighed: small but seen)
        for c_ in g_:
            if c_:
                m = to_md(c_); hist[m] = hist.get(m, 0) + 8
    hud = [to_md(ng_color(match_pal[M.HUD_COLOR_ENTRIES[0]])), to_md(ng_color(match_pal[M.HUD_COLOR_ENTRIES[1]]))]
    fixed = {8: hud[0], 9: hud[1], 14: (0, 0, 0), 15: (7, 7, 7)}
    rest = {c_: n for c_, n in hist.items() if min(sum((a - b) ** 2 for a, b in zip(c_, q)) for q in fixed.values()) > 1}
    free = [i for i in range(1, 16) if i not in fixed]
    cols = kmeans_colors(rest, len(free))
    slots = dict(fixed); slots.update({free[i]: cols[i] for i in range(len(cols))})
    pal = [0] * 16
    for k, c_ in slots.items():
        pal[k] = md_word(c_)
    def idx(c_):
        if c_ is None:
            return 0
        m = to_md(c_)
        return min(slots, key=lambda k: sum((a - b) ** 2 for a, b in zip(m, slots[k])))
    data, c = bytearray(), ['const u16 dog_pal[16] = {%s};' % ', '.join('0x%03X' % w for w in pal)]
    inits = []
    for n, im in enumerate(images):
        H, W = len(im), len(im[0])
        th, tw = (H + 7) // 8, (W + 7) // 8
        def px(x, y):
            return im[y][x] if y < H and x < W else None
        pieces, start = [], len(data) // 32
        tile = {(tx, ty): [idx(px(tx * 8 + x, ty * 8 + y)) for y in range(8) for x in range(8)]
                for tx in range(tw) for ty in range(th)}
        for bx in range(0, tw, 4):                  # 4-tile wide bands, empty tiles left out where possible
            cols = range(bx, min(bx + 4, tw))
            rows = [ty for ty in range(th) if any(any(tile[(tx, ty)]) for tx in cols)]
            while rows:
                run_ = [rows[0]]
                while len(run_) < 4 and len(rows) > len(run_) and rows[len(run_)] == run_[-1] + 1:
                    run_.append(rows[len(run_)])
                rows = rows[len(run_):]
                used = [tx for tx in cols if any(any(tile[(tx, ty)]) for ty in run_)]
                c0, c1 = used[0], used[-1]
                t0 = len(data) // 32 - start
                for tx in range(c0, c1 + 1):
                    for ty in run_:
                        data.extend(pack_tile(tile[(tx, ty)]))
                pieces.append('{%d, %d, %d, %d}' % (c0 * 8, run_[0] * 8, ((c1 - c0) << 2) | (len(run_) - 1), t0))
        c.append('static const SprPiece dg%d_p[] = {%s};' % (n, ', '.join(pieces)))
        inits.append('{dog_tiles + %d, %d, %d, dg%d_p}' % (start * 32, len(data) // 32 - start, len(pieces), n))
    c.append('const Frame dog_img[%d] = {%s};' % (len(images), ', '.join(inits)))
    c.append('const u16 dog_hud_at = %d;' % (len(data) // 32))
    for g_ in glyphs:
        data.extend(pack_tile([idx(c_) for c_ in g_]))
    c.append('const DogPic dog_pics[%d] = {%s};' % (len(pics), ', '.join('{0x%04X, %d, %d, %d}' % p_ for p_ in pics)))
    for name, sq in seqs.items():
        c.append('const s16 dog_%s[%d][3] = {%s};' % (name, len(sq), ', '.join('{%d, %d, %d}' % e for e in sq)))
    c.append('const u16 dog_roll[8] = {%s};' % ', '.join(str(want[('roll', t)]) for t in dg['roll']))
    c.append('const u16 dog_flag[%d] = {%s};' % (len(dg['flags']), ', '.join(str(want[('flag', t)]) for t in dg['flags'])))
    for name in ('dshadow', 'shadow', 'pole', 'logo'):
        c.append('const s16 dog_%s[3] = {%d, %d, %d};' % ((name,) + tuple(singles[name])))
    h = ['/* DOG DISTANCE (make_dog): sprites with palette 3 = dog_pal; tiles banked with char_tiles;',
         '   sequences [n][3] = image, x, y (one entry per frame); singles = image, x, y */',
         'extern const u8 dog_tiles[];', 'extern const u16 dog_pal[16];', 'extern const Frame dog_img[];',
         '/* as played: picture of an animation frame (key = frame << 4 | zoom) at (dx, dy) from its anchor */',
         'typedef struct { u16 key, img; s16 dx, dy; } DogPic;',
         'extern const DogPic dog_pics[%d];' % len(pics), '#define DOG_PICS %d' % len(pics),
         'extern const s16 dog_wag[%d][3], dog_girl[%d][3];' % tuple(len(seqs[k]) for k in ('wag', 'girl')),
         '#define DOG_WAG %d' % len(seqs['wag']), '#define DOG_GIRL %d' % len(seqs['girl']),
         'extern const u16 dog_roll[8], dog_flag[%d];' % len(dg['flags']),
         '#define DOG_FLAGS %d' % len(dg['flags']),
         'extern const s16 dog_dshadow[3], dog_shadow[3], dog_pole[3], dog_logo[3];',
         '/* dog_tiles + 32 * dog_hud_at: the HUD glyphs (each character\'s flag, the timer digits 0-9; 4 tiles each) */',
         'extern const u16 dog_hud_at;']
    print('dog game: %d images, %d KB of tiles' % (len(images), len(data) // 1024))
    return c, h, bytes(data)

def make_result(shots, pal):
    """Match result overlay (manifest RESULT_*): per layout one plane A image of the portrait
    frames and texts, plus SET COUNTS sprites, all with 4 colours fitted to them."""
    from mdgfx import md_word, pack_tile
    parts = {k: chain_image(shots[shot], x, y, pl, 'result ' + k) for k, (shot, (x, y, pl)) in M.RESULT_PARTS.items()}
    ox, oy = M.RESULT_ORIGIN
    W, H = M.RESULT_SIZE
    shot, (x, y, pl) = M.SET_COUNTS['label']
    label = chain_image(shots[shot], x, y, pl, 'result counts label')
    images = []
    for name, (frames, texts) in M.RESULT_LAYOUTS.items():
        canvas = [[None] * W for _ in range(H)]
        items = [(parts['frame_l'], frames[0]), (parts['frame_r'], frames[1])] + \
                [(parts[t], M.RESULT_PARTS[t][1][:2]) for t in texts] + \
                [(label, M.SET_COUNTS['label'][1][:2])]     # SET COUNTS: on the plane, not a sprite
        for img, (x, y) in items:
            for yy, row in enumerate(img):
                for xx, c_ in enumerate(row):
                    if c_ and 0 <= y - oy + yy < H and 0 <= x - ox + xx < W:
                        canvas[y - oy + yy][x - ox + xx] = c_
        images.append(('rs_' + name, canvas))
    counts = [('d%d' % d, v) for d, v in sorted(M.SET_COUNTS['digits'].items())]
    count_imgs = [(k, chain_image(shots[shot], x, y, pl, 'result counts')) for k, (shot, (x, y, pl)) in counts]
    data = bytearray()
    cols, made = fitted_parts(images + [('rs_counts_' + k, img) for k, img in count_imgs], pal, data, 'result_tiles')
    c = ['const u16 result_pal[4] = {%s};' % ', '.join('0x%03X' % md_word(x) for x in cols)]
    for name, init, mp in made[:len(images)]:
        c += [mp, 'const BannerPart %s = %s;' % (name.replace('rs_', 'result_'), init)]
    _, idx = fit4([img for _, img in images] + [img for _, img in count_imgs], pal)
    for k, img in count_imgs:                   # sprites (32 px pieces), like the banner's
        h, w = len(img) // 8, len(img[0]) // 8
        pieces, start = [], len(data) // 32
        for bx in range(0, w, 4):
            pw = min(4, w - bx)
            t0 = len(data) // 32 - start
            for tx in range(pw):
                for ty in range(h):
                    data.extend(pack_tile([idx(img[ty * 8 + y][(bx + tx) * 8 + x]) for y in range(8) for x in range(8)]))
            pieces.append('{%d, 0, %d, %d}' % (bx * 8, ((pw - 1) << 2) | (h - 1), t0))
        c.append('static const SprPiece rs_counts_%s_p[] = {%s};' % (k, ', '.join(pieces)))
        c.append('const Frame result_counts_%s = {result_tiles + %d, %d, %d, rs_counts_%s_p};' % (k, start * 32, len(data) // 32 - start, len(pieces), k))
    c.append('const s16 result_frame_pos[3][2][2] = {%s};' % ', '.join(
        '{{%d, %d}, {%d, %d}}' % (f[0][0], f[0][1], f[1][0], f[1][1]) for f, _ in M.RESULT_LAYOUTS.values()))
    c.append('const s16 result_portrait_offset[2][2] = {{%d, %d}, {%d, %d}};' % tuple(v for o in M.RESULT_PORTRAIT_OFFSET for v in o))
    print('result overlay: %s' % ', '.join('%s %d tiles' % (n, int(i.split(', ')[1])) for n, i, _ in made[:len(images)]))
    return c, bytes(data)

def make_setstart(shots):
    """Set start overlays (manifest SET_START), one palette per group: plane A parts."""
    from mdgfx import md_word
    data = bytearray()
    c, names, pals = [], [], []
    for group, (shot, parts) in M.SET_START.items():
        images = [('ss_' + key, chain_image(shots[shot], x, y, pl, 'set start ' + key)) for key, (x, y, pl) in parts.items()]
        cols, made = fitted_parts(images, shots[shot][1], data, 'setstart_tiles')
        pals.append('{%s}' % ', '.join('0x%03X' % md_word(x) for x in cols))
        for (name, init, mp), (key, (x, y, _)) in zip(made, parts.items()):
            c.append(mp)
            c.append('const BannerPart setstart_%s = %s;' % (key, init))
            c.append('const u16 setstart_%s_pos[2] = {%d, %d};' % (key, x // 8, y // 8))
            names.append(key)
    # 1P: ROUND r / SET s panel from the C ROM (manifest ROUND_PANEL), with its own goal markers
    # and rules line (the same as set 1's, in this group's colours)
    from neogeo import ng_color
    rp = M.ROUND_PANEL
    shot = shots[rp['shot']]
    def panel(r, s_):
        cols = [[rp['base'] + 7 * k + row for row in range(7)] for k in rp['cols']]
        if (r, s_) != (1, 1):
            t = rp['triples'] + 21 * rp['triple_index'][(r, s_)]
            cols[7:] = [[t + 7 * k + row for row in range(7)] for k in (2, 1, 0)]
        img = [[None] * (16 * len(cols)) for _ in range(112)]
        for cx, col in enumerate(cols):
            for row, code in enumerate(col):
                px = _game.tile(code)
                for yy in range(16):
                    for xx in range(16):
                        if px[yy * 16 + xx]:
                            img[row * 16 + yy][cx * 16 + xx] = ng_color(shot[1][rp['pal'] * 16 + px[yy * 16 + xx]])
        return img
    px, py = rp['pos']
    parts = [('round_words', [row[:112] for row in panel(1, 1)], (px, py))]
    parts += [('round_r%d' % r, [row[112:] for row in panel(r, 1 if r > 1 else 1)[:56]], (px + 112, py)) for r in range(1, 7)]
    parts += [('round_s%d' % s_, [row[112:] for row in panel(1, s_)[56:]], (px + 112, py + 56)) for s_ in range(1, 4)]
    x, y, pl = rp['rules']
    parts.append(('round_rules', chain_image(shot, x, y, pl, 'round rules'), (x, y)))
    for key in ('l3', 'l5', 'r3', 'r5'):
        x, y, pl = M.SET_START['set1'][1][key]
        parts.append(('round_m' + key, chain_image(shot, x, y, pl, 'round ' + key), (x, y)))
    cols, made = fitted_parts([('ss_' + k, img) for k, img, _ in parts], shot[1], data, 'setstart_tiles')
    pals.append('{%s}' % ', '.join('0x%03X' % md_word(x) for x in cols))
    for (name, init, mp), (key, _, (x, y)) in zip(made, parts):
        c.append(mp)
        c.append('const BannerPart setstart_%s = %s;' % (key, init))
        c.append('const u16 setstart_%s_pos[2] = {%d, %d};' % (key, x // 8, y // 8))
        names.append(key)
    c.insert(0, 'const u16 setstart_pal[%d][4] = {%s};' % (len(pals), ', '.join(pals)))
    print('set start overlay: %s, %d tiles' % (', '.join(names), len(data) // 32))
    return c, bytes(data), names

def make_banner(pal, shots):
    """Score banner pieces from the game's tiles, coloured with palette 1: entries 10-13 get 4
    colours fitted to the banner (the disc is not in play while it shows), plus 8, 9, 14, 15."""
    from neogeo import ng_color
    from mdgfx import to_md, md_word, kmeans_colors, pack_tile
    def column(tiles, palno):
        rows = []
        for t in tiles:
            px = _game.tile(t)
            for y in range(16):
                rows.append([ng_color(pal[palno * 16 + px[y * 16 + x]]) if px[y * 16 + x] else None for x in range(16)])
        return rows
    parts = {'bar': [column([t + k for k in range(4)], M.BANNER_PAL) for t in M.BANNER_BAR]}
    parts['digits'] = [[column([M.BANNER_DIGIT + 5 + 10 * d + k for k in range(5)], M.BANNER_PAL),
                        column([M.BANNER_DIGIT + 10 * d + k for k in range(5)], M.BANNER_PAL)] for d in range(10)]
    parts['ribbons'] = [[column([b - 3 * k + j for j in range(3)], 0x19) for k in range(4)] for b in M.GOAL_RIBBONS]
    shot, (x, y, pl) = M.SET_COUNTS['label']
    counts = {'label': chain_image(shots[shot], x, y, pl, 'set counts')}
    for d, (shot, (x, y, pl)) in sorted(M.SET_COUNTS['digits'].items()):
        counts['d%d' % d] = chain_image(shots[shot], x, y, pl, 'set count %d' % d)
    hist = {}
    def count(col):
        for row in col:
            for c_ in row:
                if c_:
                    m = to_md(c_); hist[m] = hist.get(m, 0) + 1
    for col in parts['bar'] + [c_ for r in parts['ribbons'] for c_ in r] + [c_ for d in parts['digits'] for c_ in d]:
        count(col)
    for img in counts.values():
        count(img)
    hud = [to_md(ng_color(pal[M.HUD_COLOR_ENTRIES[0]])), to_md(ng_color(pal[M.HUD_COLOR_ENTRIES[1]]))]
    fixed = {8: hud[0], 9: hud[1], 14: (0, 0, 0), 15: (7, 7, 7)}
    rest = {c_: n for c_, n in hist.items() if min(sum((a - b) ** 2 for a, b in zip(c_, q)) for q in fixed.values()) > 1}
    cols = kmeans_colors(rest, 4) if rest else []
    cols += [(0, 0, 0)] * (4 - len(cols))
    slots = dict(fixed); slots.update({10 + i: cols[i] for i in range(4)})
    def idx(c_):
        if c_ is None:
            return 0
        m = to_md(c_)
        return min(slots, key=lambda k: sum((a - b) ** 2 for a, b in zip(m, slots[k])))
    def image(cols):            # side by side 16 px columns -> rows
        return [sum((col[y] for col in cols), []) for y in range(len(cols[0]))]
    from mdgfx import TileBank
    data = bytearray()
    c = ['const u16 banner_pal[4] = {%s};' % ', '.join('0x%03X' % md_word(x) for x in cols)]
    def plane(name, img):
        """-> C initializer of a BannerPart: its own tiles (deduplicated) and a cell map."""
        H, W = len(img), len(img[0])
        bank = TileBank(0)
        cells = []
        for cy in range(H // 8):
            for cx in range(W // 8):
                px = [idx(img[cy * 8 + y][cx * 8 + x]) for y in range(8) for x in range(8)]
                if not any(px):
                    cells.append(0xFFFF); continue
                t, flip = bank.add(px)
                cells.append((flip << 11) | t)
        start = len(data) // 32
        data.extend(bank.data())
        c.append('static const u16 %s_map[] = {%s};' % (name, ', '.join('0x%04X' % w for w in cells)))
        return '{banner_tiles + %d, %d, %d, %d, %s_map}' % (start * 32, len(bank.tiles), W // 8, H // 8, name)
    c.append('const BannerPart banner_bar = %s;' % plane('bn_bar', image(parts['bar'])))
    # set end: the rows under y = 120 (cells 7-32, rows 15-19) are composed on plane A at run
    # time from the bar, the score digits' bottoms and, in front, SET COUNTS and the sets (as
    # sprites they would take most of the 320 sprite pixels of those lines from the players)
    OX, OY, OW, OH = 56, 120, 208, 40
    lx, ly = M.SET_COUNTS['label'][1][:2]
    def overlay(img, x, y, x0, w):
        cv = [[None] * w for _ in range(OH)]
        for yy, row in enumerate(img):
            for xx, c_ in enumerate(row):
                if c_ and 0 <= y - OY + yy < OH and 0 <= x - x0 + xx < w:
                    cv[y - OY + yy][x - x0 + xx] = c_
        return cv
    c.append('const BannerPart banner_ovl_label = %s;' % plane('bn_ovl', overlay(counts['label'], lx, ly, OX, OW)))
    dparts = [plane('bn_ocd%d%d' % (side, d), overlay(counts['d%d' % d], dx, ly, dx, 48))
              for side, dx in ((0, 56), (1, 216)) for d in range(4)]
    c.append('const BannerPart banner_ovl_sets[2][4] = {{%s}, {%s}};' % (', '.join(dparts[:4]), ', '.join(dparts[4:])))
    bottoms = [plane('bn_db%d' % d, image(parts['digits'][d])[48:80]) for d in range(10)]
    c.append('const BannerPart banner_digit_bottom[10] = {%s};' % ', '.join(bottoms))
    def frame(name, img):
        H, W = len(img), len(img[0])
        pieces, start = [], len(data) // 32
        for by in range(0, (H + 7) // 8, 4):
            for bx in range(0, (W + 7) // 8, 4):
                w, h = min(4, (W + 7) // 8 - bx), min(4, (H + 7) // 8 - by)
                t0 = len(data) // 32 - start
                for tx in range(w):
                    for ty in range(h):
                        data.extend(pack_tile([idx(img[(by + ty) * 8 + y][(bx + tx) * 8 + x]) for y in range(8) for x in range(8)]))
                pieces.append('{%d, %d, %d, %d}' % (bx * 8, by * 8, ((w - 1) << 2) | (h - 1), t0))
        c.append('static const SprPiece %s_p[] = {%s};' % (name, ', '.join(pieces)))
        return '{banner_tiles + %d, %d, %d, %s_p}' % (start * 32, len(data) // 32 - start, len(pieces), name)
    c.append('const Frame banner_digits[10] = {%s};' % ', '.join(
        frame('bn_d%d' % d, image(parts['digits'][d])) for d in range(10)))
    c.append('const Frame banner_digits_top[10] = {%s};' % ', '.join(        # down to y = 120
        frame('bn_dt%d' % d, image(parts['digits'][d])[:48]) for d in range(10)))
    c.append('const Frame banner_ribbons[4] = {%s};' % ', '.join(
        frame('bn_rb%d' % k, image(parts['ribbons'][k])) for k in range(4)))
    return c, bytes(data)

def make_supers(run):
    """Per character super shot: run the recorded game over the shot, read the disc position from
    RAM each frame and render only the effect sprites; keep the effects in a box around the disc."""
    import struct as _st
    from mdgfx import to_md, md_word, kmeans_colors, pack_tile
    from neogeo import ng_color
    build = sys.argv[3]
    rec = M.RECORDINGS['play']
    x0, y0, x1, y1 = M.SUPER_FX_BOX
    c, data, counts = [], bytearray(), []
    for ci in range(6):
        start, side = M.SUPER_SHOTS[ci]
        base = os.path.join(build, 'super%d' % ci)
        run('play', rec, [(start, start + 120)], base, ['-O', M.SUPER_FX_PALETTES, '-R', base + '.ram'])
        ram = {}
        with open(base + '.ram', 'rb') as f:
            while True:
                h = f.read(4)
                if not h:
                    break
                fn = _st.unpack('<I', h)[0]; r = f.read(0x10000)
                W = lambda a_: (r[a_] << 8) | r[a_ + 1]
                sx = lambda v: v - (1 << 32) if v & 0x80000000 else v
                ram[fn] = (sx((W(0xA06) << 16) | W(0xA08)) / 65536, sx((W(0xA0A) << 16) | W(0xA0C)) / 65536, W(0xA22))
        state = ram[start][2]
        frames = []
        for fn, px, pal in read_frames(base + '.frames', start, start + 120):
            dx, dy, st = ram[fn]
            if st != state:
                break
            box = []
            for yy in range(y0, y1):
                row = []
                for xx in range(x0, x1):
                    X, Y = int(dx) + xx, int(dy) + yy
                    v = px[Y * 320 + X] if 0 <= X < 320 and 0 <= Y < 224 else 0
                    row.append(ng_color(pal[v & 0xFFF]) if v else None)
                box.append(row)
            frames.append((dx, dy, box))
        os.remove(base + '.ram'); os.remove(base + '.frames')
        # path: whole-pixel steps, mirrored to a throw to the right
        path, px_, py_ = [], frames[0][0], frames[0][1]
        for dx, dy, _ in frames[1:]:
            sx_, sy_ = int(round(dx - px_)), int(round(dy - py_))
            path += [-sx_ if side else sx_, sy_]
            px_ += sx_; py_ += sy_
        # 4 colours for the effects, then each box -> MD sprite pieces (4x4 tile blocks)
        hist = {}
        for _, _, box in frames:
            for row in box:
                for col in row:
                    if col:
                        m = to_md(col); hist[m] = hist.get(m, 0) + 1
        cols = kmeans_colors(hist, 4) if hist else [(7, 7, 7)]
        cols += [(0, 0, 0)] * (4 - len(cols))
        slots = {10 + i: cols[i] for i in range(4)}
        slots.update({14: (0, 0, 0), 15: (7, 7, 7)})
        def idx(col):
            if col is None:
                return 0
            m = to_md(col)
            return min(slots, key=lambda k: sum((a_ - b_) ** 2 for a_, b_ in zip(m, slots[k])))
        uniq, seq = {}, []
        for _, _, box in frames:
            if side:
                box = [row[::-1] for row in box]
            key = tuple(idx(v) for row in box for v in row)
            if key not in uniq:
                uniq[key] = len(uniq)
            seq.append(uniq[key])
        W_, H_ = x1 - x0, y1 - y0
        fr_c = []
        for key, k in sorted(uniq.items(), key=lambda kv: kv[1]):
            pieces, start_t = [], len(data) // 32
            for by in range(0, H_ // 8, 4):
                for bx in range(0, W_ // 8, 4):
                    blk = [[key[(by * 8 + y) * W_ + bx * 8 + x] for x in range(32)] for y in range(32)]
                    if not any(v for row in blk for v in row):
                        continue
                    t0 = len(data) // 32 - start_t
                    for tx in range(4):
                        for ty in range(4):
                            data += pack_tile([blk[ty * 8 + y][tx * 8 + x] for y in range(8) for x in range(8)])
                    pieces.append('{%d, %d, %d, %d}' % (x0 + bx * 8, y0 + by * 8, (3 << 2) | 3, t0))
            ntiles = len(data) // 32 - start_t
            c.append('static const SprPiece sfx%d_%d_p[] = {%s};' % (ci, k, ', '.join(pieces) or '{0, 0, 0, 0}'))
            fr_c.append('{super_tiles + %d, %d, %d, sfx%d_%d_p}' % (start_t * 32, ntiles, len(pieces), ci, k))
        c.append('static const Frame sfx%d_frames[] = {%s};' % (ci, ', '.join(fr_c)))
        c.append('static const s8 sp%d_path[] = {%s};' % (ci, ', '.join(map(str, path))))
        c.append('static const u8 sp%d_fx[] = {%s};' % (ci, ', '.join(map(str, seq))))
        c.append('static const u16 sp%d_pal[4] = {%s};' % (ci, ', '.join('0x%03X' % md_word(col) for col in cols)))
        counts.append(len(frames))
        print('super %d: %d frames, %d effect frames, %d KB' % (ci, len(frames), len(uniq), len(data) // 1024))
    c.append('const SuperShot super_shots[6] = {%s};' % ', '.join(
        '{%d, sp%d_path, sp%d_fx, sfx%d_frames, sp%d_pal}' % (counts[i], i, i, i, i) for i in range(6)))
    return c, bytes(data)

def main():
    rom, bios, build = sys.argv[1:4]
    rs, bs = RomSet(rom), RomSet(bios)
    global _game
    from extract import Game
    _game = Game(rom)
    def get(key):
        if key in M.FILES:
            return rs.get(*M.FILES[key])
        crc, names = M.BIOS_FILES[key]
        try:
            return bs.get(crc, names)
        except FileNotFoundError:
            return rs.get(crc, names)
    romdir = os.path.join(build, 'ngrom')
    os.makedirs(romdir, exist_ok=True)
    paths = {}
    for key in ['p1', 'm1', 'c1', 'c2', 'c3', 'c4', 's1', 'bios', 'sfix', 'lo']:
        paths[key] = os.path.join(romdir, key + '.bin')
        data = get(key)
        if not os.path.exists(paths[key]) or os.path.getsize(paths[key]) != len(data):
            open(paths[key], 'wb').write(data)
    ngrec = os.path.join(build, 'ngrec')

    def run(name, rec, ranges, out, extra=()):
        inp = os.path.join(build, 'rec_%s_inputs.txt' % name)
        open(inp, 'w').write('\n'.join(rec['inputs']) + '\n')
        cmd = [ngrec, '-p', paths['p1'], '-b', paths['bios'], '-m', paths['m1'],
               '-c', paths['c1'], '-c', paths['c2'], '-c', paths['c3'], '-c', paths['c4'],
               '-s', paths['s1'], '-S', paths['sfix'], '-l', paths['lo'],
               '-o', out, '-n', str(rec['frames']), '-i', inp]
        for t in M.TEXT_SUBST:
            cmd += ['-X', t]
        for a, b in ranges:
            cmd += ['-r', '%d-%d' % (a, b)]
        for p_ in rec.get('pokes', []):
            cmd += ['-M', p_]
        cmd += rec.get('extra', [])
        subprocess.run(cmd + list(extra), check=True)

    music, sfx = [], []                 # sound tables referenced by the movies' events
    def sound_id(cmd):
        name = M.MOVIE_SOUND.get(cmd)
        if name is None:
            for n, code in M.MUSIC.items():
                if normalize(tuple(code[0])) == normalize(cmd):
                    name = n
            for n, code in M.SAMPLE_SFX.items():
                if tuple(code) == cmd:
                    name = n
        if name is None:
            return None
        if name == 'stop':
            return 0xFFFF
        if name in M.MUSIC:
            if name not in music:
                music.append(name)
            return 0x8000 | music.index(name)
        if name not in sfx:
            sfx.append(name)
        return sfx.index(name)

    banked, header, total = [], [], 0
    frames_c, label_decls, pal_decls, screen_cram = [], [], [], {}
    for rname, rec in M.RECORDINGS.items():
        movies = {n: m for n, m in M.MOVIES.items() if m['rec'] == rname}
        if not movies:
            continue
        base = os.path.join(build, 'rec_' + rname)
        run(rname, rec, [(0, -1)], base + '_log')
        cmds = parse_commands(base + '_log.snd')
        spans = {n: (marker_frame(cmds, m['start']), marker_frame(cmds, m['end'])) for n, m in movies.items()}
        run(rname, rec, sorted(spans.values()), base)
        for name, (first, last) in sorted(spans.items(), key=lambda kv: kv[1]):
            m = movies[name]
            step = m.get('opts', {}).get('step', 1)
            events = {}
            for fr, c in cmds:
                if first <= fr <= last:
                    sid = sound_id(normalize(c))
                    if sid is not None:
                        events.setdefault((fr - first) // step, []).append(sid)
            mv = Movie(read_frames(base + '.frames', first, last), **m.get('opts', {}))
            loop = m.get('loop')
            blob, st = mv.encode(sound=events, loop_from=None if loop is None else (loop - first) // step)
            for lname, ranges in m.get('labels', {}).items():
                vals = []
                for i in mv.out_src:
                    fr = first + i * step
                    vals.append(next((v for (a, b), v in ranges.items() if a <= fr <= b), 0xFF))
                frames_c.append('const u8 %s_%s[%d] = {%s};' % (name, lname, len(vals), ', '.join(map(str, vals))))
                label_decls.append('extern const u8 %s_%s[];' % (name, lname))
            path = os.path.join(build, name + '.bin')
            open(path, 'wb').write(blob)
            banked.append('V %s_data %s' % (name, path))
            total += len(blob)
            print('%s: frames %d-%d, %d KB, %s' % (name, first, last, len(blob) // 1024, st))
            header.append(name)
        os.remove(base + '.frames')
        if rname == M.BONUS_DEMO['rec']:
            bonus_c, bonus_blob = make_bonus(run, cmds, sound_id, build)
    # ---- still screens with sprite elements cut from the same recorded frame
    sprite_names, tiles_all = [], bytearray()
    for name, sc in M.SCREEN_SHOTS.items():
        rec = M.RECORDINGS[sc['rec']]
        base = os.path.join(build, 'shot_' + name)
        fr = sc['frame']
        run(sc['rec'], rec, [(fr, fr)], base, ['-N', '-V', base + '.vram'])
        vram, pal = read_vram(base + '.vram')
        chains = sprite_chains(vram)
        def resolve(sel):
            if isinstance(sel, tuple):
                return [sel]
            x0, y0, x1, y1 = sel['rect']
            return [(c[0], c[1]) for c in chains if x0 <= c[2] < x1 and y0 <= c[3] < y1]
        extra = []
        for sel in sc.get('hide', []):
            for a_, b_ in (resolve(sel) if not isinstance(sel, str) else [tuple(map(int, sel.split('-')))]):
                extra += ['-H', '%d-%d' % (a_, b_)]
        for t in sc.get('subst', []):
            extra += ['-X', t]
        for t in sc.get('blank_fix', []):
            extra += ['-B', t]
        cram = None
        if sc.get('image', True):
            run(sc['rec'], rec, [(fr, fr)], base, extra)
            mv = Movie(read_frames(base + '.frames', fr, fr), npal=sc.get('npal', 4))
            blob, st = mv.encode()
            path = os.path.join(build, name + '.bin')
            open(path, 'wb').write(blob)
            banked.append('V %s_data %s' % (name, path))
            header.append(name)
            total += len(blob)
            cram = [w for p in mv.cram(0) for w in p]
            os.remove(base + '.frames')
        elif sc.get('cram_from'):
            cram = screen_cram[sc['cram_from']]
        screen_cram[name] = cram
        for sname, spec in sc.get('sprites', {}).items():
            sel, own = (spec, None) if not isinstance(spec, dict) or 'rect' in spec else (spec['sel'], spec.get('own_palette'))
            if isinstance(spec, dict) and 'sel' in spec:
                sel, own = spec['sel'], spec.get('own_palette')
            ranges = resolve(sel)
            if not ranges:
                raise SystemExit('%s: no sprites for %s' % (name, sname))
            img, x0, y0 = render_chain(vram, pal, ranges)
            pals = cram
            if own is not None:
                own_words = fit_palette(img)
                pals = [0] * 64
                pals[own * 16:own * 16 + 16] = own_words
                frames_c.append('const u16 %s_pal[16] = {%s};' % (sname, ', '.join('0x%03X' % w for w in own_words)))
                pal_decls.append('extern const u16 %s_pal[16];' % sname)
            data, pieces = sprite_frame(img, pals, only=own)
            frames_c.append('static const SprPiece %s_p[] = {%s};' % (sname, ', '.join(
                '{%d, %d, %d, %d}' % pc for pc in pieces)))
            frames_c.append('const Frame %s = {screen_sprite_tiles + %d, %d, %d, %s_p};' % (
                sname, len(tiles_all), len(data) // 32, len(pieces), sname))
            frames_c.append('const s16 %s_pos[2] = {%d, %d};' % (sname, x0, y0))
            sprite_names.append(sname)
            tiles_all += data
        print('%s: frame %d, sprites %s' % (name, fr, ', '.join(sc.get('sprites', {}))))
        os.remove(base + '.vram')
    open(os.path.join(build, 'screen_sprites.bin'), 'wb').write(bytes(tiles_all) or bytes(32))

    # ---- courts as they look in a match (all their sprite layers), minus players, disc, shadows
    # and the scoreboard digits; converted for plane B with palettes 0 and 1 (tools/extract.py)
    import struct as _st
    from extract import convert_plane
    from mdgfx import TileBank
    from neogeo import ng_color
    court_c, court_a, fence_c, fence_tab = [], [], [], []
    from mdgfx import to_md
    for ci in range(len(M.COURT_LIST_ROW)):
        rname = 'court%d' % ci
        rec = M.RECORDINGS[rname]
        base = os.path.join(build, 'shot_' + rname)
        fr = M.COURT_FRAME
        run(rname, rec, [(fr, fr)], base, ['-N', '-V', base + '.vram'])
        vram, pal = read_vram(base + '.vram')
        extra = ['-B', M.COURT_BLANK_FIX]
        for a_, b_, x_, y_ in sprite_chains(vram):
            pl, t = vram[a_ * 64 + 1] >> 8, vram[a_ * 64] | ((vram[a_ * 64 + 1] << 12) & 0xF0000)
            if any(lo <= pl <= hi for lo, hi in M.COURT_HIDE_PALETTES) or any(lo <= t <= hi for lo, hi in M.COURT_HIDE_TILES):
                extra += ['-H', '%d-%d' % (a_, b_)]
        fences = [(a_, b_, y_) for a_, b_, x_, y_ in sprite_chains(vram)
                  if b_ - a_ == 15 and x_ == 32 and (vram[0x8200 + a_] & 0x3F) == 2]
        def render(more):
            run(rname, rec, [(fr, fr)], base, extra + more)
            (_, px, npal_), = list(read_frames(base + '.frames', fr, fr))
            cache = {}
            def rgb(v):
                if v not in cache:
                    cache[v] = ng_color(npal_[v & 0xFFF]) if v else ng_color(npal_[0xFFF])
                return cache[v]
            return [[rgb(px[y * 320 + x]) for x in range(320)] for y in range(224)], npal_
        img, npal_ = render([])
        bank = TileBank(1)
        words, cram = convert_plane(img, 0, 0, 40, 28, 2, 0, bank, ncol=M.COURT_COLORS)
        # fence shake: the top and bottom fences in their 2 other frames (tiles + 0x20, + 0x40);
        # only the cells that change are kept, converted with the court's palettes
        pal_md = [[((w >> 1) & 7, (w >> 5) & 7, (w >> 9) & 7) for w in cram[p]] for p in range(2)]
        patches = []
        for fa, fb, fy in sorted(fences, key=lambda f: f[2]):
            for step in (1, 2):
                vimg, _ = render(['-T', '%d-%d:%x' % (fa, fb, 0x20 * step)])
                cells = []
                for cy in range(28):
                    for cx in range(40):
                        a8 = [img[cy * 8 + y][cx * 8 + x] for y in range(8) for x in range(8)]
                        b8 = [vimg[cy * 8 + y][cx * 8 + x] for y in range(8) for x in range(8)]
                        if a8 != b8:
                            cells.append((cy * 40 + cx, b8))
                patch, pbank = [], TileBank(M.FENCE_VRAM[0 if fy < 112 else 1])
                for cell, b8 in cells:
                    best = min(range(2), key=lambda p: sum(min(sum((u - v) ** 2 for u, v in zip(to_md(c), q)) for q in pal_md[p][1:M.COURT_COLORS[p] + 1]) for c in b8))
                    pl = pal_md[best]
                    idx = [1 + min(range(M.COURT_COLORS[best]), key=lambda i: sum((u - v) ** 2 for u, v in zip(to_md(c), pl[i + 1]))) for c in b8]
                    t, flip = pbank.add(idx)
                    patch.append((cell, (best << 13) | (flip << 11) | t))
                if len(pbank.tiles) > 128:
                    raise SystemExit('%s: fence frame needs %d tiles (> 128)' % (rname, len(pbank.tiles)))
                patch = (patch, pbank.data())
                patches.append(patch)
        if len(patches) != 4:
            raise SystemExit('%s: expected 2 fences, found %d' % (rname, len(patches) // 2))
        if ci == 0:
            match_pal = npal_
        if len(bank.tiles) > 1079:
            raise SystemExit('%s: %d tiles, more than the 1079 the match leaves for the court' % (rname, len(bank.tiles)))
        for kind, data in (('tiles', bank.data()), ('map', _st.pack('>%dH' % len(words), *words)),
                           ('pal', _st.pack('>32H', *(cram[0] + cram[1])))):
            path = os.path.join(build, 'courtshot%d_%s.bin' % (ci, kind))
            open(path, 'wb').write(data)
            if kind == 'tiles':                 # loaded once per match: banked (video window)
                banked.append('V courtshot%d_tiles %s' % (ci, os.path.abspath(path)))
                continue
            court_a += ['    .balign 2', '    .globl courtshot%d_%s' % (ci, kind), 'courtshot%d_%s:' % (ci, kind),
                        '    .incbin "%s"' % os.path.abspath(path)]
        court_c.append('{courtshot%d_tiles, %d, courtshot%d_map, courtshot%d_pal}' % (ci, len(bank.tiles) * 32, ci, ci))
        for k, (patch, ptiles) in enumerate(patches):      # [top 1, top 2, bottom 1, bottom 2]
            fence_c.append('static const u16 fence%d_%d[] = {%d, %d, %s};' % (ci, k, len(ptiles) // 32, len(patch), ', '.join(
                '%d, 0x%04X' % (cell, w) for cell, w in patch)))
            path = os.path.join(build, 'fence%d_%d.bin' % (ci, k))
            open(path, 'wb').write(ptiles or bytes(32))
            court_a += ['    .balign 2', '    .globl fence%d_%d_tiles' % (ci, k), 'fence%d_%d_tiles:' % (ci, k),
                        '    .incbin "%s"' % os.path.abspath(path)]
            fence_c.insert(0, 'extern const u8 fence%d_%d_tiles[];' % (ci, k))
        fence_tab.append('{%s}' % ', '.join('{fence%d_%d, fence%d_%d_tiles}' % (ci, k, ci, k) for k in range(4)))
        print('%s: %d tiles' % (rname, len(bank.tiles)))
        for ext in ('.frames', '.vram'):
            os.remove(base + ext)

    sup_c, sup_bin = make_supers(run)
    open(os.path.join(build, 'super_tiles.bin'), 'wb').write(sup_bin or bytes(32))
    hud_c, hud_bin = make_hud(match_pal, rs)
    shots = vram_shots(run, set([v[0] for v in M.SET_START.values()] + [M.SET_COUNTS['label'][0]] +
                                [v[0] for v in M.SET_COUNTS['digits'].values()] + [v[0] for v in M.RESULT_PARTS.values()] +
                                [M.ROUND_PANEL['shot']]))
    res_c, res_bin = make_result(shots, match_pal)
    dog_c, dog_h, dog_bin = make_dog(run, match_pal, rs.get(*M.FILES['s1']))
    rk_c, rk_h, rk_bin = make_ranking(run)
    open(os.path.join(build, 'rank_faces.bin'), 'wb').write(rk_bin)
    end_c, end_a, end_h = make_ending(run, banked)
    men_c, men_a, men_h = make_menu(run, banked, rs.get(*M.FILES['s1']))
    bow_c, bow_a, bow_h = make_bowl(run, banked, rs.get(*M.FILES['s1']), match_pal)
    open(os.path.join(build, 'dog_tiles.bin'), 'wb').write(dog_bin)
    banked.append('V:chars dog_tiles %s' % os.path.abspath(os.path.join(build, 'dog_tiles.bin')))
    open(os.path.join(build, 'result_tiles.bin'), 'wb').write(res_bin)
    ban_c, ban_bin = make_banner(match_pal, shots)
    ss_c, ss_bin, ss_names = make_setstart(shots)
    open(os.path.join(build, 'setstart_tiles.bin'), 'wb').write(ss_bin)
    open(os.path.join(build, 'banner_tiles.bin'), 'wb').write(ban_bin)
    open(os.path.join(build, 'hud_tiles.bin'), 'wb').write(hud_bin)
    c = ['/* generated by tools/mkmovies.py -- do not edit */', '#include "movies.h"', '#include "sound.h"']
    c += frames_c
    c += hud_c
    c += sup_c
    c += ['extern const u8 bonus_data[];'] + bonus_c
    c += ban_c
    c += ss_c
    c += res_c
    c += dog_c
    c += rk_c
    c += end_c
    c += men_c
    c += bow_c
    c += ['extern const u8 %s[];' % n for n in [l.split(':')[0] for l in court_a if l.endswith(':')]]
    c += ['extern const u8 courtshot%d_tiles[];' % ci for ci in range(len(court_c))]
    c += ['const BgAsset bg_court_shots[%d] = { %s };' % (len(court_c), ', '.join(court_c))]
    c += fence_c + ['const FencePatch court_fence[%d][4] = { %s };' % (len(fence_tab), ', '.join(fence_tab))]
    a = ['| generated by tools/mkmovies.py -- do not edit', '    .section .rodata', '    .balign 2',
         '    .globl screen_sprite_tiles', 'screen_sprite_tiles:',
         '    .incbin "%s"' % os.path.abspath(os.path.join(build, 'screen_sprites.bin')), '    .balign 2']
    for name in header:
        a += ['    .globl %s' % name, '%s:' % name, '    .long %s_data' % name, '    .word %s_data_page' % name]
    a += court_a
    a += end_a
    a += men_a
    a += bow_a
    a += ['    .balign 2', '    .globl rank_face_tiles', 'rank_face_tiles:', '    .incbin "%s"' % os.path.abspath(os.path.join(build, 'rank_faces.bin'))]
    a += ['    .balign 2', '    .globl bg_court_pages', 'bg_court_pages:'] + \
         ['    .word courtshot%d_tiles_page' % ci for ci in range(len(court_c))]
    open(os.path.join(build, 'bonus_data.bin'), 'wb').write(bonus_blob)
    banked.append('V bonus_data %s' % os.path.abspath(os.path.join(build, 'bonus_data.bin')))
    a += ['    .balign 2', '    .globl setstart_tiles', 'setstart_tiles:', '    .incbin "%s"' % os.path.abspath(os.path.join(build, 'setstart_tiles.bin'))]
    a += ['    .balign 2', '    .globl result_tiles', 'result_tiles:', '    .incbin "%s"' % os.path.abspath(os.path.join(build, 'result_tiles.bin'))]
    a += ['    .balign 2', '    .globl banner_tiles', 'banner_tiles:', '    .incbin "%s"' % os.path.abspath(os.path.join(build, 'banner_tiles.bin'))]
    a += ['    .balign 2', '    .globl super_tiles', 'super_tiles:', '    .incbin "%s"' % os.path.abspath(os.path.join(build, 'super_tiles.bin'))]
    a += ['    .balign 2', '    .globl fixfont_tiles', 'fixfont_tiles:', '    .incbin "%s"' % os.path.abspath(os.path.join(build, 'fixfont.bin'))]
    a += ['    .balign 2', '    .globl rankfont_tiles', 'rankfont_tiles:', '    .incbin "%s"' % os.path.abspath(os.path.join(build, 'rankfont.bin'))]
    a += ['    .balign 2', '    .globl hud_tiles', 'hud_tiles:', '    .incbin "%s"' % os.path.abspath(os.path.join(build, 'hud_tiles.bin'))]
    open(os.path.join(build, 'movies.s'), 'w').write('\n'.join(a) + '\n')
    c.append('const Music *const movie_music[] = { %s };' % ', '.join('&' + n for n in music) if music else
             'const Music *const movie_music[1];')
    c.append('const u16 movie_sfx[] = { %s };' % ', '.join(sfx) if sfx else 'const u16 movie_sfx[1];')
    h = ['/* generated by tools/mkmovies.py -- do not edit */', '#pragma once', '#include "types.h"',
         '#include "sounddata.h"',
         '/* data: in the video bank window (0x300000), mapped from ROM page `page` */',
         'typedef struct { const u8 *data; u16 page; } Movie;']
    h += ['extern const Movie %s;' % n for n in header]
    h += ['#include "chardata.h"', 'extern const u8 screen_sprite_tiles[];']
    h += ['/* per output frame labels of a movie (see MOVIES[...][\'labels\'] in the manifest) */'] + label_decls
    h += ['/* own palettes of sprites cut from screens */'] + pal_decls
    h += ['#include "bg.h"', 'extern const BgAsset bg_court_shots[];   /* courts recorded in a match: tiles banked, */',
          'extern const u16 bg_court_pages[];       /* map with bank_map_video(bg_court_pages[court]) */',
          '/* fence shake frames per court [top 1, top 2, bottom 1, bottom 2]: cells = tile count, cell count,',
          '   then (cell, map word); the tiles go to FENCE_VRAM (src/vram.h) */',
          'typedef struct { const u16 *cells; const u8 *tiles; } FencePatch;',
          'extern const FencePatch court_fence[][4];']
    h += ['/* match HUD made of the original tiles (tools/mkmovies.py make_hud) */',
          'extern const u8 hud_tiles[];',
          '#define HUD_DIGITS 0          /* 10 big score digits, 4 sprite tiles each */',
          '#define HUD_TIMES 40          /* 31 TIME boxes (seconds 30..0), then TIME UP, 4 sprite tiles each */',
          '#define HUD_TIME_TOP 30',
          '#define HUD_TIME_UP 31',
          '#define HUD_GLYPHS 168        /* plane tiles: P 1 2 0-9 */',
          '#define HUD_FLAGS 181         /* [character][side] 4 plane tiles (TL, BL, TR, BR) */',
          '#define HUD_SET_BAR 229       /* set lamp: 3 sprite tiles (rows 8-15 of the bar), end, middle, end */',
          '#define HUD_BOX 232           /* TIME box halves (8 tiles each, by column): tens 0 1 3 U, units 0-9 P */',
          'extern const u16 hud_box_src[16];       /* the TIME box\'s colours (its tiles use these indexes) */',
          'extern const u16 hud_flag_pal[6][2][4];   /* palette of each flag tile */',
          'extern const u16 hud_colors[2];          /* palette 1 entries 8 and 9 */',
          'extern const u8 fixfont_tiles[];        /* ASCII 0x20-0x5F, the game font in the HUD colours */',
          'extern const u8 rankfont_tiles[];       /* ranking scores: space, 0-9, 2 tiles each (top, bottom), HUD colours */',
          '/* super shots recorded from the game: per character the disc path (dx, dy per frame from the',
          '   throw, for a throw to the right) and the effect drawn around the disc each frame */',
          'typedef struct { u16 frames; const s8 *path; const u8 *fx; const Frame *fx_frames; const u16 *pal; } SuperShot;',
          'extern const u8 super_tiles[];',
          'extern const SuperShot super_shots[6];',
          '/* score banner drawn on plane A with palette 1 (entries 10-13 = banner_pal): each part has',
          '   its own tiles and a w x h cell map (0xFFFF = empty cell, else flip << 11 | tile) */',
          'typedef struct { const u8 *tiles; u16 ntiles, w, h; const u16 *map; } BannerPart;',
          'extern const u8 banner_tiles[];',
          'extern const u16 banner_pal[4];',
          'extern const BannerPart banner_bar;',
          '/* set end, rows 15-19 composed at run time: SET COUNTS (cells 7-32), a side\'s sets [side][sets]',
          '   (cells 7-12 / 27-32), the score digits\' bottoms (4 x 4 cells), their tops as sprites */',
          'extern const BannerPart banner_ovl_label, banner_ovl_sets[2][4], banner_digit_bottom[10];',
          'extern const Frame banner_digits_top[10];',
          'extern const Frame banner_ribbons[4];          /* "n POINTS GOAL": right goal 3, 5, left goal 3, 5 (48 tiles) */',
          'extern const Frame banner_digits[10];          /* sprites, 40 tiles each */',
          '/* set start overlay (make_setstart): plane A parts, palette 1 entries 10-13 = setstart_pal[group]',
          '   (groups: set 1, set 2, final, sudden death);',
          '   *_pos = cell column, row */',
          'extern const u8 setstart_tiles[];',
          'extern const u16 setstart_pal[5][4];       /* set 1, set 2, final, sudden death, 1P round panels */',
          'extern const BannerPart setstart_round_words, setstart_round_r1, setstart_round_r2, setstart_round_r3, setstart_round_r4, setstart_round_r5, setstart_round_r6,',
          '    setstart_round_s1, setstart_round_s2, setstart_round_s3, setstart_round_rules, setstart_round_ml3, setstart_round_ml5, setstart_round_mr3, setstart_round_mr5;',
          'extern const u16 setstart_round_words_pos[2], setstart_round_r1_pos[2], setstart_round_s1_pos[2], setstart_round_rules_pos[2],',
          '    setstart_round_ml3_pos[2], setstart_round_ml5_pos[2], setstart_round_mr3_pos[2], setstart_round_mr5_pos[2];',
          'extern const BannerPart setstart_panel_set1, setstart_panel_set2, setstart_panel_final, setstart_panel_sudden, setstart_rules, setstart_l3, setstart_l5, setstart_r3, setstart_r5;',
          'extern const u16 setstart_panel_set1_pos[2], setstart_panel_set2_pos[2], setstart_panel_final_pos[2], setstart_panel_sudden_pos[2], setstart_rules_pos[2], setstart_l3_pos[2], setstart_l5_pos[2], setstart_r3_pos[2], setstart_r5_pos[2];',
          '/* match result (make_result): plane A images per layout (P1 wins, P2 wins, draw) at cell',
          '   (3, 4), palette 1 entries 10-13 = result_pal; SET COUNTS sprites in the same colours;',
          '   frame positions [layout][side] (x, y); portraits at frame + result_portrait_offset[side] */',
          'extern const u8 result_tiles[];',
          'extern const u16 result_pal[4];',
          'extern const BannerPart result_p1win, result_p2win, result_draw;',
          'extern const Frame result_counts_d0, result_counts_d1, result_counts_d2, result_counts_d3;',
          'extern const s16 result_frame_pos[3][2][2], result_portrait_offset[2][2];',
          ] + dog_h + rk_h + end_h + men_h + bow_h + [
          '/* frisbee dog bonus demo (make_bonus): bonus_data (banked) = beach tiles for plane B (64x28',
          '   map) then the object tiles; bonus_frames: per record scroll, n, then n x (sprite id, object',
          '   frame, x, y); bonus_sounds: (record, sound id) pairs ending with 0xFFFF */',
          'extern const u8 bonus_data[], bonus_data_page[];',
          'extern const Frame bonus_objects[];',
          'extern const u8 bonus_flicker[];   /* per object: 1 = a shadow or sand puff (every other frame) */',
          'extern const u16 bonus_frames[], bonus_sounds[], bonus_pal[64], bonus_map[64 * 28];',
          'extern const u16 bonus_count, bonus_step, bonus_bg_tiles;']
    h += ['extern const Frame %s; extern const s16 %s_pos[2];   /* sprites cut from a screen, pos = where the game drew them */' % (n, n) for n in sprite_names]
    h += ['/* sound events: 0xFFFF stop music, 0x8000 | n movie_music[n], else movie_sfx[n] */',
          'extern const Music *const movie_music[];', 'extern const u16 movie_sfx[];']
    open(os.path.join(build, 'movies.c'), 'w').write('\n'.join(c) + '\n')
    open(os.path.join(build, 'movies.h'), 'w').write('\n'.join(h) + '\n')
    open(os.path.join(build, 'banked_movies.txt'), 'w').write('\n'.join(banked) + '\n')
    print('movies: %d KB' % (total // 1024))

main()
