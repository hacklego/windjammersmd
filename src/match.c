/* A Windjammers match: disc physics, catching/throwing, scoring, sets, HUD and the CPU player. */
#include "match.h"
#include "player.h"
#include "vdp.h"
#include "vram.h"
#include "input.h"
#include "text.h"
#include "bg.h"
#include "sound.h"
#include "rand.h"
#include "assets.h"
#include "movies.h"
#include "bank.h"

extern const Frame disc_fly_frames[], shadow_frames[], fireball_frames[];

#define FIX(n)  ((s32)(n) << 16)
#define INT(v)  ((s16)((v) >> 16))

/* court geometry (screen pixels) */
#define FIELD_TOP     52      /* disc bounces between these (ground plane y) */
#define FIELD_BOTTOM  200
#define GOAL_LEFT     20
#define GOAL_RIGHT    300
#define NET_X         160
#define ZONE5_TOP     100     /* centre goal zone worth 5 points, the rest 3 */
#define ZONE5_BOTTOM  152
#define PLAYER_TOP    64
#define PLAYER_BOTTOM 198
#define DISC_HEIGHT   24      /* flying disc drawn this far above its shadow */
#define GRAVITY       0x2000  /* lob gravity, 16.16 px/frame^2 */
#define HOLD_LIMIT    150     /* frames before an automatic throw */

enum { D_HELD, D_FLY, D_DEAD };
enum { T_NORMAL, T_SUPER, T_LOB, T_POP, T_CURVE };   /* T_POP: knocked up by a slide */
enum { PH_INTRO, PH_PLAY, PH_POINT, PH_SET_END, PH_DONE };

typedef struct {
    u16 state, holder, thrower, kind;
    s32 x, y, z, vx, vy, vz;
    u16 age, shown;                     /* frames in flight; frame id currently in VRAM */
    const SuperShot *sup;               /* super shot: recorded path and effects */
    s16 sdir, sflip;                    /* -1 = thrown to the left; -1 = path upside down */
    u16 fx_shown;
    s32 ang, rate;                      /* curve: angle (16.16, 256 = full turn) and its change per frame */
    u16 spd;                            /* curve: speed (1/32 px/frame) */
} Disc;

static Disc disc;
static u16 phase, phase_timer, server, time_left, time_frames, set_no;
static u16 sudden_death;                /* this set is the SUDDEN DEATH set: the first point wins it */
static u16 time_up;                     /* time ran out: the set ends at the next catch or point */
static u16 set_won[2];                  /* who got the set that just ended (both on a tie) */
static u16 control[2], paused, demo, demo_ticks, cpu_level = 2;
#define DEMO_TICKS 1140
void match_set_cpu_level(u16 level) { cpu_level = level > 6 ? 6 : level; }
static const Music *match_music;
void match_set_music(const Music *m) { match_music = m; }
u16 stat_catches, stat_throws, stat_pops, stat_supers;   /* for automated tests */
static Pad ctl[2];                      /* this frame's buttons for each side */
static u16 hud_dirty;

/* ---------------------------------------------------------------- helpers */

static s16 fwd(const Player *p) { return p->side ? -1 : 1; }

static s32 move_speed(const Player *p) { return p->ch->run_speed; }

/* The original's disc model: an angle (0-255, 0x40 = straight right, 0xC0 = left) and a speed in
 * 1/32 px/frame; velocity = sin/cos(angle) * speed, sin scaled to 4096. */
static const s16 sin_q[65] = { 0, 101, 201, 301, 401, 501, 601, 700, 799, 897, 995, 1092, 1189, 1285, 1380, 1474, 1567, 1660, 1751, 1842, 1931, 2019, 2106, 2191, 2276, 2359, 2440, 2520, 2598, 2675, 2751, 2824, 2896, 2967, 3035, 3102, 3166, 3229, 3290, 3349, 3406, 3461, 3513, 3564, 3612, 3659, 3703, 3745, 3784, 3822, 3857, 3889, 3920, 3948, 3973, 3996, 4017, 4036, 4052, 4065, 4076, 4085, 4091, 4095, 4096 };
static s16 isin(u16 a) {
    a &= 0xFF;
    if (a < 0x40) return sin_q[a];
    if (a < 0x80) return sin_q[0x80 - a];
    if (a < 0xC0) return -sin_q[a - 0x80];
    return -sin_q[0x100 - a];
}
static void disc_velocity(u16 angle, u16 speed) {
    disc.vx = ((s32)isin(angle) * speed) >> 1;              /* 16.16 px/frame */
    disc.vy = -((s32)isin(angle + 0x40) * speed) >> 1;
}

/* Throw angle from the stick, as the original: straight, up/down 45 deg, up/down+forward 22.5 deg,
 * up/down+back 67.5 deg; mirrored for the right-hand player. */
static u16 throw_angle(const Player *p, s16 dx, s16 dy) {
    s16 f = dx * fwd(p);
    u16 a = 0x40;
    if (dy) a = f > 0 ? 0x10 : f < 0 ? 0x30 : 0x20;          /* degrees away from straight */
    a = dy < 0 ? 0x40 - a : dy > 0 ? 0x40 + a : 0x40;
    if (dx == 0 && dy == 0) a = 0x40;
    return p->side ? (u16)(0x100 - a) & 0xFF : a;
}

/* Curve throws, as the original: the stick turned through 90 degrees or more (two 45 degree steps)
 * within the last few frames before A. The curve turns the way the stick last turned (clockwise on
 * screen = the angle grows). Stick directions: 0 up, 1 up-right ... 7 up-left, 8 centred. */
#define STICK_HIST 8
static u8 stick_hist[2][STICK_HIST];    /* newest first */
static s16 ai_curve[2];                 /* the CPU's curve choice (it does not turn a stick) */

static void stick_record(u16 side, s16 dx, s16 dy) {
    static const u8 dir[3][3] = { { 7, 0, 1 }, { 6, 8, 2 }, { 5, 4, 3 } };   /* [dy + 1][dx + 1] */
    u16 i;
    for (i = STICK_HIST - 1; i; i--) stick_hist[side][i] = stick_hist[side][i - 1];
    stick_hist[side][0] = dir[dy + 1][dx + 1];
}

static s16 curve_sense(u16 side) {      /* -> 0, 1 (clockwise) or -1 */
    u16 i, last = 8, path = 0;
    s16 sense = 0;
    if (control[side] == CTRL_CPU) return ai_curve[side];
    for (i = 0; i < STICK_HIST; i++) {
        u16 d = stick_hist[side][i];
        s16 step;
        if (d == 8 || d == last) continue;
        if (last != 8) {
            step = (s16)((last - d) & 7);           /* from the older direction d to the newer one */
            if (step > 4) step -= 8;
            if (!sense) sense = step > 0 ? 1 : -1;
            path += step < 0 ? -step : step;
        }
        last = d;
    }
    return path >= 2 ? sense : 0;
}

/* Throw speed: quicker returns are faster; within the power window it is a power throw. */
static u16 throw_speed(const Player *p, u16 *power) {
    u16 h = p->hold_frames;
    *power = h < p->ch->power_frames;
    if (*power) return 0x120;
    if (h >= 64) return 0x60;
    return p->ch->throw_speed[h >> 2];
}

static s16 iabs(s16 v) { return v < 0 ? -v : v; }

static void banner(const char *a, const char *b) {
    text_clear_row(12); text_clear_row(14);
    if (a) text_center(12, a);
    if (b) text_center(14, b);
}

/* HUD as in the original: "P1 [flag] score" and "P2 [flag] score" in the top row (plane A), the
 * scoreboard's big digits and TIME box as sprites (tools/mkmovies.py make_hud). */
static u16 hud_time_shown;

static void hud_init(void) {
    u16 side, k, sr = ints_off();
    vdp_load_tiles(hud_tiles, VRAM_HUD, HUD_TIMES);                                  /* big digits */
    vdp_load_tiles(hud_tiles + HUD_GLYPHS * 32, VRAM_HUD + HUD_TIMES, HUD_FLAGS - HUD_GLYPHS);
    for (side = 0; side < 2; side++)
        vdp_load_tiles(hud_tiles + (HUD_FLAGS + (players[side].char_index * 2 + side) * 4) * 32,
                       VRAM_HUD_FLAGS + side * 4, 4);
    vdp_load_tiles(hud_tiles + HUD_SET_BAR * 32, VRAM_HUD_SET_BAR, 3);
    ints_restore(sr);
    vdp_set_color(16 + PAL1_HUD, hud_colors[0]);
    vdp_set_color(16 + PAL1_HUD + 1, hud_colors[1]);
    for (side = 0; side < 2; side++) {
        u16 x = side ? 26 : 2, ci = players[side].char_index;
        vdp_set_tile(VRAM_PLANE_A, x, 1, TILE_ATTR(1, 1, 0, 0, VRAM_HUD + HUD_TIMES));
        vdp_set_tile(VRAM_PLANE_A, x + 1, 1, TILE_ATTR(1, 1, 0, 0, VRAM_HUD + HUD_TIMES + 1 + side));
        for (k = 0; k < 4; k++)
            vdp_set_tile(VRAM_PLANE_A, x + 3 + (k >> 1), 1 + (k & 1),
                         TILE_ATTR(hud_flag_pal[ci][side][k], 1, 0, 0, VRAM_HUD_FLAGS + side * 4 + k));
    }
    hud_time_shown = 0xFFFF;
}

/* The arcade's score in the top row, right-aligned up to 7 digits (see match_score_add). */
static u32 arcade_score[2];

static void draw_hud(void) {
    u16 side, i;
    for (side = 0; side < 2; side++) {
        u32 v = arcade_score[side];
        u16 col = side ? 37 : 13;
        for (i = 0; i < 7; i++, v /= 10)
            vdp_set_tile(VRAM_PLANE_A, col - i, 1, (v || !i) ? TILE_ATTR(1, 1, 0, 0, VRAM_HUD + HUD_TIMES + 3 + (u16)(v % 10)) : 0);
    }
    hud_dirty = 0;
}

/* The TIME box, as in the original: a big box over the scoreboard (the arcade's fix layer, here
 * plane A in front of the HUD sprites) shows "30" for the first three seconds of a set, "15" for
 * three seconds, then counts 10..1; each time 10 frames after the clock ticks, for 48 frames. From
 * 00 it says "TIME UP" until the set ends. Its tiles keep the box palette's indexes (hud_box_src),
 * mapped to the nearest colours of this court's palette 1. */
#define BOX_COL 18
#define BOX_ROW 1
static u8 box_lut[16], box_buf[16 * 32];
static u16 box_loaded = 0xFFFF, box_frames, box_delay, box_next, box_set_start;

static u16 col_dist(u16 a, u16 b) {
    s16 r = ((a >> 1) & 7) - ((b >> 1) & 7), g = ((a >> 5) & 7) - ((b >> 5) & 7), bl = ((a >> 9) & 7) - ((b >> 9) & 7);
    return r * r + g * g + bl * bl;
}

static u16 box_pal1[16], box_use_disc;  /* palette 1 in a match; the disc's colours in 10-13 */

static void box_lut_build(void) {       /* the box's colours -> palette 1 (10-13 only while they hold the disc's) */
    u16 i, j, last = box_use_disc ? 15 : PAL1_DISC - 1;
    box_lut[0] = 0;
    for (i = 1; i < 16; i++) {
        u16 best = 1;
        for (j = 2; j < 16; j++) {
            if (j > last && j < PAL1_BLACK) continue;
            if (col_dist(hud_box_src[i], box_pal1[j]) < col_dist(hud_box_src[i], box_pal1[best])) best = j;
        }
        box_lut[i] = best;
    }
}

static void box_init(u16 court_no) {
    const u16 *court = (const u16 *)bg_court_shots[court_no].pal + 16;
    u16 i;
    for (i = 1; i < 8; i++) box_pal1[i] = court[i];
    box_pal1[PAL1_HUD] = hud_colors[0]; box_pal1[PAL1_HUD + 1] = hud_colors[1];
    for (i = 0; i < 4; i++) box_pal1[PAL1_DISC + i] = ((const u16 *)disc_colors)[i];
    box_pal1[PAL1_BLACK] = 0x000; box_pal1[PAL1_WHITE] = 0xEEE;
    box_use_disc = 1;
    box_lut_build();
    box_loaded = 0xFFFF; box_frames = 0;
}

static u16 box_pending;                 /* 1 show / 2 clear the cells right after the vblank, with the sprites */

static void box_cells_now(u16 on) {
    u16 c, r;
    for (c = 0; c < 4; c++)
        for (r = 0; r < 4; r++)
            vdp_set_tile(VRAM_PLANE_A, BOX_COL + c, BOX_ROW + r,
                         on ? TILE_ATTR(1, 1, 0, 0, VRAM_HUD_BOX + (c >> 1) * 8 + (c & 1) * 4 + r) : 0);
}

static void box_cells(u16 on) { box_pending = on ? 1 : 2; }

static void box_convert(u16 k) {        /* the box's 16 tiles in this palette, to VRAM at the vblank */
    const u8 *src[2];
    u16 i;
    src[0] = hud_tiles + (HUD_BOX + (k >> 8) * 8) * 32;
    src[1] = hud_tiles + (HUD_BOX + (4 + (k & 0xFF)) * 8) * 32;
    for (i = 0; i < 16 * 32; i++) {
        u8 b = src[i >> 8][i & 255];
        box_buf[i] = box_lut[b >> 4] << 4 | box_lut[b & 15];
    }
    dma_queue(box_buf, VRAM_HUD_BOX << 5, 16 * 16);
    box_loaded = k;
}

static void box_show(u16 tens, u16 units, u16 frames) {     /* tens 0, 1, 2 = 3, 3 = U; units 0-9, 10 = P */
    u16 k = tens << 8 | units;
    if (k != box_loaded) box_convert(k);
    if (!box_frames) box_cells(1);
    box_frames = frames;
}

/* palette 1's 10-13 now hold the disc's colours (1) or an overlay's (0): the box keeps its own */
static void box_palette(u16 disc_colours) {
    if (disc_colours == box_use_disc) return;
    box_use_disc = disc_colours;
    box_lut_build();
    if (box_loaded != 0xFFFF) box_convert(box_loaded);
}

static void box_tick(void) {            /* the clock has just been set or gone down */
    u16 t = time_left;
    if (t >= 28 && t <= 30) box_next = 2 << 8 | 0;
    else if (t >= 13 && t <= 15) box_next = 1 << 8 | 5;
    else if (t >= 1 && t <= 10) box_next = (t / 10) << 8 | t % 10;
    else if (!t) box_next = 3 << 8 | 10;
    else return;
    box_delay = 10;
}

static void box_update(void) {
    if (box_delay && !--box_delay)      /* "TIME UP" stays until the set ends */
        box_show(box_next >> 8, box_next & 0xFF, (box_next & 0xFF) == 10 ? 0xFFFF : 48);
    else if (box_frames && box_frames != 0xFFFF && !--box_frames) box_cells(0);
}

static void box_hide(void) {
    if (box_frames || box_pending) box_cells_now(0);
    box_frames = box_delay = box_pending = 0;
}

static void hud_sprites(void) {
    u16 side, box = time_up ? HUD_TIME_UP : HUD_TIME_TOP - (time_left > 30 ? 30 : time_left);
    if (box != hud_time_shown) {
        dma_queue(hud_tiles + (HUD_TIMES + box * 4) * 32, VRAM_HUD_TIME << 5, 4 * 16);
        hud_time_shown = box;
    }
    u16 prio = !box_frames;             /* behind the TIME box while it is up */
    if (!box_frames) spr_add(152, 12, 2, 2, TILE_ATTR(1, 1, 0, 0, VRAM_HUD_TIME));
    for (side = 0; side < 2; side++) {
        u16 sc = players[side].score > 99 ? 99 : players[side].score, x = side ? 169 : 121;
        spr_add(x, 16, 2, 2, TILE_ATTR(1, prio, 0, 0, VRAM_HUD + HUD_DIGITS + (sc / 10) * 4));
        spr_add(x + 16, 16, 2, 2, TILE_ATTR(1, prio, 0, 0, VRAM_HUD + HUD_DIGITS + (sc % 10) * 4));
        if (players[side].sets) {       /* as the original: the bar over the score lights up */
            spr_add(x, 8, 2, 1, TILE_ATTR(1, 1, 0, 0, VRAM_HUD_SET_BAR));
            spr_add(x + 16, 8, 2, 1, TILE_ATTR(1, 1, 0, 0, VRAM_HUD_SET_BAR + 1));
        }
    }
}

static void clamp_player(Player *p) {
    s32 lo = FIX(p->side ? NET_X + 12 : 24), hi = FIX(p->side ? 296 : NET_X - 12);
    if (p->x < lo) p->x = lo;
    if (p->x > hi) p->x = hi;
    if (p->y < FIX(PLAYER_TOP)) p->y = FIX(PLAYER_TOP);
    if (p->y > FIX(PLAYER_BOTTOM)) p->y = FIX(PLAYER_BOTTOM);
}

/* ---------------------------------------------------------------- fences */

/* A disc hitting the top or bottom fence shakes it, as in the original: its other two frames
 * (recorded per court, tools/mkmovies.py) alternate for a few frames. */
static u16 cur_court, fence_t[2] = { 0xFFFF, 0xFFFF }, fence_shown[2];
static const u8 fence_seq[] = { 1, 1, 2, 1, 2, 1, 0, 1, 0 };

static void fence_cells(const FencePatch *fp, u16 base, u16 f) {
    const u8 *map = bg_court_shots[cur_court].map;
    const u16 *patch = fp->cells;
    u16 nt = *patch++, n = *patch++;
    (void)f;
    if (!base) vdp_load_tiles(fp->tiles, VRAM_FENCE, nt);
    while (n--) {
        u16 cell = *patch++, w = *patch++;
        if (base) w = (map[cell * 2] << 8) | map[cell * 2 + 1];
        vdp_set_tile(VRAM_PLANE_B, cell % 40, cell / 40, w);
    }
}

static void fence_cells(const FencePatch *fp, u16 base, u16 f);
static void fence_hit(u16 bottom) {
    u16 o = bottom ^ 1;
    if (fence_shown[o]) {           /* one shaking fence at a time: they share the tile slots */
        u16 sr = ints_off();
        fence_cells(&court_fence[cur_court][o * 2 + fence_shown[o] - 1], 1, o);
        ints_restore(sr);
        fence_shown[o] = 0;
    }
    fence_t[o] = 0xFFFF;
    fence_t[bottom] = 0;
}

static void fence_update(void) {
    u16 f;
    for (f = 0; f < 2; f++) {
        u16 k, sr;
        if (fence_t[f] == 0xFFFF) continue;
        k = fence_t[f] >> 1 < sizeof fence_seq ? fence_seq[fence_t[f] >> 1] : 0;
        if (k != fence_shown[f]) {
            sr = ints_off();
            if (fence_shown[f]) fence_cells(&court_fence[cur_court][f * 2 + fence_shown[f] - 1], 1, f);
            if (k) fence_cells(&court_fence[cur_court][f * 2 + k - 1], 0, f);
            ints_restore(sr);
            fence_shown[f] = k;
        }
        if ((fence_t[f] >> 1) >= sizeof fence_seq) fence_t[f] = 0xFFFF;
        else fence_t[f]++;
    }
}

/* ---------------------------------------------------------------- disc */

static void give_disc(u16 side) {
    Player *p = &players[side];
    disc.state = D_HELD; disc.holder = side; disc.kind = T_NORMAL;
    disc.z = 0;
    p->state = PS_HOLD; p->state_timer = 0;
    p->hold_frames = 64;                /* a serve is never a power throw */
    player_set_anim(p, ANIM_HOLD, 1);
    pal1_fixed_colors(0);
    box_palette(1);
}

static void launch(Player *p) {
    s16 f = fwd(p);
    u16 power, speed = throw_speed(p, &power);
    s32 sp = (s32)speed << 11;
    disc.state = D_FLY; disc.thrower = p->side; disc.kind = p->throw_kind; disc.age = 0;
    disc.x = p->x + FIX(f * 16); disc.y = p->y; disc.z = 0; disc.vz = 0;
    switch (p->throw_kind) {
    case T_SUPER: {
        /* the character's own super shot, as recorded from the original (tools/mkmovies.py) */
        u16 i;
        disc.sup = &super_shots[p->char_index];
        disc.sdir = f;
        disc.sflip = (p->throw_dir == (u16)-1) ? -1 : 1;
        disc.fx_shown = 0xFFFF;
        disc.vx = disc.vy = 0;
        pal1_fixed_colors(1);
        for (i = 0; i < 4; i++) vdp_set_color(16 + PAL1_DISC + i, disc.sup->pal[i]);
        box_palette(0);
        voice_play(VOICE_SUPER, p->char_index);
        stat_supers++;
        break; }
    case T_LOB: {
        s32 tx = FIX(p->side ? 72 : 248), ty = p->y + (s32)(s16)p->throw_dir * FIX(48);
        if (ty < FIX(FIELD_TOP + 12)) ty = FIX(FIELD_TOP + 12);
        if (ty > FIX(FIELD_BOTTOM - 12)) ty = FIX(FIELD_BOTTOM - 12);
        disc.vx = (tx - disc.x) >> 6; disc.vy = (ty - disc.y) >> 6;   /* lands after 64 frames */
        disc.vz = GRAVITY * 32;
        sfx_play(SFX_LOB);
        break; }
    case T_CURVE:
        disc.ang = (s32)p->throw_angle << 16;
        disc.rate = (s32)p->ch->curve_rate * speed;
        if ((s16)p->throw_dir_curve < 0) disc.rate = -disc.rate;
        disc.spd = speed;
        disc_velocity(p->throw_angle, speed);
        sfx_play(power ? SFX_POWER : SFX_THROW);
        break;
    default:
        disc_velocity(p->throw_angle, speed);
        sfx_play(power ? SFX_POWER : SFX_THROW);
    }
    p->super_ready = 0;
    stat_throws++;
}

static void start_point_pause(void);

/* ---------------------------------------------------------------- score banner */

/* After a point the original shows the score on a purple bar ("00-03"): the bar on plane A (its
 * tiles in the font's slots), the big digits as sprites in the fence/HUD spare slots. */
static u16 banner_on, banner_val[4], banner_pending, banner_bar_pending;
static u16 counts_on;                   /* set end: SET COUNTS shown (counts_show) */
static const u16 banner_digit_vram[4] = { VRAM_FENCE, VRAM_FENCE + 40, VRAM_FENCE + 80, VRAM_HUD + 68 };
static const s16 banner_digit_x[4] = { 80, 112, 176, 208 };

static void part_draw(const BannerPart *b, u16 vram, u16 col, u16 row) {
    u16 x, y, i = 0, sr = ints_off();
    vdp_load_tiles(b->tiles, vram, b->ntiles);
    for (y = 0; y < b->h; y++)
        for (x = 0; x < b->w; x++, i++)
            if (b->map[i] != 0xFFFF)
                vdp_set_tile(VRAM_PLANE_A, col + x, row + y, TILE_ATTR(1, 1, 0, 0, vram) + b->map[i]);
    ints_restore(sr);
}

/* Set start, as in the original: the SET panel (SET 1, SET 2, SET FINAL or SUDDEN DEATH; in 1P
 * "ROUND r / SET s") and in
 * set 1 the goal value markers and the "12 POINTS / 30 SEC" line, on plane A while the set is
 * introduced. Their tiles go wherever
 * there is room: nothing else uses the font, fence, spare HUD and disc slots meanwhile. */
static u16 setstart_on;
#define POOLS 5
static u16 pool_at[POOLS] = { 0, VRAM_FENCE, VRAM_FONT, VRAM_HUD + 68, VRAM_DISC };   /* [0]: after the court's tiles */
static u16 pool_len[POOLS] = { 0, 128, 72, 60, 36 };
static u16 pool_used[POOLS];

static u16 pool_alloc(u16 n) {          /* best fit: the region with the least room that has enough */
    u16 i, best = 0xFFFF;
    for (i = 0; i < POOLS; i++)
        if (pool_len[i] - pool_used[i] >= n && (best == 0xFFFF || pool_len[i] - pool_used[i] < pool_len[best] - pool_used[best]))
            best = i;
    if (best == 0xFFFF) return 0xFFFF;
    pool_used[best] += n;
    return pool_at[best] + pool_used[best] - n;
}

static void setstart_part(const BannerPart *b, const u16 *pos, u16 row) {
    u16 v = pool_alloc(b->ntiles);
    if (v != 0xFFFF) part_draw(b, v, pos[0], row);
}

enum { SS_SET1, SS_SET2, SS_FINAL, SS_SUDDEN };
static u16 match_round;                 /* 1P: round 1-5, 6 = FINAL ("ROUND r / SET s" panels); 0: 2P */
void match_set_round(u16 round) { match_round = round > 6 ? 6 : round; }

static void setstart_markers(const BannerPart *l3, const u16 *l3_pos, const BannerPart *r3, const u16 *r3_pos,
                             const BannerPart *l5, const u16 *l5_pos, const BannerPart *r5, const u16 *r5_pos) {
    /* 3 at the top and bottom of each goal, 5 in the middle (the same tiles twice) */
    u16 vl3 = pool_alloc(l3->ntiles), vr3 = pool_alloc(r3->ntiles);
    if (vl3 != 0xFFFF) { part_draw(l3, vl3, l3_pos[0], l3_pos[1]); part_draw(l3, vl3, l3_pos[0], 150 / 8); }
    if (vr3 != 0xFFFF) { part_draw(r3, vr3, r3_pos[0], r3_pos[1]); part_draw(r3, vr3, r3_pos[0], 150 / 8); }
    setstart_part(l5, l5_pos, l5_pos[1]);
    setstart_part(r5, r5_pos, r5_pos[1]);
}

static void setstart_show(u16 kind) {
    static const BannerPart *const panel[4] = { &setstart_panel_set1, &setstart_panel_set2, &setstart_panel_final, &setstart_panel_sudden };
    static const u16 *const pos[4] = { setstart_panel_set1_pos, setstart_panel_set2_pos, setstart_panel_final_pos, setstart_panel_sudden_pos };
    static const BannerPart *const round_digit[6] = { &setstart_round_r1, &setstart_round_r2, &setstart_round_r3,
                                                      &setstart_round_r4, &setstart_round_r5, &setstart_round_r6 };
    static const BannerPart *const set_digit[3] = { &setstart_round_s1, &setstart_round_s2, &setstart_round_s3 };
    u16 i, round = match_round && kind != SS_SUDDEN;
    for (i = 0; i < POOLS; i++) pool_used[i] = 0;
    for (i = 0; i < 4; i++) vdp_set_color(16 + PAL1_DISC + i, setstart_pal[round ? 4 : kind][i]);
    box_palette(0);
    vdp_wait_vblank();
    setstart_on = 1;
    if (round) {                        /* 1P: ROUND r / SET s */
        setstart_part(&setstart_round_words, setstart_round_words_pos, setstart_round_words_pos[1]);
        setstart_part(round_digit[match_round - 1], setstart_round_r1_pos, setstart_round_r1_pos[1]);
        setstart_part(set_digit[kind], setstart_round_s1_pos, setstart_round_s1_pos[1]);
        if (kind != SS_SET1) return;
        setstart_part(&setstart_round_rules, setstart_round_rules_pos, setstart_round_rules_pos[1]);
        setstart_markers(&setstart_round_ml3, setstart_round_ml3_pos, &setstart_round_mr3, setstart_round_mr3_pos,
                         &setstart_round_ml5, setstart_round_ml5_pos, &setstart_round_mr5, setstart_round_mr5_pos);
        return;
    }
    setstart_part(panel[kind], pos[kind], pos[kind][1]);
    if (kind != SS_SET1) return;            /* later sets only show their panel */
    setstart_part(&setstart_rules, setstart_rules_pos, setstart_rules_pos[1]);
    setstart_markers(&setstart_l3, setstart_l3_pos, &setstart_r3, setstart_r3_pos,
                     &setstart_l5, setstart_l5_pos, &setstart_r5, setstart_r5_pos);
}

static void setstart_hide(void) {
    u16 y;
    if (!setstart_on) return;
    for (y = 2; y < 28; y++) text_clear_row(y);
    text_init();
    pal1_fixed_colors(0);
    box_palette(1);
    setstart_on = 0;
    hud_init();                     /* the markers covered part of the HUD's second row */
    hud_dirty = 1;
}

static void banner_show(void) {
    u16 k, i, sr;
    for (i = 0; i < 4; i++) vdp_set_color(16 + PAL1_DISC + i, banner_pal[i]);
    box_palette(0);
    banner_val[0] = players[0].score / 10 % 10; banner_val[1] = players[0].score % 10;
    banner_val[2] = players[1].score / 10 % 10; banner_val[3] = players[1].score % 10;
    sr = ints_off();
    for (k = 0; k < 4; k++)
        vdp_load_tiles(banner_digits[banner_val[k]].tiles, banner_digit_vram[k], banner_digits[banner_val[k]].ntiles);
    ints_restore(sr);
    banner_on = 1;
    banner_bar_pending = 1;         /* drawn after the next vblank, with the digit sprites */
}

static void banner_hide(void) {
    u16 y;
    banner_bar_pending = 0;
    if (!banner_on) return;
    for (y = 9; y < 21; y++) text_clear_row(y);
    text_init();
    banner_on = 0;
}

static void banner_sprites(void) {
    u16 k;
    if (!banner_on) return;
    for (k = 0; k < 4; k++)
        frame_draw(counts_on ? &banner_digits_top[banner_val[k]] : &banner_digits[banner_val[k]],
                   banner_digit_x[k], 72, banner_digit_vram[k], 1, 1, 0);
}

/* "n POINTS GOAL" ribbon sliding out of the goal after a score, as sprites. Its tiles go after
 * the score bar's in the font's slots (restored by text_init when the banner goes). */
#define VRAM_RIBBON (VRAM_FONT + 16)
static u16 ribbon_on, ribbon_t, ribbon_side;
static s16 ribbon_y;
static const Frame *ribbon_f;

static void ribbon_show(u16 side, u16 pts, s16 y) {
    const Frame *f = ribbon_f = &banner_ribbons[(side ? 2 : 0) + (pts == 5)];
    dma_queue(f->tiles, VRAM_RIBBON << 5, f->ntiles << 4);
    ribbon_side = side;
    ribbon_y = pts == 5 ? 96 : y < (FIELD_TOP + FIELD_BOTTOM) / 2 ? 33 : 159;
    ribbon_t = 0; ribbon_on = 1;
}

static void ribbon_sprites(void) {
    s16 off;            /* px back towards the goal: out in 8 frames, a pause, then slowly back */
    if (!ribbon_on) return;
    if (ribbon_t < 60) ribbon_t++;
    off = ribbon_t < 8 ? 19 - ribbon_t * 19 / 8 : ribbon_t < 35 ? 0 : ribbon_t - 35;
    frame_draw(ribbon_f, ribbon_side ? 54 - off : 202 + off, ribbon_y, VRAM_RIBBON, 1, 1, 0);
}

/* At the end of a set the banner also shows "SET COUNTS" and each side's sets, composed into the
 * bar on plane A at build time (as sprites they would crowd out the players' on those lines). */

static void pieces_load(const Frame *f, const u16 *vram) {
    u16 i;
    for (i = 0; i < f->npieces; i++) {
        const SprPiece *p = &f->pieces[i];
        vdp_load_tiles(f->tiles + p->tile * 32, vram[i], (((p->size >> 2) & 3) + 1) * ((p->size & 3) + 1));
    }
}

static void pieces_draw(const Frame *f, const u16 *vram, s16 x, s16 y) {
    u16 i;
    for (i = 0; i < f->npieces; i++) {
        const SprPiece *p = &f->pieces[i];
        u16 pl = (p->size & 0x20) ? (p->size >> 6) & 3 : 1;      /* 0x20: the piece's own palette */
        spr_add(x + p->dx, y + p->dy, ((p->size >> 2) & 3) + 1, (p->size & 3) + 1, TILE_ATTR(pl, 1, 0, 0, vram[i]));
    }
}

static u16 sets_shown(u16 side) { return players[side].sets > 3 ? 3 : players[side].sets; }

/* draw a part's cell over a tile in RAM: its non-zero pixels replace the tile's (flips applied) */
static void part_over(u8 *dst, const BannerPart *b, s16 cx, s16 cy) {
    u16 m, y, i;
    const u8 *t;
    if (cx < 0 || cy < 0 || cx >= (s16)b->w || cy >= (s16)b->h) return;
    m = b->map[cy * b->w + cx];
    if (m == 0xFFFF) return;
    t = b->tiles + (m & 0x7FF) * 32;
    for (y = 0; y < 8; y++) {
        const u8 *row = t + ((m & 0x1000) ? 7 - y : y) * 4;
        u8 *d = dst + y * 4;
        for (i = 0; i < 4; i++) {
            u8 v = (m & 0x0800) ? (u8)((row[3 - i] >> 4) | (row[3 - i] << 4)) : row[i];
            if (v & 0xF0) d[i] = (d[i] & 0x0F) | (v & 0xF0);
            if (v & 0x0F) d[i] = (d[i] & 0xF0) | (v & 0x0F);
        }
    }
}

static void counts_show(void) {
    /* cells 7-32, rows 15-19: bar, then the score digits' bottoms, then SET COUNTS and the sets */
    static const u16 dcol[4] = { 10, 14, 22, 26 };
    const BannerPart *lay[8];
    s16 lx[8], ly[8];
    u16 n = 0, k, col, row, slot = 0, sr;
    u16 region_at[3], region_len[3], r = 0;
    u8 tile[32];
    lay[n] = &banner_bar; lx[n] = 8; ly[n++] = 11;
    for (k = 0; k < 4; k++) { lay[n] = &banner_digit_bottom[banner_val[k]]; lx[n] = dcol[k]; ly[n++] = 15; }
    lay[n] = &banner_ovl_label; lx[n] = 7; ly[n++] = 15;
    lay[n] = &banner_ovl_sets[0][sets_shown(0)]; lx[n] = 7; ly[n++] = 15;
    lay[n] = &banner_ovl_sets[1][sets_shown(1)]; lx[n] = 27; ly[n++] = 15;
    if (banner_bar_pending) { part_draw(&banner_bar, VRAM_FONT, 8, 11); banner_bar_pending = 0; }
    sr = ints_off();                    /* the score digits as sprites down to y = 120 only */
    for (k = 0; k < 4; k++)
        vdp_load_tiles(banner_digits_top[banner_val[k]].tiles, banner_digit_vram[k], banner_digits_top[banner_val[k]].ntiles);
    ints_restore(sr);
    region_at[0] = pool_at[0]; region_len[0] = pool_len[0];      /* VRAM free meanwhile */
    region_at[1] = VRAM_FONT + 16; region_len[1] = 56;
    region_at[2] = VRAM_DISC; region_len[2] = 36;
    ribbon_on = 0;
    for (row = 15; row < 20; row++)
        for (col = 7; col < 33; col++) {
            u16 any = 0, word = 0, i;
            for (i = 0; i < 32; i++) tile[i] = 0;
            for (i = 0; i < n; i++) part_over(tile, lay[i], col - lx[i], row - ly[i]);
            for (i = 0; i < 32; i++) any |= tile[i];
            if (any) {
                while (r < 3 && slot >= region_len[r]) { r++; slot = 0; }
                if (r < 3) {
                    word = TILE_ATTR(1, 1, 0, 0, region_at[r] + slot);
                    sr = ints_off();
                    vdp_load_tiles(tile, region_at[r] + slot, 1);
                    ints_restore(sr);
                    slot++;
                }
            }
            sr = ints_off();
            vdp_set_tile(VRAM_PLANE_A, col, row, word);
            ints_restore(sr);
        }
    counts_on = 1;
}

static void super_done(void) {
    if (disc.kind == T_SUPER && disc.fx_shown != 0xFFFF) { text_init(); disc.fx_shown = 0xFFFF; }
}

static void score_point(u16 side, u16 pts) {
    char buf[20];
    super_done();
    {   /* the score bar's digits use the fence's tile slots: settle any shaking fence */
        u16 f, sr = ints_off();
        for (f = 0; f < 2; f++) {
            if (fence_shown[f]) fence_cells(&court_fence[cur_court][f * 2 + fence_shown[f] - 1], 1, f);
            fence_shown[f] = 0; fence_t[f] = 0xFFFF;
        }
        ints_restore(sr);
    }
    players[side].score += pts;
    /* the original (P-ROM 0x902C, 0x122BE): 100 a point, and 1000 for each point past the goal */
    arcade_score[side] += pts * 100;
    if (!sudden_death && players[side].score > SET_POINTS) arcade_score[side] += (players[side].score - SET_POINTS) * 1000;
    disc.state = D_DEAD;
    pal1_fixed_colors(0);
    box_palette(1);
    sfx_play(pts == 2 ? SFX_GOAL2 : pts == 5 ? SFX_GOAL5 : SFX_GOAL);
    (void)buf;
    banner_pending = 20;          /* the score bar comes up a moment after the goal */
    server = side ^ 1;          /* the player who conceded serves */
    player_force_anim(&players[side], ANIM_CHEER, 1);          /* as in the original */
    player_force_anim(&players[side ^ 1], ANIM_SAD, 1);
    players[0].state = players[1].state = PS_FROZEN;
    if (pts != 2) ribbon_show(side, pts, INT(disc.y));
    if (demo) text_clear_row(14);    /* PRESS START: its glyphs' tiles are lent to the ribbon */
    start_point_pause();
    hud_dirty = 1;
}

/* As the original (counted in a recorded game): a standing player catches the disc, a sliding one
 * knocks it up instead; it floats up and comes down slowly, and whoever catches it then gets the
 * power to throw a super shot. Left to land, it is 2 points against that half. */
#define POP_GRAVITY 0x0F00

static void disc_pop(Player *p) {
    disc.kind = T_POP; disc.thrower = p->side;
    disc.vx = -disc.vx / 12; disc.vy = disc.vy / 12;
    disc.z = 0; disc.vz = 0x22000;              /* up about 40 px, down again after ~75 frames */
    stat_pops++;
    pal1_fixed_colors(0);
    box_palette(1);
    super_done();
    sfx_play(SFX_BOUNCE);
}

static void try_catch(Player *p) {
    s16 dx, dy;
    u16 pop;
    if (disc.state != D_FLY || (p->state != PS_FREE && p->state != PS_DASH)) return;
    pop = disc.kind == T_POP;
    if (pop) {
        if (p->state == PS_DASH || disc.vz > 0 || disc.z > FIX(28)) return;   /* stand under it */
    } else {
        /* only discs heading into this player's half */
        if (p->side == 0 && disc.vx > 0) return;
        if (p->side == 1 && disc.vx < 0) return;
        if (disc.thrower == p->side) return;
        if (disc.z > FIX(20)) return;
    }
    dx = iabs(INT(disc.x - p->x)); dy = iabs(INT(disc.y - p->y));
    if (dx > (p->state == PS_DASH ? 22 : 16) || dy > (p->state == PS_DASH ? 18 : 14)) return;
    if (p->state == PS_DASH && (disc.kind == T_NORMAL || disc.kind == T_CURVE)) { disc_pop(p); return; }
    disc.state = D_HELD; disc.holder = p->side; disc.z = 0;
    p->super_ready = pop;
    p->throw_queued = 0;
    p->state = PS_CATCH; p->state_timer = 0;
    player_force_anim(p, ANIM_CATCH, 0);
    pal1_fixed_colors(0);
    box_palette(1);
    super_done();
    if (disc.kind == T_SUPER) voice_play(VOICE_POWERCATCH, p->char_index);
    else if (pop) voice_play(VOICE_CHARGE, p->char_index);
    else sfx_play(SFX_CATCH);
    stat_catches++;
    if (time_up) { phase = PH_SET_END; phase_timer = 0; }
}

/* curve hitting a wall (the original's 0x25EB2): reflect, turn 16 further the curve's way, keep
 * the angle away from the wall, then fly straight on */
static void curve_bounce(u16 bottom) {
    u16 a = (u16)((bottom ? 0x180 : 0x80) - ((disc.ang >> 16) & 0xFF));
    u16 right = disc.vx > 0;
    a = (a + (disc.rate < 0 ? -16 : 16)) & 0xFF;
    if (!bottom) {
        if (right && (a < 0x10 || a >= 0xC0)) a = 0x10;
        if (!right && (a < 0x41 || a >= 0xF1)) a = 0xF0;
    } else {
        if (right && a >= 0x71 && a < 0xC1) a = 0x70;
        if (!right && a >= 0x40 && a < 0x90) a = 0x90;
    }
    disc.kind = T_NORMAL;
    disc_velocity(a, disc.spd);
}

static void update_disc(void) {
    if (disc.state != D_FLY) return;
    disc.age++;
    if (disc.kind == T_CURVE) {
        disc.ang += disc.rate;
        disc_velocity((u16)(disc.ang >> 16) & 0xFF, disc.spd);
    }
    disc.x += disc.vx; disc.y += disc.vy;
    if (disc.vz || disc.z) {
        disc.z += disc.vz; disc.vz -= disc.kind == T_POP ? POP_GRAVITY : GRAVITY;
        if (disc.z <= 0) {      /* landed */
            disc.z = 0;
            if (disc.kind == T_POP) { score_point(INT(disc.x) < NET_X ? 1 : 0, 2); return; }
            if (disc.kind == T_LOB) { score_point(disc.thrower, 2); return; }
        }
    }
    if (disc.kind == T_SUPER) {
        u16 t = disc.age - 1;
        if (t + 1 < disc.sup->frames) {
            s16 dx = disc.sup->path[t * 2], dy = disc.sup->path[t * 2 + 1];
            disc.x += FIX(dx * disc.sdir);
            disc.y += FIX(dy * disc.sflip);
            disc.vx = FIX(dx * disc.sdir); disc.vy = FIX(dy * disc.sflip);  /* carried on after the path */
            if ((disc.y < FIX(FIELD_TOP) && dy * disc.sflip < 0) || (disc.y > FIX(FIELD_BOTTOM) && dy * disc.sflip > 0))
                disc.sflip = -disc.sflip;
        }
    }
    if (disc.y < FIX(FIELD_TOP)) {
        disc.y = FIX(FIELD_TOP);
        if (disc.kind == T_CURVE) curve_bounce(0); else disc.vy = -disc.vy;
        sfx_play(SFX_BOUNCE); fence_hit(0);
    }
    if (disc.y > FIX(FIELD_BOTTOM)) {
        disc.y = FIX(FIELD_BOTTOM);
        if (disc.kind == T_CURVE) curve_bounce(1); else disc.vy = -disc.vy;
        sfx_play(SFX_BOUNCE); fence_hit(1);
    }
    if (disc.z == 0 && (disc.x < FIX(GOAL_LEFT) || disc.x > FIX(GOAL_RIGHT))) {
        s16 y = INT(disc.y);
        score_point(disc.x < FIX(GOAL_LEFT) ? 1 : 0, (y >= ZONE5_TOP && y <= ZONE5_BOTTOM) ? 5 : 3);
    }
}

static void draw_disc(void) {
    const Frame *f;
    u16 id;
    s16 x, y;
    if (disc.state == D_DEAD) return;
    if (disc.state == D_HELD) return;        /* drawn as part of the holder's animation frames */
    {
        if (disc.kind == T_SUPER) { id = 200 + ((disc.age >> 2) & 3); f = &fireball_frames[id - 200]; }
        else { id = (disc.age >> 1) & 7; f = &disc_fly_frames[id]; }
        x = INT(disc.x); y = INT(disc.y) - DISC_HEIGHT - INT(disc.z);
    }
    if (id != disc.shown) { dma_queue(f->tiles, VRAM_DISC << 5, f->ntiles << 4); disc.shown = id; }
    if (disc.kind == T_SUPER && disc.age < disc.sup->frames) {
        u16 k = disc.sup->fx[disc.age];
        const Frame *fx = &disc.sup->fx_frames[k];
        if (k != disc.fx_shown) { dma_queue(fx->tiles, VRAM_FX << 5, fx->ntiles << 4); disc.fx_shown = k; }
        frame_draw(fx, INT(disc.x), INT(disc.y), VRAM_FX, 1, 1, disc.sdir < 0);
    }
    frame_draw(f, x, y, VRAM_DISC, 1, 1, 0);
}

static void draw_shadows(void) {
    if (disc.state == D_FLY) frame_draw(&shadow_frames[0], INT(disc.x), INT(disc.y), VRAM_SHADOW, 1, 0, 0);
    frame_draw(&shadow_frames[1], INT(players[0].x), INT(players[0].y), VRAM_SHADOW + 2, 1, 0, 0);
    frame_draw(&shadow_frames[1], INT(players[1].x), INT(players[1].y), VRAM_SHADOW + 2, 1, 0, 0);
}

/* ---------------------------------------------------------------- players */

static void update_player(Player *p, const Pad *c) {
    s16 dx = 0, dy = 0;
    if (c->held & BTN_LEFT) dx = -1;
    if (c->held & BTN_RIGHT) dx = 1;
    if (c->held & BTN_UP) dy = -1;
    if (c->held & BTN_DOWN) dy = 1;
    p->state_timer++;
    if (p->hold_frames < 0xFFFF) p->hold_frames++;
    stick_record(p->side, dx, dy);

    switch (p->state) {
    case PS_FREE: {
        s32 sp = move_speed(p);
        if ((c->pressed & BTN_A) && (dx || dy)) {
            p->state = PS_DASH; p->state_timer = 0; p->dash_dx = dx; p->dash_dy = dy;
            player_force_anim(p, dy < 0 ? ANIM_SLIDE_UP : dy > 0 ? ANIM_SLIDE_DOWN : ANIM_SLIDE_F, 0);
            break;
        }
        if (dx && dy) sp = (sp * 181) >> 8;
        p->x += dx * sp; p->y += dy * sp;
        if (dx) player_set_anim(p, ANIM_RUN_H, 1);
        else if (dy < 0) player_set_anim(p, ANIM_RUN_UP, 1);
        else if (dy > 0) player_set_anim(p, ANIM_RUN_DOWN, 1);
        else player_set_anim(p, ANIM_IDLE, 1);
        break; }
    case PS_DASH: {
        s32 sp = move_speed(p) * 3;
        if (p->dash_dx && p->dash_dy) sp = (sp * 181) >> 8;
        p->x += p->dash_dx * sp; p->y += p->dash_dy * sp;
        if (p->state_timer >= 12) p->state = PS_FREE;
        break; }
    case PS_CATCH:
        if (c->pressed & BTN_A) p->throw_queued = 1;      /* pressed during the catch: throw at once */
        if (p->anim_done) {
            p->state = PS_HOLD; p->state_timer = 0; p->hold_frames = 0;
            player_set_anim(p, ANIM_HOLD, 1);
        }
        break;
    case PS_HOLD:
        if ((c->pressed & BTN_A) || p->throw_queued) {
            p->throw_queued = 0;
            p->throw_angle = throw_angle(p, dx, dy);
            p->throw_kind = p->super_ready ? T_SUPER : T_NORMAL;
            if (!p->super_ready && (p->throw_dir_curve = (u16)curve_sense(p->side)) != 0) p->throw_kind = T_CURVE;
        } else if (c->pressed & BTN_B) {
            p->throw_kind = T_LOB;              /* straight on without up or down, as the original */
        } else if (p->state_timer > HOLD_LIMIT) {
            p->throw_kind = T_NORMAL; dy = 0;
            p->throw_angle = throw_angle(p, 0, 0);
        } else break;
        p->throw_dir = (u16)dy;
        p->state = PS_THROW; p->state_timer = 0;
        player_force_anim(p, (p->throw_kind == T_LOB) ? ANIM_LOB : ANIM_THROW, 0);
        break;
    case PS_THROW:
        if (disc.state == D_HELD && disc.holder == p->side
            && p->step >= ((p->throw_kind == T_LOB) ? 2 : 3)) launch(p);
        if (p->anim_done) { p->state = PS_FREE; player_set_anim(p, ANIM_IDLE, 1); }
        break;
    case PS_FROZEN:
        break;
    }
    clamp_player(p);
    player_advance(p);
}

/* ---------------------------------------------------------------- CPU */

static s16 ai_target_y[2], ai_wait[2];

/* where (y) the disc will cross x = px, following wall bounces */
static s16 predict_y(s16 px) {
    s32 x = disc.x, y = disc.y, vx = disc.vx, vy = disc.vy;
    u16 i;
    if (disc.kind == T_LOB || disc.kind == T_POP) {
        /* lob: aim for the landing point */
        s32 z = disc.z, vz = disc.vz;
        for (i = 0; i < 200 && z > 0; i++) { x += vx; y += vy; z += vz; vz -= GRAVITY; }
        return INT(y);
    }
    if (disc.kind == T_CURVE) {         /* follow the curve (roughly: straight after a wall) */
        s32 a = disc.ang;
        u16 curving = 1;
        for (i = 0; i < 200; i++) {
            if ((vx < 0 && x <= FIX(px)) || (vx > 0 && x >= FIX(px))) break;
            if (curving) {
                a += disc.rate;
                vx = ((s32)isin(a >> 16) * disc.spd) >> 1;
                vy = -((s32)isin((a >> 16) + 0x40) * disc.spd) >> 1;
            }
            x += vx; y += vy;
            if (y < FIX(FIELD_TOP) || y > FIX(FIELD_BOTTOM)) { vy = -vy; curving = 0; }
            if (vx == 0) break;
        }
        return INT(y);
    }
    for (i = 0; i < 200; i++) {
        if ((vx < 0 && x <= FIX(px)) || (vx > 0 && x >= FIX(px))) break;
        x += vx; y += vy;
        if (y < FIX(FIELD_TOP) || y > FIX(FIELD_BOTTOM)) vy = -vy;
    }
    return INT(y);
}

static void ai_control(Player *p, Pad *out) {
    u16 held = 0, pressed = 0;
    s16 px = INT(p->x), py = INT(p->y), tx, ty;
    if (p->state == PS_HOLD) {
        if (p->state_timer == 1)       /* quick power returns get likelier with the level */
            ai_wait[p->side] = (rand16() % 8) < cpu_level ? 1 : 6 + (rand16() & 31);
        if (p->state_timer >= ai_wait[p->side]) {
            u16 r = rand16() & 15, fwdkey = p->side ? BTN_LEFT : BTN_RIGHT, backkey = p->side ? BTN_RIGHT : BTN_LEFT;
            if (r < 3) { pressed = BTN_B; held = r == 0 ? 0 : (r & 1) ? BTN_UP : BTN_DOWN; }   /* lob */
            else {
                pressed = BTN_A;
                ai_curve[p->side] = (r & 3) == 0 && (rand16() % 6) < cpu_level ? ((rand16() & 1) ? 1 : -1) : 0;
                held = r < 8 ? 0 : (r & 1) ? BTN_UP : BTN_DOWN;
                if (r >= 12) held |= (r & 2) ? fwdkey : backkey;
            }
        }
    } else if (disc.state == D_FLY && disc.kind == T_POP && (p->side ? INT(disc.x) >= NET_X - 16 : INT(disc.x) < NET_X + 16)) {
        /* a disc knocked up on this side: stand under it, catch it, then the super */
        tx = INT(disc.x); ty = INT(disc.y);
        if (tx < px - 3) held |= BTN_LEFT; else if (tx > px + 3) held |= BTN_RIGHT;
        if (ty < py - 3) held |= BTN_UP; else if (ty > py + 3) held |= BTN_DOWN;
    } else if (disc.state == D_FLY && (p->side ? disc.vx > 0 : disc.vx < 0)
               && disc.age > 16 - cpu_level * 3) {                              /* reaction time */
        if (((frame_counter + p->side * 4) & 7) == 0) {
            s16 err = 32 >> (cpu_level >> 1);                                    /* +-16 .. +-4 px */
            ai_target_y[p->side] = predict_y(px) + (s16)(rand16() % (u16)err) - (err >> 1);
        }
        ty = ai_target_y[p->side];
        if (disc.kind == T_LOB) {
            s32 x = disc.x, vx = disc.vx, z = disc.z, vz = disc.vz;
            while (z > 0) { x += vx; z += vz; vz -= GRAVITY; }
            tx = INT(x);
            if (tx < px - 4) held |= BTN_LEFT; else if (tx > px + 4) held |= BTN_RIGHT;
        }
        if (ty < py - 4) held |= BTN_UP; else if (ty > py + 4) held |= BTN_DOWN;
        if (cpu_level >= 2 && iabs(ty - py) > 40 && iabs(INT(disc.x) - px) < 90 && (rand16() & 3) == 0)
            pressed |= BTN_A;                                                    /* dash */
        else if (cpu_level >= 2 && disc.kind == T_NORMAL && iabs(INT(disc.x) - px) < 36 && iabs(ty - py) < 12
                 && (rand16() % 128) < cpu_level - 1) {                          /* slide into it: up it goes */
            held |= p->side ? BTN_RIGHT : BTN_LEFT;
            pressed |= BTN_A;
        }
    } else {
        /* drift back home */
        tx = p->side ? 270 : 50; ty = 128;
        if (tx < px - 8) held |= BTN_LEFT; else if (tx > px + 8) held |= BTN_RIGHT;
        if (ty < py - 8) held |= BTN_UP; else if (ty > py + 8) held |= BTN_DOWN;
    }
    out->held = held;
    out->pressed = pressed;
}

/* ---------------------------------------------------------------- flow */

static void reset_positions(void) {
    u16 i;
    for (i = 0; i < 2; i++) {
        Player *p = &players[i];
        p->x = FIX(i ? 272 : 48); p->y = FIX(128);
        p->state = PS_FREE; p->super_ready = 0;
        player_set_anim(p, ANIM_IDLE, 1);
    }
}

static void start_point_pause(void) { phase = PH_POINT; phase_timer = 0; }

static void start_set(void) {
    char t[8] = "SET ";
    players[0].score = players[1].score = 0;
    time_left = SET_SECONDS; time_frames = 0; time_up = 0;
    box_hide();
    box_set_start = 1;                  /* "30" once play starts */
    reset_positions();
    disc.state = D_DEAD;
    t[4] = '0' + set_no; t[5] = 0;
    (void)t;
    banner(0, 0);
    {   /* tied sets give both players the set: 1-1 -> SET FINAL, 2-2 -> SUDDEN DEATH */
        u16 kind = set_no == 1 ? SS_SET1 : players[0].sets != players[1].sets ? SS_SET2
                 : players[0].sets >= 2 ? SS_SUDDEN : SS_FINAL;
        sudden_death = kind == SS_SUDDEN;
        setstart_show(kind);
    }
    if (match_music) snd_music(match_music);
    phase = PH_INTRO; phase_timer = 0;
    hud_dirty = 1;
}

static void serve(void) {
    ribbon_on = 0;
    if (box_set_start) { box_set_start = 0; box_tick(); }
    disc.shown = 0xFFFF;            /* the disc's tiles may have been lent to an overlay */
    banner_hide();
    setstart_hide();
    reset_positions();
    give_disc(server);
    banner(0, 0);
    phase = PH_PLAY;
    sfx_play(SFX_SERVE);
}

/* time up, a point in the sudden death set or 12 points: the set is over */
static u16 set_over(void) {
    return time_up || sudden_death || players[0].score >= SET_POINTS || players[1].score >= SET_POINTS;
}

/* ---------------------------------------------------------------- match result */

/* As in the original, over the court: the two portrait frames with WIN! and LOSE (or DRAW GAME),
 * the winner's VS portrait and the loser's dejected one, and the sets. The players are not drawn,
 * which frees their VRAM and palettes 2 and 3 for the portraits. */
static const Frame *const port_win[2][6] = {
    { &spr_vsport_l0, &spr_vsport_l1, &spr_vsport_l2, &spr_vsport_l3, &spr_vsport_l4, &spr_vsport_l5 },
    { &spr_vsport_r0, &spr_vsport_r1, &spr_vsport_r2, &spr_vsport_r3, &spr_vsport_r4, &spr_vsport_r5 } };
static const u16 *const port_win_pal[2][6] = {
    { spr_vsport_l0_pal, spr_vsport_l1_pal, spr_vsport_l2_pal, spr_vsport_l3_pal, spr_vsport_l4_pal, spr_vsport_l5_pal },
    { spr_vsport_r0_pal, spr_vsport_r1_pal, spr_vsport_r2_pal, spr_vsport_r3_pal, spr_vsport_r4_pal, spr_vsport_r5_pal } };
static const Frame *const port_lose[2][6] = {
    { &spr_resport_l0, &spr_resport_l1, &spr_resport_l2, &spr_resport_l3, &spr_resport_l4, &spr_resport_l5 },
    { &spr_resport_r0, &spr_resport_r1, &spr_resport_r2, &spr_resport_r3, &spr_resport_r4, &spr_resport_r5 } };
static const u16 *const port_lose_pal[2][6] = {
    { spr_resport_l0_pal, spr_resport_l1_pal, spr_resport_l2_pal, spr_resport_l3_pal, spr_resport_l4_pal, spr_resport_l5_pal },
    { spr_resport_r0_pal, spr_resport_r1_pal, spr_resport_r2_pal, spr_resport_r3_pal, spr_resport_r4_pal, spr_resport_r5_pal } };

#define RESULT_VRAM VRAM_FONT           /* the plane image: font + both players' slots (328 tiles) */
static u16 rs_at[5], rs_len[5];

static u16 rs_alloc(u16 n) {            /* first fit among the slots free meanwhile */
    u16 i;
    for (i = 0; i < 5; i++)
        if (rs_len[i] >= n) { rs_at[i] += n; rs_len[i] -= n; return rs_at[i] - n; }
    return VRAM_FENCE;                  /* (does not happen with the game's images) */
}

static void pieces_alloc(const Frame *f, u16 *vram) {
    u16 i;
    for (i = 0; i < f->npieces; i++) {
        u16 sz = f->pieces[i].size;
        vram[i] = rs_alloc((((sz >> 2) & 3) + 1) * ((sz & 3) + 1));
    }
}

static void result_screen(u16 winner) {
    static const BannerPart *const image[3] = { &result_p1win, &result_p2win, &result_draw };
    const Frame *const cdig[4] = { &result_counts_d0, &result_counts_d1, &result_counts_d2, &result_counts_d3 };
    u16 kind = winner == MATCH_DRAW ? 2 : winner, side, i, t, sr;
    const Frame *port[2], *dig[2];
    u16 pv[2][6], dv[2][2];
    spr_clear();
    vdp_wait_vblank();                  /* players and overlays gone before their tiles are reused */
    rs_at[0] = RESULT_VRAM + image[kind]->ntiles; rs_len[0] = VRAM_DISC - rs_at[0];
    rs_at[1] = VRAM_DISC; rs_len[1] = 36;
    rs_at[2] = VRAM_HUD + 68; rs_len[2] = 60;
    rs_at[3] = VRAM_FENCE; rs_len[3] = 128;
    rs_at[4] = VRAM_SHADOW + 10; rs_len[4] = 18;
    for (i = 0; i < 4; i++) vdp_set_color(16 + PAL1_DISC + i, result_pal[i]);
    sr = ints_off();                    /* the HUD flags use the palettes the portraits take */
    for (side = 0; side < 2; side++)
        for (i = 0; i < 4; i++) vdp_set_tile(VRAM_PLANE_A, (side ? 26 : 2) + 3 + (i >> 1), 1 + (i & 1), 0);
    ints_restore(sr);
    for (side = 0; side < 2; side++) {
        u16 ci = players[side].char_index, won = winner == side;
        port[side] = won ? port_win[side][ci] : port_lose[side][ci];
        vdp_set_palette(2 + side, won ? port_win_pal[side][ci] : port_lose_pal[side][ci]);
        pieces_alloc(port[side], pv[side]);
        dig[side] = cdig[sets_shown(side)];
        pieces_alloc(dig[side], dv[side]);
    }
    part_draw(image[kind], RESULT_VRAM, 3, 4);
    sr = ints_off();
    for (side = 0; side < 2; side++) { pieces_load(port[side], pv[side]); pieces_load(dig[side], dv[side]); }
    ints_restore(sr);
    for (t = 0; t < 300; t++) {
        spr_clear();
        hud_sprites();
        pieces_draw(dig[0], dv[0], 56, 124);
        pieces_draw(dig[1], dv[1], 216, 124);
        for (side = 0; side < 2; side++)
            pieces_draw(port[side], pv[side], result_frame_pos[kind][side][0] + result_portrait_offset[side][0],
                        result_frame_pos[kind][side][1] + result_portrait_offset[side][1]);
        vdp_wait_vblank();
        input_update();
        if (t > 60 && ((pads[0].pressed | pads[1].pressed) & BTN_START)) break;
    }
    spr_clear();
    vdp_wait_vblank();
    for (t = 3; t < 28; t++) text_clear_row(t);
    text_init();
    for (side = 0; side < 2; side++) {          /* as the players need them again */
        vdp_set_palette(2 + side, players[side].ch->palettes + side * 16);
        players[side].shown_frame = 0xFFFF;
    }
    pal1_fixed_colors(0);
    box_palette(1);
    disc.shown = 0xFFFF;
    hud_init();
    hud_dirty = 1;
}

static void sort_and_draw(void) {
    Player *a = &players[0], *b = &players[1];
    spr_clear();
    hud_sprites();
    ribbon_sprites();               /* in front of the banner, as in the original */
    banner_sprites();
    draw_disc();
    if (a->y > b->y) { player_draw(a); player_draw(b); }   /* nearer the camera first = on top */
    else { player_draw(b); player_draw(a); }
    draw_shadows();
}

void match_score_reset(void) { arcade_score[0] = arcade_score[1] = 0; }
u32 match_score(u16 side) { return arcade_score[side]; }
void match_score_add(u16 side, u32 points) { arcade_score[side] += points; if (arcade_score[side] > 9999999) arcade_score[side] = 9999999; }
u16 match_sets(u16 side) { return players[side].sets; }

u16 match_run(u16 char0, u16 char1, u16 court, u16 p1_control, u16 p2_control) {
    u16 winner = 0;
    control[0] = p1_control & 0x7F; control[1] = p2_control;   /* p1 | 0x80: CPU, not a demo (tests) */
    demo = p1_control == CTRL_CPU;
    if (demo) match_score_reset();
    text_clear();
    bank_map_video(bg_court_pages[court]);       /* the court's tiles */
    bg_load(&bg_court_shots[court]);
    pool_at[0] = VRAM_BG_TILES + (bg_court_shots[court].tiles_size >> 5);
    pool_len[0] = VRAM_FONT - pool_at[0];
    cur_court = court;
    fence_t[0] = fence_t[1] = 0xFFFF;
    fence_shown[0] = fence_shown[1] = 0;
    {
        u16 sr = ints_off();
        vdp_load_tiles(shadow_frames[0].tiles, VRAM_SHADOW, shadow_frames[0].ntiles);
        vdp_load_tiles(shadow_frames[1].tiles, VRAM_SHADOW + 2, shadow_frames[1].ntiles);
        ints_restore(sr);
    }
    player_init(&players[0], 0, char0);
    player_init(&players[1], 1, char1);
    players[0].sets = players[1].sets = 0;
    text_use_game_font(1);
    hud_init();
    box_init(court);
    disc.shown = 0xFFFF;
    set_no = 1; server = 0; paused = 0;
    start_set();

    for (demo_ticks = 0;; demo_ticks++) {
        if (banner_bar_pending) { part_draw(&banner_bar, VRAM_FONT, 8, 11); banner_bar_pending = 0; }
        if (box_pending) { box_cells_now(box_pending == 1); box_pending = 0; }
        input_update();
        if (demo) {                     /* attract mode: as long as the arcade's demo, PRESS START blinking */
            if (demo_ticks >= DEMO_TICKS) { spr_clear(); vdp_wait_vblank(); text_use_game_font(0); return 0xFFFE; }
            /* (not over an overlay: they borrow the font's tiles) */
            if ((demo_ticks & 31) == 0 && !(setstart_on | banner_on | ribbon_on | counts_on)) text_center(14, "PRESS START");
            if ((demo_ticks & 31) == 20) text_clear_row(14);
        }
        if (control[0] == CTRL_HUMAN) ctl[0] = pads[0]; else ai_control(&players[0], &ctl[0]);
        if (control[1] == CTRL_HUMAN) ctl[1] = pads[1]; else ai_control(&players[1], &ctl[1]);
        if (demo && ((pads[0].pressed | pads[1].pressed) & BTN_START)) { spr_clear(); vdp_wait_vblank(); text_use_game_font(0); return 0xFFFF; }

        if (!demo && phase == PH_PLAY && (pads[0].pressed & BTN_START)) {
            paused ^= 1;
            banner(paused ? "PAUSE" : 0, 0);
        }
        if (paused) { vdp_wait_vblank(); continue; }

        phase_timer++;
        switch (phase) {
        case PH_INTRO:
            if (phase_timer > 100) serve();
            break;
        case PH_PLAY:
            update_player(&players[0], &ctl[0]);
            update_player(&players[1], &ctl[1]);
            try_catch(&players[0]);
            try_catch(&players[1]);
            update_disc();
            /* as in the original: 00 for a second, then TIME UP, and the set ends as soon as
               the disc is caught (try_catch) or scores */
            if (phase == PH_PLAY && !time_up && ++time_frames >= 60) {
                time_frames = 0;
                if (time_left) { time_left--; box_tick(); }
                else {
                    time_up = 1;
                    sfx_play(SFX_TIMEUP);
                    if (disc.state == D_HELD) { phase = PH_SET_END; phase_timer = 0; }
                }
                hud_dirty = 1;
            }
            break;
        case PH_POINT:
            player_advance(&players[0]); player_advance(&players[1]);
            if (banner_pending && !--banner_pending) banner_show();
            if (phase_timer > 110) {
                if (set_over()) { phase = PH_SET_END; phase_timer = 0; }
                else serve();
            }
            break;
        case PH_SET_END:
            if (phase_timer == 1) {
                u16 side;
                box_hide();
                /* the higher score gets the set; a tie gives it to both */
                set_won[0] = players[0].score >= players[1].score;
                set_won[1] = players[1].score >= players[0].score;
                for (side = 0; side < 2; side++) {
                    players[side].sets += set_won[side];
                    player_force_anim(&players[side], set_won[side] ? ANIM_CHEER : ANIM_LOSE, 1);
                }
                players[0].state = players[1].state = PS_FROZEN;
                disc.state = D_DEAD;
                banner(0, 0);
                if (!banner_on) { banner_pending = 0; banner_show(); }
                counts_show();
                hud_dirty = 1;
                snd_music(&mus_set);
                if (set_won[0] != set_won[1]) {
                    voice_play(VOICE_SETWIN, players[set_won[1]].char_index);
                    arcade_score[set_won[1]] += 5000 + time_left * 100;    /* P-ROM 0x1134C: + 100 a second left */
                }
            }
            player_advance(&players[0]); player_advance(&players[1]);
            if (phase_timer > 180) {
                u16 s0 = players[0].sets, s1 = players[1].sets;
                counts_on = 0;
                banner_hide();
                if (s0 != s1 && (s0 >= SETS_TO_WIN || s1 >= SETS_TO_WIN)) { winner = s1 > s0; phase = PH_DONE; }
                else if (s0 == s1 && s0 > SETS_TO_WIN) { winner = MATCH_DRAW; phase = PH_DONE; }   /* 3-3 */
                else { set_no++; server = set_won[0] != set_won[1] ? set_won[0] : server ^ 1; start_set(); }
            }
            break;
        case PH_DONE:
            box_hide();
            if (!demo) result_screen(winner);
            spr_clear();
            vdp_wait_vblank();
            text_use_game_font(0);
            return winner;
        }
        if (hud_dirty) draw_hud();
        box_update();
        fence_update();
        sort_and_draw();
        vdp_wait_vblank();
    }
}
