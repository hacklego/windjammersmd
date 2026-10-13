"""RE helper: match logged sprite columns (capture_anims.lua) to frame records -> animation timelines."""
import sys, struct, collections

def load_frames(pbe, tables):
    p = open(pbe, 'rb').read()
    w = lambda a: struct.unpack('>H', p[a:a+2])[0]
    l = lambda a: struct.unpack('>I', p[a:a+4])[0]
    index = {}
    for ta, n in tables:
        for i in range(n):
            a = l(ta + 4 * i); nc = w(a) & 0xFF; q = a + 2; tiles = []
            for c in range(nc):
                tiles.append(w(q + 2)); q += 6
                if c == 0: q += 4
            index.setdefault(frozenset(tiles), '%x:%d' % (ta, i))
    return index

def main(pbe, log, pal):
    from charsheet import TABLES
    mirrored = [(ta + 0x34a9c - 0x32048, n) for ta, n in TABLES]  # mirrored set has the same layout
    index = load_frames(pbe, TABLES + mirrored)
    per = collections.defaultdict(list); inp = {}; pos = {}
    for line in open(log):
        if line.startswith('I '):
            parts = line.split(); inp[int(parts[1])] = parts[2] if len(parts) > 2 else '-'
            continue
        f, n, x, y, t, at = line.split()
        if int(at, 16) >> 8 == pal and int(f) not in pos: pos[int(f)] = (int(x), int(y))
        if int(at, 16) >> 8 == pal:
            per[int(f)].append(int(t, 16))
    runs = []
    for f in sorted(per):
        # auto-animated tiles change their low bits; try exact match first
        key = frozenset(per[f]); name = index.get(key, '?')
        if runs and runs[-1][0] == name: runs[-1][2] += 1
        else: runs.append([name, f, 1])
    for name, f, d in runs:
        print('%5d %-12s x%-3d in=%-10s pos=%s' % (f, name, d, inp.get(f, '-'), pos.get(f)))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3], 0))
