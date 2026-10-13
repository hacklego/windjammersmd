#pragma once
#include "types.h"

/* One hardware sprite of a character frame, relative to the character's feet. */
typedef struct { s16 dx, dy; u16 size; u16 tile; } SprPiece;   /* size = (w-1)<<2 | (h-1), | 0x10 = palette 1 */
typedef struct { const u8 *tiles; u16 ntiles; u16 npieces; const SprPiece *pieces; } Frame;
typedef struct { u16 frame; u16 dur; } AnimStep;                 /* list ends with frame 0xFFFF */

enum { ANIM_IDLE, ANIM_HOLD, ANIM_AIM, ANIM_THROW, ANIM_RUN_H, ANIM_RUN_UP, ANIM_RUN_DOWN, ANIM_CATCH,
       ANIM_SLIDE_F, ANIM_SLIDE_UP, ANIM_SLIDE_DOWN, ANIM_LOB, ANIM_CHEER, ANIM_SAD, ANIM_LOSE, ANIM_COUNT };

typedef struct {
    const char *name, *country;
    u16 speed, power;               /* rough ratings used by the CPU */
    s32 run_speed;                  /* px/frame, 16.16 (the original's values) */
    u16 power_frames;               /* throwing within this many frames of a catch = power throw */
    u16 curve_rate;                 /* curve throw: angle change per frame = rate * speed (16.16) */
    const u16 *throw_speed;         /* 16 speeds (1/32 px/frame) by frames held / 4 */
    const u16 *palettes;            /* 32 colours: player-1 palette then player-2 palette */
    const Frame *frames;
    const AnimStep *anims[ANIM_COUNT];
} CharDef;

extern const CharDef characters[];
extern const u8 char_tiles[], char_tiles_page[];   /* banked: map with bank_map_video(CHAR_TILES_PAGE) */
#define CHAR_TILES_PAGE ((u16)(u32)char_tiles_page)
