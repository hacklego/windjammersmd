#include "bg.h"
#include "vdp.h"
#include "vram.h"
#include "assets.h"

#define BG(n) { n##_tiles, n##_tiles_SIZE, n##_map, n##_pal }
const BgAsset bg_vs = BG(scr_vs), bg_ending = BG(scr_ending);

void pal1_fixed_colors(u16 fire) {
    const u16 *dc = (const u16 *)disc_colors + (fire ? 4 : 0);
    u16 i;
    for (i = 0; i < 4; i++) vdp_set_color(16 + PAL1_DISC + i, dc[i]);
    vdp_set_color(16 + PAL1_BLACK, 0x000);   /* PAL1_HUD colours are set by the match (hud_init) */
    vdp_set_color(16 + PAL1_WHITE, 0xEEE);
}

void bg_load(const BgAsset *b) {
    u16 sr = ints_off();
    vdp_display(0);
    vdp_load_tiles(b->tiles, VRAM_BG_TILES, b->tiles_size >> 5);
    vdp_set_plane_rect(VRAM_PLANE_B, 0, 0, 40, 28, (const u16 *)b->map);
    vdp_set_palette(0, (const u16 *)b->pal);
    vdp_set_palette(1, (const u16 *)b->pal + 16);
    pal1_fixed_colors(0);
    vdp_display(1);
    ints_restore(sr);
}
