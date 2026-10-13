/* Sound: FM/PSG register streams played by the 68000, samples by the Z80 DAC driver.
 * The streams and samples are converted from the original game by tools/mksound.py. */
#include "sound.h"
#include "bank.h"

#define Z80_BUSREQ (*(volatile u16 *)0xA11100)
#define Z80_RESET  (*(volatile u16 *)0xA11200)
#define Z80_RAM    ((volatile u8 *)0xA00000)
#define YM         ((volatile u8 *)0xA04000)
#define PSG        (*(volatile u8 *)0xC00011)

enum { CMD_END, CMD_WAIT, CMD_YM0, CMD_YM1, CMD_PSG, CMD_SAMPLE, CMD_LOOP, CMD_STOP, CMD_DRUM };

typedef struct { const u8 *base, *p; u16 wait, active; } Stream;

static Stream music, psg;
static const Music *volatile req_music;
static const u8 *volatile req_psg;
static const u8 *kit;                /* current tune's drum table: count, then (z80 addr, len) pairs */
static volatile u16 req_music_flag, req_sfx = 0xFFFF;
static u16 tempo = TEMPO_NORMAL, tempo_acc;
static u16 sfx_hold;                 /* steps during which drums must not cut an effect */
static u16 rom_busy;                 /* steps the ROM voice is still playing a drum */
static u16 bus_held;

static void bus_grab(void)
{
    if (bus_held) return;
    Z80_BUSREQ = 0x0100;
    while (Z80_BUSREQ & 0x0100) { }
    bus_held = 1;
}

static void bus_release(void)
{
    volatile u8 *ym = YM;
    if (!bus_held) return;
    while (ym[0] & 0x80) { }
    ym[0] = 0x2A;                    /* leave the address latch where the DAC driver expects it */
    Z80_BUSREQ = 0;
    bus_held = 0;
}

static void ym_write(u16 part, u8 reg, u8 val)
{
    volatile u8 *ym = YM;
    bus_grab();
    while (ym[0] & 0x80) { }
    ym[part * 2] = reg;
    ym[part * 2 + 1] = val;
}

static void sample_start(u16 id)
{
    const Sample *s = &sample_table[id];
    volatile u8 *z = Z80_RAM;
    u32 a = (u32)s->data;
    u16 bank = (u16)(a >> 15), addr = 0x8000 | ((u16)a & 0x7FFF);
    bus_grab();
    bank_map_sample(s->page);
    z[0x41] = bank; z[0x42] = bank >> 8;
    z[0x43] = addr; z[0x44] = addr >> 8;
    z[0x45] = s->len; z[0x46] = s->len >> 8;
    z[0x40] = 1;
}

/* Second PCM channel: a drum from the kit in Z80 RAM. */
static void drum_start(u16 n)
{
    volatile u8 *z = Z80_RAM;
    const u8 *e;
    if (!kit || n >= (u16)((kit[0] << 8) | kit[1])) return;
    e = kit + 2 + n * 4;
    bus_grab();
    z[0x51] = e[1]; z[0x52] = e[0];
    z[0x53] = e[3]; z[0x54] = e[2];
    z[0x50] = 1;
}

/* Copy a tune's drum kit into Z80 RAM (the Z80 is paused meanwhile). */
static void kit_load(const u8 *k)
{
    volatile u8 *z = Z80_RAM + 0x200;
    const u8 *src;
    u16 n, len;
    kit = k;
    if (!k) return;
    n = (k[0] << 8) | k[1];
    src = k + 2 + n * 4;
    len = (src[0] << 8) | src[1];
    src += 2;
    bus_grab();
    Z80_RAM[0x51] = 0x00; Z80_RAM[0x52] = 0x1F;     /* park the drum channel on silence */
    Z80_RAM[0x53] = 1; Z80_RAM[0x54] = 0;
    Z80_RAM[0x50] = 1;
    while (len--) *z++ = *src++;
}

/* A drum hit. The ROM voice plays it at full rate unless an effect is sounding or it is
   still busy with another drum; then the half-rate kit voice takes it if the drum is in
   the kit. Only a drum outside the kit that lands on another drum cuts it short. */
static void drum_hit(u16 id, u16 slot)
{
    if (sfx_hold) {
        if (slot != 0xFF) drum_start(slot);
    } else if (rom_busy && slot != 0xFF) {
        drum_start(slot);
    } else {
        sample_start(id);
        rom_busy = sample_table[id].len / 108 + 1;
    }
}

static void fm_silence(void)
{
    static const u8 keys[5] = { 0, 1, 2, 4, 5 };    /* 0: the ADPCM-B voice */
    u16 i, op;
    for (i = 0; i < 5; i++) {
        u16 part = keys[i] >> 2, ch = keys[i] & 3;
        ym_write(0, 0x28, keys[i]);
        for (op = 0; op < 16; op += 4) {
            ym_write(part, 0x40 + op + ch, 0x7F);
            ym_write(part, 0x80 + op + ch, 0xFF);
        }
    }
}

static void stream_start(Stream *s, const u8 *data)
{
    s->base = data;
    s->p = data ? data + 4 : 0;
    s->wait = 0;
    s->active = data != 0;
}

static void stream_run(Stream *s, u16 drums)
{
    const u8 *p;
    if (!s->active) return;
    if (s->wait) { s->wait--; return; }
    p = s->p;
    for (;;) {
        switch (*p++) {
        case CMD_END: s->p = p; return;
        case CMD_WAIT: s->wait = *p++ + 1; s->p = p; return;
        case CMD_YM0: ym_write(0, p[0], p[1]); p += 2; break;
        case CMD_YM1: ym_write(1, p[0], p[1]); p += 2; break;
        case CMD_PSG: PSG = *p++; break;
        case CMD_SAMPLE: if (drums && !sfx_hold) sample_start(*p); p++; break;
        case CMD_DRUM: if (drums) drum_hit(p[0], p[1]); p += 2; break;
        case CMD_LOOP: p = s->base + (((u32)s->base[0] << 24) | ((u32)s->base[1] << 16) | (s->base[2] << 8) | s->base[3]); break;
        default: s->active = 0; return;
        }
    }
}

void snd_init(void)
{
    volatile u8 *z = Z80_RAM;
    u16 i;
    Z80_BUSREQ = 0x0100;
    Z80_RESET = 0x0100;
    while (Z80_BUSREQ & 0x0100) { }
    for (i = 0; i < Z80_DRIVER_SIZE; i++) z[i] = z80_driver[i];
    Z80_RESET = 0x0000;
    for (i = 0; i < 64; i++) __asm__ volatile ("nop");
    Z80_BUSREQ = 0x0000;
    Z80_RESET = 0x0100;
    PSG = 0x9F; PSG = 0xBF; PSG = 0xDF; PSG = 0xFF;
}

static const Music *current_music;
void snd_music(const Music *m) { current_music = m; req_music = m; req_music_flag = 1; }
void music_play(const Music *m) { if (m != current_music) snd_music(m); }

/* HBlank fires every 56 lines (4 per frame); the stream player runs on the 1st and 3rd. */
volatile u16 hint_count;
void hblank_handler(void)
{
    u16 n = hint_count++;
    if (n == 0 || n == 2) snd_step();
}
void snd_tempo(u16 rate) { tempo = rate; }
void snd_sfx(u16 id) { if (id < N_SAMPLES) req_sfx = id; }
void snd_psg(const u8 *stream) { req_psg = stream; }

void snd_step(void)
{
    if (req_music_flag) {
        req_music_flag = 0;
        fm_silence();
        PSG = 0x9F; PSG = 0xBF; PSG = 0xDF;          /* the music's PSG voices (converted SSG) */
        kit_load(req_music ? req_music->kit : 0);
        if (req_music) bank_map_music(req_music->page);
        stream_start(&music, req_music ? req_music->stream : 0);
        tempo_acc = 0;
    }
    if (req_psg) {
        PSG = 0x9F; PSG = 0xBF; PSG = 0xDF;
        stream_start(&psg, req_psg);
        req_psg = 0;
    }
    if (sfx_hold) sfx_hold--;
    if (rom_busy) rom_busy--;
    if (req_sfx != 0xFFFF) {
        u16 id = req_sfx;
        req_sfx = 0xFFFF;
        sample_start(id);
        sfx_hold = sample_table[id].len / 108 + 1;
        rom_busy = 0;
    }
    tempo_acc += tempo;
    while (tempo_acc >= TEMPO_NORMAL) {
        tempo_acc -= TEMPO_NORMAL;
        stream_run(&music, 1);
    }
    stream_run(&psg, 0);
    bus_release();
}
