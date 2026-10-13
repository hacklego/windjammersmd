"""RE helper: from a match_anims.py timeline, report the repeating frame cycle seen in each
input window (and the longest no-input loops), as (table:index, duration) lists."""
import sys, re, collections

def load(path):
    runs = []
    for line in open(path):
        m = re.match(r'\s*(\d+) (\S+)\s+x(\d+)\s+in=(\S+)', line)
        if m:
            runs.append((int(m.group(1)), m.group(2), int(m.group(3)), m.group(4)))
    return runs

def period(seq):
    """Smallest repeating unit of seq (needs >=2 repeats)."""
    for p in range(1, len(seq) // 2 + 1):
        if all(seq[i] == seq[i % p] for i in range(len(seq))):
            return seq[:p]
    return None

def cycles(runs):
    out = collections.OrderedDict()
    # group consecutive runs by input label
    i = 0
    while i < len(runs):
        j = i
        while j < len(runs) and runs[j][3] == runs[i][3]:
            j += 1
        seg = runs[i:j]
        names = [r[1] for r in seg]
        # strip transition frames at both ends, find longest periodic stretch
        best = None
        for a in range(len(seg)):
            for b in range(len(seg), a + 3, -1):
                p = period(names[a:b])
                if p and (best is None or (b - a) > best[0]):
                    best = (b - a, [(n, d) for n, _, d, _ in [(r[1], 0, r[2], 0) for r in seg[a:a + len(p)]]])
                    break
        key = '%s@%d' % (seg[0][3], seg[0][0])
        if best and len(best[1]) >= 2:
            out[key] = best[1]
        i = j
    return out

def windows(runs):
    """input label -> list of frame-index sequences (one per occurrence of that input window)."""
    out = collections.defaultdict(list)
    i = 0
    while i < len(runs):
        j = i
        while j < len(runs) and runs[j][3] == runs[i][3]:
            j += 1
        out[runs[i][3]].append([(r[1], r[2]) for r in runs[i:j]])
        i = j
    return out

def summarize(path):
    for label, occs in sorted(windows(load(path)).items()):
        if label == '-':
            continue
        # frames that appear in at least half of the occurrences, in first-seen order
        counts = collections.Counter(n for occ in occs for n in dict.fromkeys(x for x, _ in occ))
        seen = []
        for occ in occs:
            for n, _ in occ:
                if counts[n] * 2 >= len(occs) and n not in seen:
                    seen.append(n)
        print('%-12s x%d  %s' % (label, len(occs), ' '.join(n.split(':')[1] for n in seen)), ' table', seen[0].split(':')[0] if seen else '-')

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "--windows":
        summarize(sys.argv[1])
    else:
        for k, v in cycles(load(sys.argv[1])).items():
            print('%-16s %s' % (k, ' '.join('%s/%d' % (n.split(':')[1], d) for n, d in v)), '  table', v[0][0].split(':')[0])
