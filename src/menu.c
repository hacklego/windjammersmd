#include "menu.h"
#include "vdp.h"
#include "input.h"
#include "text.h"
#include "bg.h"
#include "player.h"
#include "sound.h"
#include "rand.h"
#include "assets.h"
#include "movie.h"
#include "vram.h"
#include "bank.h"
#include "movies.h"
#include "match.h"
#include "ranking.h"


static void frame_end(void) {
    vdp_wait_vblank();
    input_update();
}

static u16 any_confirm(u16 pad) { return pads[pad].pressed & (BTN_A | BTN_B | BTN_START); }

/* The original's big font (arrow, digits, letters) for the menus, at MENU_GLYPH_VRAM. */
#define MENU_GLYPH_VRAM VRAM_PLAYER0            /* 148 tiles: the players' slots are free in menus */

static void glyph_put(u16 glyph, u16 col, u16 row) {        /* 2 x 2 tiles: TL, BL, TR, BR */
    u16 v = MENU_GLYPH_VRAM + glyph * 4, sr = ints_off();
    vdp_set_tile(VRAM_PLANE_A, col, row, TILE_ATTR(1, 1, 0, 0, v));
    vdp_set_tile(VRAM_PLANE_A, col, row + 1, TILE_ATTR(1, 1, 0, 0, v + 1));
    vdp_set_tile(VRAM_PLANE_A, col + 1, row, TILE_ATTR(1, 1, 0, 0, v + 2));
    vdp_set_tile(VRAM_PLANE_A, col + 1, row + 1, TILE_ATTR(1, 1, 0, 0, v + 3));
    ints_restore(sr);
}

static void glyph_clear(u16 col, u16 row) {
    u16 sr = ints_off();
    vdp_set_tile(VRAM_PLANE_A, col, row, 0); vdp_set_tile(VRAM_PLANE_A, col, row + 1, 0);
    vdp_set_tile(VRAM_PLANE_A, col + 1, row, 0); vdp_set_tile(VRAM_PLANE_A, col + 1, row + 1, 0);
    ints_restore(sr);
}

static void big_text(u16 col, u16 row, const char *s) {     /* letters, digits, spaces */
    for (; *s; s++, col += 2) {
        if (*s >= '0' && *s <= '9') glyph_put(1 + (*s - '0'), col, row);
        else if (*s >= 'A' && *s <= 'Z') glyph_put(11 + (*s - 'A'), col, row);
        else glyph_clear(col, row);
    }
}

static void menu_screen(const BgAsset *bg) {
    u16 i, sr;
    spr_clear();
    text_clear();
    vdp_wait_vblank();
    if (bg == &bg_menushot) bank_map_video((u16)(u32)menushot_tiles_page);
    bg_load(bg);
    for (i = 0; i < 8; i++) vdp_set_color(16 + 8 + i, menu_glyph_pal[i]);
    sr = ints_off();
    vdp_load_tiles(menu_glyphs, MENU_GLYPH_VRAM, MENU_GLYPHS);
    ints_restore(sr);
}

/* GAME MODE SELECT as the original: its screen, the arrow, the countdown (at 0 the highlighted
 * mode starts); and, ours, OPTIONS below. */
u16 mode_select(void) {
    static const u16 rows[3] = { 10, 14, 18 };
    u16 sel = 0, timer = 9, t = 0, i;
    menu_screen(&bg_menushot);
    big_text(10, rows[2], "OPTIONS");
    for (;;) {
        for (i = 0; i < 3; i++) if (i != sel) glyph_clear(menu_arrow_col, rows[i]);
        glyph_put(0, menu_arrow_col, rows[sel]);
        glyph_put(1 + timer, menu_timer_cell[0], menu_timer_cell[1]);
        frame_end();
        if (pads[0].pressed & BTN_UP) { sel = (sel + 2) % 3; sfx_play(SFX_MOVE); t = 0; timer = 9; }
        if (pads[0].pressed & BTN_DOWN) { sel = (sel + 1) % 3; sfx_play(SFX_MOVE); t = 0; timer = 9; }
        if (any_confirm(0) || (++t == 60 && (t = 0, timer-- == 0))) {
            sfx_play(SFX_SELECT);
            if (sel < 2) break;
            options_screen();
            menu_screen(&bg_menushot);
            big_text(10, rows[2], "OPTIONS");
            timer = 9; t = 0;
        }
    }
    text_clear();
    return sel;
}

/* ---------------------------------------------------------------- OPTIONS */

u16 game_level = 4;                     /* 1-8, as the arcade's LEVEL setting: the CPU's strength */

static const char *const control_names[3][2] = {
    { "A", "B" }, { "B", "C" }, { "C", "B" } };              /* throw / slide, lob */

void options_screen(void) {
    static const u16 rows[4] = { 7, 11, 17, 21 };
    u16 sel = 0, i, redraw = 1;
    char line[42];
    menu_screen(&bg_menublank);
    big_text(13, 2, "OPTIONS");
    big_text(6, rows[0], "LEVEL");
    big_text(6, rows[1], "CONTROL");
    big_text(6, rows[2], "HOW TO PLAY");
    big_text(6, rows[3], "EXIT");
    for (;;) {
        if (redraw) {
            const char *const *cn = control_names[control_type];
            glyph_put(1 + game_level, 30, rows[0]);
            glyph_put(2 + control_type, 30, rows[1]);
            for (i = 0; i < 41; i++) line[i] = ' ';
            line[40] = 0;
            text_use_game_font(1);
            text_print(6, rows[1] + 3, "                              ");
            {   /* e.g. "A THROW AND SLIDE   B LOB" */
                char *q = line;
                const char *w;
                *q++ = cn[0][0];
                for (w = " THROW AND SLIDE   "; *w; ) *q++ = *w++;
                *q++ = cn[1][0];
                for (w = " LOB"; *w; ) *q++ = *w++;
                *q = 0;
            }
            text_print(6, rows[1] + 3, line);
            redraw = 0;
        }
        for (i = 0; i < 4; i++) if (i != sel) glyph_clear(3, rows[i]);
        glyph_put(0, 3, rows[sel]);
        frame_end();
        if (pads[0].pressed & BTN_UP) { sel = (sel + 3) % 4; sfx_play(SFX_MOVE); }
        if (pads[0].pressed & BTN_DOWN) { sel = (sel + 1) % 4; sfx_play(SFX_MOVE); }
        if (pads[0].pressed & (BTN_LEFT | BTN_RIGHT)) {
            s16 d = (pads[0].pressed & BTN_RIGHT) ? 1 : -1;
            if (sel == 0) game_level = (u16)((game_level - 1 + 8 + d) % 8 + 1);
            if (sel == 1) control_type = (u16)((control_type + 3 + d) % 3);
            sfx_play(SFX_MOVE);
            redraw = 1;
        }
        if (pads[0].pressed & BTN_START) break;
        if (pads[0].pressed & (BTN_A | BTN_B)) {
            if (sel == 3) break;
            if (sel == 2) {
                sfx_play(SFX_SELECT);
                how_to_play();
                menu_screen(&bg_menublank);
                big_text(13, 2, "OPTIONS");
                big_text(6, rows[0], "LEVEL");
                big_text(6, rows[1], "CONTROL");
                big_text(6, rows[2], "HOW TO PLAY");
                big_text(6, rows[3], "EXIT");
                redraw = 1;
            } else if (sel < 2) {
                if (sel == 0) game_level = game_level % 8 + 1;
                else control_type = (control_type + 1) % 3;
                sfx_play(SFX_MOVE);
                redraw = 1;
            }
        }
    }
    sfx_play(SFX_SELECT);
    text_use_game_font(0);
    text_clear();
}

/* ---------------------------------------------------------------- HOW TO PLAY */

/* The original's four demonstrations (its own titles), with our text for the Mega Drive's
 * buttons, then two pages of ours: the lob and the super shot. Any button skips. */
static const char *const howto_text[4][7] = {
    { "USE THE D-PAD TO", "MOVE YOUR", "CHARACTER.", 0 },
    { "STAND IN THE WAY", "OF THE DISC TO", "CATCH IT. HOLD A", "DIRECTION AND PRESS", "# TO SLIDE THERE.", 0 },
    { "HOLD THE D-PAD IN", "THE DIRECTION YOU", "WANT AND PRESS # TO", "THROW. THROW AT", "ONCE AFTER A CATCH", "FOR A POWER SHOT.", 0 },
    { "TURN THE D-PAD A", "QUARTER CIRCLE", "(DOWN, DOWN-FORWARD", "FORWARD) AND PRESS", "#: THE DISC CURVES.", 0 },
};
static const char *const howto_more[2][8] = {
    { "PRESS @ TO LOB THE DISC", "OVER YOUR OPPONENT.", "UP OR DOWN AIMS IT.", "", "IF IT LANDS, IT SCORES", "2 POINTS.", 0 },
    { "SLIDE (D-PAD AND #) INTO", "THE INCOMING DISC: IT", "FLIES UP INTO THE AIR.", "", "STAND UNDER IT AND CATCH", "IT: YOUR NEXT THROW IS", "YOUR SUPER SHOT.", 0 },
};
static u16 howto_page;

static void howto_print(u16 col, u16 row, const char *s) {   /* # = throw button, @ = lob button */
    char line[42];
    u16 i;
    for (i = 0; s[i] && i < 40; i++)
        line[i] = s[i] == '#' ? control_names[control_type][0][0] : s[i] == '@' ? control_names[control_type][1][0] : s[i];
    line[i] = 0;
    text_print(col, row, line);
}

/* the still background pattern on plane B, its tiles out of the movie's way */
#define PATTERN_VRAM VRAM_UI
static void pattern_rows(u16 y0, u16 y1) {
    const u8 *map = bg_menublank.map;
    u16 x, y, sr = ints_off();
    for (y = y0; y < y1; y++) {
        vdp_vram_addr(VRAM_PLANE_B + ((y * PLANE_W) << 1));
        for (x = 0; x < 40; x++) {
            u16 w = (map[(y * 40 + x) * 2] << 8) | map[(y * 40 + x) * 2 + 1];
            VDP_DATA = (w & 0x7FF) ? (w & 0xF800) | ((w & 0x7FF) + PATTERN_VRAM - 1) : 0;
        }
    }
    ints_restore(sr);
}

static void howto_hook(u16 tick) {
    u16 page = mv_howto_page[movie_index], i;
    (void)tick;
    if (page == howto_page || page > 3) return;
    howto_page = page;
    pattern_rows(6, 20);
    for (i = 0; howto_text[page][i]; i++) howto_print(21, 6 + 2 * i, howto_text[page][i]);
}

void how_to_play(void) {
    u16 i, k, t, skip;
    spr_clear();
    text_clear();
    vdp_wait_vblank();
    /* our text on plane B, in front of the movie (high priority), palette 3 */
    vdp_set_color(48 + 8, hud_colors[0]); vdp_set_color(48 + 9, hud_colors[1]);
    vdp_set_color(48 + 14, 0x000); vdp_set_color(48 + 15, 0xEEE);
    text_use_game_font(1);
    text_set_palette(3);
    text_set_plane(VRAM_PLANE_B);
    {
        u16 sr = ints_off();
        vdp_load_tiles(bg_menublank.tiles, PATTERN_VRAM, bg_menublank.tiles_size >> 5);
        ints_restore(sr);
        vdp_set_palette(0, (const u16 *)bg_menublank.pal);
    }
    howto_page = 0xFFFF;
    movie_begin();                      /* (clears plane B too) */
    pattern_rows(0, 28);
    movie_hook = howto_hook;
    movie_keep_palettes = 0x9;          /* 0: the pattern, 3: our text */
    skip = movie_play(&mv_howto, MOVIE_SKIP, 0);
    movie_keep_palettes = 0;
    movie_hook = 0;
    movie_end();
    text_clear();
    text_set_plane(VRAM_PLANE_A);
    text_set_palette(1);
    if (!skip) {
        for (k = 0; k < 2; k++) {
            menu_screen(&bg_menublank);
            text_use_game_font(1);
            big_text(k ? 10 : 17, 3, k ? "SUPER SHOT" : "LOB");
            for (i = 0; howto_more[k][i]; i++) howto_print(7, 9 + 2 * i, howto_more[k][i]);
            for (t = 0; t < 420; t++) {
                frame_end();
                if (t > 20 && any_confirm(0)) break;
            }
        }
    }
    text_clear();
    text_use_game_font(0);
}

/* The original's player select: both cursors on one screen (1P and 2P markers cut from it). */
static void marker_pos(u16 k, s16 *x, s16 *y) { *x = 16 + (k & 1) * 144; *y = 72 + (k >> 1) * 56; }

static u16 move_cursor(u16 cur, u16 pad) {
    u16 b = pads[pad].pressed;
    if (b & (BTN_LEFT | BTN_RIGHT)) { cur ^= 1; sfx_play(SFX_MOVE); }
    if (b & BTN_UP) { cur = (cur + NUM_CHARS - 2) % NUM_CHARS; sfx_play(SFX_MOVE); }
    if (b & BTN_DOWN) { cur = (cur + 2) % NUM_CHARS; sfx_play(SFX_MOVE); }
    return cur;
}

void select_players(u16 two, u16 *c0, u16 *c1) {
    u16 cur[2] = { 0, 1 }, done[2] = { 0, !two }, t = 0, sr;
    spr_clear();
    text_clear();
    movie_begin();
    movie_play(&scr_select, 0, 0);
    sr = ints_off();
    vdp_load_tiles(spr_1p.tiles, VRAM_UI, spr_1p.ntiles);
    vdp_load_tiles(spr_2p.tiles, VRAM_UI + spr_1p.ntiles, spr_2p.ntiles);
    ints_restore(sr);
    while (!done[0] || !done[1]) {
        u16 k;
        s16 x, y;
        for (k = 0; k < 2; k++) {
            if (done[k]) continue;
            cur[k] = move_cursor(cur[k], k);
            if (any_confirm(k)) { done[k] = 1; sfx_play(SFX_SELECT); }
        }
        spr_clear();
        t++;
        for (k = 0; k < 1 + two; k++) {
            if (!done[k] && (t & 16)) continue;        /* blink until chosen */
            marker_pos(cur[k], &x, &y);
            if (k) frame_draw(&spr_2p, x + 24, y, VRAM_UI + spr_1p.ntiles, 0, 1, 0);
            else frame_draw(&spr_1p, x, y, VRAM_UI, 0, 1, 0);
        }
        frame_end();
    }
    for (t = 0; t < 30; t++) frame_end();
    spr_clear();
    movie_end();
    *c0 = cur[0];
    *c1 = cur[1];
}

/* The original's court roulette: it spins for a while, then stops on a random court. */
static u16 roll_court, roll_ticks;
static void roll_hook(u16 tick)
{
    if (tick >= roll_ticks && mv_courtroll_court[movie_index] == roll_court && mv_courtroll_lit[movie_index])
        movie_stop = 1;
}

u16 court_select(u16 cur) {
    u16 t;
    (void)cur;
    spr_clear();
    text_clear();
    roll_court = rand16() % NUM_COURTS;
    roll_ticks = 90 + (rand16() & 63);
    movie_begin();
    movie_hook = roll_hook;
    movie_play(&mv_courtroll, 0, 0);
    movie_hook = 0;
    sfx_play(SFX_SELECT);
    for (t = 0; t < 60; t++) frame_end();
    movie_end();
    return roll_court;
}

/* The original's VS screen: background and panels as a still, each side's portrait (own palette)
 * and country name cut from recordings of the game. */
static const Frame *const vs_port[2][6] = { { &spr_vsport_l0, &spr_vsport_l1, &spr_vsport_l2, &spr_vsport_l3, &spr_vsport_l4, &spr_vsport_l5 }, { &spr_vsport_r0, &spr_vsport_r1, &spr_vsport_r2, &spr_vsport_r3, &spr_vsport_r4, &spr_vsport_r5 } };
static const s16 *const vs_port_pos[2][6] = { { spr_vsport_l0_pos, spr_vsport_l1_pos, spr_vsport_l2_pos, spr_vsport_l3_pos, spr_vsport_l4_pos, spr_vsport_l5_pos }, { spr_vsport_r0_pos, spr_vsport_r1_pos, spr_vsport_r2_pos, spr_vsport_r3_pos, spr_vsport_r4_pos, spr_vsport_r5_pos } };
static const u16 *const vs_port_pal[2][6] = { { spr_vsport_l0_pal, spr_vsport_l1_pal, spr_vsport_l2_pal, spr_vsport_l3_pal, spr_vsport_l4_pal, spr_vsport_l5_pal }, { spr_vsport_r0_pal, spr_vsport_r1_pal, spr_vsport_r2_pal, spr_vsport_r3_pal, spr_vsport_r4_pal, spr_vsport_r5_pal } };
static const Frame *const vs_name[2][6] = { { &spr_vsname_l0, &spr_vsname_l1, &spr_vsname_l2, &spr_vsname_l3, &spr_vsname_l4, &spr_vsname_l5 }, { &spr_vsname_r0, &spr_vsname_r1, &spr_vsname_r2, &spr_vsname_r3, &spr_vsname_r4, &spr_vsname_r5 } };
static const s16 *const vs_name_pos[2][6] = { { spr_vsname_l0_pos, spr_vsname_l1_pos, spr_vsname_l2_pos, spr_vsname_l3_pos, spr_vsname_l4_pos, spr_vsname_l5_pos }, { spr_vsname_r0_pos, spr_vsname_r1_pos, spr_vsname_r2_pos, spr_vsname_r3_pos, spr_vsname_r4_pos, spr_vsname_r5_pos } };

void vs_screen(u16 c0, u16 c1, u16 stage) {
    u16 t, side, sr, tile = VRAM_PLAYER0, ntile = VRAM_UI;
    const u16 ch[2] = { c0, c1 };
    (void)stage;
    spr_clear();
    text_clear();
    snd_music(&mus_vs);
    movie_begin();
    movie_play(&scr_vs, 0, 0);
    for (side = 0; side < 2; side++) {
        const Frame *p = vs_port[side][ch[side]], *n = vs_name[side][ch[side]];
        sr = ints_off();
        vdp_load_tiles(p->tiles, tile + side * 128, p->ntiles);
        vdp_load_tiles(n->tiles, ntile + side * 32, n->ntiles);
        ints_restore(sr);
        vdp_set_palette(2 + side, vs_port_pal[side][ch[side]]);
    }
    for (t = 0; t < 180; t++) {
        spr_clear();
        for (side = 0; side < 2; side++) {
            frame_draw(vs_name[side][ch[side]], vs_name_pos[side][ch[side]][0], vs_name_pos[side][ch[side]][1],
                       ntile + side * 32, 0, 1, 0);
            frame_draw(vs_port[side][ch[side]], vs_port_pos[side][ch[side]][0], vs_port_pos[side][ch[side]][1],
                       tile + side * 128, 0, 1, 0);
        }
        frame_end();
        if (t > 30 && any_confirm(0)) break;
    }
    spr_clear();
    frame_end();
    movie_end();
}

/* The big font on the court (plane A, in front): its tiles with the colours mapped to the nearest
 * of palette 1 (the court's), each position of a text its own slot of 4 tiles. */
#define COURT_GLYPHS (VRAM_HUD + 68)         /* 15 slots: the HUD area's last 60 tiles */
static u8 cg_lut[16], cg_code[16];
static u8 cg_buf[15][128];

static u16 col_dist(u16 a, u16 b) {
    s16 r = ((a >> 1) & 7) - ((b >> 1) & 7), g = ((a >> 5) & 7) - ((b >> 5) & 7), bl = ((a >> 9) & 7) - ((b >> 9) & 7);
    return r * r + g * g + bl * bl;
}

static void court_glyphs_begin(void) {
    u16 i, j;
    for (i = 0; i < 16; i++) {
        u16 best = 1;
        cg_lut[i] = i;
        if (i < 8) continue;
        for (j = 1; j < 16; j++)
            if (col_dist(menu_glyph_pal[i - 8], cram_shadow[16 + j]) < col_dist(menu_glyph_pal[i - 8], cram_shadow[16 + best])) best = j;
        cg_lut[i] = best;
    }
    for (i = 0; i < 15; i++) cg_code[i] = 0xFF;
}

static void court_big(u16 slot, u16 col, u16 row, u8 code) {    /* big-font code at a 2 x 2 cell */
    u16 v = COURT_GLYPHS + slot * 4, i, sr;
    if (cg_code[slot] != code) {
        const u8 *src = menu_glyphs + big_glyph_index(code) * 32;
        cg_code[slot] = code;
        for (i = 0; i < 128; i++) cg_buf[slot][i] = (cg_lut[src[i] >> 4] << 4) | cg_lut[src[i] & 15];
        dma_queue(cg_buf[slot], v << 5, 64);
    }
    sr = ints_off();
    vdp_set_tile(VRAM_PLANE_A, col, row, TILE_ATTR(1, 1, 0, 0, v));
    vdp_set_tile(VRAM_PLANE_A, col, row + 1, TILE_ATTR(1, 1, 0, 0, v + 1));
    vdp_set_tile(VRAM_PLANE_A, col + 1, row, TILE_ATTR(1, 1, 0, 0, v + 2));
    vdp_set_tile(VRAM_PLANE_A, col + 1, row + 1, TILE_ATTR(1, 1, 0, 0, v + 3));
    ints_restore(sr);
}

static u8 big_code(char c) {                /* letters, digits; anything else: blank */
    if (c >= 'A' && c <= 'Z') return (u8)(0x40 + 4 * (c - 'A'));
    if (c >= '0' && c <= '9') return (u8)(4 * (c - '0'));
    return RANK_BLANK;
}

static void court_big_text(u16 slot, u16 col, u16 row, const char *s) {
    for (; *s; s++, col += 2, slot++) court_big(slot, col, row, big_code(*s));
}

/* As in the arcade: still on the court, the winner celebrating in the middle and the loser at the
 * side. A score for the RANKING TOP5 first gets a NAME (P1's corner of the HUD, up to 30 s); then
 * "CONTINUE 9" counts down in the big font (with the name still shown), then GAME OVER. Continuing
 * starts the score again from 0. */
u16 continue_screen(void) {
    u16 n = 9, t = 0, ret = 0, naming, k;
    Player *win = &players[1], *lose = &players[0];
    u32 score = match_score(0);
    for (t = 3; t < 28; t++) text_clear_row(t);     /* keep the HUD, as the arcade does */
    t = 0;
    text_use_game_font(1);
    snd_music(&mus_gameover);
    win->x = (s32)160 << 16; win->y = (s32)128 << 16;
    lose->x = (s32)40 << 16; lose->y = (s32)132 << 16;
    player_force_anim(win, ANIM_CHEER, 1);
    player_force_anim(lose, ANIM_SAD, 1);
    court_glyphs_begin();
    naming = ranking_place(score) < 5;
    if (naming) {
        u16 sr = ints_off();
        for (k = 2; k < 15; k++) { vdp_set_tile(VRAM_PLANE_A, k, 1, 0); vdp_set_tile(VRAM_PLANE_A, k, 2, 0); }
        ints_restore(sr);
        text_print(3, 2, "NAME");
        name_entry_begin(score, lose->char_index);
    }
    for (;;) {
        u16 done = naming ? name_entry_step() : 1;
        if (naming) for (k = 0; k < 3; k++) court_big(k, 8 + 2 * k, 1, name_entry_letter(k));
        player_advance(win); player_advance(lose);
        spr_clear();
        player_draw(win); player_draw(lose);
        frame_end();
        if (done) break;
    }
    for (;;) {
        char line[10] = "CONTINUE";
        court_big_text(3, 10, 12, line);
        court_big(11, 28, 12, big_code('0' + n));
        player_advance(win); player_advance(lose);
        spr_clear();
        player_draw(win); player_draw(lose);
        frame_end();
        if (pads[0].pressed & BTN_START) { sfx_play(SFX_SELECT); ret = 1; break; }
        if (++t == 60) { t = 0; if (n-- == 0) break; sfx_play(SFX_MOVE); }
    }
    for (k = 12; k < 14; k++) text_clear_row(k);
    if (!ret) {
        court_big_text(3, 11, 12, "GAME");
        court_big_text(7, 21, 12, "OVER");
        for (t = 0; t < 180; t++) {
            player_advance(win); player_advance(lose);
            spr_clear();
            player_draw(win); player_draw(lose);
            frame_end();
            if (t > 30 && (pads[0].pressed & BTN_START)) break;
        }
    } else match_score_reset();
    spr_clear();
    text_clear();
    text_use_game_font(0);
    return ret;
}

void ending_screen(u16 winner_char, const char *line1, const char *line2) {
    u16 t;
    Player *p = &players[0];
    text_clear();
    bg_load(&bg_ending);
    snd_music(&mus_menu);
    player_init(p, 0, winner_char);
    p->x = (s32)160 << 16; p->y = (s32)200 << 16;
    player_force_anim(p, ANIM_CHEER, 1);
    text_center(4, line1);
    if (line2) text_center(6, line2);
    for (t = 0; t < 600; t++) {
        player_advance(p);
        spr_clear();
        player_draw(p);
        frame_end();
        if (t > 60 && (pads[0].pressed & BTN_START)) break;
    }
    spr_clear();
}

/* The original's ending after ROUND FINAL: its picture above, the staff pages below in the game's
 * font ("CONGRATULATIONS! ..." to "1994 DATA EAST CORPORATION"), with its tune. */
void ending_show(void) {
    u16 page, t;
    const EndLine *l;
    spr_clear();
    text_clear();
    vdp_wait_vblank();
    bank_map_video((u16)(u32)endshot_tiles_page);
    bg_load(&bg_endshot);
    vdp_set_color(16 + PAL1_HUD, hud_colors[0]);
    vdp_set_color(16 + PAL1_HUD + 1, hud_colors[1]);
    text_use_game_font(1);
    snd_music(&mus_ending);
    for (page = 0; page < ENDING_PAGES; page++) {
        for (t = 16; t < 28; t++) text_clear_row(t);
        for (l = ending_lines; l->page != 0xFF; l++)
            if (l->page == page) text_print(0, l->row, l->text);
        for (t = 0; t < ENDING_PAGE_FRAMES * (page == ENDING_PAGES - 1 ? 2 : 1); t++) {
            frame_end();
            if (t > 30 && (pads[0].pressed & BTN_START)) break;
        }
    }
    text_clear();
    text_use_game_font(0);
}
