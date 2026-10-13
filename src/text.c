#include "text.h"
#include "vdp.h"
#include "vram.h"
#include "assets.h"
#include "movies.h"

static const u8 *cur_font;
static u16 cur_pal = 1, cur_plane = VRAM_PLANE_A;

void text_set_plane(u16 plane) { cur_plane = plane; }

void text_set_palette(u16 pal) { cur_pal = pal; }

/* Menus use white letters on black cells (readable on any picture); matches use the game's own
 * fix-layer letters (text_use_game_font), as the original draws its texts over the court. */
void text_init(void) {
    u16 sr = ints_off();
    if (!cur_font) cur_font = font_tiles;
    vdp_load_tiles(cur_font, VRAM_FONT, FONT_TILES);
    ints_restore(sr);
}

void text_use_game_font(u16 on) {
    cur_font = on ? fixfont_tiles : font_tiles;
    text_init();
}

static u16 glyph(char c) {
    if (c == 'm' && cur_font == fixfont_tiles) c = '^';     /* the game font's 'm' (metres) */
    if (c >= 'a' && c <= 'z') c -= 32;
    if (c < 0x20 || c >= 0x20 + FONT_TILES) c = ' ';
    return TILE_ATTR(cur_pal, 1, 0, 0, VRAM_FONT + (c - 0x20));
}

void text_print(u16 x, u16 y, const char *s) {
    u16 sr = ints_off();
    vdp_vram_addr(cur_plane + ((y * PLANE_W + x) << 1));
    while (*s) VDP_DATA = glyph(*s++);
    ints_restore(sr);
}

/* centred, with one black cell of padding each side so the text sits on a solid strip */
void text_center(u16 y, const char *s) {
    char buf[42];
    u16 n = 0;
    buf[0] = ' ';
    while (s[n] && n < 38) { buf[n + 1] = s[n]; n++; }
    buf[n + 1] = ' '; buf[n + 2] = 0;
    text_print((40 - (n + 2)) >> 1, y, buf);
}

void text_clear_row(u16 y) {
    u16 i, sr = ints_off();
    vdp_vram_addr(cur_plane + ((y * PLANE_W) << 1));
    for (i = 0; i < 40; i++) VDP_DATA = 0;
    ints_restore(sr);
}

void text_clear(void) {
    u16 sr = ints_off();
    vdp_fill_plane(cur_plane, 0);
    ints_restore(sr);
}

void fmt_number(char *out, u16 value, u16 digits) {
    out[digits] = 0;
    while (digits--) { out[digits] = '0' + value % 10; value /= 10; }
}

void text_number(u16 x, u16 y, u16 value, u16 digits) {
    char buf[8];
    fmt_number(buf, value, digits);
    text_print(x, y, buf);
}
