#pragma once
#include "types.h"

void text_init(void);                                 /* upload the current font */
void text_set_plane(u16 plane);                       /* VRAM_PLANE_A (default) or VRAM_PLANE_B */
void text_set_palette(u16 pal);                       /* palette of the letters (default 1) */
void text_use_game_font(u16 on);                      /* 1: the game's font (HUD colours), 0: menu font */
void text_print(u16 x, u16 y, const char *s);         /* plane A, 8x8 cells */
void text_center(u16 y, const char *s);
void text_clear_row(u16 y);
void text_clear(void);
void text_number(u16 x, u16 y, u16 value, u16 digits); /* zero padded */
void fmt_number(char *out, u16 value, u16 digits);
