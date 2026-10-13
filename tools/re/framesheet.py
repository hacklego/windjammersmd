#!/usr/bin/env python3
"""Labelled sheet of frames from the game's master frame table (P-ROM 0x32020 + 4 * index):
framesheet.py ROMDIR OUT.png first last [palette]"""
import os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from PIL import Image, ImageDraw
from extract import Game, frame_columns
rom, out, a, b = sys.argv[1], sys.argv[2], int(sys.argv[3], 16), int(sys.argv[4], 16)
palno = int(sys.argv[5], 16) if len(sys.argv) > 5 else None
g = Game(rom)
cells = []
for i in range(a, b + 1):
    cols, pal = frame_columns(g, (0x32020, i))
    pl = palno if palno is not None else pal
    im = Image.new('RGB', (96, 112), (40, 40, 60))
    for x, y, h, t, hf, cpal in cols:
        for r in range(h):
            px = g.tile(t + r)
            for yy in range(16):
                for xx in range(16):
                    v = px[yy * 16 + (15 - xx if hf else xx)]
                    X, Y = 48 + x + xx, 96 + y + r * 16 + yy
                    if v and 0 <= X < 96 and 0 <= Y < 112:
                        im.putpixel((X, Y), g.color(pl if cpal == pal else cpal, v))
    cells.append((i, im))
cols_n = 16
sh = Image.new('RGB', (cols_n * 96, ((len(cells) + cols_n - 1) // cols_n) * 112))
d = ImageDraw.Draw(sh)
for k, (i, im) in enumerate(cells):
    x, y = (k % cols_n) * 96, (k // cols_n) * 112
    sh.paste(im, (x, y)); d.text((x + 2, y + 2), '%x' % i, fill=(255, 255, 0))
sh.save(out)
