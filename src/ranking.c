/* RANKING TOP5 and the NAME entry (see ranking.h). The screen is drawn as the original: the
 * arcade's backdrop with its title (a still, tools/mkmovies.py scr_ranking) and, on plane B in
 * front of it, each entry's big rank digit, score (the 2-row font) and name (big font); the faces
 * are sprites. */
#include "ranking.h"
#include "vdp.h"
#include "vram.h"
#include "input.h"
#include "text.h"
#include "movie.h"
#include "movies.h"
#include "sound.h"
#include "player.h"

typedef struct { u32 score; u8 name[4]; u16 gid; } Rank;
static Rank table[5];

void ranking_init(void) {
    u16 k, i;
    for (k = 0; k < 5; k++) {
        table[k].score = rank_default_score[k];
        for (i = 0; i < 4; i++) table[k].name[i] = rank_default_name[k][i];
        table[k].gid = rank_default_gid[k];
    }
}

u16 ranking_place(u32 score) {
    u16 k = 0;
    while (k < 5 && score <= table[k].score) k++;
    return k;
}

static void ranking_insert(u32 score, const u8 *name, u16 gid) {
    u16 k = ranking_place(score), j, i;
    if (k >= 5) return;
    for (j = 4; j > k; j--) {
        table[j].score = table[j - 1].score;
        for (i = 0; i < 4; i++) table[j].name[i] = table[j - 1].name[i];
        table[j].gid = table[j - 1].gid;
    }
    table[k].score = score;
    for (i = 0; i < 3; i++) table[k].name[i] = name[i];
    table[k].name[3] = 0;
    table[k].gid = gid;
}

u16 big_glyph_index(u8 code) {        /* menu_glyphs: arrow, 0-9, A-Z, then the symbols */
    if (code < 0x28) return 4 + code;
    if (code < 0x40) return 148 + (code - 0x28);
    if (code < 0xA8) return 44 + (code - 0x40);
    return 172 + (code - 0xA8);
}

/* ---------------------------------------------------------------- NAME entry */

static struct { u32 score; u16 gid, slot, li, hold, timer, blink; u8 name[4]; } ne;

void name_entry_begin(u32 score, u16 char_index) {
    ne.score = score; ne.gid = rank_gid_of_char[char_index];
    ne.slot = ne.li = ne.hold = ne.blink = 0;
    ne.timer = 30 * 60;
    ne.name[0] = ne.name[1] = ne.name[2] = RANK_BLANK; ne.name[3] = 0;
}

u16 name_entry_step(void) {
    u16 held = pads[0].held, hit = pads[0].pressed, move = 0, done = 0;
    if (ne.slot >= 3) return 1;
    ne.blink++;
    if (held & (BTN_LEFT | BTN_RIGHT)) {
        if (hit & (BTN_LEFT | BTN_RIGHT)) { move = 1; ne.hold = 0; }
        else if (++ne.hold >= 32) move = 1;         /* held: every frame after half a second */
    } else ne.hold = 0;
    if (move) {
        ne.li = held & BTN_RIGHT ? (ne.li + 1) % RANK_LETTERS : (ne.li + RANK_LETTERS - 1) % RANK_LETTERS;
        sfx_play(SFX_MOVE);
    }
    if (hit & (BTN_A | BTN_B | BTN_C)) {
        u8 c = rank_letters[ne.li];
        sfx_play(SFX_SELECT);
        if (c == RANK_END) done = 1;
        else { ne.name[ne.slot++] = c; if (ne.slot == 3) done = 1; }
    }
    if (!done && --ne.timer == 0) {                 /* time up: the letter shown is entered */
        u8 c = rank_letters[ne.li];
        if (c != RANK_END) ne.name[ne.slot] = c;
        done = 1;
    }
    if (done) { ranking_insert(ne.score, ne.name, ne.gid); ne.slot = 3; }
    return done;
}

u8 name_entry_letter(u16 k) {
    if (k < ne.slot) return ne.name[k];
    if (k == ne.slot && !(ne.blink & 8)) return rank_letters[ne.li];    /* 8 frames on, 8 off */
    return RANK_BLANK;
}

/* ---------------------------------------------------------------- the screens */

#define V_GLYPH  VRAM_PLAYER0               /* big-font glyphs as needed, 4 tiles each (up to 24), */
#define V_RFONT  (V_GLYPH + 96)             /* the score font (22 tiles), */
#define V_FACE   (V_RFONT + 22)             /* the faces (24 tiles each) */
#define FACE_TILES 24

static u8 glyph_code[24];
static u16 glyph_count;

static u16 glyph_vram(u8 code) {            /* loads a big-font glyph once */
    u16 i, sr;
    for (i = 0; i < glyph_count; i++) if (glyph_code[i] == code) return V_GLYPH + i * 4;
    if (glyph_count == 24) return V_GLYPH;
    glyph_code[glyph_count] = code;
    sr = ints_off();
    vdp_load_tiles(menu_glyphs + big_glyph_index(code) * 32, V_GLYPH + glyph_count * 4, 4);
    ints_restore(sr);
    return V_GLYPH + glyph_count++ * 4;
}

static void big_put(u16 col, u16 row, u8 code) {       /* 2 x 2 cells, plane B in front, palette 2 */
    u16 v = glyph_vram(code), sr = ints_off();
    vdp_set_tile(VRAM_PLANE_B, col, row, TILE_ATTR(2, 1, 0, 0, v));
    vdp_set_tile(VRAM_PLANE_B, col, row + 1, TILE_ATTR(2, 1, 0, 0, v + 1));
    vdp_set_tile(VRAM_PLANE_B, col + 1, row, TILE_ATTR(2, 1, 0, 0, v + 2));
    vdp_set_tile(VRAM_PLANE_B, col + 1, row + 1, TILE_ATTR(2, 1, 0, 0, v + 3));
    ints_restore(sr);
}

/* palettes 2 (big font in 8-15, faces in 1-7) and 3 (faces; the game font's colours in 8, 9, 14, 15) */
static void screen_palettes(void) {
    u16 p2[16], p3[16], i;
    for (i = 0; i < 16; i++) { p2[i] = rank_face_pal[0][i]; p3[i] = rank_face_pal[1][i]; }
    for (i = 0; i < 8; i++) p2[8 + i] = menu_glyph_pal[i];
    p3[8] = dog_pal[8]; p3[9] = dog_pal[9]; p3[14] = dog_pal[14]; p3[15] = dog_pal[15];
    vdp_set_palette(2, p2);
    vdp_set_palette(3, p3);
}

static void still(const Movie *m) {
    spr_clear();
    text_clear();
    movie_begin();
    movie_keep_palettes = 0x0C;
    movie_play(m, 0, 0);
    movie_keep_palettes = 0;
    screen_palettes();
    glyph_count = 0;
    text_set_plane(VRAM_PLANE_B);
    text_use_game_font(1);
    text_set_palette(3);
}

static void still_end(void) {
    spr_clear();
    vdp_wait_vblank();
    text_clear();
    text_set_plane(VRAM_PLANE_A);
    text_set_palette(1);
    text_use_game_font(0);
    movie_end();
}

u16 ranking_show(void) {
    u16 t, k, i, sr, ret = 0;
    still(&scr_ranking);
    sr = ints_off();
    vdp_load_tiles(rankfont_tiles, V_RFONT, 22);
    for (k = 0; k < 5; k++) vdp_load_tiles(rank_faces[table[k].gid].tiles, V_FACE + k * FACE_TILES, rank_faces[table[k].gid].ntiles);
    ints_restore(sr);
    for (k = 0; k < 5; k++) {                       /* fix rows 8 + 4 k: the rank, score, name */
        u16 row = 6 + 4 * k;
        u32 v = table[k].score;
        big_put(8, row, (u8)(4 * (k + 1)));
        for (i = 0; i < 7; i++, v /= 10) {
            u16 g = (v || !i) ? 1 + (u16)(v % 10) : 0;
            if (i == 6 && !g) break;
            sr = ints_off();
            vdp_set_tile(VRAM_PLANE_B, 23 - i, row, TILE_ATTR(3, 1, 0, 0, V_RFONT + g * 2));
            vdp_set_tile(VRAM_PLANE_B, 23 - i, row + 1, TILE_ATTR(3, 1, 0, 0, V_RFONT + g * 2 + 1));
            ints_restore(sr);
        }
        for (i = 0; i < 3; i++) big_put(26 + 2 * i, row, table[k].name[i]);
    }
    for (t = 0; t < 300; t++) {
        spr_clear();
        for (k = 0; k < 5; k++)
            frame_draw(&rank_faces[table[k].gid], RANK_FACE_X, RANK_ROW_Y + 32 * k, V_FACE + k * FACE_TILES, 0, 0, 0);
        if ((t & 31) == 0) {                        /* PRESS START: 32 frames off, 32 on */
            if (t & 32) text_print(14, 12, "PRESS START");
            else text_print(14, 12, "           ");
        }
        vdp_wait_vblank();
        input_update();
        if (pads[0].pressed & BTN_START) { ret = 1; break; }
    }
    still_end();
    return ret;
}

void ranking_after_ending(u32 score, u16 char_index) {
    u16 t, k;
    if (ranking_place(score) < 5) {                 /* NAME over the DATA EAST screen */
        still(&scr_deend);
        name_entry_begin(score, char_index);
        u16 shown[3] = { 0xFFFF, 0xFFFF, 0xFFFF };
        text_print(3, 2, "NAME");
        for (t = 0; t < 120; ) {
            if (name_entry_step()) t++;             /* (then a moment with the name) */
            for (k = 0; k < 3; k++) {               /* each slot its own glyph tiles */
                u8 c = name_entry_letter(k);
                if (c != shown[k]) {
                    u16 v = V_GLYPH + 4 * (20 + k), sr = ints_off();
                    shown[k] = c;
                    vdp_load_tiles(menu_glyphs + big_glyph_index(c) * 32, v, 4);
                    vdp_set_tile(VRAM_PLANE_B, 8 + 2 * k, 1, TILE_ATTR(2, 1, 0, 0, v));
                    vdp_set_tile(VRAM_PLANE_B, 8 + 2 * k, 2, TILE_ATTR(2, 1, 0, 0, v + 1));
                    vdp_set_tile(VRAM_PLANE_B, 9 + 2 * k, 1, TILE_ATTR(2, 1, 0, 0, v + 2));
                    vdp_set_tile(VRAM_PLANE_B, 9 + 2 * k, 2, TILE_ATTR(2, 1, 0, 0, v + 3));
                    ints_restore(sr);
                }
            }
            vdp_wait_vblank();
            input_update();
        }
        still_end();
    }
    ranking_show();
}
