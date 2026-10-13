#!/bin/sh
# Fetch an m68k cross compiler into .toolchain/ without root (Debian/Ubuntu).
# Any other m68k gcc also works: make PREFIX=m68k-elf-
set -e
cd "$(dirname "$0")/.."
mkdir -p .toolchain/debs
cd .toolchain/debs
apt-get download gcc-13-m68k-linux-gnu cpp-13-m68k-linux-gnu binutils-m68k-linux-gnu gcc-13-m68k-linux-gnu-base
for f in *.deb; do dpkg -x "$f" ../root; done
# Z80 core for the sound driver simulator (tools/snd/sndsim.c)
cd ..
if [ ! -d src/z80 ]; then
    git clone --depth 1 https://github.com/superzazu/z80.git src/z80
    # the Neo Geo sound CPU banking needs the full 16-bit port address on IN
    python3 -I - <<'PY'
p = 'src/z80/z80.c'
s = open(p).read()
s = s.replace('  *r = z->port_in(z, z->c);', '  z80_port_addr = (z->b << 8) | z->c;\n  *r = z->port_in(z, z->c);')
s = s.replace('  uint8_t val = z->port_in(z, z->c);', '  z80_port_addr = (z->b << 8) | z->c;\n  uint8_t val = z->port_in(z, z->c);')
s = s.replace('    z->a = z->port_in(z, port);', '    z80_port_addr = (z->a << 8) | port;\n    z->a = z->port_in(z, port);')
s = s.replace('#include "z80.h"', '#include "z80.h"\n\nuint16_t z80_port_addr;\n', 1)
open(p, 'w').write(s)
PY
fi
# Musashi 68000 core for the Neo Geo recorder (tools/ngrec)
if [ ! -d src/musashi ]; then
    git clone --depth 1 https://github.com/kstenerud/Musashi.git src/musashi
fi
echo "toolchain ready in .toolchain/root/usr/bin"
