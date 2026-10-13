/*
 * sndsim - runs the Neo Geo Z80 sound driver (m1 ROM) and logs every YM2610
 * register write with a cycle timestamp. Used to translate music and effects.
 * Command bytes are handed over one at a time, each after the driver has read the last.
 *
 *   sndsim M1.bin OUT.log SECONDS [frame:code ...]
 * Log lines: "<z80 cycle> <part 0|1> <reg> <value>"   (hex reg/value)
 *            "<z80 cycle> C <code>"                    (command accepted)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "z80.h"

extern uint16_t z80_port_addr;

#define CYC_PER_FRAME 67584   /* 4 MHz / 59.185 Hz */

static uint8_t rom[0x80000], ram[0x800];
static size_t rom_size;
static unsigned bank[4];
static uint8_t latch, reply, nmi_enabled, nmi_wanted;
static unsigned long latch_read_at;  /* cycle when the driver last read a command byte */
static int latch_pending;            /* a byte is waiting to be read by the driver */
static uint8_t ym_addr[2], ym_reg[2][256];
static uint8_t status;              /* bit0 timer A flag, bit1 timer B flag */
static long ta_left, tb_left;       /* cycles until overflow, <0 = stopped */
static uint8_t adpcm_flags;
static long adpcm_left[7];
static FILE *out;
static z80 cpu;

static uint8_t rb(void *u, uint16_t a)
{
    (void)u;
    if (a < 0x8000) return rom[a % rom_size];
    if (a < 0xc000) return rom[(bank[3] * 0x4000 + (a & 0x3fff)) % rom_size];
    if (a < 0xe000) return rom[(bank[2] * 0x2000 + (a & 0x1fff)) % rom_size];
    if (a < 0xf000) return rom[(bank[1] * 0x1000 + (a & 0x0fff)) % rom_size];
    if (a < 0xf800) return rom[(bank[0] * 0x0800 + (a & 0x07ff)) % rom_size];
    return ram[a & 0x7ff];
}
static void wb(void *u, uint16_t a, uint8_t v)
{
    (void)u;
    if (a >= 0xf800) ram[a & 0x7ff] = v;
}
static long ta_period(void) { return (1024 - ((ym_reg[0][0x24] << 2) | (ym_reg[0][0x25] & 3))) * 72L; }
static long tb_period(void) { return (256 - ym_reg[0][0x26]) * 1152L; }

static void ym_write(int part, uint8_t reg, uint8_t v)
{
    ym_reg[part][reg] = v;
    fprintf(out, "%lu %d %02x %02x\n", cpu.cyc, part, reg, v);
    if (part == 0 && reg == 0x27) {
        if ((v & 1) && ta_left < 0) ta_left = ta_period();
        if (!(v & 1)) ta_left = -1;
        if ((v & 2) && tb_left < 0) tb_left = tb_period();
        if (!(v & 2)) tb_left = -1;
        if (v & 0x10) status &= ~1;
        if (v & 0x20) status &= ~2;
    }
    if (part == 1 && reg == 0x00 && !(v & 0x80)) {
        for (int c = 0; c < 6; c++) if (v & (1 << c)) {
            long start = (ym_reg[1][0x10 + c] | (ym_reg[1][0x18 + c] << 8)) << 8;
            long end = ((ym_reg[1][0x20 + c] | (ym_reg[1][0x28 + c] << 8)) << 8) | 0xff;
            long samples = (end - start + 1) * 2;
            adpcm_left[c] = samples > 0 ? samples * 216 : 1;   /* 18.5 kHz at 4 MHz */
            adpcm_flags &= ~(1 << c);
        }
    }
    if (part == 0 && reg == 0x1c) adpcm_flags &= ~v;          /* flag reset mask */
}
static uint8_t pin(z80 *z, uint8_t p)
{
    (void)z;
    switch (p & 0x0f) {
        case 0x00: nmi_wanted = 0; latch_pending = 0; latch_read_at = cpu.cyc; return latch;
        case 0x04: return status;
        case 0x05: return ym_reg[0][ym_addr[0]];
        case 0x06: return adpcm_flags;
        case 0x08: bank[0] = z80_port_addr >> 8; return 0;
        case 0x09: bank[1] = z80_port_addr >> 8; return 0;
        case 0x0a: bank[2] = z80_port_addr >> 8; return 0;
        case 0x0b: bank[3] = z80_port_addr >> 8; return 0;
    }
    return 0xff;
}
static void pout(z80 *z, uint8_t p, uint8_t v)
{
    (void)z;
    switch (p & 0x0f) {
        case 0x00: latch = 0; break;
        case 0x04: ym_addr[0] = v; break;
        case 0x05: ym_write(0, ym_addr[0], v); break;
        case 0x06: ym_addr[1] = v; break;
        case 0x07: ym_write(1, ym_addr[1], v); break;
        case 0x08: nmi_enabled = !(p & 0x10); break;
        case 0x0c: reply = v; break;
    }
}

int main(int argc, char **argv)
{
    if (argc < 4) { fprintf(stderr, "usage: sndsim M1 OUT SECONDS [frame:code ...]\n"); return 1; }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror(argv[1]); return 1; }
    rom_size = fread(rom, 1, sizeof rom, f);
    fclose(f);
    out = fopen(argv[2], "w");
    if (!out) { perror(argv[2]); return 1; }
    double secs = atof(argv[3]);
    struct { long frame; int code; } cmds[256];
    int ncmds = 0;
    for (int i = 4; i < argc && ncmds < 256; i++) {
        unsigned code;
        if (sscanf(argv[i], "%ld:%x", &cmds[ncmds].frame, &code) == 2) cmds[ncmds++].code = code;
    }
    bank[0] = 0x1e; bank[1] = 0x0e; bank[2] = 0x06; bank[3] = 0x02;
    ta_left = tb_left = -1;
    z80_init(&cpu);
    cpu.read_byte = rb; cpu.write_byte = wb; cpu.port_in = pin; cpu.port_out = pout;
    unsigned long end = (unsigned long)(secs * 4000000.0);
    int next = 0;
    while (cpu.cyc < end) {
        unsigned long before = cpu.cyc;
        /* like the 68000, send the next byte only after the driver has taken the previous one
           (several bytes queued for the same frame would otherwise overwrite each other) */
        if (next < ncmds && cpu.cyc >= (unsigned long)cmds[next].frame * CYC_PER_FRAME
            && !latch_pending && cpu.cyc >= latch_read_at + 2000) {
            latch_pending = 1;
            latch = cmds[next].code;
            nmi_wanted = 1;
            fprintf(out, "%lu C %02x\n", cpu.cyc, latch);
            next++;
        }
        if (nmi_wanted && nmi_enabled) { nmi_wanted = 0; z80_gen_nmi(&cpu); }
        cpu.int_pending = (status & (ym_reg[0][0x27] >> 2) & 3) != 0;
        z80_step(&cpu);
        long d = (long)(cpu.cyc - before);
        if (ta_left >= 0 && (ta_left -= d) <= 0) { if (ym_reg[0][0x27] & 4) status |= 1; ta_left += ta_period(); }
        if (tb_left >= 0 && (tb_left -= d) <= 0) { if (ym_reg[0][0x27] & 8) status |= 2; tb_left += tb_period(); }
        for (int c = 0; c < 6; c++)
            if (adpcm_left[c] > 0 && (adpcm_left[c] -= d) <= 0) adpcm_flags |= 1 << c;
    }
    fclose(out);
    return 0;
}
