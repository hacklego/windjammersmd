"""Neo Geo ROM set loading and graphics decoding helpers."""
import os, zipfile, zlib

def _crc(data):
    return zlib.crc32(data) & 0xffffffff

class RomSet:
    """Loads a Neo Geo set from a directory or a MAME .zip, locating files by CRC32."""
    def __init__(self, path):
        self.files = {}
        if os.path.isdir(path):
            for name in os.listdir(path):
                full = os.path.join(path, name)
                if os.path.isfile(full) and os.path.getsize(full) <= 16 << 20:
                    with open(full, 'rb') as f:
                        self.files[name.lower()] = f.read()
        else:
            with zipfile.ZipFile(path) as z:
                for info in z.infolist():
                    if not info.is_dir():
                        self.files[os.path.basename(info.filename).lower()] = z.read(info)
        self.by_crc = {_crc(d): d for d in self.files.values()}

    def get(self, crc, names=()):
        if crc in self.by_crc:
            return self.by_crc[crc]
        for n in names:
            if n.lower() in self.files:
                return self.files[n.lower()]
        raise FileNotFoundError('ROM file with CRC %08x (%s) not found' % (crc, '/'.join(names)))

def interleave_c(codd, ceven):
    """Combine an odd/even C ROM pair into 128-byte tiles (bitplanes 0,1 from odd; 2,3 from even)."""
    return codd, ceven

def decode_tile(codd, ceven, tile):
    """Decode one 16x16 Neo Geo sprite tile -> list of 256 color indexes (row major)."""
    base = tile * 64
    out = [0] * 256
    # 4 blocks of 8x8: top-right, bottom-right, top-left, bottom-left
    for blk, (bx, by) in enumerate(((8, 0), (8, 8), (0, 0), (0, 8))):
        for row in range(8):
            o = base + blk * 16 + row * 2
            p0, p1 = codd[o], codd[o + 1]
            p2, p3 = ceven[o], ceven[o + 1]
            y = by + row
            for bit in range(8):
                c = ((p0 >> bit) & 1) | (((p1 >> bit) & 1) << 1) | (((p2 >> bit) & 1) << 2) | (((p3 >> bit) & 1) << 3)
                out[y * 16 + bx + bit] = c
    return out

def decode_fix(srom, tile):
    """Decode an 8x8 fix layer tile (4bpp, column-pair order) -> 64 indexes."""
    base = tile * 32
    out = [0] * 64
    # bytes are arranged in columns: x pairs (4,5),(6,7),(0,1),(2,3); each byte = 2 pixels (low nibble = left)
    for ci, x in enumerate((4, 6, 0, 2)):
        for y in range(8):
            b = srom[base + ci * 8 + y]
            out[y * 8 + x] = b & 15
            out[y * 8 + x + 1] = b >> 4
    return out

def ng_color(w):
    """Neo Geo palette word -> (r,g,b) 8-bit."""
    dark = (w >> 15) & 1
    r = ((w >> 8) & 15) << 1 | ((w >> 14) & 1)
    g = ((w >> 4) & 15) << 1 | ((w >> 13) & 1)
    b = (w & 15) << 1 | ((w >> 12) & 1)
    def ex(v):
        v = (v << 1) | (0 if dark else 1)  # 6 bit approx
        return (v * 255) // 63
    return ex(r), ex(g), ex(b)
