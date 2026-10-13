#pragma once
#include "types.h"

#define SET_POINTS   12
#define SET_SECONDS  30
#define SETS_TO_WIN  2
#define MATCH_DRAW   2       /* match_run: 3-3 in sets after the sudden death set */

/* who controls player 2 */
enum { CTRL_CPU, CTRL_HUMAN };

#include "sound.h"
void match_set_cpu_level(u16 level);
void match_set_music(const Music *m);
/* match_set_cpu_level: 0 (easy) .. 6 (hard) */
void match_set_round(u16 round);            /* 1P round (1.., set panels), 0 for 2P */

/* the arcade's score shown in the top row (kept from match to match in 1P): points x 100, 1000 a
 * point past the goal, 5000 + 100 a second left for a set */
void match_score_reset(void);
void match_score_add(u16 side, u32 points);
u32 match_score(u16 side);
u16 match_sets(u16 side);                   /* sets won in the last match */

/* returns the winning side (0/1) or MATCH_DRAW; for a demo (CPU vs CPU): 0xFFFF if interrupted with Start,
 * 0xFFFE when its time is up */
u16 match_run(u16 char0, u16 char1, u16 court, u16 p1_control, u16 p2_control);
