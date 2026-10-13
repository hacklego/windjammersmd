/* The frisbee dog bonus game as the attract mode shows it, replayed from the recording made at
 * build time (tools/mkmovies.py make_bonus): the beach scrolls on plane B, the dog, the frisbee,
 * the thrower and the sunbathers are sprites at their recorded positions. */
#include "bonus.h"
#include "vdp.h"
#include "vram.h"
#include "input.h"
#include "text.h"
#include "bank.h"
#include "movie.h"
#include "movies.h"
#include "player.h"
#include "sound.h"
#include "match.h"

#define SLOTS 7
static const u16 slot_vram[SLOTS] = { 1152, 1216, 1280, 1344, 1408, 1920, 1984 };   /* 64 tiles each */

static void set_scroll_b(u16 x) {
    u16 sr = ints_off();
    vdp_vram_addr(VRAM_HSCROLL + 2);
    VDP_DATA = x;
    ints_restore(sr);
}

static void hud(u32 hi, char unit, u16 flag, u16 wait);
static u16 dog_record;                  /* best distance this session (HI) */

u16 bonus_demo(void) {
    const u16 *p = bonus_frames, *snd = bonus_sounds;
    u16 slot_id[SLOTS], slot_frame[SLOTS], slot_used[SLOTS];
    u16 r, k, i, sr, ret = 0;
    for (i = 0; i < SLOTS; i++) { slot_id[i] = 0xFFFF; slot_frame[i] = 0xFFFF; }
    spr_clear();
    text_clear();
    vdp_wait_vblank();
    bank_map_video((u16)(u32)bonus_data_page);
    sr = ints_off();
    vdp_display(0);
    vdp_load_tiles(bonus_data, 1, bonus_bg_tiles);
    vdp_set_plane_rect(VRAM_PLANE_B, 0, 0, 64, 28, bonus_map);
    ints_restore(sr);
    for (i = 0; i < 4; i++) vdp_set_palette(i, bonus_pal + 16 * i);
    {   /* the HUD text as in the original ("HI" is this session's best distance), palette 3 */
        u16 pal3[16];
        for (i = 0; i < 16; i++) pal3[i] = bonus_pal[48 + i];
        pal3[8] = dog_pal[8]; pal3[9] = dog_pal[9]; pal3[14] = dog_pal[14]; pal3[15] = dog_pal[15];
        vdp_set_palette(3, pal3);
        text_use_game_font(1);
        text_set_palette(3);
        match_score_reset();            /* (not the demo match's points) */
        hud(dog_record, 'm', 0, 0);
    }
    vdp_wait_vblank();
    vdp_display(1);
    for (r = 0; r < bonus_count && !ret; r++) {
        u16 scroll = *p++, n = *p++, nd = 0, d;
        const Frame *df[SLOTS];
        s16 dx[SLOTS], dy[SLOTS];
        u16 dv[SLOTS], dfl[SLOTS];
        while (*snd == r) { movie_sound(snd[1]); snd += 2; }
        for (i = 0; i < SLOTS; i++) slot_used[i] = 0;
        for (k = 0; k < n; k++, p += 4) {
            u16 id = p[0], fr = p[1], s;
            const Frame *f = &bonus_objects[fr];
            for (s = 0; s < SLOTS && slot_id[s] != id; s++) {}
            if (s == SLOTS) {                       /* a new object: take a slot not in use */
                for (s = 0; s < SLOTS && slot_used[s]; s++) {}
                if (s == SLOTS) continue;
                slot_id[s] = id; slot_frame[s] = 0xFFFF;
            }
            slot_used[s] = 1;
            if (slot_frame[s] != fr) {
                dma_queue(f->tiles, slot_vram[s] << 5, f->ntiles << 4);
                slot_frame[s] = fr;
            }
            df[nd] = f; dx[nd] = (s16)p[2]; dy[nd] = (s16)p[3]; dv[nd] = slot_vram[s]; dfl[nd++] = bonus_flicker[fr];
        }
        for (i = 0; i < SLOTS; i++) if (!slot_used[i]) slot_id[i] = 0xFFFF;
        set_scroll_b(scroll);
        for (i = 0; i < bonus_step; i++) {
            spr_clear();                            /* shadows and sand puffs every other frame, as the original */
            for (d = 0; d < nd; d++) if (!dfl[d] || !(i & 1)) frame_draw(df[d], dx[d], dy[d], dv[d], 0, 1, 0);
            vdp_wait_vblank();
            input_update();
            if ((pads[0].pressed | pads[1].pressed) & BTN_START) { ret = 1; break; }
        }
    }
    spr_clear();
    vdp_wait_vblank();
    set_scroll_b(0);
    sr = ints_off();
    vdp_fill_plane(VRAM_PLANE_B, 0);
    ints_restore(sr);
    text_clear();
    text_set_palette(1);
    text_use_game_font(0);
    return ret;
}

/* ---------------------------------------------------------------- DOG DISTANCE */

/* The bonus round, with the original's rules read from its code (P-ROM 0x1FEC0-0x20A40, the
 * collisions 0x1ACAA / 0x1AD74) and RAM (tools/ngrec). At GO the player has the disc; the
 * throw's speed is the match's (a quick throw is a power throw, after 75 frames the disc goes
 * anyway). The disc slows by 1/4096 a frame and weaves 27 px up and down every 340 frames; it
 * rises (1 px a frame less 0xE0/65536 a frame, falling with drag) and grows on screen as it does,
 * lands after 790 frames, bounces once at a quarter of its speed and stops. The camera follows
 * it. After the throw the player steers the dog (it runs along at the disc's speed less 1.5,
 * the pad adds 2.5 px a frame, A/B/C jumps): catching the disc as it lands is worth 5000
 * (TECHNICAL POINT), in a jump 10000; it then carries it. Running into a sunbather trips it,
 * which also slows the disc. The distance is (x - 64) / 32 m where the disc stops, 100 a metre. */
#define V_PLAYER   1152                 /* sprite tiles: the thrower (streamed per frame) */
#define V_DOG      1280                 /* the dog (up to 96 tiles), */
#define V_HELD     (V_DOG + 96)         /* the disc in its mouth, */
#define V_GSHADOW  (V_HELD + 16)        /* its shadow */
#define V_DISC     1408                 /* the disc (64 x 64) */
#define V_SHADOW   1664                 /* window plane area, unused here: shadows, pole, girl, */
#define V_DSHADOW  (V_SHADOW + 16)
#define V_POLE     (V_SHADOW + 20)
#define V_GIRL     (V_SHADOW + 48)
#define V_FLAG     1920                 /* fence area: the title, then two flags, */
#define V_OBST     1968                 /* the sunbather (80 tiles) */
#define V_HUDG     1024                 /* after the beach's tiles: P1's flag, the timer's digits */
#define FX(n)      ((s32)(n) << 16)

static void img_load(u16 img, u16 vram) {
    const Frame *f = &dog_img[img];
    dma_queue(f->tiles, vram << 5, f->ntiles << 4);
}

static void img_draw(u16 img, s16 x, s16 y, u16 vram) {
    frame_draw(&dog_img[img], x, y, vram, 3, 1, 0);
}

/* pictures in the VRAM slots: -1 = none loaded yet */
static s16 dog_shown = -1, held_shown = -1, gshadow_shown = -1, obst_shown = -1, girl_shown = -1, disc_shown = -1, flag_shown[2];

/* the shadows (and the thrower's): the original draws them every other frame only */
#define SHADOWS_NOW  (!(frame_counter & 1))

static void thrower_shadow(const Player *p) {
    if (SHADOWS_NOW) img_draw(dog_shadow[0], (s16)(p->x >> 16) - 12, (s16)(p->y >> 16) - 3, V_SHADOW);
}

static void dog_put(u16 img, s16 x, s16 y) {
    if (dog_shown != (s16)img) { img_load(img, V_DOG); dog_shown = img; }
    img_draw(img, x, y, V_DOG);
}

static void disc_put(u16 img, s16 x, s16 y) {
    if (disc_shown != (s16)img) { img_load(img, V_DISC); disc_shown = img; }
    img_draw(img, x, y, V_DISC);
}

/* the picture of animation frame f at zoom e (the nearest zoom cut) at its anchor (x, y) */
static void pic_put(u16 f, u16 e, s16 x, s16 y, u16 vram, s16 *shown) {
    const DogPic *p, *best = 0;
    u16 bd = 0xFFFF;
    for (p = dog_pics; p < dog_pics + DOG_PICS; p++)
        if ((p->key >> 4) == f) {
            u16 pe = p->key & 15, d = pe > e ? pe - e : e - pe;
            if (d < bd) { bd = d; best = p; }
        }
    if (!best) return;
    if (*shown != (s16)best->img) { img_load(best->img, vram); *shown = best->img; }
    img_draw(best->img, x + best->dx, y + best->dy, vram);
}

/* the bonus rounds' top rows as in the original: "P1 [flag] score" (the score right-aligned, ending
 * in column 13), "P2 WAIT" (blinking, when playing), "HI n" below (this session's best, unit 'm'
 * or none); flag: its 4 tiles (TL, BL, TR, BR) in VRAM, 0 = none */
static void hud(u32 hi, char unit, u16 flag, u16 wait) {
    char line[42];                      /* (even size: gcc fills odd-placed arrays with long moves) */
    u32 v = match_score(0);
    u16 i, r;
    for (r = 1; r <= 2; r++) {
        for (i = 0; i < 40; i++) line[i] = ' ';
        line[40] = 0;
        if (r == 1) {
            line[2] = 'P'; line[3] = '1';
            for (i = 0; i < 7; i++, v /= 10) if (v || !i) line[13 - i] = '0' + (char)(v % 10);
            if (wait && (frame_counter & 32)) { line[28] = 'P'; line[29] = '2'; line[31] = 'W'; line[32] = 'A'; line[33] = 'I'; line[34] = 'T'; }
        } else {
            line[17] = 'H'; line[18] = 'I';
            for (i = 0; i < 7; i++, hi /= 10) if (hi || !i) line[22 - i] = '0' + (char)(hi % 10);
            if (unit) line[23] = unit;
        }
        if (flag) {                     /* the text around the flag (columns 5 and 6), then the flag */
            u16 sr;
            line[5] = 0;
            text_print(0, r, line);
            text_print(7, r, line + 7);
            sr = ints_off();
            vdp_set_tile(VRAM_PLANE_A, 5, r, TILE_ATTR(3, 1, 0, 0, flag + r - 1));
            vdp_set_tile(VRAM_PLANE_A, 6, r, TILE_ATTR(3, 1, 0, 0, flag + r + 1));
            ints_restore(sr);
        } else text_print(0, r, line);
    }
}

/* the timer's big digits (2 x 2 tiles each: TL, BL, TR, BR from glyphs) in columns 32-35, rows 3-4 */
static void big_digit(u16 glyphs, u16 d, u16 col, u16 row) {
    u16 v = glyphs + d * 4, sr = ints_off();
    vdp_set_tile(VRAM_PLANE_A, col, row, TILE_ATTR(3, 1, 0, 0, v));
    vdp_set_tile(VRAM_PLANE_A, col, row + 1, TILE_ATTR(3, 1, 0, 0, v + 1));
    vdp_set_tile(VRAM_PLANE_A, col + 1, row, TILE_ATTR(3, 1, 0, 0, v + 2));
    vdp_set_tile(VRAM_PLANE_A, col + 1, row + 1, TILE_ATTR(3, 1, 0, 0, v + 3));
    ints_restore(sr);
}

static void big_timer(u16 glyphs, u16 timer) {
    big_digit(glyphs, timer / 10, 32, 3); big_digit(glyphs, timer % 10, 34, 3);
}

static void frame_end_dog(s32 cam) {
    vdp_wait_vblank();
    set_scroll_b((u16)(-(s16)(cam >> 16)) & 0x3FF);
    input_update();
}

/* the original's animation tables (P-ROM 0x20782-0x20809): the dog, and the disc in its mouth */
static const u16 dg_run[8] = { 0xA32, 0xA33, 0xA34, 0xA35, 0xA36, 0xA37, 0xA38, 0xA39 };
static const u16 dg_back[8] = { 0xA49, 0xA4B, 0xA4D, 0xA4B, 0xA49, 0xA4B, 0xA4D, 0xA4B };
static const u16 dg_back_d[8] = { 0xA4A, 0xA4C, 0xA4E, 0xA4C, 0xA4A, 0xA4C, 0xA4E, 0xA4C };
static const u16 dg_jump[2][4] = { { 0xA3A, 0xA3B, 0xA3D, 0xA3F }, { 0xA3A, 0xA3B, 0xA41, 0xA43 } };   /* (right held) */
static const u16 dg_jump_d[2][4] = { { 0xA3C, 0xA3C, 0xA42, 0xA44 }, { 0xA3C, 0xA3C, 0xA42, 0xA44 } };
static const u16 dg_trip[2] = { 0xA45, 0xA47 };
static const u16 dg_sit[2][6] = { { 0xA55, 0xA57, 0xA58, 0xA59, 0xA58, 0xA57 }, { 0xA4F, 0xA51, 0xA52, 0xA54, 0xA52, 0xA51 } };
static const u16 dg_sit_d[6] = { 0xA50, 0xA53, 0xA50, 0xA53, 0xA50, 0xA53 };
/* the sunbathers: picture, hit box and the picture when the dog runs into them */
static const u16 ob_frame[4] = { 0xAB4, 0xAB2, 0xAB0, 0xAAE };
static const u16 ob_react[4][4] = { { 0xAB5, 0xAB5, 0xAB6, 0xAB7 }, { 0xAB3, 0xAB3, 0xAB3, 0xAB3 },
                                    { 0xAB1, 0xAB1, 0xAB1, 0xAB1 }, { 0xAAF, 0xAAF, 0xAAF, 0xAAF } };
typedef struct { s16 x, y, w, h; } Box;
static const Box ob_box[4] = { { -2, -2, 8, 20 }, { -2, -6, 12, 18 }, { 0, -4, 10, 22 }, { 0, -6, 8, 11 } };

static const Box *dog_box(u16 f) {     /* the dog's hit box in frame f (none: 0) */
    static const Box run = { 4, -14, 14, 7 }, jump = { 4, -16, 28, 8 }, jump2 = { 6, -18, 18, 10 },
                     trip = { 2, -10, 12, 8 }, back = { 1, -12, 10, 9 };
    if (f >= 0xA32 && f <= 0xA39) return &run;
    if (f == 0xA3A || f == 0xA3B || f == 0xA41 || f == 0xA43) return &jump;
    if (f == 0xA3D || f == 0xA3F) return &jump2;
    if (f == 0xA45 || f == 0xA47) return &trip;
    if (f == 0xA49 || f == 0xA4B || f == 0xA4D) return &back;
    return 0;
}

static s16 iabs(s16 v) { return v < 0 ? -v : v; }
static s32 labs32(s32 v) { return v < 0 ? -v : v; }

/* pad directions -> movement at speed sp (16.16): straight, or 181/256 of it on each axis */
static void pad_move(u16 dir, s32 sp, s32 *mx, s32 *my) {
    s32 d = (sp >> 8) * 181;
    *mx = *my = 0;
    if (dir & BTN_UP) *my = -sp;
    else if (dir & BTN_DOWN) *my = sp;
    if (dir & BTN_LEFT) *mx = -sp;
    else if (dir & BTN_RIGHT) *mx = sp;
    if (*mx && *my) { *mx = *mx < 0 ? -d : d; *my = *my < 0 ? -d : d; }
}

enum { DOG_WAIT, DOG_RUN, DOG_JUMP, DOG_TRIP, DOG_SIT };

u16 bonus_dog(u16 char_index) {
    Player *p = &players[0];
    /* the disc: position, speed, height (16.16); the camera */
    s32 dx = 0, dy = 0, vx = 0, vy = 0, h = 0, vh = 0, cam = 0, camv = 0;
    u16 catchable = 0, stopped = 0, cam_phase = 0, spin = 0;
    /* the dog: position, jump height and speed, state, animation, trip */
    s32 gx = FX(64), gy = FX(168), gh = 0, gvh = 0, tvx = 0;
    u16 gstate = DOG_WAIT, gc = 0, gtrip = 0, recov = 0, bumped = 0, holding = 0, jumpcatch = 0, gsnd = 0, gframe = 0xA32;
    /* the sunbather */
    s32 ox = FX(1024), oy = FX(160);
    u16 otype = 0, oon = 1, obump = 0, oc = 0;
    u16 t, sr, i, phase = 0, timer = 20, tick = 0, thrown = 0, power = 0, metres = 0, points = 0, technical = 0;
    s16 throw_t = -1, end_t = -1;
    char line[42];
    spr_clear();
    text_clear();
    vdp_wait_vblank();
    /* the beach (from the attract demo's data), then the bank with the player and dog sprites */
    bank_map_video((u16)(u32)bonus_data_page);
    sr = ints_off();
    vdp_display(0);
    vdp_load_tiles(bonus_data, 1, bonus_bg_tiles);
    vdp_set_plane_rect(VRAM_PLANE_B, 0, 0, 64, 28, bonus_map);
    ints_restore(sr);
    vdp_set_palette(0, bonus_pal);
    vdp_set_palette(1, bonus_pal + 16);
    vdp_set_palette(3, dog_pal);
    player_init(p, 0, char_index);                  /* maps the character bank (dog tiles too) */
    p->x = (s32)61 << 16; p->y = (s32)101 << 16;          /* where the original has them (its shadow at 49, 98) */
    player_force_anim(p, ANIM_IDLE, 1);
    text_use_game_font(1);
    text_set_palette(3);
    dog_shown = held_shown = gshadow_shown = obst_shown = girl_shown = disc_shown = flag_shown[0] = flag_shown[1] = -1;
    sr = ints_off();
    vdp_load_tiles(dog_img[dog_logo[0]].tiles, V_FLAG, dog_img[dog_logo[0]].ntiles);
    vdp_load_tiles(dog_img[dog_shadow[0]].tiles, V_SHADOW, dog_img[dog_shadow[0]].ntiles);
    vdp_load_tiles(dog_img[dog_dshadow[0]].tiles, V_DSHADOW, dog_img[dog_dshadow[0]].ntiles);
    vdp_load_tiles(dog_img[dog_pole[0]].tiles, V_POLE, dog_img[dog_pole[0]].ntiles);
    vdp_load_tiles(dog_tiles + 32 * (dog_hud_at + 4 * char_index), V_HUDG, 4);
    vdp_load_tiles(dog_tiles + 32 * (dog_hud_at + 24), V_HUDG + 4, 40);
    ints_restore(sr);
    set_scroll_b(0);
    vdp_wait_vblank();
    vdp_display(1);
    snd_music(&mus_bonus);

    /* title and countdown, then GO: the player has the disc */
    for (t = 0;; t++) {
        spr_clear();
        hud(dog_record, 'm', V_HUDG, 1); big_timer(V_HUDG + 4, timer);
        if (t == 0) text_center(6, "BONUS ROUND!");
        if (t < 150) img_draw(dog_logo[0], dog_logo[1], dog_logo[2], V_FLAG);
        if (t == 150) { text_clear_row(6); }
        if (t == 150 || t == 190 || t == 230) { text_center(13, t == 150 ? "3" : t == 190 ? "2" : "1"); sfx_play(SFX_BEEP); }
        if (t == 270) { text_center(13, "GO!"); sfx_play(SFX_GO); }
        if (t == 300) text_clear_row(13);
        {
            const s16 *w = dog_wag[t % DOG_WAG];
            dog_put(w[0], w[1], w[2]);
        }
        if (SHADOWS_NOW) img_draw(dog_shadow[0], 52, 134, V_SHADOW);      /* under the sitting dog */
        img_draw(dog_pole[0], dog_pole[1], dog_pole[2], V_POLE);
        {
            const s16 *g = dog_girl[(t >> 1) % DOG_GIRL];
            if (girl_shown != g[0]) { img_load(g[0], V_GIRL); girl_shown = g[0]; }
            img_draw(g[0], g[1], g[2], V_GIRL);
        }
        player_advance(p);
        player_draw(p);
        thrower_shadow(p);
        frame_end_dog(0);
        if (t == 270) break;
    }
    /* sprite tiles of the title are no longer needed: the flags take them */
    p->state = PS_HOLD; p->hold_frames = 0;
    player_force_anim(p, ANIM_HOLD, 1);
    for (t = 0;; t++) {
        u16 k, pad = pads[0].held, hit = pads[0].pressed;
        s16 cx, sx, sy;
        if (++tick == 60) { tick = 0; if (timer) timer--; }
        spr_clear();
        hud(dog_record, 'm', V_HUDG, 1); big_timer(V_HUDG + 4, timer);
        if (t == 30) text_clear_row(13);
        /* the throw */
        if (!thrown && throw_t < 0 && ((hit & BTN_A) || p->hold_frames >= 75)) {
            throw_t = 0;
            player_force_anim(p, ANIM_THROW, 0);
        }
        if (throw_t >= 0 && !thrown && p->step >= 3) {
            u16 speed;
            thrown = 1; throw_t = 0;
            power = p->hold_frames < p->ch->power_frames;
            speed = power ? 0x120 : p->hold_frames >= 64 ? 0x60 : p->ch->throw_speed[p->hold_frames >> 2];
            vx = (s32)speed << 11;
            dx = FX(84); dy = FX(120); vy = 0; h = 0; vh = FX(1); catchable = 1;
            gstate = DOG_RUN; gc = 0;
            hit = 0;                                        /* (the throw's A does not make the dog jump) */
            sfx_play(power ? SFX_POWER : SFX_THROW);
            sfx_play(SFX_BARK);
        }
        if (!thrown) p->hold_frames++;
        if (thrown) {
#ifdef TEST_DOGAI   /* automated test: the dog goes for the disc (jumps for it if TEST_DOGAI is 2) */
            pad = hit = 0;
            if (gx < dx - FX(2)) pad |= BTN_RIGHT;
            if (gx > dx + FX(2)) pad |= BTN_LEFT;
            if (gy < dy + FX(14)) pad |= BTN_DOWN;
            if (gy > dy + FX(18)) pad |= BTN_UP;
            if (TEST_DOGAI == 2 && h > 0 && h < FX(24) && vh < 0) hit = BTN_A;
#endif
            /* the dog (P-ROM 0x1FF98): the pad steers it unless it carries the disc on the ground */
            if (holding && gstate != DOG_JUMP) pad = hit = 0;
            if (cam == 0) pad &= BTN_UP | BTN_DOWN;         /* not sideways before the camera moves */
            if (gstate == DOG_RUN) {
                if (bumped) {                               /* ran into a sunbather: trips */
                    gstate = DOG_TRIP; gc = 0; gtrip = 0; tvx = vx; recov = 0;
                    if (labs32(vx) >= 0x28000) { vx -= 0x4000; if (vx < 0) vx = 0; }
                } else if (hit & (BTN_A | BTN_B | BTN_C)) {
                    gstate = DOG_JUMP; gc = 0; gh = 0; gvh = -FX(3);
                } else {
                    s32 mx, my, move, drift = vx;
                    u16 fwd;
                    if (recov) pad &= ~BTN_LEFT;            /* catching up with the screen */
                    pad_move(pad, 0x28000, &mx, &my);
                    gx += mx; gy += my;
                    if (!holding) drift -= recov ? -0x18000 : 0x18000;
                    gx += drift; move = mx + drift;
                    fwd = !holding && vx >= FX(2) && move >= 0;
                    if (gc >= 0x1000) { gc &= 0xFFF; sfx_play(fwd ? SFX_BARK : SFX_PANT); }
                    gframe = fwd ? dg_run[(gc >> 9) & 7] : dg_back[(gc >> 9) & 7];
                    move = labs32(move) >> 11;
                    gc += (u16)(move > 0x200 ? 0x200 : move) + (fwd ? 0 : 0x40);
                    if (!recov && vx == 0) { gstate = DOG_SIT; gc = 0; gsnd = 0; }
                }
            }
            if (gstate == DOG_JUMP) {
                s32 mx, my;
                pad_move(pad, 0x1C000, &mx, &my);
                gx += mx; gy += my;
                gx += holding ? vx : vx - (recov ? -FX(2) : 0x4000);
                gh += gvh;
                if (gh >= 0) { gstate = DOG_RUN; gc = 0; gh = gvh = 0; }
                else {
                    gvh += holding ? 0x1800 : 0x2400;
                    gframe = dg_jump[(pad & BTN_RIGHT) != 0][(gc >> 9) & 3];
                    gc += 0x38;
                    if (gc >= 0x800) gc = 0x7D0;
                }
            }
            if (gstate == DOG_TRIP) {
                gframe = dg_trip[gc >= 4];
                if (gc < 7) gc++;
                gx += tvx; tvx -= tvx >> 4;
                gtrip++;
                if (gtrip == 4) sfx_play(SFX_PANT);
                if (gtrip == 16) sfx_play(SFX_YELP);
                if (gx < cam - FX(16)) gx = cam - FX(16);
                if (gtrip >= 32) { recov = 1; gstate = DOG_RUN; gc = 0; tvx = 0; }
            } else if (gstate != DOG_SIT) {                 /* stays on the screen (P-ROM 0x2053A) */
                s32 lo = cam + FX(40 + (recov ? 16 : 0)), hi = cam + FX(280 - (recov ? 16 : 0));
                if (gx < lo) { if (!recov) gx = lo & ~0xFFFF; }
                else if (gx >= hi) { if (!recov) gx = hi & ~0xFFFF; }
                else recov = 0;
                if (gy < FX(124)) gy = FX(124);
                if (gy > FX(192)) gy = FX(192);
            }
            bumped = 0;
            if (gstate == DOG_SIT) {
                gframe = dg_sit[holding != 0][gc >> 3];
                if (++gc >= 0x30) gc = 0;
                if (gsnd == (holding ? 0 : 0x20)) sfx_play(holding ? SFX_YAP : SFX_WHINE);
                if (gsnd <= 0x20) gsnd++;
            }
            /* the disc: carried, or flying (P-ROM: speed, weave, height with drag, one bounce) */
            if (holding) {
                if (gstate != DOG_JUMP) { vx -= vx >> 4; if ((labs32(vx) & ~0x3FFF) == 0) vx = 0; }
                dx = gx; dy = gy;
            } else if (!stopped) {
                vx -= vx >> 12;
                dx += vx;
                vy -= ((dy - FX(147)) >> 8) * 22 >> 8;      /* the weave: (2 pi / 340)^2 */
                dy += vy;
                h += vh;
                if (catchable) vh -= (0x7000 + (vh < 0 ? vh : 0)) >> 7;
                else vh -= 0x700;
                if (h < -FX(15)) {
                    if (catchable) { h += FX(1); vh = -vh; vx >>= 2; catchable = 0; sfx_play(SFX_BOUNCE); }
                    else { vx = vh = 0; stopped = 1; }
                }
            }
            spin = spin == 7 ? 0 : spin + 1;
            /* the camera (P-ROM 0x1002E0): waits until the disc is 220 px in, follows at half its
               speed, then at its speed then, until the disc is 127 px in, then with it */
            if (cam_phase == 0 && dx - cam > FX(220)) cam_phase = 1;
            if (cam_phase == 1) { camv = vx >> 1; if (dx - cam >= FX(250)) { cam_phase = 2; camv = vx; } }
            if (cam_phase == 2 && dx - cam <= 0x7F5800) cam_phase = 3;
            if (cam_phase == 3) camv = vx;
            if (cam_phase) cam += camv;
            /* the sunbather: the next one 640 px on once this one is behind, while the disc is high */
            if (oon && ox < cam - FX(32)) {
                if (vh < -0x6000) oon = 0;
                else {
                    ox += FX(640);
                    oy = FX((((u16)(gx >> 16) + (u16)(gy >> 16) + (u16)frame_counter) & 0x3F) + 0x60);
                    otype = (otype + 1) & 3; obump = 0; oc = 0;
                }
            }
            if (oon && obump && oc < 24) oc++;
            /* collisions: the dog catches the disc (P-ROM 0x1ACAA), runs into the sunbather (0x1AD74) */
            {
                const Box *b = dog_box(gframe);
                s16 e = gstate == DOG_JUMP ? 7 + (iabs((s16)(gh >> 16)) >> 3) : 15;
                if (e > 15) e = 15;
                if (b && catchable && !holding && gstate != DOG_SIT) {
                    s16 d4 = (s16)(h >> 16) + 16, d5 = iabs((s16)(gh >> 16)) + 2, w = b->w - (15 - e);
                    if (w < 0) w = 0;
                    if (d4 && d4 >= d5 && d4 < d5 + 15
                        && iabs((s16)(gx >> 16) + b->x - (s16)(dx >> 16)) <= w + 6
                        && iabs((s16)(gy >> 16) + b->y - (s16)(dy >> 16)) <= 6 + b->h) {
                        holding = 1; jumpcatch = gstate == DOG_JUMP;
                        technical = jumpcatch ? 10000 : 5000;
                        sfx_play(SFX_CATCH);
                    }
                }
                if (b && gstate == DOG_RUN && oon && !obump) {
                    const Box *o = &ob_box[otype];
                    if (iabs((s16)(ox >> 16) + o->x - (s16)(gx >> 16) - b->x) <= b->w + o->w
                        && iabs((s16)(oy >> 16) + o->y - (s16)(gy >> 16) - b->y) <= b->h + o->h) {
                        bumped = 1; obump = 1; oc = 0;
                        sfx_play(otype == 1 ? SFX_OUCH : SFX_KYAA);
                    }
                }
            }
            if (throw_t < 0x7FFF) throw_t++;
        }
        cx = (s16)(cam >> 16);
        /* things on the beach: start pole, sunbather, distance flags every 20 m */
        if (cx < 320) {
            img_draw(dog_pole[0], dog_pole[1] - cx, dog_pole[2], V_POLE);
            if (cx < 200) {
                const s16 *g = dog_girl[(t >> 1) % DOG_GIRL];
                if (girl_shown != g[0]) { img_load(g[0], V_GIRL); girl_shown = g[0]; }
                img_draw(g[0], g[1] - cx, g[2], V_GIRL);
            }
        }
        for (k = 0; k < DOG_FLAGS; k++) {
            s16 fx = 64 + 640 * (k + 1) - 8 - cx;
            if (fx > -32 && fx < 320) {
                u16 v = V_FLAG + (k & 1) * 24;
                if (flag_shown[k & 1] != (s16)k) { img_load(dog_flag[k], v); flag_shown[k & 1] = k; }
                img_draw(dog_flag[k], fx, 40, v);
            }
        }
        /* the disc in flight (bigger the higher it is) and its shadow, on the ground at the end */
        sx = (s16)((dx - cam) >> 16); sy = (s16)(dy >> 16);
        if (thrown && !holding) {
            s16 hh = (s16)(h >> 16);
            if (hh > 0) {
                s16 z = 63 + 2 * hh;
                u16 f = 0xA + spin;
                if (z > 255) z = 255;
                if ((z >> 4) != 15) f &= ~1;
                pic_put(f, z >> 4, sx, sy + 48 - (3 * z >> 3), V_DISC, &disc_shown);
                if (SHADOWS_NOW) img_draw(dog_dshadow[0], sx - 17, sy - 17, V_DSHADOW);
            } else {
                disc_put(dog_roll[stopped ? 0 : spin], sx - 10, sy - 16);
            }
        }
        /* the dog and the sunbather, the nearer one in front */
        {
            s16 gsx = (s16)((gx - cam) >> 16), gsy = (s16)(gy >> 16), osx = (s16)((ox - cam) >> 16), osy = (s16)(oy >> 16);
            u16 odraw = oon && osx > -40 && osx < 360, dog_first = gsy >= osy;
            for (i = 0; i < 2; i++) {
                if ((i == 0) == dog_first) {
                    if (!thrown) {
                        const s16 *w = dog_wag[t % DOG_WAG];
                        dog_put(w[0], w[1], w[2]);
                    } else {
                        s16 e = gstate == DOG_JUMP ? 7 + (iabs((s16)(gh >> 16)) >> 3) : 15;
                        s16 ay = gsy + (s16)(gh >> 17);
                        if (e > 15) e = 15;
                        if (holding) {
                            u16 hf = gstate == DOG_JUMP ? dg_jump_d[(pad & BTN_RIGHT) != 0][(gc >> 9) & 3]
                                   : gstate == DOG_SIT ? dg_sit_d[gc >> 3] : dg_back_d[(gc >> 9) & 7];
                            pic_put(hf, e, gsx, ay, V_HELD, &held_shown);
                        }
                        pic_put(gframe, e, gsx, ay, V_DOG, &dog_shown);
                    }
                } else if (odraw) {
                    pic_put(obump ? ob_react[otype][oc >> 3] : ob_frame[otype], 0, osx, osy, V_OBST, &obst_shown);
                }
            }
            if (SHADOWS_NOW && thrown) {
                s16 e = gstate == DOG_JUMP ? 7 + (iabs((s16)(gh >> 16)) >> 3) : 15;
                pic_put(0xA00, e > 15 ? 15 : e, gsx, gsy, V_GSHADOW, &gshadow_shown);
            } else if (SHADOWS_NOW) img_draw(dog_shadow[0], 52, 134, V_SHADOW);     /* under the sitting dog */
        }
        /* the thrower: at the start line, then running in at the end to cheer */
        if (!thrown || throw_t < 120) {
            s32 px = p->x;
            p->x -= cam;
            player_advance(p);
            player_draw(p);
            thrower_shadow(p);
            p->x = px;
            if (thrown && p->anim_done) player_force_anim(p, ANIM_IDLE, 1);
        } else if (gstate == DOG_SIT) {
            if (phase == 0) {
                phase = 1; end_t = 0;
                metres = (u16)((dx - FX(64)) >> 21);
                p->x = -((s32)16 << 16); p->y = (s32)168 << 16;
                player_force_anim(p, ANIM_RUN_H, 1);
            }
            if (phase == 1 && p->x < ((s32)60 << 16)) p->x += (s32)0x28000;
            else if (phase == 1) { phase = 2; player_force_anim(p, ANIM_CHEER, 1); sfx_play(SFX_BARK); }
            player_advance(p);
            player_draw(p);
            thrower_shadow(p);
            end_t++;
            if (end_t > 400 || (end_t > 120 && (pads[0].pressed & (BTN_A | BTN_START)))) break;
        }
        if (end_t == 60) {
            if (metres > dog_record) dog_record = metres;
            points = metres * 100 + technical;
            match_score_add(0, points);
            for (i = 0; i < 42; i++) line[i] = 0;
            text_print(10, 6, "RECORD");
            fmt_number(line, dog_record, 3); line[3] = ' '; line[4] = 'M'; line[5] = '!'; line[6] = 0;
            text_print(20, 6, line);
            text_print(6, 9, "DISTANCE");
            fmt_number(line, metres, 3); line[3] = 0;
            text_print(16, 9, line);
            text_print(20, 9, "X 100");
            fmt_number(line, metres * 100, 5); line[5] = ' '; line[6] = '!'; line[7] = 0;
            text_print(27, 9, line);
            text_print(6, 12, "TECHNICAL POINT");
            fmt_number(line, technical, 5); line[5] = ' '; line[6] = '!'; line[7] = 0;
            for (k = 0; k < 4 && line[k] == '0'; k++) line[k] = ' ';
            text_print(27, 12, line);
            /* as the original (P-ROM 0xBC2E): by the points, under 10000 / 15000 / more */
            text_center(15, points < 10000 ? "GOOD!" : points < 15000 ? "WELL DONE!" : "EXCELLENT!");
        }
        frame_end_dog(cam);
    }
    spr_clear();
    vdp_wait_vblank();
    set_scroll_b(0);
    sr = ints_off();
    vdp_fill_plane(VRAM_PLANE_B, 0);
    ints_restore(sr);
    text_clear();
    text_set_palette(1);
    text_use_game_font(0);
    return points;
}

/* ---------------------------------------------------------------- FLYING DISC BOWLING */

/* The original's numbers (tools/ngrec, RAM): pins on a 16 px grid from (240, 168), the throw as in
 * a match (angle from the stick, speed from how quickly it follows the catch), the disc stops on
 * the first pin it hits and the pins it knocks slide on, slowing, knocking others. Our own:
 * the collision details, the side walls (y 112 / 208, the disc bounces) and moving along the
 * line. Ten frames of bowling in 40 seconds; the sheet as the original (marks: spare, strike, G, -, digit); points: total x 200,
 * strikes x 1000, spares x 500. */
extern const Frame disc_fly_frames[];
#define BW_DISC     1920                /* fence area: the disc, the pin's 5 pictures (4 tiles each), the glyphs */
#define BW_PIN      (BW_DISC + 4)
#define BW_GLYPH    (BW_PIN + 20)        /* (marks 32, big digits 40) */
#define BW_FLAG     (BW_GLYPH + 72)     /* P1's flag */
#define BW_LANE_TOP 112
#define BW_LANE_BOT 208

typedef struct { s32 x, y, vx, vy; u16 down, moving, spin, gone; } Pin;
static Pin pins[10];
static u8 bw_ball[21];                  /* pins per ball (0xFF = not thrown), 0x80 | 0 = gutter */
static u16 bw_strikes, bw_spares;
static u32 bowl_record;                 /* best points this session (HI) */

static void glyph_cell(u16 g, u16 col, u16 row) {           /* a mark: 2 tiles, top and bottom */
    u16 sr = ints_off();
    vdp_set_tile(VRAM_PLANE_A, col, row, TILE_ATTR(3, 1, 0, 0, BW_GLYPH + g * 2));
    vdp_set_tile(VRAM_PLANE_A, col, row + 1, TILE_ATTR(3, 1, 0, 0, BW_GLYPH + g * 2 + 1));
    ints_restore(sr);
}

static void cell_of(u16 f, u16 b, u16 *col, u16 *row) {
    if (f < 5) { *col = 4 + 4 * f + 2 * b; *row = 4; }
    else if (f < 9) { *col = 9 + 4 * (f - 5) + 2 * b; *row = 9; }
    else { *col = 25 + 2 * b; *row = 9; }
}

static u16 pins_of(u16 i) { return bw_ball[i] == 0xFF ? 0 : bw_ball[i] & 0x7F; }

/* score sheet: marks of every ball thrown, totals of the frames that can be counted */
static void bw_sheet(void) {
    u16 f = 0, i = 0, total = 0;
    char num[8];
    bw_strikes = bw_spares = 0;
    for (f = 0; f < 10 && bw_ball[i] != 0xFF; f++) {
        u16 col, row, a = pins_of(i), known = 1, score = 0, nb;
        u16 last = f == 9;
        u16 g0 = bw_ball[i] & 0x80 ? 2 : a == 10 ? 1 : a ? 5 + a : 3;
        cell_of(f, 0, &col, &row); glyph_cell(g0, col, row);
        if (a == 10) bw_strikes++;
        if (a == 10 && !last) {                      /* strike: the next two balls count too */
            nb = 1;
            if (bw_ball[i + 1] == 0xFF || bw_ball[i + 2] == 0xFF) known = 0;
            else score = 10 + pins_of(i + 1) + pins_of(i + 2);
        } else {
            u16 b = pins_of(i + 1);
            nb = 2;
            if (bw_ball[i + 1] == 0xFF) known = 0;
            else {
                u16 g1 = bw_ball[i + 1] & 0x80 ? 2 : (a < 10 && a + b == 10) ? 0 : b == 10 ? 1 : b ? 5 + b : 3;
                cell_of(f, 1, &col, &row); glyph_cell(g1, col, row);
                if (a < 10 && a + b == 10) bw_spares++;
                if (a + b >= 10) {                   /* spare (or strike in the 10th): one more ball */
                    if (bw_ball[i + 2] == 0xFF) known = 0;
                    else score = a + b + pins_of(i + 2);
                    if (last && bw_ball[i + 2] != 0xFF) {
                        u16 c = pins_of(i + 2);
                        cell_of(f, 2, &col, &row);
                        glyph_cell(bw_ball[i + 2] & 0x80 ? 2 : c == 10 ? 1 : c ? 5 + c : 3, col, row);
                    }
                } else score = a + b;
            }
        }
        if (!known) break;
        total += score;
        cell_of(f, 0, &col, &row);
        fmt_number(num, total, 3);
        {   /* right-aligned in the frame's box */
            u16 k = 0, end = f < 5 ? 6 + 4 * f : f < 9 ? 11 + 4 * (f - 5) : 29;
            while (num[k] == '0' && k < 2) num[k++] = ' ';
            text_print(end - 2, f < 5 ? 6 : 11, num);
        }
        i += nb;
    }
    fmt_number(num, total, 3);
    { u16 k = 0; while (num[k] == '0' && k < 2) num[k++] = ' '; }
    text_print(33, 10, num);
    bw_ball[20] = (u8)total;                 /* (kept for the result) */
}

static void pins_reset(u16 all) {
    u16 k;
    for (k = 0; k < 10; k++) {
        if (all) pins[k].down = pins[k].gone = 0;
        else if (pins[k].down) pins[k].gone = 1;
        pins[k].x = (s32)bowl_pins[k][0] << 16; pins[k].y = (s32)bowl_pins[k][1] << 16;
        pins[k].vx = pins[k].vy = 0; pins[k].moving = 0; pins[k].spin = 0;
    }
}

static s32 sabs(s32 v) { return v < 0 ? -v : v; }

static void frame_end(void) {
    vdp_wait_vblank();
    input_update();
}

static void num_trim(char *out, u16 value, u16 digits) {   /* right-aligned, no leading zeros */
    u16 k = 0;
    fmt_number(out, value, digits);
    while (k + 1 < digits && out[k] == '0') out[k++] = ' ';
}

/* a moving thing at (x, y) with velocity (vx, vy) touches pin k: knock it over */
static void pin_knock(Pin *q, s32 x, s32 y, s32 vx, s32 vy) {
    s16 dx = (s16)((q->x - x) >> 16), dy = (s16)((q->y - y) >> 16);
    s32 n = (dx < 0 ? -dx : dx) + (dy < 0 ? -dy : dy) + 1, sp = sabs(vx) + sabs(vy);
    q->down = 1; q->moving = 1;             /* its own speed plus a push away from the hitter */
    q->vx = vx * 5 / 8 + sp * dx / n / 2;
    q->vy = vy * 5 / 8 + sp * dy / n / 2;
}

u16 bonus_bowl(u16 char_index) {
    Player *p = &players[0];
    static const s16 sin9[9] = { 0, 1567, 2896, 3784, 4096, 3784, 2896, 1567, 0 };
    s32 dx = 0, dy = 0, vx = 0, vy = 0;
    u16 t, sr, k, timer = 40, tick = 0, ball = 0, frame = 0, in_frame = 0, state = 0, wait = 0, over = 0;
    u16 bgn, v_spr, gutter = 0, hit = 0, standing_before = 10;
    u32 points;
    s16 mx = 320;                           /* pinsetter x */
    char line[42];
    spr_clear();
    text_clear();
    vdp_wait_vblank();
    bank_map_video((u16)(u32)bowlshot_tiles_page);
    bg_load(&bg_bowlshot);
    bgn = bg_bowlshot.tiles_size >> 5;
    v_spr = 1 + bgn;                        /* the title, then the pinsetter, after the lane's tiles */
    vdp_set_color(16 + PAL1_HUD, hud_colors[0]);
    vdp_set_color(16 + PAL1_HUD + 1, hud_colors[1]);
    vdp_set_palette(3, bowl_pal);
    player_init(p, 0, char_index);          /* maps the character bank (the bowling sprites too) */
    p->x = (s32)52 << 16; p->y = (s32)168 << 16;
    player_force_anim(p, ANIM_IDLE, 1);
    text_use_game_font(1);
    sr = ints_off();
    vdp_load_tiles(bowl_glyphs, BW_GLYPH, 72);
    vdp_load_tiles(bowl_glyphs + 32 * (72 + 4 * char_index), BW_FLAG, 4);
    for (k = 0; k < 5; k++) vdp_load_tiles(bowl_img[k].tiles, BW_PIN + 4 * k, 4);
    vdp_load_tiles(bowl_img[6].tiles, v_spr, bowl_img[6].ntiles);
    ints_restore(sr);
    for (k = 0; k < 21; k++) bw_ball[k] = 0xFF;
    pins_reset(1);
    snd_music(&mus_bonus);
    /* title */
    text_center(6, "BONUS ROUND!");
    for (t = 0; t < 150; t++) {
        hud(bowl_record, 0, BW_FLAG, 1);
        spr_clear();
        frame_draw(&bowl_img[6], bowl_logo_pos[0], bowl_logo_pos[1], v_spr, 3, 1, 0);
        for (k = 0; k < 10; k++) {
            frame_draw(&bowl_img[0], (s16)(pins[k].x >> 16) - 4, (s16)(pins[k].y >> 16) - 25, BW_PIN, 3, 1, 0);
            frame_draw(&bowl_img[1], (s16)(pins[k].x >> 16) - 8, (s16)(pins[k].y >> 16) - 17, BW_PIN + 4, 3, 1, 0);
        }
        player_advance(p);
        player_draw(p);
        big_timer(BW_GLYPH + 32, 40);
        frame_end();
    }
    text_clear_row(6);
    sr = ints_off();
    vdp_load_tiles(bowl_img[5].tiles, v_spr, bowl_img[5].ntiles);           /* the pinsetter */
    ints_restore(sr);
    p->state = PS_HOLD; p->hold_frames = 0;
    player_force_anim(p, ANIM_HOLD, 1);
    /* play: state 0 holding, 1 the throw, 2 the disc and pins moving, 3 the pinsetter */
    for (t = 0; !over; t++) {
        if (++tick == 60) { tick = 0; if (timer) timer--; }
        big_timer(BW_GLYPH + 32, timer);
        hud(bowl_record, 0, BW_FLAG, 1);
        spr_clear();
        if (state == 0) {
            p->hold_frames++;
            if ((pads[0].held & BTN_UP) && p->y > ((s32)(BW_LANE_TOP + 16) << 16)) p->y -= 0x18000;   /* move along the line */
            if ((pads[0].held & BTN_DOWN) && p->y < ((s32)(BW_LANE_BOT - 8) << 16)) p->y += 0x18000;
            if ((pads[0].pressed & BTN_A) || p->hold_frames >= 75) {
                state = 1; player_force_anim(p, ANIM_THROW, 0);
            }
        } else if (state == 1 && p->step >= 3) {
            u16 power = p->hold_frames < p->ch->power_frames, a = 4;     /* angle in 22.5 degree steps */
            u16 speed = power ? 0x120 : p->hold_frames >= 64 ? 0x60 : p->ch->throw_speed[p->hold_frames >> 2];
            u16 h = pads[0].held;
            if (h & BTN_UP) a = (h & BTN_RIGHT) ? 3 : (h & BTN_LEFT) ? 1 : 2;
            else if (h & BTN_DOWN) a = (h & BTN_RIGHT) ? 5 : (h & BTN_LEFT) ? 7 : 6;
            vx = ((s32)sin9[a] * speed) >> 1;                  /* angle a * 22.5 degrees from up */
            vy = a <= 4 ? -(((s32)sin9[4 - a] * speed) >> 1) : ((s32)sin9[a - 4] * speed) >> 1;
            dx = p->x + ((s32)16 << 16); dy = p->y;
            sfx_play(power ? SFX_POWER : SFX_THROW);
            state = 2; wait = 0; gutter = hit = 0;
            standing_before = 0;
            for (k = 0; k < 10; k++) if (!pins[k].down) standing_before++;
        }
        if (state == 2) {
            u16 still = 1;
            if (vx || vy) {                                     /* the disc */
                dx += vx; dy += vy;
                if (dy < ((s32)BW_LANE_TOP << 16) || dy > ((s32)BW_LANE_BOT << 16)) {   /* off the side walls */
                    dy = dy < ((s32)BW_LANE_TOP << 16) ? (s32)BW_LANE_TOP << 16 : (s32)BW_LANE_BOT << 16;
                    vy = -vy;
                    sfx_play(SFX_BOUNCE);
                }
                if (dx > ((s32)330 << 16)) { vx = vy = 0; gutter = !hit; }
                else for (k = 0; k < 10; k++) {
                    Pin *q = &pins[k];
                    if (q->down || q->gone) continue;
                    if (sabs(q->x - dx) < ((s32)8 << 16) && sabs(q->y - dy) < ((s32)8 << 16)) {
                        pin_knock(q, dx, dy, vx, vy);
                        vx = vy = 0; hit = 1;                    /* the disc stops on the pin */
                        sfx_play(SFX_BOUNCE);
                        break;
                    }
                }
                still = 0;
            }
            for (k = 0; k < 10; k++) {                          /* knocked pins slide on */
                Pin *q = &pins[k];
                u16 j;
                if (!q->moving) continue;
                q->x += q->vx; q->y += q->vy;
                if (q->y < ((s32)BW_LANE_TOP << 16) || q->y > ((s32)BW_LANE_BOT << 16)) q->vy = -q->vy;
                for (j = 0; j < 10; j++) {
                    Pin *o = &pins[j];
                    if (o->down || o->gone) continue;
                    if (sabs(o->x - q->x) < ((s32)9 << 16) && sabs(o->y - q->y) < ((s32)9 << 16)) {
                        pin_knock(o, q->x, q->y, q->vx / 2, q->vy / 2);
                        q->vx /= 2; q->vy /= 2;
                    }
                }
                q->vx -= q->vx >> 3; q->vy -= q->vy >> 3;
                if ((t & 3) == 0) q->spin++;
                if (sabs(q->vx) + sabs(q->vy) < 0x2000) q->moving = 0;
                else still = 0;
            }
            if (still && ++wait == 40) {
                u16 n = 0;
                for (k = 0; k < 10; k++) if (pins[k].down && !pins[k].gone) n++;
                bw_ball[ball++] = (u8)(n | (gutter && !hit ? 0x80 : 0));
                bw_sheet();
                /* next ball: a new frame after a strike or the frame's second ball (third in the 10th) */
                in_frame++;
                {
                    u16 total = standing_before == 10 ? n : 10 - standing_before + n, all = 0;
                    u16 done = 0;
                    if (frame < 9) { if (n == 10 && in_frame == 1) done = 1; else if (in_frame == 2) done = 1; }
                    else {
                        if (in_frame == 3) done = 1;
                        else if (in_frame == 2 && pins_of(ball - 2) + pins_of(ball - 1) < 10 && pins_of(ball - 2) < 10) done = 1;
                        if (n == standing_before && standing_before > 0) all = 1;    /* cleared: a new rack */
                    }
                    (void)total;
                    if (done) { frame++; in_frame = 0; all = 1; }
                    if (frame == 10) over = 1;
                    state = 3; wait = 0; mx = 320;
                    standing_before = all ? 10 : 0;
                    if (all) pins_reset(1); else pins_reset(0);
                }
                if (timer == 0) over = 1;
            }
            if (!still) wait = 0;
        } else if (state == 3) {                                /* the pinsetter comes and goes */
            wait++;
            mx = wait < 24 ? 320 - wait * 5 : wait < 40 ? 200 : 200 + (wait - 40) * 5;
            if (wait >= 64) {
                state = 0; p->hold_frames = 0;
                player_force_anim(p, ANIM_HOLD, 1);
            }
            frame_draw(&bowl_img[5], mx, bowl_machine_pos[1], v_spr, 3, 1, 0);
        }
        /* pins: standing (with its shadow), tumbling, lying */
        for (k = 0; k < 10; k++) {
            Pin *q = &pins[k];
            s16 x = (s16)(q->x >> 16), y = (s16)(q->y >> 16);
            if (q->gone) continue;
            if (state == 3 && q->down && mx < x) continue;      /* swept away */
            if (!q->down) {
                frame_draw(&bowl_img[0], x - 4, y - 25, BW_PIN, 3, 1, 0);
                frame_draw(&bowl_img[1], x - 8, y - 17, BW_PIN + 4, 3, 1, 0);
            } else {
                u16 f = q->moving ? q->spin % 3 : 1;
                frame_draw(&bowl_img[2 + f], x - 8, y - 20, BW_PIN + 4 * (2 + f), 3, 1, q->spin & 4 ? 1 : 0);
            }
        }
        if (state == 2 && (vx || vy)) {
            const Frame *f = &disc_fly_frames[(t >> 1) & 7];
            dma_queue(f->tiles, BW_DISC << 5, f->ntiles << 4);
            frame_draw(f, (s16)(dx >> 16), (s16)(dy >> 16) - 24, BW_DISC, 1, 1, 0);
        }
        player_advance(p);
        if (state == 1 || state == 2) { if (p->anim_done) player_set_anim(p, ANIM_IDLE, 1); }
        player_draw(p);
        if (timer == 0 && state == 0) over = 1;
        frame_end();
    }
    /* results */
    points = (u32)bw_ball[20] * 200 + (u32)bw_strikes * 1000 + (u32)bw_spares * 500;
    if (points > bowl_record) bowl_record = points;
    hud(bowl_record, 0, BW_FLAG, 0);
    player_force_anim(p, ANIM_CHEER, 1);
    for (k = 0; k < 42; k++) line[k] = 0;
    text_print(10, 14, "TOTAL");
    num_trim(line, bw_ball[20], 3); text_print(17, 14, line);
    text_print(21, 14, "X  200 =");
    num_trim(line, bw_ball[20] * 200, 5); text_print(30, 14, line);
    text_print(10, 16, "STRIKE");
    num_trim(line, bw_strikes, 2); text_print(18, 16, line);
    text_print(21, 16, "X 1000 =");
    num_trim(line, bw_strikes * 1000, 5); text_print(30, 16, line);
    text_print(10, 18, "SPARE");
    num_trim(line, bw_spares, 2); text_print(18, 18, line);
    text_print(21, 18, "X  500 =");
    num_trim(line, bw_spares * 500, 5); text_print(30, 18, line);
    for (t = 0; t < 300; t++) {
        spr_clear();
        for (k = 0; k < 10; k++) if (!pins[k].down && !pins[k].gone) {
            frame_draw(&bowl_img[0], (s16)(pins[k].x >> 16) - 4, (s16)(pins[k].y >> 16) - 25, BW_PIN, 3, 1, 0);
            frame_draw(&bowl_img[1], (s16)(pins[k].x >> 16) - 8, (s16)(pins[k].y >> 16) - 17, BW_PIN + 4, 3, 1, 0);
        }
        player_advance(p);
        player_draw(p);
        frame_end();
        if (t > 60 && (pads[0].pressed & (BTN_A | BTN_START))) break;
    }
    spr_clear();
    vdp_wait_vblank();
    text_clear();
    text_use_game_font(0);
    return points > 0xFFFF ? 0xFFFF : (u16)points;
}
