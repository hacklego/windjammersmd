#pragma once
#include "types.h"
#include "chardata.h"

#define PLAYER_SLOT_TILES 128           /* VRAM tiles reserved per player (see tools/extract.py) */

enum { PS_FREE, PS_DASH, PS_CATCH, PS_HOLD, PS_THROW, PS_FROZEN };

typedef struct {
    const CharDef *ch;
    u16 char_index;
    u16 side;                           /* 0 = left (faces right), 1 = right (mirrored) */
    u16 vram;                           /* first VRAM tile of this player's slot */
    s32 x, y;                           /* feet position, 16.16 fixed point */
    u16 anim, step, timer, anim_loop, anim_done;
    u16 shown_frame;                    /* frame currently in VRAM (0xFFFF = none) */
    u16 state, state_timer;
    s16 dash_dx, dash_dy;
    u16 throw_kind, throw_dir;          /* pending throw, released mid-animation */
    u16 throw_angle;                    /* 0-255, see match.c */
    u16 hold_frames;                    /* frames holding the disc */
    u16 throw_queued;                   /* A pressed while catching */
    u16 throw_dir_curve;                /* curve throw: (s16) 1 clockwise, -1 the other way */
    u16 super_ready;                    /* next throw is a super shot */
    u16 score, sets;
} Player;

extern Player players[2];

void player_init(Player *p, u16 side, u16 char_index);
void player_set_anim(Player *p, u16 anim, u16 loop);
void player_force_anim(Player *p, u16 anim, u16 loop);
void player_advance(Player *p);
void player_draw(Player *p);
void frame_draw(const Frame *f, s16 x, s16 y, u16 vram_tile, u16 pal, u16 prio, u16 hflip);
