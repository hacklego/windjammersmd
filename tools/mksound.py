#!/usr/bin/env python3
"""Translate the Neo Geo game's audio for the Mega Drive.

The original Z80 sound driver is run in sim/sndsim; its YM2610 register writes
are turned into streams for the YM2612 (FM) and SN76489 (SSG parts), and the
ADPCM-A samples it triggers are decoded to 8-bit PCM for a small Z80 DAC driver.
Output: build/gen/sound.s, build/gen/sound.h.
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neogeo import RomSet
import manifest_wjammers as M

# usage: mksound.py <rom dir or zip> <build dir>   (sim binary: <build dir>/sndsim)
GEN = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else 'build'
SND = os.path.join(GEN, 'snd')
SIM = os.path.join(GEN, 'sndsim')
ROMSET = RomSet(sys.argv[1]) if len(sys.argv) > 1 else None
M1 = os.path.join(SND, 'm1.bin')

Z80_CLK_NEO = 4000000
CMD_FRAME = 120
T0 = CMD_FRAME * 67584
STEP = Z80_CLK_NEO / (2 * 59.92)          # two player steps per Mega Drive frame
FNUM_SCALE = 8000000 / 7670453            # YM2610 clock / YM2612 clock
PCM_RATE = 3579545 / 276                  # average loop time of the Z80 mixing driver
KIT_BASE, KIT_SIZE, KIT_MAX_LEN = 0x0200, 0x1D00, 3000   # drum kit area in Z80 RAM
ADPCM_RATE = 8000000 / 432

# Tracks and effects come from the manifest: name -> (command bytes, seconds, looping)
MUSIC = M.MUSIC
SAMPLE_SFX = M.SAMPLE_SFX      # name -> command bytes; the first sample it triggers is used
PSG_SFX = {}

CMD_END, CMD_WAIT, CMD_YM0, CMD_YM1, CMD_PSG, CMD_SAMPLE, CMD_LOOP, CMD_STOP, CMD_DRUM = range(9)


def record(code, secs):
    """Run the original driver: reset, then send the command bytes (code may be a list)."""
    codes = code if isinstance(code, (list, tuple)) else [code]
    os.makedirs(SND, exist_ok=True)
    path = os.path.join(SND, 'code%s_%d.log' % ('_'.join('%02x' % c for c in codes), secs))
    if not os.path.exists(path):
        subprocess.run([SIM, M1, path + '.tmp', str(secs + 3), '60:03'] + [f'{CMD_FRAME}:{c:x}' for c in codes], check=True)
        os.rename(path + '.tmp', path)
    ev = []
    for line in open(path):
        p = line.split()
        if p[1] == 'C':
            continue
        t = int(p[0])
        if t >= T0:
            ev.append((t - T0, int(p[1]), int(p[2], 16), int(p[3], 16)))
    return ev


class Samples:
    def __init__(self):
        # ADPCM-A sample space: the V ROMs back to back
        self.rom = {}
        for i, key in enumerate(('v1', 'v2', 'v3', 'v4')):
            self.rom[i * 0x100000] = ROMSET.get(*M.FILES[key])
        self.ids = {}
        self.raw = []
        self.pcm = []
        steps = [16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143,
                 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963,
                 1060, 1166, 1282, 1411, 1552]
        self.jedi = []
        for s in steps:
            for nib in range(16):
                v = (2 * (nib & 7) + 1) * s // 8
                self.jedi.append(-v if nib & 8 else v)
        self.inc = [-1, -1, -1, -1, 2, 5, 7, 9]

    def byte(self, a):
        for base, data in self.rom.items():
            if base <= a < base + len(data):
                return data[a - base]
        return 0x80

    def decode(self, start, end):
        acc, step = 0, 0
        out = []
        for a in range(start << 8, ((end << 8) | 0xff) + 1):
            b = self.byte(a)
            for nib in (b >> 4, b & 15):
                acc = (acc + self.jedi[step * 16 + nib]) & 0xfff
                step = min(48, max(0, step + self.inc[nib & 7]))
                out.append(acc - 0x1000 if acc & 0x800 else acc)
        return out

    def get(self, start, end):
        key = (start, end)
        if key in self.ids:
            return self.ids[key]
        src = self.decode(start, end)
        ratio = ADPCM_RATE / PCM_RATE
        n = int(len(src) / ratio)
        raw = []
        for i in range(n):
            a = int(i * ratio)
            b = min(len(src), max(a + 1, int((i + 1) * ratio)))
            raw.append(sum(src[a:b]) / (b - a))          # box filter while decimating
        self.ids[key] = len(self.raw)
        self.raw.append(raw)
        return self.ids[key]

    def finish(self):
        """Pick one gain for all samples (peaks near full scale) and convert to 8-bit."""
        mags = sorted(abs(v) for r in self.raw for v in r)
        ref = mags[int(len(mags) * 0.999)] if mags else 1
        gain = min(8.0, 118.0 / max(ref, 1))
        self.pcm = []
        for raw in self.raw:
            pcm = bytearray(max(0, min(255, int(v * gain) + 128)) for v in raw)
            while len(pcm) > 64 and abs(pcm[-1] - 128) < 3:
                pcm.pop()
            self.pcm.append(bytes(pcm[:65535]))
        return gain


def sample_triggers(ev):
    """Yield (t, start, end) for each ADPCM-A key-on."""
    reg = {}
    for t, part, r, v in ev:
        if part != 1 or r >= 0x30:
            continue
        reg[r] = v
        if r == 0 and not v & 0x80:
            for c in range(6):
                if v & (1 << c):
                    yield t, reg.get(0x10 + c, 0) | reg.get(0x18 + c, 0) << 8, reg.get(0x20 + c, 0) | reg.get(0x28 + c, 0) << 8


_ADPCMB_F0 = {}

def adpcmb_f0(start, end):
    """Fundamental (Hz) of an ADPCM-B sample played at delta-N 65536 (55.5 kHz), or 0 if it has
    no clear pitch. Yamaha delta-T decoding + autocorrelation."""
    key = (start, end)
    if key in _ADPCMB_F0:
        return _ADPCMB_F0[key]
    v = b''.join(ROMSET.get(*M.FILES[k]) for k in ('v1', 'v2', 'v3', 'v4'))
    step, acc, pcm = 127, 0, []
    tab = [57, 57, 57, 57, 77, 102, 128, 153]
    for a in range(start, min(end + 1, start + 4096)):
        for n in (v[a] >> 4, v[a] & 15):
            d = (2 * (n & 7) + 1) * step // 8
            acc = max(-32768, min(32767, acc - d if n & 8 else acc + d))
            step = max(127, min(24576, step * tab[n & 7] // 64))
            pcm.append(acc)
    w = pcm[len(pcm) // 4: len(pcm) // 4 + 2048]
    m = sum(w) / max(1, len(w)); w = [x - m for x in w]
    e0 = sum(x * x for x in w) or 1
    best, lag = 0, 0
    for L in range(40, 1000):
        c = sum(w[i] * w[i + L] for i in range(0, len(w) - L, 2))
        if c > best:
            best, lag = c, L
    f0 = 55555.0 / lag if lag and best / e0 > 0.25 else 0
    _ADPCMB_F0[key] = f0
    return f0

# FM voice for the ADPCM-B instruments (the YM2612's channel 1 is free in the converted music):
# a plain bass patch. (reg, value) for operator slots 1..4 of channel 1 (part 0, index 0).
ADPCMB_PATCH = [(0x30, 0x00), (0x34, 0x01), (0x38, 0x00), (0x3C, 0x01),       # DT/MUL
                (0x40, 0x22), (0x44, 0x30), (0x48, 0x28), (0x4C, 0x00),       # TL (carrier 4C)
                (0x50, 0x1F), (0x54, 0x1F), (0x58, 0x1F), (0x5C, 0x1F),       # AR
                (0x60, 0x0A), (0x64, 0x0C), (0x68, 0x0A), (0x6C, 0x08),       # D1R
                (0x70, 0x04), (0x74, 0x04), (0x78, 0x04), (0x7C, 0x04),       # D2R
                (0x80, 0x26), (0x84, 0x26), (0x88, 0x26), (0x8C, 0x28),       # SL/RR
                (0xB0, 0x30), (0xB4, 0xC0)]                                   # FB 6, ALG 0, L+R

def fm_freq(hz):
    """Hz -> (A4 value, A0 value) for the YM2612 (7.67 MHz)."""
    for block in range(8):
        fnum = int(hz * 144 * (1 << (21 - block)) / 7670453 + 0.5)
        if fnum < 2048:
            return (block << 3) | (fnum >> 8), fnum & 0xff
    return 0x3f, 0xff

def music_events(ev, samples):
    """Filter/translate raw writes into (t, cmd, a, b) player events."""
    out = []
    reg = {}
    fhi = {}
    ssg = [0] * 16
    ssg[7] = 0x3f
    psg_last = {}
    def ssg_update(t, ch):
        """SSG channel -> PSG tone channel (same mapping as build_psg)."""
        tp = ssg[ch * 2] | (ssg[ch * 2 + 1] & 15) << 8
        vol = ssg[8 + ch]
        lvl = 12 if vol & 0x10 else vol & 15
        if ssg[7] & (1 << ch):
            lvl = 0
        att = 15 if lvl == 0 else min(15, int((15 - lvl) * 1.5 + 0.5))
        n = max(1, min(1023, int(tp * 0.8949 + 0.5)))
        if att != 15 and psg_last.get(('n', ch)) != n:
            out.append((t, CMD_PSG, 0x80 | ch << 5 | (n & 15), 0))
            out.append((t, CMD_PSG, n >> 4, 0))
            psg_last[('n', ch)] = n
        if psg_last.get(('a', ch), 15) != att:
            out.append((t, CMD_PSG, 0x90 | ch << 5 | att, 0))
            psg_last[('a', ch)] = att
    adb = {}                                # ADPCM-B registers
    adb_on = [False, None]                  # playing, (f0, note end time)
    out.extend((0, CMD_YM0, r, v) for r, v in ADPCMB_PATCH)
    def adb_pitch(t):
        f0 = adb_on[1][0] if adb_on[1] else 0
        dn = adb.get(0x19, 0) | adb.get(0x1a, 0) << 8
        if not f0 or not dn:
            return
        a4, a0 = fm_freq(f0 * dn / 65536.0)
        out.append((t, CMD_YM0, 0xA4, a4))
        out.append((t, CMD_YM0, 0xA0, a0))
    for t, part, r, v in ev:
        if adb_on[0] and adb_on[1] and t >= adb_on[1][1]:       # the sample ran out
            out.append((adb_on[1][1], CMD_YM0, 0x28, 0x00)); adb_on[0] = False
        if part == 0 and 0x10 <= r <= 0x1b:  # ADPCM-B -> FM channel 1
            adb[r] = v
            if r == 0x10 and v & 0x80:
                st = adb.get(0x12, 0) | adb.get(0x13, 0) << 8
                en = adb.get(0x14, 0) | adb.get(0x15, 0) << 8
                f0 = adpcmb_f0(st << 8, (en << 8) | 0xff)
                dn = adb.get(0x19, 0) | adb.get(0x1a, 0) << 8
                rate = 55555.0 * max(dn, 1) / 65536.0
                dur = ((en - st + 1) * 512) / rate * 4e6
                adb_on[:] = [True, (f0, t + (1e18 if v & 0x10 else dur))]
                out.append((t, CMD_YM0, 0x28, 0x00))
                if f0:
                    vol = adb.get(0x1b, 0xff)
                    out.append((t, CMD_YM0, 0x4C, min(0x7f, int((255 - vol) / 8))))
                    adb_pitch(t)
                    out.append((t, CMD_YM0, 0x28, 0xF0))
            elif r == 0x10 and v & 0x01 and adb_on[0]:
                out.append((t, CMD_YM0, 0x28, 0x00)); adb_on[0] = False
            elif r in (0x19, 0x1a) and adb_on[0]:
                adb_pitch(t)
            continue
        if part == 0 and r < 0x10:          # SSG -> PSG
            ssg[r] = v
            if r < 6:
                ssg_update(t, r >> 1)
            elif 8 <= r <= 10:
                ssg_update(t, r - 8)
            elif r == 7:
                for ch in range(3):
                    ssg_update(t, ch)
            continue
        if part == 1 and r < 0x30:
            reg[r] = v
            if r == 0 and not v & 0x80:
                for c in range(6):
                    if v & (1 << c):
                        s = reg.get(0x10 + c, 0) | reg.get(0x18 + c, 0) << 8
                        e = reg.get(0x20 + c, 0) | reg.get(0x28 + c, 0) << 8
                        if (reg.get(0x08 + c, 0x1f) & 0x1f) and e >= s:
                            out.append((t, CMD_SAMPLE, samples.get(s, e), 0))
            continue
        if part == 0 and r < 0x30:
            if r == 0x28:
                ch = v & 7
                if ch not in (1, 2, 5, 6):
                    continue
                out.append((t, CMD_YM0, 0x28, (v & 0xf0) | (4 if ch == 6 else ch)))
            elif r == 0x22:
                out.append((t, CMD_YM0, r, v))
            continue
        idx = r & 3
        if idx not in (1, 2):
            continue
        # YM2610 voice 6 would land on the Mega Drive's DAC channel: move it to voice 4
        mr = (r & 0xfc) if (part == 1 and idx == 2) else r
        cmd = CMD_YM1 if part else CMD_YM0
        if 0xa4 <= r <= 0xa6:
            fhi[(part, idx)] = v
            continue
        if 0xa0 <= r <= 0xa2:
            hi = fhi.get((part, idx), 0)
            block, fnum = (hi >> 3) & 7, ((hi & 7) << 8) | v
            fnum = int(fnum * FNUM_SCALE + 0.5)
            while fnum > 0x7ff and block < 7:
                fnum >>= 1
                block += 1
            fnum = min(fnum, 0x7ff)
            out.append((t, cmd, mr + 4, (block << 3) | (fnum >> 8)))
            out.append((t, cmd, mr, fnum & 0xff))
            continue
        if 0xa8 <= r <= 0xaf:
            continue
        out.append((t, cmd, mr, v))
    return out


def find_loop(events):
    return find_loop_window(events) or find_loop_period(events)


def find_loop_period(events):
    """Fallback: the shortest period over which the note-start sequence repeats exactly
    (checked on the second half of the recording), starting as early as it holds."""
    ko = [(i, e[0], e[3] & 7) if e[1] == CMD_YM0 else (i, e[0], 8 + e[2] % 240)
          for i, e in enumerate(events)
          if (e[1] == CMD_YM0 and e[2] == 0x28 and e[3] & 0xf0) or e[1] == CMD_SAMPLE]
    vals = [k[2] for k in ko]
    n = len(vals)
    for p in range(30, n // 2):
        if all(vals[i] == vals[i - p] for i in range(n // 2, n)):
            first = n - p
            while first > 0 and vals[first - 1] == vals[first - 1 + p]:
                first -= 1
            cycles = ko[first + p][1] - ko[first][1]
            j = ko[first][0]
            while j > 0 and events[j][0] - events[j - 1][0] < 3000:
                j -= 1
            return j, cycles
    return None


def find_loop_window(events):
    """Find the musical loop from the key-on pattern.

    Exact register streams never repeat (free-running vibrato), but the sequence of
    key-ons does. Returns (index of the first event of the loop, loop length in cycles).
    """
    # note starts: FM key-ons and sample triggers (tracks that are mostly drums/voices have few FM notes)
    ko = [(i, e[0], e[3] & 7) if e[1] == CMD_YM0 else (i, e[0], 8 + e[2] % 240)
          for i, e in enumerate(events)
          if (e[1] == CMD_YM0 and e[2] == 0x28 and e[3] & 0xf0) or e[1] == CMD_SAMPLE]
    vals = bytes(k[2] for k in ko)
    win = 60
    if len(ko) < 4 * win:
        return None
    pos = len(vals) - win
    while True:
        pos = vals.rfind(vals[-win:], 0, pos + win - 1)
        if pos < 0:
            return None
        period = len(vals) - win - pos
        cycles = ko[-1][1] - ko[-1 - period][1]
        i = len(ko) - 1 - period
        while i >= 0 and vals[i] == vals[i + period] and abs((ko[i + period][1] - ko[i][1]) - cycles) < 40000:
            i -= 1
        first = i + 1
        if len(ko) - first >= 2 * period:
            # back up to the start of the driver tick that contains this key-on
            j = ko[first][0]
            while j > 0 and events[j][0] - events[j - 1][0] < 3000:
                j -= 1
            return j, cycles


def encode(events, loop_at=None, total_steps=None):
    """events: [(step, cmd, a, b)] sorted. Returns stream bytes with a 4-byte loop offset header."""
    body = bytearray()
    loop_off = 0xffffffff
    cur = 0
    by_step = {}
    for s, c, a, b in events:
        by_step.setdefault(s, []).append((c, a, b))
    last = total_steps if total_steps is not None else (max(by_step) + 1 if by_step else 1)
    marks = sorted(set(by_step) | ({loop_at} if loop_at is not None else set()))

    def wait(n):
        # n >= 1 steps pass before the next data
        while n > 0:
            if n == 1:
                body.append(CMD_END)
                n = 0
            else:
                k = min(n, 257)
                body.append(CMD_WAIT)
                body.append(k - 2)
                n -= k

    for s in marks:
        if s >= last:
            break
        if s > cur:
            wait(s - cur)
            cur = s
        if loop_at is not None and s == loop_at:
            loop_off = len(body) + 4
        for c, a, b in by_step.get(s, ()):
            body.append(c)
            body.append(a)
            if c in (CMD_YM0, CMD_YM1, CMD_DRUM):
                body.append(b)
    if last > cur:
        wait(last - cur)
    body.append(CMD_LOOP if loop_at is not None else CMD_STOP)
    return struct.pack('>I', loop_off) + bytes(body)


def build_music(code, secs, looping, samples):
    """Returns (events as (step, cmd, a, b), loop step or None, total steps or None, description)."""
    ev = music_events(record(code, secs), samples)
    if not ev:
        return [], None, None, 'empty'
    loop = find_loop(ev) if looping else None
    if loop:
        i0, t_period = loop
        t_start = ev[i0][0]
        s0 = int(t_start / STEP + 0.5)
        psteps = int(t_period / STEP + 0.5)
        out = [(min(int(t / STEP + 0.5), s0), c, a, b) for t, c, a, b in ev[:i0]]
        for t, c, a, b in ev[i0:]:
            if t >= t_start + t_period:
                break
            out.append((s0 + min(int((t - t_start) / STEP + 0.5), psteps - 1), c, a, b))
        return out, s0, s0 + psteps, f'loop {t_start / 4e6:.1f}s + {t_period / 4e6:.1f}s'
    out = [(int(t / STEP + 0.5), c, a, b) for t, c, a, b in ev]
    return out, None, None, f'one-shot {ev[-1][0] / 4e6:.1f}s'


def build_kit(events, samples):
    """Pick the tune's most used drums for the RAM kit, the half-rate second PCM voice used
    when the ROM voice is busy. Every drum hit becomes CMD_DRUM (sample id, kit slot or FFh);
    the player decides which voice takes it. Returns (events, kit bytes)."""
    import collections
    use = collections.Counter(a for _, c, a, _ in events if c == CMD_SAMPLE)
    kit, data, table = {}, bytearray(), []
    for sid, _ in use.most_common():
        pcm = samples.pcm[sid]
        half = bytes((pcm[i] + pcm[min(i + 1, len(pcm) - 1)]) // 2 for i in range(0, len(pcm), 2))[:KIT_MAX_LEN]
        if not half or len(data) + len(half) > KIT_SIZE:
            continue
        kit[sid] = len(table)
        table.append((KIT_BASE + len(data), len(half)))
        data += half
    out = [(s, CMD_DRUM, a, kit.get(a, 0xff)) if c == CMD_SAMPLE else (s, c, a, b) for s, c, a, b in events]
    blob = struct.pack('>H', len(table)) + b''.join(struct.pack('>HH', a, n) for a, n in table)
    blob += struct.pack('>H', len(data)) + bytes(data)
    return out, blob


def build_psg(code):
    """SSG effect -> PSG stream."""
    ev = [(t, r, v) for t, part, r, v in record(code, 6) if part == 0 and r < 0x10]
    reg = [0] * 16
    reg[7] = 0x3f
    last = {}
    out = []
    steps = sorted({int(t / STEP + 0.5) for t, _, _ in ev})
    i = 0
    for s in steps:
        while i < len(ev) and int(ev[i][0] / STEP + 0.5) <= s:
            reg[ev[i][1]] = ev[i][2]
            i += 1
        for ch in range(3):
            tp = reg[ch * 2] | (reg[ch * 2 + 1] & 15) << 8
            vol = reg[8 + ch]
            lvl = 12 if vol & 0x10 else vol & 15
            if reg[7] & (1 << ch):
                lvl = 0
            att = 15 if lvl == 0 else min(15, int((15 - lvl) * 1.5 + 0.5))
            n = max(1, min(1023, int(tp * 0.8949 + 0.5)))
            if att != 15 and last.get(('n', ch)) != n:
                out.append((s, CMD_PSG, 0x80 | ch << 5 | (n & 15), 0))
                out.append((s, CMD_PSG, n >> 4, 0))
                last[('n', ch)] = n
            if last.get(('a', ch), 15) != att:
                out.append((s, CMD_PSG, 0x90 | ch << 5 | att, 0))
                last[('a', ch)] = att
    end = (steps[-1] + 1) if steps else 0
    for ch in range(3):
        if last.get(('a', ch), 15) != 15:
            out.append((end, CMD_PSG, 0x90 | ch << 5 | 15, 0))
    return encode(out)


def z80_driver():
    """Assemble the two-channel DAC mixer. Returns bytes.

    Channel A streams 8-bit PCM from banked ROM (effects, voices); channel B plays a drum
    from the kit in Z80 RAM at half rate. Mailboxes: 40h (A: flag, bank, addr, len) and
    50h (B: flag, addr, len). Idle channels read a silent byte at 1F00h.
    """
    code = bytearray()
    labels, fix = {}, []

    def emit(*b):
        code.extend(b)

    def label(n):
        labels[n] = len(code)

    def abs16(n):
        fix.append((len(code), n, 'abs'))
        code.extend(b'\0\0')

    def rel(n):
        fix.append((len(code), n, 'rel'))
        code.append(0)

    emit(0xF3)                              # di
    emit(0x31, 0xF0, 0x1F)                  # ld sp,1FF0h
    emit(0xC3); abs16('main')               # jp main
    while len(code) < 0x60:
        emit(0)                             # 40h/50h mailboxes, 47h current bank
    label('main')
    emit(0x3E, 0x80, 0x32, 0x00, 0x1F)      # ld a,80h / ld (1F00h),a
    emit(0x21, 0x00, 0x40, 0x36, 0x2B)      # ld hl,4000h / ld (hl),2Bh
    emit(0x23, 0x36, 0x80)                  # inc hl / ld (hl),80h     ; DAC on
    emit(0x21, 0x00, 0x1F, 0x01, 0x00, 0x00)        # ld hl,1F00h / ld bc,0
    emit(0xD9, 0x21, 0x00, 0x1F, 0x01, 0x00, 0x00, 0x16, 0x00, 0xD9)   # exx / same / ld d,0 / exx
    label('play')
    emit(0x3E, 0x2A, 0x32, 0x00, 0x40)      # ld a,2Ah / ld (4000h),a
    emit(0x7E)                              # ld a,(hl)                ; channel A
    label('incA')
    emit(0x00)                              # nop <-> inc hl
    emit(0x5F)                              # ld e,a
    emit(0x7C, 0xB7, 0x20); rel('nowrap')   # ld a,h / or a / jr nz,nowrap
    emit(0x2A, 0x47, 0x00, 0x23, 0x22, 0x47, 0x00)  # ld hl,(curbank) / inc hl / ld (curbank),hl
    emit(0xCD); abs16('setbank')            # call setbank
    emit(0x21, 0x00, 0x80)                  # ld hl,8000h
    label('nowrap')
    emit(0x0B, 0x78, 0xB1, 0x20); rel('a_ok')       # dec bc / ld a,b / or c / jr nz,a_ok
    emit(0xAF, 0x32); abs16('incA')         # xor a / ld (incA),a
    emit(0x21, 0x00, 0x1F)                  # ld hl,1F00h
    label('a_ok')
    emit(0xD9)                              # exx
    emit(0x7E, 0x5F)                        # ld a,(hl) / ld e,a       ; channel B
    emit(0x7A, 0xEE, 0x01, 0x57)            # ld a,d / xor 1 / ld d,a
    emit(0x28); rel('b_skip')               # jr z,b_skip              ; advance every other sample
    label('incB')
    emit(0x00)                              # nop <-> inc hl
    emit(0x0B, 0x78, 0xB1, 0x20); rel('b_ok')       # dec bc / ld a,b / or c / jr nz,b_ok
    emit(0xAF, 0x32); abs16('incB')         # xor a / ld (incB),a
    emit(0x21, 0x00, 0x1F)                  # ld hl,1F00h
    emit(0x18); rel('b_ok')                 # jr b_ok
    label('b_skip')
    emit(0x18, 0x00, 0x00, 0x00)            # jr $+2 / nop / nop       ; even out the timing
    label('b_ok')
    emit(0x7B, 0xD9, 0x83)                  # ld a,e / exx / add a,e
    emit(0x38); rel('hi')                   # jr c,hi
    emit(0xD6, 0x80, 0x30); rel('out')      # sub 80h / jr nc,out
    emit(0xAF, 0x18); rel('out')            # xor a / jr out
    label('hi')
    emit(0xC6, 0x80, 0x30); rel('out')      # add a,80h / jr nc,out
    emit(0x3E, 0xFF)                        # ld a,FFh
    label('out')
    emit(0x32, 0x01, 0x40)                  # ld (4001h),a
    emit(0x3A, 0x40, 0x00, 0xB7, 0x20); rel('startA')   # ld a,(40h) / or a / jr nz,startA
    emit(0x3A, 0x50, 0x00, 0xB7, 0x20); rel('startB')   # ld a,(50h) / or a / jr nz,startB
    emit(0x3E, 0x01, 0x3D, 0x20, 0xFD)      # ld a,1 / dec a / jr nz,$-1
    emit(0xC3); abs16('play')               # jp play
    label('startA')
    emit(0xAF, 0x32, 0x40, 0x00)            # xor a / ld (40h),a
    emit(0x2A, 0x41, 0x00, 0x22, 0x47, 0x00)        # ld hl,(41h) / ld (curbank),hl
    emit(0xCD); abs16('setbank')            # call setbank
    emit(0x2A, 0x43, 0x00)                  # ld hl,(43h)
    emit(0xED, 0x4B, 0x45, 0x00)            # ld bc,(45h)
    emit(0x3E, 0x23, 0x32); abs16('incA')   # ld a,23h / ld (incA),a
    emit(0xC3); abs16('play')               # jp play
    label('startB')
    emit(0xAF, 0x32, 0x50, 0x00)            # xor a / ld (50h),a
    emit(0xD9)                              # exx
    emit(0x2A, 0x51, 0x00)                  # ld hl,(51h)
    emit(0xED, 0x4B, 0x53, 0x00)            # ld bc,(53h)
    emit(0x16, 0x00, 0xD9)                  # ld d,0 / exx
    emit(0x3E, 0x23, 0x32); abs16('incB')   # ld a,23h / ld (incB),a
    emit(0xC3); abs16('play')               # jp play
    label('setbank')                        # hl = bank number (9 bits, sent LSB first)
    emit(0xC5, 0x06, 0x09)                  # push bc / ld b,9
    label('sb')
    emit(0x7D, 0x32, 0x00, 0x60)            # ld a,l / ld (6000h),a
    emit(0xCB, 0x3C, 0xCB, 0x1D)            # srl h / rr l
    emit(0x10); rel('sb')                   # djnz sb
    emit(0xC1, 0xC9)                        # pop bc / ret
    for pos, name, kind in fix:
        if kind == 'abs':
            code[pos:pos + 2] = struct.pack('<H', labels[name])
        else:
            d = labels[name] - (pos + 1)
            assert -128 <= d <= 127, name
            code[pos] = d & 0xff
    assert len(code) <= KIT_BASE
    return bytes(code)


def main():
    os.makedirs(GEN, exist_ok=True)
    os.makedirs(SND, exist_ok=True)
    with open(M1, 'wb') as f:
        f.write(ROMSET.get(*M.FILES['m1']))
    samples = Samples()
    s = ['| generated by tools/mksound.py -- do not edit', '    .section .rodata']
    h = ['/* generated by tools/mksound.py -- do not edit */', '#ifndef SOUND_DATA_H', '#define SOUND_DATA_H',
         '#include "types.h"',
         '/* stream: in the music bank window (0x200000), mapped from ROM page `page` (tools/mkbanks.py) */',
         'typedef struct { const u8 *stream; const u8 *kit; u16 page; } Music;']
    banked = []

    def blob(name, data, ctype='u8'):
        path = os.path.join(GEN, name + '.bin')
        open(path, 'wb').write(data)
        s.extend(['    .balign 2', f'    .globl {name}', f'{name}:', f'    .incbin "{path}"'])
        h.append(f'extern const {ctype} {name}[];')

    tunes = {name: build_music(code, secs, looping, samples) for name, (code, secs, looping) in MUSIC.items()}
    for name, code in PSG_SFX.items():
        data = build_psg(code)
        blob(name, data)
        print(f'{name}: {len(data)} bytes')
    for name, code in SAMPLE_SFX.items():
        trig = list(sample_triggers(record(code, 3)))
        if not trig:
            print(f'{name}: no sample for code {code:02x}')
            h.append(f'#define {name} 0xFFFF')
            continue
        h.append(f'#define {name} {samples.get(trig[0][1], trig[0][2])}')
    # character voices: [category][character] -> sample id, from the game's own table
    p1 = ROMSET.get(*M.FILES['p1'])
    p1 = bytes(b for pair in zip(p1[1::2], p1[0::2]) for b in pair)
    vt = []
    for name, cat in M.VOICE_CATEGORIES.items():
        row = []
        for ch in range(6):
            code = p1[M.VOICE_TABLE + cat * 8 + ch]
            trig = list(sample_triggers(record([0x18, code], 3))) if code else []
            row.append(samples.get(trig[0][1], trig[0][2]) if trig else 0xFFFF)
        vt.append(row)
        h.append(f'#define {name} {len(vt) - 1}')
    s.extend(['    .balign 2', '    .globl voice_table', 'voice_table:'] +
             ['    .word ' + ', '.join(str(v) for v in row) for row in vt])
    h.append(f'extern const u16 voice_table[{len(vt)}][6];   /* [VOICE_*][character] -> sample id */')
    gain = samples.finish()
    for name, (events, loop_at, total, info) in tunes.items():
        events, kit = build_kit(events, samples)
        data = encode(events, loop_at, total)
        path = os.path.join(GEN, name + '_stream.bin')
        open(path, 'wb').write(data)
        banked.append(f'M {name}_stream {path}')
        h.append(f'extern const u8 {name}_stream[];')
        blob(name + '_kit', kit)
        s.extend(['    .balign 2', f'    .globl {name}', f'{name}:', f'    .long {name}_stream, {name}_kit',
                  f'    .word {name}_stream_page'])
        h.append(f'extern const Music {name};')
        print(f'{name}: {len(data)} bytes, {info}, kit {struct.unpack(">H", kit[:2])[0]} drums / {len(kit)} bytes')
    blob('z80_driver', z80_driver())
    h.append(f'#define Z80_DRIVER_SIZE {len(z80_driver())}')
    s.extend(['    .balign 2', '    .globl sample_table', 'sample_table:'])
    for i, pcm in enumerate(samples.pcm):
        s.append(f'    .long sample{i}')
        s.append(f'    .word {len(pcm)}, sample{i}_page')
    for i, pcm in enumerate(samples.pcm):
        path = os.path.join(GEN, f'sample{i}.bin')
        open(path, 'wb').write(pcm)
        banked.append(f'S sample{i} {path}')
    s.append('    .balign 2')
    h.append('/* data: in the sample window (0x180000), mapped from ROM page `page` */')
    h.append('typedef struct { const u8 *data; u16 len, page; } Sample;')
    h.append(f'extern const Sample sample_table[{len(samples.pcm)}];')
    h.append(f'#define N_SAMPLES {len(samples.pcm)}')
    h.append('#endif')
    open(os.path.join(GEN, 'sounddata.s'), 'w').write('\n'.join(s) + '\n')
    open(os.path.join(GEN, 'sounddata.h'), 'w').write('\n'.join(h) + '\n')
    open(os.path.join(GEN, 'banked_sound.txt'), 'w').write('\n'.join(banked) + '\n')
    print(f'{len(samples.pcm)} samples, {sum(len(p) for p in samples.pcm) // 1024} KB PCM at {PCM_RATE:.0f} Hz, gain {gain:.2f}')


if __name__ == '__main__':
    main()
