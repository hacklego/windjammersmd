#!/usr/bin/env python3
"""Convert ngrec .frames output to PNGs (debugging): ngframes.py OUT.frames DIR [every]"""
import os, struct, sys
from array import array
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from neogeo import ng_color

PIXELS = 320 * 224

def frames(path):
    """Yield (frame number, flags, pixels array('H'), palette array('H')) from an ngrec file."""
    with open(path, 'rb') as f:
        while True:
            hdr = f.read(6)
            if len(hdr) < 6:
                return
            fn, fl = struct.unpack('<IH', hdr)
            if not fl & 0x4000:
                px = array('H'); px.frombytes(f.read(PIXELS * 2))
                if sys.byteorder == 'big':
                    px.byteswap()
            if not fl & 0x8000:
                pal = array('H'); pal.frombytes(f.read(0x2000))
                if sys.byteorder == 'big':
                    pal.byteswap()
            yield fn, fl, px, pal

def to_image(px, pal):
    cache = {}
    out = bytearray(PIXELS * 3)
    for i, v in enumerate(px):
        c = cache.get(v)
        if c is None:
            c = cache[v] = bytes(ng_color(pal[(v & 0xFFF) if v else 0xFFF]))
        out[i * 3:i * 3 + 3] = c
    return Image.frombytes('RGB', (320, 224), bytes(out))

if __name__ == '__main__':
    out = sys.argv[2]; os.makedirs(out, exist_ok=True)
    every = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    for fn, fl, px, pal in frames(sys.argv[1]):
        if fn % every == 0:
            to_image(px, pal).save(os.path.join(out, '%05d.png' % fn))
