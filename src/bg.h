#pragma once
#include "types.h"

typedef struct { const u8 *tiles; u16 tiles_size; const u8 *map; const u8 *pal; } BgAsset;

extern const BgAsset bg_vs, bg_ending;

void bg_load(const BgAsset *b);       /* tiles + plane B + palettes 0/1 (display stays on) */
void pal1_fixed_colors(u16 fire);     /* black/white text colours + disc (or fireball) colours */
