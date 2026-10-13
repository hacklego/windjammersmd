#!/usr/bin/env python3
"""Contact sheet of PNGs: sheet.py OUT.png COLS SCALE files..."""
import sys
from PIL import Image
out, cols, scale = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
fs = sys.argv[4:]
w, h = (int(v * scale) for v in Image.open(fs[0]).size)
rows = (len(fs) + cols - 1) // cols
sh = Image.new('RGB', (cols * w, rows * h))
for i, f in enumerate(fs):
    sh.paste(Image.open(f).convert('RGB').resize((w, h)), ((i % cols) * w, (i // cols) * h))
sh.save(out)
