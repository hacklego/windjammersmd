#!/usr/bin/env python3
"""Pad a Mega Drive ROM to a 128KB multiple and fix the header ROM-end and checksum."""
import struct, sys

data = bytearray(open(sys.argv[1], 'rb').read())
size = (len(data) + 0x1FFFF) & ~0x1FFFF
data += b'\xff' * (size - len(data))
struct.pack_into('>I', data, 0x1A4, size - 1)
csum = 0
for i in range(0x200, size, 2):
    csum = (csum + ((data[i] << 8) | data[i + 1])) & 0xFFFF
struct.pack_into('>H', data, 0x18E, csum)
open(sys.argv[1], 'wb').write(data)
print('%s: %d KB, checksum %04X' % (sys.argv[1], size // 1024, csum))
