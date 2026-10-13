/* Tile movies converted from recordings of the original game (tools/mkmovie.py).
 * Two name tables alternate: plane A at 0xC000 and the window plane at 0xD000 covering the
 * whole screen. A frame is drawn into the hidden one, then shown by switching the window on
 * or off during vblank, together with the frame's palette. Plane B stays free for text. */
#include "movie.h"
#include "vdp.h"
#include "input.h"
#include "sound.h"
#include "bank.h"

#define NT_PLANE  0xC000
#define NT_WINDOW 0xD000

void (*movie_hook)(u16 tick);
u16 movie_keep_palettes;
u16 movie_index;             /* frame on screen */
u16 movie_stop;              /* set by the hook: stop after this frame */

/* the original game's sound commands, recorded with the movie (see tools/mkmovies.py) */
void movie_sound(u16 id)
{
    if (id == 0xFFFF) snd_music(0);
    else if (id & 0x8000) snd_music(movie_music[id & 0x7FFF]);
    else snd_sfx(movie_sfx[id]);
}

static u16 rd16(const u8 *p) { return (p[0] << 8) | p[1]; }
static u32 rd32(const u8 *p) { return ((u32)rd16(p) << 16) | rd16(p + 2); }

static void show(u16 window) { vdp_set_reg(18, window ? 0x80 : 0x00); }

void movie_begin(void)
{
    u16 i, sr = ints_off();
    show(0);
    vdp_set_reg(17, 0);
    vdp_set_reg(3, NT_WINDOW >> 10);
    vdp_vram_addr(NT_PLANE);
    for (i = 0; i < 0x1000; i++) VDP_DATA32 = 0;     /* both name tables */
    ints_restore(sr);
}

void movie_end(void)
{
    u16 i, sr = ints_off();
    show(0);
    vdp_set_reg(3, VRAM_WINDOW >> 10);
    vdp_vram_addr(NT_PLANE);
    for (i = 0; i < 0x800; i++) VDP_DATA32 = 0;
    ints_restore(sr);
}

u16 movie_play(const Movie *mv, u16 opts, u16 max_ticks)
{
    const u8 *m = mv->data;
    u16 n, loop, k = 0, back = 0, dur_prev = 0, tick = 0;
    const u8 *tiles, *p = m + 8, *loop_p = 0;
    u16 shown_at = frame_counter;
    bank_map_video(mv->page);
    n = rd16(m); loop = rd16(m + 2); tiles = m + rd32(m + 4);
    for (;;) {
        u16 dur, fl, i, cnt, sr, nsnd = 0;
        const u8 *cram = 0, *snd = 0;
        u16 nt = back ? NT_WINDOW : NT_PLANE;
        if (k == loop) loop_p = p;
        if (k == n) {
            if (!loop_p) break;
            p = loop_p; k = loop;
        }
        dur = rd16(p); fl = rd16(p + 2); p += 4;
        if (fl & 1) { cram = p; p += 128; }
        if (fl & 4) { nsnd = rd16(p); snd = p + 2; p += 2 + 2 * nsnd; }
        if (fl & 2) { vdp_wait_vblank(); vdp_display(0); }
        sr = ints_off();
        for (cnt = rd16(p), p += 2; cnt; cnt--, p += 8)
            vdp_dma_vram(tiles + rd32(p + 4), rd16(p) << 5, rd16(p + 2) << 4);
        for (cnt = rd16(p), p += 2; cnt; cnt--) {
            u16 cell = rd16(p), len = rd16(p + 2);
            p += 4;
            vdp_vram_addr(nt + (cell << 1));
            for (i = 0; i < len; i++, p += 2) VDP_DATA = rd16(p);
        }
        ints_restore(sr);
        /* show the previous frame for its duration, then flip in the vblank after it */
        for (;;) {
            u16 last = (u16)(frame_counter + 1 - shown_at) >= dur_prev;
            if (last && cram) {
                for (i = 0; i < 64; i++)
                    if (!(movie_keep_palettes & (1 << (i >> 4)))) cram_shadow[i] = rd16(cram + 2 * i);
                cram_dirty = 1;
            }
            vdp_wait_vblank();
            input_update();
            if (movie_hook) movie_hook(tick);
            tick++;
            if ((opts & MOVIE_SKIP) && (pads[0].pressed | pads[1].pressed) & (BTN_START | BTN_A | BTN_B))
                return 1;
            if (max_ticks && tick >= max_ticks) return 0;
            if (movie_stop) { movie_stop = 0; return 2; }
            if (last) break;
        }
        show(back);
        if (fl & 2) vdp_display(1);
        movie_index = k;
        shown_at = frame_counter;
        dur_prev = dur;
        back ^= 1;
        k++;
        while (nsnd--) { movie_sound(rd16(snd)); snd += 2; }
    }
    while ((u16)(frame_counter - shown_at) < dur_prev) {     /* hold the last frame */
        vdp_wait_vblank();
        input_update();
        if (movie_hook) movie_hook(tick);
        tick++;
        if ((opts & MOVIE_SKIP) && (pads[0].pressed | pads[1].pressed) & (BTN_START | BTN_A | BTN_B))
            return 1;
    }
    return 0;
}
