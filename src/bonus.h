#pragma once
#include "types.h"

/* The frisbee dog bonus game from the attract mode; returns 1 if Start was pressed. */
u16 bonus_demo(void);

/* DOG DISTANCE, the bonus round after round 2 in 1P mode: throw (A; quicker = farther) and the
 * player steers the dog to catch it. Adds the points (metres x 100, + 5000 / 10000 for a catch) to
 * the score and returns them. */
u16 bonus_dog(u16 char_index);

/* FLYING DISC BOWLING, the bonus round after round 4 in 1P mode: 40 seconds of bowling with the
 * disc. Returns the points. */
u16 bonus_bowl(u16 char_index);
