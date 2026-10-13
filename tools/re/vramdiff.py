#!/usr/bin/env python3
"""List Neo Geo sprites (chains) in an ngrec -V dump, or the ones that differ between two frames.
vramdiff.py DUMP frameA [frameB]"""
import struct, sys
def load(path):
    out = {}
    with open(path, 'rb') as f:
        while True:
            h = f.read(4)
            if not h: break
            fn = struct.unpack('<I', h)[0]
            v = struct.unpack('<%dH' % 0x8800, f.read(0x8800 * 2)); f.read(0x2000)
            out[fn] = v
    return out
def chains(v):
    res = []; cur = None
    for n in range(1, 381):
        yc = v[0x8200 + n]
        if yc & 0x40 and cur: cur['n'].append(n); continue
        cur = dict(n=[n], y=0x200 - (yc >> 7), x=v[0x8400 + n] >> 7, h=yc & 0x3F, zoom=v[0x8000 + n])
        res.append(cur)
    for c in res:
        n = c['n'][0]
        c['tile'] = v[n * 64] | ((v[n * 64 + 1] << 12) & 0xF0000); c['pal'] = v[n * 64 + 1] >> 8
        c['sig'] = tuple((v[k * 64], v[k * 64 + 1], v[0x8200 + k], v[0x8400 + k], v[0x8000 + k]) for k in c['n'])
    return [c for c in res if c['h']]
d = load(sys.argv[1]); a = chains(d[int(sys.argv[2])])
if len(sys.argv) > 3:
    b = chains(d[int(sys.argv[3])]); sb = {c['sig'] for c in b}; sa = {c['sig'] for c in a}
    a = [c for c in a if c['sig'] not in sb] + [dict(c, new=1) for c in b if c['sig'] not in sa]
for c in a:
    print('%s sprites %3d-%3d x=%3d y=%3d h=%2d tile=%05x pal=%02x zoom=%04x' % ('+' if c.get('new') else ' ', c['n'][0], c['n'][-1], c['x'], c['y'] - 16, c['h'], c['tile'], c['pal'], c['zoom']))
