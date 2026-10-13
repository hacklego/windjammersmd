#pragma once
#include "types.h"

enum { MODE_VS_CPU, MODE_VS_2P };

u16 mode_select(void);
void options_screen(void);              /* LEVEL, CONTROL, HOW TO PLAY */
void how_to_play(void);
extern u16 game_level;                  /* 1-8 (4 = the arcade's default) */
void select_players(u16 two, u16 *c0, u16 *c1); /* the original's select screen */
u16 court_select(u16 start);
void vs_screen(u16 c0, u16 c1, u16 stage);
u16 continue_screen(void);                   /* 1 = continue */
void ending_screen(u16 winner_char, const char *line1, const char *line2);
void ending_show(void);                 /* 1P: the original's ending (picture and staff pages) */
