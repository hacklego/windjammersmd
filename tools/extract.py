#!/usr/bin/env python3
"""Build-time asset extractor: Windjammers Neo Geo ROM set -> Mega Drive assets.

usage: extract.py <rom dir or wjammers.zip> <build dir> [--preview]

Everything written here is derived from the user's own ROM and goes into the
(gitignored) build directory; nothing extracted is ever stored in the repo.
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neogeo import RomSet, decode_tile, ng_color
from mdgfx import to_md, md_word, fit_palettes, nearest, TileBank, pack_tile
import manifest_wjammers as M

def swap16(d):
    b = bytearray(d)
    b[0::2], b[1::2] = d[1::2], d[0::2]
    return bytes(b)

class Game:
    def __init__(self, rompath):
        rs = RomSet(rompath)
        g = lambda k: rs.get(*M.FILES[k])
        self.p = swap16(g('p1'))
        self.c = [(g('c1'), g('c2')), (g('c3'), g('c4'))]
        self.s1 = g('s1')
        self._tiles = {}

    def w(self, a):
        return struct.unpack('>H', self.p[a:a + 2])[0]

    def tile(self, t):
        t &= 0x7FFF
        if t not in self._tiles:
            pr = self.c[t >> 14]
            self._tiles[t] = decode_tile(pr[0], pr[1], t & 0x3FFF)
        return self._tiles[t]

    def color(self, pal, idx):
        return ng_color(self.w(M.PALETTES + pal * 32 + idx * 2))

    def render_map(self, a):
        """Render a 0x20nn tilemap record -> (width, height, rows of RGB or None)."""
        n = self.w(a) & 0xFF; q = a + 2
        cols = []
        for c in range(n):
            h = self.w(q) & 0x3F; q += 2
            cols.append([(self.w(q + 4 * i), self.w(q + 4 * i + 2)) for i in range(h)]); q += 4 * h
            if c == 0:
                q += 4
        H = max(len(c) for c in cols) * 16; W = n * 16
        img = [[None] * W for _ in range(H)]
        for ci, col in enumerate(cols):
            for ti, (t, at) in enumerate(col):
                data = self.tile(t | ((at >> 4) & 0xF) << 16)
                pl, hf, vf = at >> 8, at & 1, (at >> 1) & 1
                for yy in range(16):
                    row = img[ti * 16 + yy]
                    for xx in range(16):
                        v = data[(15 - yy if vf else yy) * 16 + (15 - xx if hf else xx)]
                        if v:
                            row[ci * 16 + xx] = self.color(pl, v)
        return W, H, img

# Palette 1 layout shared by every screen: 1..9 background, 10..13 disc, 14 black, 15 white
BG_COLORS = [15, 9]
DISC_SLOT, BLACK, WHITE = 10, 14, 15

def convert_plane(img, x0, y0, wt, ht, npal, palbase, bank, ncol=BG_COLORS):
    """Convert an RGB image region into an MD tilemap using `npal` palettes."""
    tiles = []
    for ty in range(ht):
        for tx in range(wt):
            px = []
            for y in range(8):
                row = img[y0 + ty * 8 + y]
                for x in range(8):
                    c = row[x0 + tx * 8 + x]
                    px.append(to_md(c) if c else (0, 0, 0))
            tiles.append(px)
    hists = []
    for px in tiles:
        h = {}
        for c in px:
            h[c] = h.get(c, 0) + 1
        hists.append(h)
    pals, assign = fit_palettes(hists, npal, ncol)
    words = []
    for px, a in zip(tiles, assign):
        pal = pals[a]
        idx = [1 + nearest(pal, c)[0] for c in px]
        t, flip = bank.add(idx)
        words.append(((palbase + a) << 13) | (flip << 11) | t)
    cram = []
    for pal in pals:
        cram.append([0] + [md_word(c) for c in pal] + [0] * (15 - len(pal)))
    return words, cram

def frame_columns(game, ref):
    """Parse a frame record referenced as (pointer table, index) -> (columns, palette).
    Columns: (x, y, height_in_16px_tiles, first_tile). Tiles run consecutively down each column."""
    table, idx = ref
    a = struct.unpack('>I', game.p[table + 4 * idx: table + 4 * idx + 4])[0]
    n = game.w(a) & 0xFF; q = a + 2; cols = []; pal = None
    for c in range(n):
        h = game.w(q) & 0x3F; t = game.w(q + 2); at = game.w(q + 4); q += 6
        if c == 0:
            xo = struct.unpack('>h', game.p[q:q + 2])[0]; yo = struct.unpack('>h', game.p[q + 2:q + 4])[0]; q += 4
        if pal is None:
            pal = at >> 8
        cols.append((xo + 16 * c, yo, h, t | ((at >> 4) & 0xF) << 16, at & 1, at >> 8))
    return cols, pal

def convert_frame(game, ref, remap=None, main_pal=None, alt_remap=None):
    """Neo Geo frame -> (tile bytes, sprite list). Each Neo Geo column (16px wide) becomes
    MD sprites 2 tiles wide and up to 4 tiles (32px) tall. Sprite entry: dx, dy, w, h, tile offset."""
    cols, _ = frame_columns(game, ref)
    tiles = bytearray(); sprites = []
    for x, y, h, t, hf, cpal in cols:
        # columns in another palette than the character's (the disc in hand, effects)
        # are drawn with palette 1 using the shared disc colour slots
        alt = alt_remap is not None and main_pal is not None and cpal != main_pal
        cremap = alt_remap(cpal) if alt else remap
        # gather the column as a 16 x (16*h) indexed image
        img = []
        for i in range(h):
            data = game.tile(t + i)
            for yy in range(16):
                row = [data[yy * 16 + (15 - xx if hf else xx)] for xx in range(16)]
                img.append([cremap[v] if cremap and v else v for v in row])
        rows = len(img) // 8  # in 8px tiles
        r = 0
        while r < rows:
            n = min(4, rows - r)
            # skip fully transparent 8px rows at the top of a chunk
            block = img[r * 8:(r + n) * 8]
            if not any(any(row) for row in block):
                r += n; continue
            off = len(tiles) // 32
            for cx in range(2):          # MD sprite tiles are column-major
                for cy in range(n):
                    px = []
                    for yy in range(8):
                        px.extend(img[(r + cy) * 8 + yy][cx * 8:cx * 8 + 8])
                    tiles += pack_tile(px)
            sprites.append((x, y + r * 8, 2, n, off, alt))
            r += n
    return bytes(tiles), sprites

def write_bin(build, name, data):
    with open(os.path.join(build, name), 'wb') as f:
        f.write(data)

def main():
    rompath, build = sys.argv[1], sys.argv[2]
    preview = '--preview' in sys.argv
    os.makedirs(build, exist_ok=True)
    game = Game(rompath)
    asm = ['| generated by tools/extract.py from the user\'s ROM -- do not commit', '\t.section .rodata', '\t.balign 2']
    hdr = ['/* generated by tools/extract.py -- do not commit */', '#pragma once', '#include "types.h"']

    def blob(sym, fname, data):
        write_bin(build, fname, data)
        asm.extend(['\t.balign 2', '\t.global %s' % sym, '%s:' % sym, '\t.incbin "%s"' % fname])
        hdr.append('extern const u8 %s[];  /* %d bytes */' % (sym, len(data)))
        hdr.append('#define %s_SIZE %d' % (sym, len(data)))

    def plane_asset(sym, img, x0, y0):
        bank = TileBank(base=1)  # VRAM tile 0 stays blank (transparent)
        words, cram = convert_plane(img, x0, y0, 40, 28, 2, 0, bank)
        if len(bank.tiles) >= MAX_BG_TILES:
            raise SystemExit('%s needs %d tiles (max %d)' % (sym, len(bank.tiles), MAX_BG_TILES - 1))
        blob(sym + '_tiles', sym + '_tiles.bin', bank.data())
        blob(sym + '_map', sym + '_map.bin', struct.pack('>%dH' % len(words), *words))
        blob(sym + '_pal', sym + '_pal.bin', struct.pack('>32H', *(cram[0] + cram[1])))
        if preview:
            preview_plane(os.path.join(build, 'preview_%s.png' % sym), words, cram, bank)
        print('%-10s %4d unique tiles' % (sym, len(bank.tiles)))

    # courts are recorded from a match instead (tools/mkmovies.py, bg_court_shots)
    hdr.append('#define NUM_COURTS %d' % len(M.COURT_LIST_ROW))

    for name, layers in M.SCREENS:
        canvas = [[None] * 320 for _ in range(224)]
        for rec, cx, cy, px, py in layers:
            W, H, img = game.render_map(rec)
            for y in range(H - cy):
                if not 0 <= py + y < 224: continue
                for x in range(W - cx):
                    c = img[cy + y][cx + x]
                    if c and 0 <= px + x < 320:
                        canvas[py + y][px + x] = c
        plane_asset('scr_' + name, canvas, 0, 0)


    blob('font_tiles', 'font_tiles.bin', convert_font(game))
    hdr.append('#define FONT_TILES %d' % FONT_GLYPHS)

    write_disc(game, blob, hdr)

    hdr.append('#define NUM_CHARS %d' % len(M.CHARACTERS))
    write_characters(game, build, blob)

    with open(os.path.join(build, 'assets.s'), 'w') as f:
        f.write('\n'.join(asm) + '\n')
    with open(os.path.join(build, 'assets.h'), 'w') as f:
        f.write('\n'.join(hdr) + '\n')

PLAYER_VRAM_TILES = 128   # must match PLAYER_SLOT_TILES in src/player.h
MAX_BG_TILES = 1080       # background tiles live in VRAM 1..1079 (see src/vram.h)
FONT_GLYPHS = 64          # ASCII 0x20..0x5F

def convert_font(game):
    """Fix-layer glyphs -> MD tiles: solid white letters on a solid black cell, so text
    stays readable over any background. (The Neo Geo font is a top-to-bottom shading
    ramp; collapsing that ramp to two colours would cut the letters in half.)"""
    from neogeo import decode_fix
    out = bytearray()
    for code in range(0x20, 0x20 + FONT_GLYPHS):
        g = decode_fix(game.s1, M.FONT_BASE + code)
        out += pack_tile([WHITE if v else BLACK for v in g])
    return bytes(out)

def frame_palette_colors(game, refs):
    """Histogram of MD colours used by a set of frames (by palette index)."""
    hist = {}
    for ref in refs:
        cols, pal = frame_columns(game, ref)
        for x, y, h, t, hf, cpal in cols:
            for i in range(h):
                for v in game.tile(t + i):
                    if v:
                        c = to_md(game.color(pal, v)); hist[c] = hist.get(c, 0) + 1
    return hist

def disc_remap(game, refs, colors):
    """Neo Geo palette index -> palette-1 disc slot, by nearest colour."""
    _, pal = frame_columns(game, refs[0])
    return {v: DISC_SLOT + nearest(colors, to_md(game.color(pal, v)))[0] for v in range(1, 16)}

def write_disc(game, blob, hdr):
    """Disc, shadow and fireball frames as sprite frames sharing the palette-1 disc slots."""
    from mdgfx import kmeans_colors
    disc_cols = kmeans_colors(frame_palette_colors(game, M.DISC_FLY), 4)
    fire_cols = kmeans_colors(frame_palette_colors(game, M.FIREBALL), 4)
    pad = lambda cs: [md_word(c) for c in cs] + [0] * (4 - len(cs))
    blob('disc_colors', 'disc_colors.bin', struct.pack('>8H', *(pad(disc_cols) + pad(fire_cols))))
    groups = [('disc_fly', M.DISC_FLY, disc_remap(game, M.DISC_FLY, disc_cols)),
              ('fireball', M.FIREBALL, disc_remap(game, M.FIREBALL, fire_cols))]
    c = ['/* generated by tools/extract.py from the user\'s ROM -- do not commit */',
         '#include "chardata.h"', '#include "assets.h"']
    for name, refs, remap in groups:
        tiles = bytearray(); frames = []
        for ref in refs:
            data, sprites = convert_frame(game, ref, remap)
            frames.append((len(tiles) // 32, len(data) // 32, sprites)); tiles += data
        blob(name + '_tiles', name + '_tiles.bin', bytes(tiles))
        for fi, (_, _, sprites) in enumerate(frames):
            c.append('static const SprPiece %s_p%d[] = {%s};' % (name, fi, ', '.join(
                '{%d, %d, %d, %d}' % (dx, dy, ((w - 1) << 2) | (h - 1) | (16 if alt else 0), off) for dx, dy, w, h, off, alt in sprites)))
        c.append('const Frame %s_frames[%d] = {' % (name, len(frames)))
        for fi, (off, n, sprites) in enumerate(frames):
            c.append('    {%s_tiles + %d, %d, %d, %s_p%d},' % (name, off * 32, n, len(sprites), name, fi))
        c.append('};')
        hdr.append('#define %s_COUNT %d' % (name.upper(), len(frames)))
        print('%-10s %d frames, max %d tiles' % (name, len(frames), max(n for _, n, _ in frames)))
    global DISC_COLS
    DISC_COLS = disc_cols
    # Shadow: a plain 16x8 dark ellipse (generated, not taken from the ROM: the ROM's
    # shadow frame is 36 tiles of mostly empty space)
    px = [[BLACK if ((x - 7.5) / 8) ** 2 + ((y - 3.5) / 4) ** 2 <= 1 else 0 for x in range(16)] for y in range(8)]
    shadow = b''.join(pack_tile([px[y][x0 + x] for y in range(8) for x in range(8)]) for x0 in (0, 8))
    blob('shadow_tiles', 'shadow_tiles.bin', shadow)
    c.append('static const SprPiece shadow_p0[] = {{-8, -4, 4, 0}};')
    # player floor shadow: 32x12 ellipse in a 32x16 sprite (generated)
    px = [[BLACK if ((x - 15.5) / 15) ** 2 + ((y - 7.5) / 6) ** 2 <= 1 else 0 for x in range(32)] for y in range(16)]
    big = b''.join(pack_tile([px[ty * 8 + y][tx * 8 + x] for y in range(8) for x in range(8)]) for tx in range(4) for ty in range(2))
    blob('pshadow_tiles', 'pshadow_tiles.bin', big)
    c.append('static const SprPiece pshadow_p0[] = {{-16, -8, 13, 0}};')
    c.append('const Frame shadow_frames[2] = {{shadow_tiles, 2, 1, shadow_p0}, {pshadow_tiles, 8, 1, pshadow_p0}};')
    hdr.append('#define SHADOW_COUNT 2')
    with open(os.path.join(sys.argv[2], 'discdata.c'), 'w') as f:
        f.write('\n'.join(c) + '\n')

def write_characters(game, build, blob):
    """Emit build/chardata.c (frames, sprite pieces, animations, palettes) + per-character tile blobs."""
    c = ['/* generated by tools/extract.py from the user\'s ROM -- do not commit */',
         '#include "chardata.h"', '#include "assets.h"']
    defs = []
    all_tiles = bytearray()           # every character's tiles in one banked blob (char_tiles)
    for ci, ch in enumerate(M.CHARACTERS):
        refs = []
        for name in M.ANIM_ORDER:
            for ref, _ in ch['anims'][name]:
                if ref not in refs:
                    refs.append(ref)
        tiles = bytearray(); frames = []
        for ref in refs:
            data, sprites = convert_frame(game, ref, main_pal=ch['palette'],
                                           alt_remap=lambda pl: {v: DISC_SLOT + nearest(DISC_COLS, to_md(game.color(pl, v)))[0] for v in range(1, 16)})
            n = len(data) // 32
            if n > PLAYER_VRAM_TILES:
                raise SystemExit('frame %s of %s needs %d tiles (> %d)' % (ref, ch['name'], n, PLAYER_VRAM_TILES))
            frames.append((len(tiles) // 32, n, sprites)); tiles += data
        base_off = len(all_tiles)
        all_tiles += tiles
        for fi, (_, _, sprites) in enumerate(frames):
            c.append('static const SprPiece c%d_f%d[] = {%s};' % (ci, fi, ', '.join(
                '{%d, %d, %d, %d}' % (dx, dy, ((w - 1) << 2) | (h - 1) | (16 if alt else 0), off) for dx, dy, w, h, off, alt in sprites)))
        c.append('static const Frame c%d_frames[] = {' % ci)
        for fi, (off, n, sprites) in enumerate(frames):
            c.append('    {char_tiles + %d, %d, %d, c%d_f%d},' % (base_off + off * 32, n, len(sprites), ci, fi))
        c.append('};')
        for name in M.ANIM_ORDER:
            steps = ch['anims'][name]
            c.append('static const AnimStep c%d_%s[] = {%s, {0xFFFF, 0}};' % (ci, name, ', '.join(
                '{%d, %d}' % (refs.index(ref), d) for ref, d in steps)))
        pals = []
        for k in range(2):
            pn = ch['palette'] + k
            pals.append([0] + [md_word(to_md(game.color(pn, i))) for i in range(1, 16)])
        c.append('static const u16 c%d_pal[32] = {%s};' % (ci, ', '.join('0x%03X' % v for v in pals[0] + pals[1])))
        gid = M.GAME_ID[ci]
        speeds = [game.w(M.THROW_SPEEDS + gid * 32 + 2 * i) for i in range(16)]
        c.append('static const u16 c%d_tspeed[16] = {%s};' % (ci, ', '.join(str(v) for v in speeds)))
        defs.append('    {"%s", "%s", %d, %d, 0x%X, %d, %d, c%d_tspeed, c%d_pal, c%d_frames, {%s}},' % (
            ch['name'], ch['country'], ch['speed'], ch['power'], int(M.RUN_SPEED[gid] * 65536),
            game.w(M.THROW_POWER_FRAMES + 2 * gid), game.w(M.CURVE_TABLE + 4 * gid + 2), ci, ci, ci,
            ', '.join('c%d_%s' % (ci, name) for name in M.ANIM_ORDER)))
        print('char  %-9s %3d frames, %5d tiles, max %d tiles/frame' % (
            ch['name'], len(frames), len(tiles) // 32, max(n for _, n, _ in frames)))
    c.append('const CharDef characters[NUM_CHARS] = {'); c.extend(defs); c.append('};')
    # the tiles live in a ROM bank shown at 0x300000 (tools/mkbanks.py), mapped by player_init()
    write_bin(build, 'char_tiles.bin', bytes(all_tiles))
    with open(os.path.join(build, 'banked_chars.txt'), 'w') as f:
        f.write('V:chars char_tiles %s\n' % os.path.abspath(os.path.join(build, 'char_tiles.bin')))
    c.insert(2, 'extern const u8 char_tiles[], char_tiles_page[];')
    print('character tiles: %d KB (banked)' % (len(all_tiles) // 1024))
    with open(os.path.join(build, 'chardata.c'), 'w') as f:
        f.write('\n'.join(c) + '\n')

def preview_plane(path, words, cram, bank):
    """Render the converted MD data back to a PNG (for checking conversion quality)."""
    from PIL import Image
    im = Image.new('RGB', (320, 224)); px = im.load()
    for i, wd in enumerate(words):
        t = bank.tiles[(wd & 0x7FF) - bank.base]; pal = cram[(wd >> 13) & 3]
        hf, vf = (wd >> 11) & 1, (wd >> 12) & 1
        for y in range(8):
            for x in range(8):
                sx, sy = (7 - x if hf else x), (7 - y if vf else y)
                b = t[sy * 4 + sx // 2]; v = (b >> 4) if sx % 2 == 0 else (b & 15)
                c = pal[v]
                px[(i % 40) * 8 + x, (i // 40) * 8 + y] = ((c >> 1 & 7) * 36, (c >> 5 & 7) * 36, (c >> 9 & 7) * 36)
    im.save(path)

if __name__ == '__main__':
    main()
