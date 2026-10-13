#pragma once
#include "types.h"
#include "movies.h"

#define MOVIE_SKIP 1          /* Start/A/B ends the movie (movie_play returns 1) */

void movie_begin(void);       /* set up the two name tables (plane A + window) */
void movie_end(void);         /* back to the normal plane layout */
/* Plays a movie blob; loops forever if it has a loop point, unless max_ticks (0 = no limit)
 * runs out (returns 0) or it is skipped (returns 1). */
u16 movie_play(const Movie *movie, u16 opts, u16 max_ticks);

extern void (*movie_hook)(u16 tick);     /* called every frame (overlays) */
void movie_sound(u16 id);                /* play a recorded sound event */
extern u16 movie_index;                  /* index of the frame on screen */
extern u16 movie_keep_palettes;         /* bit p: the movie leaves palette p alone (set by the caller) */
extern u16 movie_stop;                   /* hook sets it: movie_play returns 2 */
