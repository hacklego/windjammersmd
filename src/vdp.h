#pragma once
#include "types.h"

#define VDP_DATA   (*(volatile u16 *)0xC00000)
#define VDP_DATA32 (*(volatile u32 *)0xC00000)
#define VDP_CTRL   (*(volatile u16 *)0xC00004)
#define VDP_CTRL32 (*(volatile u32 *)0xC00004)

/* VRAM layout (H40, 64x32 planes) */
#define VRAM_WINDOW  0xB000
#define VRAM_HSCROLL 0xB800
#define VRAM_SPRITES 0xBC00
#define VRAM_PLANE_A 0xC000
#define VRAM_PLANE_B 0xE000
#define PLANE_W 64

#define TILE_ATTR(pal, prio, vf, hf, idx) (((pal) << 13) | ((prio) << 15) | ((vf) << 12) | ((hf) << 11) | (idx))

/* Bulk VDP work from the main loop must not be interrupted by the vblank handler,
 * which also drives the control port (DMA setup, CRAM upload). */
static inline u16 ints_off(void) { u16 sr; __asm__ volatile("move.w %%sr, %0\n\tmove.w #0x2700, %%sr" : "=d"(sr) : : "memory"); return sr; }
static inline void ints_restore(u16 sr) { __asm__ volatile("move.w %0, %%sr" : : "d"(sr) : "memory"); }

void vdp_init(void);
void vdp_set_reg(u16 reg, u8 val);
void vdp_display(u16 on);
void vdp_boot_stage(u16 color);
void vdp_vram_addr(u16 addr);
void vdp_load_tiles(const void *src, u16 tile, u16 count);
void vdp_dma_vram(const void *src, u16 dest, u16 words);
void vdp_set_palette(u16 pal, const u16 *colors);
void vdp_set_color(u16 index, u16 color);
void vdp_set_plane_rect(u16 plane, u16 x, u16 y, u16 w, u16 h, const u16 *map);
void vdp_fill_plane(u16 plane, u16 value);
void vdp_set_tile(u16 plane, u16 x, u16 y, u16 value);
void vdp_wait_vblank(void);
void vdp_fade_palettes(const u16 *target, u16 step);

/* sprite list built in RAM each frame and DMA'd in vblank */
typedef struct { s16 y; u16 size_link; u16 attr; s16 x; } Sprite;
extern Sprite sprite_table[80];
extern u16 sprite_count;
void spr_clear(void);
void spr_add(s16 x, s16 y, u16 w, u16 h, u16 attr); /* w,h in tiles 1..4 */

/* queued DMA transfers executed during vblank */
void dma_queue(const void *src, u16 dest, u16 words);
void dma_flush(void);

extern volatile u16 frame_counter;
extern u16 cram_shadow[64];
extern volatile u16 cram_dirty;
