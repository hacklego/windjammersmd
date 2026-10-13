"""RE helper: parse a Neo Geo VRAM dump (SCB1-4) into sprite columns and render them.
Used only during development to discover how the game composes its graphics."""
import struct, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from neogeo import decode_tile, ng_color

def load_words(path):
    d = open(path, 'rb').read()
    return list(struct.unpack('>%dH' % (len(d) // 2), d))

def parse_sprites(vram):
    """Return list of columns: dict(n, x, y, h, shrink, tiles=[(tile, pal, hflip, vflip)])"""
    cols = []
    px = py = ph = 0
    for n in range(1, 381):
        scb2, scb3, scb4 = vram[0x8000 + n], vram[0x8200 + n], vram[0x8400 + n]
        if scb3 & 0x40:  # sticky: chain to previous
            x = (px + 16) & 0x1FF; y = py; h = ph
        else:
            x = scb4 >> 7; y = (496 - (scb3 >> 7)) & 0x1FF; h = scb3 & 0x3F
        px, py, ph = x, y, h
        if h == 0:
            continue
        tiles = []
        for i in range(min(h, 32)):
            lo = vram[n * 64 + i * 2]; at = vram[n * 64 + i * 2 + 1]
            tiles.append((lo | ((at >> 4) & 0xF) << 16, at >> 8, at & 1, (at >> 1) & 1))
        cols.append(dict(n=n, x=x, y=y, h=h, shrink=scb2, tiles=tiles))
    return cols

class CRom:
    def __init__(self, romdir):
        r = lambda f: open(os.path.join(romdir, f), 'rb').read()
        self.pairs = [(r('065-c1.c1'), r('065-c2.c2')), (r('065-c3.c3'), r('065-c4.c4'))]
        self.cache = {}
    def tile(self, t):
        t &= 0x7FFF
        if t not in self.cache:
            p = self.pairs[t >> 14]
            self.cache[t] = decode_tile(p[0], p[1], t & 0x3FFF)
        return self.cache[t]

def render(vram, pal, crom, only=None):
    from PIL import Image
    im = Image.new('RGB', (320, 224), ng_color(pal[0xFFF]))
    px = im.load()
    for c in parse_sprites(vram):
        if only and c['n'] not in only:
            continue
        for i, (t, p, hf, vf) in enumerate(c['tiles']):
            data = crom.tile(t)
            for yy in range(16):
                sy = (c["y"] + i * 16 + yy) & 0x1FF
                if sy >= 224: continue
                for xx in range(16):
                    sx = (c['x'] + xx) & 0x1FF
                    if sx >= 320: continue
                    v = data[(15 - yy if vf else yy) * 16 + (15 - xx if hf else xx)]
                    if v: px[sx, sy] = ng_color(pal[p * 16 + v])
    return im

if __name__ == '__main__':
    vram = load_words(sys.argv[1]); pal = load_words(sys.argv[2])
    render(vram, pal, CRom(sys.argv[3])).save(sys.argv[4])
