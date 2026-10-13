#include "player.h"
#include "bank.h"
#include "vdp.h"
#include "vram.h"

Player players[2];

void player_init(Player *p, u16 side, u16 char_index) {
    bank_map_video(CHAR_TILES_PAGE);      /* the character tiles' ROM bank */
    p->ch = &characters[char_index];
    p->char_index = char_index;
    p->side = side;
    p->vram = side ? VRAM_PLAYER1 : VRAM_PLAYER0;
    p->x = (s32)(side ? 320 - 48 : 48) << 16;
    p->y = (s32)128 << 16;
    p->shown_frame = 0xFFFF;
    p->state = PS_FREE;
    p->super_ready = 0;
    p->anim = 0xFFFF;
    player_set_anim(p, ANIM_IDLE, 1);
    vdp_set_palette(2 + side, p->ch->palettes + side * 16);
}

void player_force_anim(Player *p, u16 anim, u16 loop) {
    p->anim = anim;
    p->anim_loop = loop;
    p->anim_done = 0;
    p->step = 0;
    p->timer = p->ch->anims[anim][0].dur;
}

void player_set_anim(Player *p, u16 anim, u16 loop) {
    if (p->anim != anim) player_force_anim(p, anim, loop);
}

void player_advance(Player *p) {
    const AnimStep *a = p->ch->anims[p->anim];
    if (p->anim_done || --p->timer) return;
    if (a[p->step + 1].frame == 0xFFFF) {
        if (!p->anim_loop) { p->anim_done = 1; return; }
        p->step = 0;
    } else {
        p->step++;
    }
    p->timer = a[p->step].dur;
}

void frame_draw(const Frame *f, s16 x, s16 y, u16 vram_tile, u16 pal, u16 prio, u16 hflip) {
    u16 i;
    for (i = 0; i < f->npieces; i++) {
        const SprPiece *s = &f->pieces[i];
        u16 w = ((s->size >> 2) & 3) + 1, h = (s->size & 3) + 1;
        s16 dx = hflip ? -s->dx - (s16)(w << 3) : s->dx;
        /* pieces flagged 0x10 (disc in hand, effects) use palette 1's shared disc colours */
        u16 pl = (s->size & 0x20) ? (s->size >> 6) & 3 : (s->size & 0x10) ? 1 : pal;   /* 0x20: own palette */
        spr_add(x + dx, y + s->dy, w, h, TILE_ATTR(pl, prio, 0, hflip, vram_tile + s->tile));
    }
}

void player_draw(Player *p) {
    u16 fi = p->ch->anims[p->anim][p->step].frame;
    const Frame *f = &p->ch->frames[fi];
    if (fi != p->shown_frame) {
        bank_map_video(CHAR_TILES_PAGE);  /* a movie may have mapped its own data since */
        dma_queue(f->tiles, p->vram << 5, f->ntiles << 4);
        p->shown_frame = fi;
    }
    frame_draw(f, p->x >> 16, p->y >> 16, p->vram, 2 + p->side, 1, p->side);
}
