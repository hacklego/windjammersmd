/*
 * ngrec - minimal headless Neo Geo (MVS) that runs the original game code and records
 * what it puts on screen, so cutscenes and attract sequences can be converted 1:1 from
 * the user's own ROM at build time. No pixels are rendered here: each recorded frame is
 * the video RAM, palette RAM and a few video registers (tools/ngrender.py draws them).
 * The Z80 runs the real sound driver; every sound command the 68000 sends is logged.
 *
 *   ngrec -p P1 -b BIOS -m M1 -c C1 -c C2 [-c C3 -c C4 ...] -s S1 -S SFIX -l LO -o OUT -n FRAMES
 *         [-r first-last]... [-e every nth frame] [-i inputs.txt] [-X FROM=TO]... [-F fixdump] [-t]
 *         [-R ramdump] [-V vramdump] [-N (no rendered frames)] [-H hide sprites a-b]... [-W lo-hi file]
 *         [-P from (profile)] [-B c0-c1,r0-r1 (blank fix cells)]... [-T a-b:delta (tile offset)]...
 *         [-M first-last/every:addr=value (poke a work RAM byte, hex address and value)]...
 *         [-O lo-hi (draw only sprites in palettes lo..hi, hex)]
 *
 * inputs.txt lines: "<first frame> <last frame> <key>[,<key>...]" with keys
 *   coin1 coin2 start1 start2 select1 up down left right a b c d  (prefix p2. for player 2)
 * Output: OUT.frames (per recorded frame, host byte order: u32 frame number, u16 flags (bit0 fix
 *   layer from the game ROM, bit1 palette bank 1, bit14 pixels as in the previous recorded frame,
 *   bit15 palette as before), unless bit14: 320x224 u16 pixels (palette << 4 | colour, 0 =
 *   backdrop, bit 12 set on fix layer pixels), unless bit15: 4096 u16 palette words),
 *   OUT.snd ("<frame> <hex byte>" per sound command).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "m68k.h"
#include "z80.h"

extern uint16_t z80_port_addr;

#define LINES 264
#define CYC_LINE 768            /* 12 MHz 68000, 384 pixel clocks of 6 MHz per line */
#define Z80_CYC_LINE 256        /* 4 MHz */

static uint8_t *prom, *bios, m1[0x80000];
static size_t prom_size, m1_size;
static uint8_t ram[0x10000], sram[0x10000];
static uint16_t vram[0x8800];          /* 0x0000-0x7FFF and 0x8000-0x87FF */
static uint16_t pal[2][0x1000];
static uint16_t vram_addr, vram_mod;
static int pal_bank, bios_vectors = 1, fix_game = 0, display = 1;
static unsigned lspc_mode, anim_speed, anim_counter, anim_timer;
static uint32_t timer_reload, timer_counter;
static int timer_irq_on, irq_pending;   /* bit0 vblank (level 1), bit1 timer (level 2) */
static int line;
static long frame;
static uint8_t snd_latch, snd_reply;
static uint32_t prom_bank = 0x100000;  /* 0x200000 window offset for >1MB P-ROMs */

/* inputs */
struct ev { long a, b; int port; uint8_t mask; };
static struct ev evs[4096];
static int nevs;

/* uPD4990A calendar (the MVS BIOS insists on a working clock) */
static uint64_t rtc_shift;
static int rtc_mode, rtc_clk, rtc_stb, rtc_din;
static unsigned rtc_tp_div = 123;      /* lines per half period of the time pulse (64 Hz) */
static unsigned rtc_cmd;
static uint8_t rtc_tp;

static FILE *frames_out, *snd_out, *ram_out, *spr_out, *watch_out;
static unsigned watch_lo = 1, watch_hi = 0;


/* ---------------------------------------------------------------------------- Z80 side */
static z80 zcpu;
static uint8_t zram[0x800];
static unsigned zbank[4] = { 0x1e, 0x0e, 0x06, 0x02 };
static uint8_t z_nmi_en, z_nmi_req, ym_addr[2], ym_reg[2][256], ym_status, adpcm_flags;
static long ta_left = -1, tb_left = -1;

static uint8_t zrb(void *u, uint16_t a)
{
    (void)u;
    if (a < 0x8000) return m1[a % m1_size];
    if (a < 0xc000) return m1[(zbank[3] * 0x4000 + (a & 0x3fff)) % m1_size];
    if (a < 0xe000) return m1[(zbank[2] * 0x2000 + (a & 0x1fff)) % m1_size];
    if (a < 0xf000) return m1[(zbank[1] * 0x1000 + (a & 0x0fff)) % m1_size];
    if (a < 0xf800) return m1[(zbank[0] * 0x0800 + (a & 0x07ff)) % m1_size];
    return zram[a & 0x7ff];
}
static void zwb(void *u, uint16_t a, uint8_t v) { (void)u; if (a >= 0xf800) zram[a & 0x7ff] = v; }
static long ta_period(void) { return (1024 - ((ym_reg[0][0x24] << 2) | (ym_reg[0][0x25] & 3))) * 72L; }
static long tb_period(void) { return (256 - ym_reg[0][0x26]) * 1152L; }
static void ym_write(int part, uint8_t reg, uint8_t v)
{
    ym_reg[part][reg] = v;
    if (part == 0 && reg == 0x27) {
        if ((v & 1) && ta_left < 0) ta_left = ta_period();
        if (!(v & 1)) ta_left = -1;
        if ((v & 2) && tb_left < 0) tb_left = tb_period();
        if (!(v & 2)) tb_left = -1;
        if (v & 0x10) ym_status &= ~1;
        if (v & 0x20) ym_status &= ~2;
    }
    if (part == 1 && reg == 0 && !(v & 0x80)) adpcm_flags |= v & 0x3f;   /* samples end at once */
    if (part == 0 && reg == 0x1c) adpcm_flags &= ~v;
}
static uint8_t zin(z80 *z, uint8_t p)
{
    (void)z;
    switch (p & 0x0f) {
        case 0x00: return snd_latch;
        case 0x04: return ym_status;
        case 0x05: return ym_reg[0][ym_addr[0]];
        case 0x06: return adpcm_flags;
        case 0x08: zbank[0] = z80_port_addr >> 8; return 0;
        case 0x09: zbank[1] = z80_port_addr >> 8; return 0;
        case 0x0a: zbank[2] = z80_port_addr >> 8; return 0;
        case 0x0b: zbank[3] = z80_port_addr >> 8; return 0;
    }
    return 0xff;
}
static void zout(z80 *z, uint8_t p, uint8_t v)
{
    (void)z;
    switch (p & 0x0f) {
        case 0x00: snd_latch = 0; break;
        case 0x04: ym_addr[0] = v; break;
        case 0x05: ym_write(0, ym_addr[0], v); break;
        case 0x06: ym_addr[1] = v; break;
        case 0x07: ym_write(1, ym_addr[1], v); break;
        case 0x08: z_nmi_en = !(p & 0x10); break;
        case 0x0c: snd_reply = v; break;
    }
}
static void z80_run(long cycles)
{
    unsigned long end = zcpu.cyc + cycles;
    while (zcpu.cyc < end) {
        unsigned long before = zcpu.cyc;
        if (z_nmi_req && z_nmi_en) { z_nmi_req = 0; z80_gen_nmi(&zcpu); }
        zcpu.int_pending = (ym_status & (ym_reg[0][0x27] >> 2) & 3) != 0;
        z80_step(&zcpu);
        long d = (long)(zcpu.cyc - before);
        if (ta_left >= 0 && (ta_left -= d) <= 0) { if (ym_reg[0][0x27] & 4) ym_status |= 1; ta_left += ta_period(); }
        if (tb_left >= 0 && (tb_left -= d) <= 0) { if (ym_reg[0][0x27] & 8) ym_status |= 2; tb_left += tb_period(); }
    }
}

/* ---------------------------------------------------------------------------- 68000 side */
static void update_irq(void)
{
    m68k_set_irq((irq_pending & 1) ? 1 : (irq_pending & 2) ? 2 : 0);
}

static uint16_t lspc_read(unsigned a)
{
    switch (a & 6) {
        case 0: case 2: return vram[vram_addr < 0x8800 ? vram_addr : vram_addr & 0x87FF];
        case 4: return vram_mod;
        default: {
            unsigned cnt = (line + 0xF8) & 0x1FF;
            return (cnt << 7) | (anim_counter & 7);
        }
    }
}
static void lspc_write(unsigned a, uint16_t v)
{
    switch (a & 0xE) {
        case 0x0: vram_addr = v; break;
        case 0x2:
            if (vram_addr < 0x8000) vram[vram_addr] = v;
            else vram[0x8000 + (vram_addr & 0x7FF)] = v;
            vram_addr = (vram_addr & 0x8000) | ((vram_addr + vram_mod) & 0x7FFF);
            break;
        case 0x4: vram_mod = v; break;
        case 0x6: lspc_mode = v; anim_speed = v >> 8; timer_irq_on = (v >> 4) & 1; break;
        case 0x8: timer_reload = (timer_reload & 0xFFFF) | ((uint32_t)v << 16); break;
        case 0xA: timer_reload = (timer_reload & 0xFFFF0000) | v; if (lspc_mode & 0x20) timer_counter = timer_reload; break;
        case 0xC: irq_pending &= ~(((v & 4) ? 1 : 0) | ((v & 2) ? 2 : 0)); update_irq(); break;
        case 0xE: break;
    }
}

static int key_down(int port, uint8_t mask)
{
    for (int i = 0; i < nevs; i++)
        if (evs[i].port == port && evs[i].mask == mask && frame >= evs[i].a && frame <= evs[i].b) return 1;
    return 0;
}
static uint8_t port_value(int port)
{
    uint8_t v = port == 2 ? 0x3F : 0xFF;   /* status A: rtc bits set below */
    for (int i = 0; i < nevs; i++)
        if (evs[i].port == port && frame >= evs[i].a && frame <= evs[i].b) v &= ~evs[i].mask;
    (void)key_down;
    return v;
}

static unsigned read8(unsigned a)
{
    a &= 0xFFFFFF;
    if (a < 0x80) return bios_vectors ? bios[a] : prom[a];
    if (a < 0x100000) return a < prom_size ? prom[a] : 0xFF;
    if (a < 0x200000) return ram[a & 0xFFFF];
    if (a < 0x300000) { uint32_t o = prom_bank + (a & 0xFFFFF); return o < prom_size ? prom[o] : 0xFF; }
    if (a < 0x320000) {
        if ((a & 0x81) == 0x00) return port_value(0);      /* P1 */
        if ((a & 0x81) == 0x01) return 0xFF;               /* DIP switches, all off */
        if ((a & 0x81) == 0x81) return 0xC0;               /* system type: test off, ... */
        return 0xFF;
    }
    if (a < 0x340000) {
        if (!(a & 1)) return snd_reply;
        /* status A: coins/service active low, bit6 RTC time pulse, bit7 RTC data */
        return (port_value(2) & 0x3F) | (rtc_tp << 6) | ((rtc_shift & 1) << 7);
    }
    if (a < 0x380000) return (a & 1) ? 0xFF : port_value(1);
    if (a < 0x3A0000) return (a & 1) ? 0xFF : (port_value(3) & 0x7F) | 0x80;   /* status B, MVS */
    if (a < 0x3C0000) return 0xFF;
    if (a < 0x3E0000) { uint16_t w = lspc_read(a); return (a & 1) ? (w & 0xFF) : (w >> 8); }
    if (a >= 0x400000 && a < 0x500000) { uint16_t w = pal[pal_bank][(a >> 1) & 0xFFF]; return (a & 1) ? (w & 0xFF) : (w >> 8); }
    if (a >= 0x800000 && a < 0xC00000) return 0xFF;      /* no memory card */
    if (a >= 0xC00000 && a < 0xD00000) return bios[a & 0x1FFFF];
    if (a >= 0xD00000 && a < 0xE00000) return sram[a & 0xFFFF];
    return 0xFF;
}

static void rtc_write(uint8_t v)
{
    int din = v & 1, clk = (v >> 1) & 1, stb = (v >> 2) & 1;
    if (clk && !rtc_clk) {                       /* rising edge: the 4-bit command register always
                                                    shifts; the 48-bit data register in shift mode */
        if (rtc_mode == 1)
            rtc_shift = ((rtc_shift >> 1) & 0x7FFFFFFFFFFFULL) | ((uint64_t)(rtc_cmd & 1) << 47);
        rtc_cmd = (rtc_cmd >> 1) | (din << 3);
    }
    if (stb && !rtc_stb && !clk) {
        unsigned cmd = rtc_cmd;
        switch (cmd) {
            case 0: rtc_mode = 0; break;                                   /* register hold */
            case 1: rtc_mode = 1; break;                                   /* shift */
            case 2: rtc_mode = 2; break;                                   /* time set: ignored */
            case 3: rtc_mode = 3;                                          /* time read */
                /* 1994-10-09 12:00:00, sunday: BCD sec, min, hour, day, month << 4 | weekday, year */
                rtc_shift = (0x12ULL << 16) | (0x09ULL << 24) | (0xA0ULL << 32) | (0x94ULL << 40);
                break;
            default:
                if (cmd <= 7) rtc_tp_div = (unsigned[]){ 123, 31, 4, 2 }[cmd - 4];
                else rtc_tp_div = 7867;          /* interval modes: 1 s and up, close enough */
        }
    }
    rtc_clk = clk; rtc_stb = stb; rtc_din = din;
}

static void write8(unsigned a, unsigned v)
{
    a &= 0xFFFFFF; v &= 0xFF;
    if (a >= 0x100000 && a < 0x200000) { ram[a & 0xFFFF] = v; return; }
    if (a >= 0x200000 && a < 0x300000) { prom_bank = 0x100000 * (1 + (v & 7)); return; }
    if (a >= 0x320000 && a < 0x340000) {
        if (!(a & 1)) {
            snd_latch = v; z_nmi_req = 1;
            if (snd_out) fprintf(snd_out, "%ld %02x\n", frame, v);
        }
        return;
    }
    if (a >= 0x380000 && a < 0x3A0000) {
        if ((a & 0x7F) == 0x51) rtc_write(v);
        return;
    }
    if (a >= 0x3A0000 && a < 0x3C0000) {
        switch (a & 0x1F) {
            case 0x03: bios_vectors = 1; break;   /* SWPBIOS */
            case 0x13: bios_vectors = 0; break;   /* SWPROM */
            case 0x0B: fix_game = 0; break;       /* BRDFIX: system fix ROM */
            case 0x1B: fix_game = 1; break;       /* CRTFIX: cartridge fix ROM */
            case 0x0F: pal_bank = 1; break;
            case 0x1F: pal_bank = 0; break;
        }
        return;
    }
    if (a >= 0x3C0000 && a < 0x3E0000) {          /* byte writes to the LSPC duplicate the byte */
        lspc_write(a, (uint16_t)(v | (v << 8)));
        return;
    }
    if (a >= 0x400000 && a < 0x500000) {
        uint16_t *p = &pal[pal_bank][(a >> 1) & 0xFFF];
        *p = (a & 1) ? ((*p & 0xFF00) | v) : ((*p & 0xFF) | (v << 8));
        return;
    }
    if (a >= 0xD00000 && a < 0xE00000) { sram[a & 0xFFFF] = v; return; }
}

unsigned int m68k_read_memory_8(unsigned int a) { return read8(a); }
unsigned int m68k_read_memory_16(unsigned int a)
{
    a &= 0xFFFFFF;
    if (a >= 0x3C0000 && a < 0x3E0000) return lspc_read(a);
    if (a >= 0x400000 && a < 0x500000) return pal[pal_bank][(a >> 1) & 0xFFF];
    return (read8(a) << 8) | read8(a + 1);
}
unsigned int m68k_read_memory_32(unsigned int a) { return (m68k_read_memory_16(a) << 16) | m68k_read_memory_16(a + 2); }
static void watch(unsigned a, unsigned v, int size)
{
    unsigned m = a & 0xFFFFFF;
    if (watch_out && m >= watch_lo && m <= watch_hi)
        fprintf(watch_out, "%ld %06x %06x %d %x\n", frame, m68k_get_reg(NULL, M68K_REG_PPC), m, size, v);
}
void m68k_write_memory_8(unsigned int a, unsigned int v) { watch(a, v, 1); write8(a, v); }
void m68k_write_memory_16(unsigned int a, unsigned int v)
{
    watch(a, v, 2);
    a &= 0xFFFFFF;
    if (a >= 0x3C0000 && a < 0x3E0000) { lspc_write(a, v); return; }
    if (a >= 0x400000 && a < 0x500000) { pal[pal_bank][(a >> 1) & 0xFFF] = v; return; }
    if (a >= 0x320000 && a < 0x340000) { write8(a, v >> 8); return; }
    write8(a, v >> 8); write8(a + 1, v);
}
void m68k_write_memory_32(unsigned int a, unsigned int v) { m68k_write_memory_16(a, v >> 16); m68k_write_memory_16(a + 2, v); }
unsigned int m68k_read_disassembler_16(unsigned int a) { return m68k_read_memory_16(a); }
unsigned int m68k_read_disassembler_32(unsigned int a) { return m68k_read_memory_32(a); }
unsigned int m68k_read_disassembler_8(unsigned int a) { return read8(a); }


/* ---------------------------------------------------------------------------- renderer */
static uint8_t *crom_odd, *crom_even, *srom_game, *srom_sys, *zoomy;
static size_t crom_tiles;
static uint16_t screen[224][320];   /* palette << 4 | colour index; 0 = backdrop */

static const uint8_t zoom_x_tables[16][16] = {
    { 0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0 }, { 0,0,0,0,1,0,0,0,1,0,0,0,0,0,0,0 },
    { 0,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0 }, { 0,0,1,0,1,0,0,0,1,0,0,0,1,0,0,0 },
    { 0,0,1,0,1,0,0,0,1,0,0,0,1,0,1,0 }, { 0,0,1,0,1,0,1,0,1,0,0,0,1,0,1,0 },
    { 0,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0 }, { 1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0 },
    { 1,0,1,0,1,0,1,0,1,1,1,0,1,0,1,0 }, { 1,0,1,1,1,0,1,0,1,1,1,0,1,0,1,0 },
    { 1,0,1,1,1,0,1,0,1,1,1,0,1,0,1,1 }, { 1,0,1,1,1,0,1,1,1,1,1,0,1,0,1,1 },
    { 1,0,1,1,1,0,1,1,1,1,1,0,1,1,1,1 }, { 1,1,1,1,1,0,1,1,1,1,1,0,1,1,1,1 },
    { 1,1,1,1,1,0,1,1,1,1,1,1,1,1,1,1 }, { 1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1 },
};

static int tile_pixel(uint32_t tile, int x, int y)
{
    if (tile >= crom_tiles) tile %= crom_tiles;
    /* 4 blocks of 8x8: top-right, bottom-right, top-left, bottom-left; 2 bytes per row */
    int blk = (x < 8 ? 2 : 0) + (y >= 8);
    size_t o = (size_t)tile * 64 + blk * 16 + (y & 7) * 2;
    int bit = x & 7;
    return ((crom_odd[o] >> bit) & 1) | (((crom_odd[o + 1] >> bit) & 1) << 1)
         | (((crom_even[o] >> bit) & 1) << 2) | (((crom_even[o + 1] >> bit) & 1) << 3);
}

static int sprite_on_line(int scanline, int y, int rows)
{
    if (rows == 0) return 0;
    int max_y = (y + rows * 0x10 - 1) & 0x1ff;
    return (max_y >= y && scanline >= y && scanline <= max_y) || (max_y < y && (scanline >= y || scanline <= max_y));
}

/* fix layer text substitutions: "FROM=TO", '?' in FROM matches any character; TO is padded
 * with spaces. Text is drawn with the game font: tile 0x300 + ASCII code. */
static int hide[16][2], nhide;
static int toff[8][3], ntoff;
static int only_lo = -1, only_hi = -1;
static int nkeep = 0; static unsigned keep[8][2];  /* -K lo-hi: draw only sprites whose first tile is in one of these ranges */  /* -O: draw only sprites in these palettes, no fix layer */        /* sprites a..b drawn with their tile numbers + delta */
static int blank[16][4], nblank;     /* fix layer cells to leave empty: c0, c1, r0, r1 */
static char subst_from[16][48], subst_to[16][48];
static int nsubst;
static uint16_t fixmap[40][32];

static void apply_subst(void)
{
    for (int col = 0; col < 40; col++)
        for (int row = 0; row < 32; row++) fixmap[col][row] = vram[0x7000 + col * 32 + row];
    for (int k = 0; k < nblank; k++)
        for (int col = blank[k][0]; col <= blank[k][1] && col < 40; col++)
            for (int row = blank[k][2]; row <= blank[k][3] && row < 32; row++) fixmap[col][row] = 0x00FF;
    for (int k = 0; k < nsubst; k++) {
        int len = (int)strlen(subst_from[k]);
        for (int row = 0; row < 32; row++)
            for (int col = 0; col + len <= 40; col++) {
                int ok = 1;
                for (int i = 0; i < len && ok; i++) {
                    uint16_t t = fixmap[col + i][row] & 0xFFF;
                    ok = (t >> 8) == 3 && (subst_from[k][i] == '?' || (t & 0xFF) == (uint8_t)subst_from[k][i]);
                }
                if (!ok) continue;
                int tl = (int)strlen(subst_to[k]);
                for (int i = 0; i < len; i++) {
                    uint8_t ch = i < tl ? (uint8_t)subst_to[k][i] : ' ';
                    fixmap[col + i][row] = (fixmap[col + i][row] & 0xF000) | 0x300 | ch;
                }
            }
    }
}

static void render(void)
{
    memset(screen, 0, sizeof screen);
    apply_subst();
    for (int sl = 0; sl < 224; sl++) {
        int scanline = sl + 16;
        int x = 0, y = 0, rows = 0, zoom_y = 0, x_zoom = 0;
        uint16_t *out = screen[sl];
        for (int n = 1; n < 381; n++) {
            uint16_t yc = vram[0x8200 + n], zc = vram[0x8000 + n];
            int hidden = 0;
            for (int h = 0; h < nhide; h++) if (n >= hide[h][0] && n <= hide[h][1]) hidden = 1;
            if (yc & 0x40) x = (x + x_zoom + 1) & 0x1ff;
            else { y = 0x200 - (yc >> 7); x = vram[0x8400 + n] >> 7; zoom_y = zc & 0xff; rows = yc & 0x3f; }
            x_zoom = (zc >> 8) & 0x0f;
            if (x >= 0x140 && x <= 0x1f0) continue;
            if (only_lo >= 0) {
                uint16_t a0 = vram[(n << 6) | 1] >> 8;
                if (a0 < only_lo || a0 > only_hi) hidden = 1;
            }
            if (nkeep) {
                unsigned t0 = vram[n << 6] | ((vram[(n << 6) | 1] << 12) & 0xF0000);
                int in = 0;
                for (int k = 0; k < nkeep; k++) if (t0 >= keep[k][0] && t0 <= keep[k][1]) in = 1;
                if (!in) hidden = 1;
            }
            if (hidden || !sprite_on_line(scanline, y, rows)) continue;
            int sprite_line = (scanline - y) & 0x1ff, zoom_line = sprite_line & 0xff, invert = sprite_line & 0x100;
            if (invert) zoom_line ^= 0xff;
            if (rows > 0x20) {
                zoom_line %= (zoom_y + 1) << 1;
                if (zoom_line > zoom_y) { zoom_line = ((zoom_y + 1) << 1) - 1 - zoom_line; invert = !invert; }
            }
            uint8_t yt = zoomy[(zoom_y << 8) | zoom_line];
            int sy = yt & 0x0f, tile = yt >> 4;
            if (invert) { sy ^= 0x0f; tile ^= 0x1f; }
            uint16_t attr = vram[(n << 6) | (tile << 1) | 1];
            uint32_t code = ((uint32_t)(attr << 12) & 0xF0000) | vram[(n << 6) | (tile << 1)];
            for (int k = 0; k < ntoff; k++) if (n >= toff[k][0] && n <= toff[k][1]) code += toff[k][2];
            if (attr & 8) code = (code & ~7u) | (anim_counter & 7);
            else if (attr & 4) code = (code & ~3u) | (anim_counter & 3);
            if (attr & 2) sy ^= 0x0f;
            const uint8_t *zx = zoom_x_tables[x_zoom];
            int px = x;
            for (int i = 0; i < 16; i++) {
                int sx = (attr & 1) ? 15 - i : i;
                if (!zx[sx]) continue;
                int c = tile_pixel(code, sx, sy);
                if (c && (px & 0x1ff) < 320) out[px & 0x1ff] = ((attr >> 8) << 4) | c;
                px++;
            }
        }
        if (only_lo >= 0) continue;
        /* fix layer */
        const uint8_t *srom = fix_game ? srom_game : srom_sys;
        int row = scanline >> 3, fy = scanline & 7;
        for (int col = 0; col < 40; col++) {
            uint16_t e = fixmap[col][row];
            uint32_t t = e & 0xFFF;
            for (int fx = 0; fx < 8; fx++) {
                static const int colsel[8] = { 2, 2, 3, 3, 0, 0, 1, 1 };
                uint8_t b = srom[t * 32 + colsel[fx] * 8 + fy];
                int c = (fx & 1) ? b >> 4 : b & 15;
                if (c) out[col * 8 + fx] = 0x1000 | ((e >> 12) << 4) | c;
            }
        }
    }
}

/* ---------------------------------------------------------------------------- main */
static uint8_t *load(const char *path, size_t *size, int swap)
{
    FILE *f = fopen(path, "rb");
    if (!f) { perror(path); exit(1); }
    fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
    uint8_t *d = malloc(n);
    if (fread(d, 1, n, f) != (size_t)n) { perror(path); exit(1); }
    fclose(f);
    if (swap) for (long i = 0; i + 1 < n; i += 2) { uint8_t t = d[i]; d[i] = d[i + 1]; d[i + 1] = t; }
    if (size) *size = n;
    return d;
}

static const struct { const char *name; int port; uint8_t mask; } keys[] = {
    { "up", 0, 1 }, { "down", 0, 2 }, { "left", 0, 4 }, { "right", 0, 8 },
    { "a", 0, 16 }, { "b", 0, 32 }, { "c", 0, 64 }, { "d", 0, 128 },
    { "p2.up", 1, 1 }, { "p2.down", 1, 2 }, { "p2.left", 1, 4 }, { "p2.right", 1, 8 },
    { "p2.a", 1, 16 }, { "p2.b", 1, 32 }, { "p2.c", 1, 64 }, { "p2.d", 1, 128 },
    { "coin1", 2, 1 }, { "coin2", 2, 2 }, { "service", 2, 4 },
    { "start1", 3, 1 }, { "select1", 3, 2 }, { "start2", 3, 4 }, { "select2", 3, 8 },
};

static void load_inputs(const char *path)
{
    FILE *f = fopen(path, "r");
    char ln[256], ks[200];
    long a, b;
    if (!f) { perror(path); exit(1); }
    while (fgets(ln, sizeof ln, f)) {
        if (ln[0] == '#' || sscanf(ln, "%ld %ld %199s", &a, &b, ks) != 3) continue;
        for (char *k = strtok(ks, ","); k; k = strtok(NULL, ",")) {
            size_t i;
            for (i = 0; i < sizeof keys / sizeof keys[0]; i++)
                if (!strcmp(k, keys[i].name)) break;
            if (i == sizeof keys / sizeof keys[0]) { fprintf(stderr, "unknown key %s\n", k); exit(1); }
            if (nevs < 4096) evs[nevs++] = (struct ev){ a, b, keys[i].port, keys[i].mask };
        }
    }
    fclose(f);
}

static FILE *fixdump;
static void dump_fix(void)
{
    fprintf(fixdump, "frame %ld\n", frame);
    for (int row = 2; row < 30; row++) {
        int any = 0;
        for (int col = 0; col < 40; col++) if ((vram[0x7000 + col * 32 + row] & 0xFFF) != 0x20 && (vram[0x7000 + col * 32 + row] & 0xFFF) != 0x320 && (vram[0x7000 + col * 32 + row] & 0xFFF) != 0xFF) any = 1;
        if (!any) continue;
        fprintf(fixdump, "%2d:", row);
        for (int col = 0; col < 40; col++) fprintf(fixdump, " %04x", vram[0x7000 + col * 32 + row]);
        fprintf(fixdump, "\n");
    }
}

static uint16_t prev_screen[224][320], prev_pal[0x1000];
static int have_prev;

static void write_frame(void)
{
    if (fixdump) dump_fix();
    uint32_t fn = (uint32_t)frame;
    render();
    int same_px = have_prev && !memcmp(screen, prev_screen, sizeof screen);
    int same_pal = have_prev && !memcmp(pal[pal_bank], prev_pal, sizeof prev_pal);
    uint16_t fl = fix_game | (pal_bank << 1) | (same_px << 14) | (same_pal << 15);
    fwrite(&fn, 4, 1, frames_out);
    fwrite(&fl, 2, 1, frames_out);
    if (!same_px) fwrite(screen, 2, 224 * 320, frames_out);      /* host byte order */
    if (!same_pal) fwrite(pal[pal_bank], 2, 0x1000, frames_out);
    memcpy(prev_screen, screen, sizeof screen);
    memcpy(prev_pal, pal[pal_bank], sizeof prev_pal);
    have_prev = 1;
}

int main(int argc, char **argv)
{
    const char *pp = 0, *bp = 0, *mp = 0, *op = 0, *ip = 0, *cp[8], *sp = 0, *ssp = 0, *lp = 0;
    int ncp = 0;
    long nframes = 600, ranges[64][2], every = 1;
    int nranges = 0, trace = 0, dis_count = 0, no_frames = 0, prof = 0, npoke = 0;
    long poke[32][5];                   /* first, last, every, address, value */
    long copy[8][5]; int ncopy = 0;     /* first, last, from, to (words), add */
    long prof_from = 0;
    unsigned dis_addr = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-p")) pp = argv[++i];
        else if (!strcmp(argv[i], "-b")) bp = argv[++i];
        else if (!strcmp(argv[i], "-m")) mp = argv[++i];
        else if (!strcmp(argv[i], "-o")) op = argv[++i];
        else if (!strcmp(argv[i], "-i")) ip = argv[++i];
        else if (!strcmp(argv[i], "-n")) nframes = atol(argv[++i]);
        else if (!strcmp(argv[i], "-t")) trace = 1;
        else if (!strcmp(argv[i], "-e")) every = atol(argv[++i]);
        else if (!strcmp(argv[i], "-F")) fixdump = fopen(argv[++i], "w");
        else if (!strcmp(argv[i], "-R")) ram_out = fopen(argv[++i], "wb");       /* u32 frame + 64 KB work RAM */
        else if (!strcmp(argv[i], "-V")) spr_out = fopen(argv[++i], "wb");       /* u32 frame + VRAM + palettes (host order) */
        else if (!strcmp(argv[i], "-N")) no_frames = 1;
        else if (!strcmp(argv[i], "-B") && nblank < 16) {       /* -B c0-c1,r0-r1: blank fix cells */
            int *b = blank[nblank];
            if (sscanf(argv[++i], "%d-%d,%d-%d", &b[0], &b[1], &b[2], &b[3]) == 4) nblank++;
        }
        else if (!strcmp(argv[i], "-O")) sscanf(argv[++i], "%x-%x", &only_lo, &only_hi);
        else if (!strcmp(argv[i], "-K") && nkeep < 8) {         /* -K lo-hi (hex tile codes) */
            if (sscanf(argv[++i], "%x-%x", &keep[nkeep][0], &keep[nkeep][1]) == 2) nkeep++;
        }
        else if (!strcmp(argv[i], "-T") && ntoff < 8) {         /* -T a-b:delta (hex) */
            if (sscanf(argv[++i], "%d-%d:%x", &toff[ntoff][0], &toff[ntoff][1], &toff[ntoff][2]) == 3) ntoff++;
        }
        else if (!strcmp(argv[i], "-H") && nhide < 16) {        /* -H a-b: do not draw sprites a..b */
            if (sscanf(argv[++i], "%d-%d", &hide[nhide][0], &hide[nhide][1]) == 2) nhide++;
        }
        else if (!strcmp(argv[i], "-P")) { prof = 1; prof_from = atol(argv[++i]); }
        else if (!strcmp(argv[i], "-W")) {      /* -W lo-hi file: log writes (frame, pc, addr, size, value) */
            sscanf(argv[++i], "%x-%x", &watch_lo, &watch_hi);
            watch_out = fopen(argv[++i], "w");
        }                          /* no rendered frames */
        else if (!strcmp(argv[i], "-X") && nsubst < 16) {
            const char *a = argv[++i], *eq = strchr(a, '=');
            if (!eq || eq - a >= 48 || strlen(eq + 1) >= 48) { fprintf(stderr, "bad -X %s\n", a); return 1; }
            memcpy(subst_from[nsubst], a, eq - a); strcpy(subst_to[nsubst], eq + 1); nsubst++;
        }
        else if (!strcmp(argv[i], "-M") && npoke < 32) {        /* -M first-last/every:addr=value */
            long *k = poke[npoke];
            if (sscanf(argv[++i], "%ld-%ld/%ld:%lx=%lx", &k[0], &k[1], &k[2], &k[3], &k[4]) == 5 && k[2] > 0) npoke++;
            else { fprintf(stderr, "bad -M %s\n", argv[i]); return 1; }
        }
        else if (!strcmp(argv[i], "-C") && ncopy < 8) {        /* -C first-last:from=to[,add]: copy a RAM word (+ add) each frame */
            long *k = copy[ncopy];
            k[4] = 0;
            if (sscanf(argv[++i], "%ld-%ld:%lx=%lx,%ld", &k[0], &k[1], &k[2], &k[3], &k[4]) >= 4) ncopy++;
            else { fprintf(stderr, "bad -C %s\n", argv[i]); return 1; }
        }
        else if (!strcmp(argv[i], "-x")) { dis_addr = strtoul(argv[++i], 0, 16); dis_count = atoi(argv[++i]); }
        else if (!strcmp(argv[i], "-c") && ncp < 8) cp[ncp++] = argv[++i];
        else if (!strcmp(argv[i], "-s")) sp = argv[++i];
        else if (!strcmp(argv[i], "-S")) ssp = argv[++i];
        else if (!strcmp(argv[i], "-l")) lp = argv[++i];
        else if (!strcmp(argv[i], "-r") && nranges < 64) {
            if (sscanf(argv[++i], "%ld-%ld", &ranges[nranges][0], &ranges[nranges][1]) == 2) nranges++;
        }
    }
    if (!pp || !bp || !mp || !op) { fprintf(stderr, "usage: ngrec -p P1 -b BIOS -m M1 -o OUT -n FRAMES [-r a-b] [-i inputs]\n"); return 1; }
    prom = load(pp, &prom_size, 1);
    bios = load(bp, 0, 1);
    { size_t n; uint8_t *m = load(mp, &n, 0); m1_size = n < sizeof m1 ? n : sizeof m1; memcpy(m1, m, m1_size); free(m); }
    if (ip) load_inputs(ip);
    if (!ncp || (ncp & 1) || !sp || !ssp || !lp) { fprintf(stderr, "need -c pairs, -s, -S, -l\n"); return 1; }
    {
        size_t total = 0, sz[8];
        uint8_t *d[8];
        for (int i = 0; i < ncp; i++) { d[i] = load(cp[i], &sz[i], 0); if (!(i & 1)) total += sz[i]; }
        crom_odd = malloc(total); crom_even = malloc(total);
        size_t o = 0;
        for (int i = 0; i < ncp; i += 2) { memcpy(crom_odd + o, d[i], sz[i]); memcpy(crom_even + o, d[i + 1], sz[i]); o += sz[i]; free(d[i]); free(d[i + 1]); }
        crom_tiles = total / 64;
        srom_game = load(sp, 0, 0); srom_sys = load(ssp, 0, 0); zoomy = load(lp, 0, 0);
    }
    char path[1024];
    if (!no_frames) { snprintf(path, sizeof path, "%s.frames", op); frames_out = fopen(path, "wb"); }
    snprintf(path, sizeof path, "%s.snd", op); snd_out = fopen(path, "w");
    if ((!no_frames && !frames_out) || !snd_out) { perror(op); return 1; }

    if (dis_count) {      /* disassemble and exit (BIOS vectors still mapped) */
        char buf[256];
        for (int i = 0; i < dis_count; i++) {
            unsigned n = m68k_disassemble(buf, dis_addr, M68K_CPU_TYPE_68000);
            printf("%06x  %s\n", dis_addr, buf);
            dis_addr += n;
        }
        return 0;
    }
    memset(sram, 0, sizeof sram);
    z80_init(&zcpu);
    zcpu.read_byte = zrb; zcpu.write_byte = zwb; zcpu.port_in = zin; zcpu.port_out = zout;
    m68k_init();
    m68k_set_cpu_type(M68K_CPU_TYPE_68000);
    m68k_pulse_reset();

    unsigned rtc_lines = 0;
    for (frame = 0; frame < nframes; frame++) {
        for (int k = 0; k < npoke; k++)
            if (frame >= poke[k][0] && frame <= poke[k][1] && (frame - poke[k][0]) % poke[k][2] == 0)
                ram[poke[k][3] & 0xFFFF] = (uint8_t)poke[k][4];
        for (int k = 0; k < ncopy; k++)
            if (frame >= copy[k][0] && frame <= copy[k][1]) {
                unsigned v = ((ram[copy[k][2] & 0xFFFF] << 8 | ram[(copy[k][2] + 1) & 0xFFFF]) + copy[k][4]) & 0xFFFF;
                ram[copy[k][3] & 0xFFFF] = v >> 8;
                ram[(copy[k][3] + 1) & 0xFFFF] = v & 0xFF;
            }
        for (line = 0; line < LINES; line++) {
            if (line == 248 - 0) {          /* counter 0x1F0: vertical blanking starts */
                int rec = nranges == 0;
                for (int r = 0; r < nranges; r++) if (frame >= ranges[r][0] && frame <= ranges[r][1]) rec = 1;
                if (rec && frame % every == 0) {
                    if (frames_out) write_frame(); else if (fixdump) dump_fix();
                    if (ram_out) { uint32_t fn = (uint32_t)frame; fwrite(&fn, 4, 1, ram_out); fwrite(ram, 1, sizeof ram, ram_out); }
                    if (spr_out) { uint32_t fn = (uint32_t)frame; fwrite(&fn, 4, 1, spr_out); fwrite(vram, 2, 0x8800, spr_out); fwrite(pal[pal_bank], 2, 0x1000, spr_out); }
                }
                irq_pending |= 1; update_irq();
                if (anim_timer-- == 0) { anim_timer = anim_speed; anim_counter++; }
            }
            if (prof && frame >= prof_from) {      /* lines from vblank until the idle loop */
                unsigned pc = m68k_get_reg(NULL, M68K_REG_PC);
                static int busy = -1;
                if (line == 249) busy = 0;
                else if (busy >= 0) {
                    if (pc >= 0x13620 && pc <= 0x13630) { fprintf(stderr, "BUSY %ld %d\n", frame, busy); busy = -1; }
                    else busy++;
                }
            }
            m68k_execute(CYC_LINE);
            z80_run(Z80_CYC_LINE);
            if (++rtc_lines >= rtc_tp_div) { rtc_lines = 0; rtc_tp ^= 1; }
        }
        if (trace && frame % 60 == 0)
            fprintf(stderr, "frame %ld pc %06x sr %04x\n", frame, m68k_get_reg(NULL, M68K_REG_PC), m68k_get_reg(NULL, M68K_REG_SR));
    }
    if (frames_out) fclose(frames_out);
    fclose(snd_out);
    if (ram_out) fclose(ram_out);
    if (spr_out) fclose(spr_out);
    return 0;
}
