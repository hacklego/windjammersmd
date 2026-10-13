"""RE helper: index-labelled contact sheet of every frame whose columns use a given palette."""
import sys, os, struct
sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ngsprites import CRom
from neogeo import ng_color
from PIL import Image, ImageDraw

TABLES = [(0x32048,27),(0x32108,24),(0x32170,30),(0x32484,27),(0x32558,84),(0x32724,36),(0x3290c,18),(0x3298c,24),
          (0x32a44,12),(0x32af8,51),(0x32c38,57),(0x32d3c,7),(0x32eb0,187),(0x331a0,102),(0x3344c,8),(0x3349c,4),
          (0x334bc,14),(0x3351c,733),(0x341b0,284),(0x34684,24),(0x348d4,45)]

def main(pbe, romdir, pal, out):
    p = open(pbe, 'rb').read()
    w = lambda a: struct.unpack('>H', p[a:a+2])[0]
    l = lambda a: struct.unpack('>I', p[a:a+4])[0]
    sw = lambda v: v - 0x10000 if v & 0x8000 else v
    crom = CRom(romdir)
    frames = []
    for ta, n in TABLES:
        for i in range(n):
            a = l(ta + 4 * i); nc = w(a) & 0xFF; q = a + 2; cols = []
            for c in range(nc):
                h = w(q) & 0x3F; t = w(q + 2); at = w(q + 4); q += 6
                if c == 0: xo, yo = sw(w(q)), sw(w(q + 2)); q += 4
                cols.append((xo + 16 * c, yo, h, t, at))
            if any(at >> 8 == pal for *_, at in cols):
                frames.append(('%x:%d' % (ta, i), cols))
    cell = 96; per = 12
    sheet = Image.new('RGB', (per * cell, ((len(frames) + per - 1) // per) * cell), (48, 48, 64))
    d = ImageDraw.Draw(sheet)
    for k, (name, cols) in enumerate(frames):
        ox, oy = (k % per) * cell, (k // per) * cell
        for xo, yo, h, t, at in cols:
            pl = at >> 8; hf = at & 1
            for i in range(h):
                tile = crom.tile(t + i)
                for yy in range(16):
                    for xx in range(16):
                        v = tile[yy * 16 + (15 - xx if hf else xx)]
                        X = ox + 48 + xo + xx; Y = oy + 76 + yo + i * 16 + yy
                        if v and ox <= X < ox + cell and oy + 10 <= Y < oy + cell:
                            sheet.putpixel((X, Y), ng_color(w(0x30000 + pl * 32 + v * 2)))
        d.text((ox + 2, oy), name, fill=(255, 255, 0))
    sheet.save(out)
    print(len(frames), 'frames')

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3], 0), sys.argv[4])
