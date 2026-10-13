#!/usr/bin/env python3
"""Decode a tools/mkmovie.py blob the way the Mega Drive player does and save PNGs.
moviepreview.py MOVIE.bin OUTDIR [max frames]"""
import os, struct, sys
from PIL import Image

def md_rgb(w):
    return (((w >> 1) & 7) * 255 // 7, ((w >> 5) & 7) * 255 // 7, ((w >> 9) & 7) * 255 // 7)

def main():
    data = open(sys.argv[1], 'rb').read()
    out = sys.argv[2]; os.makedirs(out, exist_ok=True)
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 1 << 30
    n, loop, toff = struct.unpack('>HHI', data[:8])
    tiles = data[toff:]
    vram = {}
    nt = [[0] * (64 * 32), [0] * (64 * 32)]
    cram = [0] * 64
    q = 8; t = 0
    for k in range(min(n, limit)):
        dur, fl = struct.unpack('>HH', data[q:q + 4]); q += 4
        if fl & 1:
            cram = list(struct.unpack('>64H', data[q:q + 128])); q += 128
        if fl & 4:
            ns = struct.unpack('>H', data[q:q + 2])[0]; q += 2 + 2 * ns
        nl = struct.unpack('>H', data[q:q + 2])[0]; q += 2
        for _ in range(nl):
            slot, cnt, off = struct.unpack('>HHI', data[q:q + 8]); q += 8
            for j in range(cnt):
                vram[slot + j] = tiles[off + 32 * j: off + 32 * j + 32]
        nr = struct.unpack('>H', data[q:q + 2])[0]; q += 2
        back = nt[k & 1]
        for _ in range(nr):
            cell, cnt = struct.unpack('>HH', data[q:q + 4]); q += 4
            ws = struct.unpack('>%dH' % cnt, data[q:q + 2 * cnt]); q += 2 * cnt
            back[cell:cell + cnt] = ws
        img = Image.new('RGB', (320, 224), md_rgb(cram[0]))
        px = img.load()
        for cy in range(28):
            for cx in range(40):
                w = back[cy * 64 + cx]
                tile = vram.get(w & 0x7FF, bytes(32))
                pal = (w >> 13) & 3; hf = (w >> 11) & 1; vf = (w >> 12) & 1
                for y in range(8):
                    for x in range(8):
                        sx = 7 - x if hf else x; sy = 7 - y if vf else y
                        b = tile[sy * 4 + sx // 2]
                        v = (b >> 4) if sx % 2 == 0 else (b & 15)
                        if v:
                            px[cx * 8 + x, cy * 8 + y] = md_rgb(cram[pal * 16 + v])
        img.save(os.path.join(out, '%04d_t%05d.png' % (k, t)))
        t += dur
    print('frames', n, 'loop', loop, 'end offset', q, 'tiles at', toff)

main()
