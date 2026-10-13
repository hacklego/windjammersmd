#!/usr/bin/env python3
"""Labelled contact sheet straight from an ngrec recording:
labsheet.py REC.frames OUT.png first last step [cols]"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw
from mkmovie import read_frames
from ngframes import to_image
rec, out, first, last, step = sys.argv[1], sys.argv[2], *map(int, sys.argv[3:6])
cols = int(sys.argv[6]) if len(sys.argv) > 6 else 8
ims = [(fn, to_image(px, pal)) for fn, px, pal in read_frames(rec, first, last) if (fn - first) % step == 0]
w, h = 160, 112
sh = Image.new('RGB', (cols * w, ((len(ims) + cols - 1) // cols) * h))
d = ImageDraw.Draw(sh)
for i, (fn, im) in enumerate(ims):
    x, y = (i % cols) * w, (i // cols) * h
    sh.paste(im.resize((w, h)), (x, y))
    d.text((x + 2, y + 2), str(fn), fill=(255, 0, 255))
sh.save(out)
