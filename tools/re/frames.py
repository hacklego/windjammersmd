"""RE helper: parse frame records from the (byte-swapped back) P-ROM and render contact sheets."""
import struct, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from ngsprites import CRom, load_words
from neogeo import ng_color

def w(p, a): return struct.unpack('>H', p[a:a+2])[0]
def sw(v): return v - 0x10000 if v & 0x8000 else v

def parse_frame(p, a):
    """-> list of columns (xoff, yoff, height, tile, attr). Columns after the first are sticky (x += 16)."""
    hdr = w(p, a); n = hdr & 0xFF; a += 2
    cols = []
    h = w(p, a) & 0x3F; t = w(p, a + 2); at = w(p, a + 4); xo = sw(w(p, a + 6)); yo = sw(w(p, a + 8)); a += 10
    cols.append((xo, yo, h, t, at))
    for i in range(1, n):
        h = w(p, a) & 0x3F; t = w(p, a + 2); at = w(p, a + 4); a += 6
        cols.append((xo + 16 * i, yo, h, t, at))
    return hdr, cols

def render_frame(p, a, crom, pal, palbase=None):
    from PIL import Image
    hdr, cols = parse_frame(p, a)
    im = Image.new('RGBA', (160, 160), (0, 0, 0, 0)); px = im.load()
    for xo, yo, h, t, at in cols:
        pl = (palbase if palbase is not None else (at >> 8))
        hf = at & 1
        for i in range(h):
            tile = crom.tile(t + i)
            for yy in range(16):
                for xx in range(16):
                    v = tile[yy * 16 + (15 - xx if hf else xx)]
                    X = 80 + xo + xx; Y = 100 + yo + i * 16 + yy
                    if v and 0 <= X < 160 and 0 <= Y < 160:
                        r, g, b = ng_color(pal[(pl * 16 + v) & 0xFFF]); px[X, Y] = (r, g, b, 255)
    return im
