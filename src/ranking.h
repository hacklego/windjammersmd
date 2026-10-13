#pragma once
#include "types.h"

/* RANKING TOP5 as the original keeps it: in RAM, so until the console is switched off (five
 * 'D.E' entries 100000..60000 at power on), with each entry's score, name (three big-font
 * letters) and character. */
void ranking_init(void);
u16 ranking_place(u32 score);              /* the place (0-4) a score would take; 5: not in the table */

/* The ranking screen of the attract loop (PRESS START blinking); returns 1 if Start was pressed. */
u16 ranking_show(void);

/* NAME entry for a new entry, as the original: left / right choose a letter (held: quickly after
 * half a second), A/B/C enters it, 'ED' ends early; 30 seconds. Each frame name_entry_step()
 * runs it (returns 1 once the name is in the table) and name_entry_letter(k) says what slot k
 * shows (big-font code). */
void name_entry_begin(u32 score, u16 char_index);
u16 name_entry_step(void);
u8 name_entry_letter(u16 k);

/* the big font (menu_glyphs) tile of a big-font code */
u16 big_glyph_index(u8 code);

/* after the ending, as the original: NAME over the DATA EAST screen, then the ranking */
void ranking_after_ending(u32 score, u16 char_index);
