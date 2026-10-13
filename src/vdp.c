#include "vdp.h"
#include "sound.h"

volatile u16 frame_counter;
u16 cram_shadow[64];
volatile u16 cram_dirty;
Sprite sprite_table[80];
u16 sprite_count;

typedef struct { u32 src; u16 dest; u16 words; } DmaJob;
static DmaJob dma_jobs[32];
static u16 dma_count;

/* Only the registers a Mega Drive game needs (same set as known-good homebrew):
 * the unused 6/8/9/14 and the DMA registers 19-23 are left alone at startup. */
static const u16 vdp_regs[] = {
    0x8014,                              /* 0: hint on (sound player, see sound.c) */
    0x8174,                              /* 1: display ON during init (boot markers), vint, DMA, V28 */
    0x8200 | (VRAM_PLANE_A >> 10),
    0x8300 | (VRAM_WINDOW >> 10),
    0x8400 | (VRAM_PLANE_B >> 13),
    0x8500 | (VRAM_SPRITES >> 9),
    0x8700,                              /* 7: backdrop colour 0 */
    0x8A37,                              /* 10: hint every 56 lines */
    0x8B00,                              /* 11: full-screen scroll */
    0x8C81,                              /* 12: H40, no interlace, no shadow/hilite */
    0x8D00 | (VRAM_HSCROLL >> 10),
    0x8F02,                              /* 15: autoincrement 2 */
    0x9001,                              /* 16: 64x32 planes */
    0x9100, 0x9200                       /* 17/18: no window */
};

void vdp_set_reg(u16 reg, u8 val) { VDP_CTRL = 0x8000 | (reg << 8) | val; }

static u8 reg1 = 0x34;
static void vdp_cram_addr(u16 addr);

/* Boot diagnostics: fill the screen with one colour (see crt0.s and the README). */
void vdp_boot_stage(u16 color) {
    vdp_cram_addr(0);
    VDP_DATA = color;
    vdp_set_reg(7, 0);
    vdp_display(1);
}

void vdp_display(u16 on) { reg1 = on ? (reg1 | 0x40) : (reg1 & ~0x40); vdp_set_reg(1, reg1); }

void vdp_vram_addr(u16 addr) { VDP_CTRL32 = 0x40000000UL | ((u32)(addr & 0x3FFF) << 16) | (addr >> 14); }
static void vdp_cram_addr(u16 addr) { VDP_CTRL32 = 0xC0000000UL | ((u32)addr << 16); }
static void vdp_vsram_addr(u16 addr) { VDP_CTRL32 = 0x40000010UL | ((u32)addr << 16); }

void vdp_init(void) {
    u16 i;
    (void)VDP_CTRL;
    for (i = 0; i < sizeof vdp_regs / sizeof vdp_regs[0]; i++) VDP_CTRL = vdp_regs[i];
    vdp_boot_stage(0x06E);       /* boot stage 3: ORANGE - video registers set */
    /* clear VRAM with long writes */
    vdp_vram_addr(0);
    for (i = 0; i < 0x4000; i++) VDP_DATA32 = 0;
    vdp_cram_addr(0);
    for (i = 0; i < 64; i++) { VDP_DATA = 0; cram_shadow[i] = 0; }
    vdp_vsram_addr(0);
    for (i = 0; i < 40; i++) VDP_DATA = 0;
    spr_clear();
    vdp_boot_stage(0xE00);       /* boot stage 4: BLUE - video memory cleared */
}

/* DMA ROM/RAM -> VRAM. Source must not cross a 128KB boundary (split here). */
static void dma_raw(u32 src, u16 dest, u16 words) {
    vdp_set_reg(19, words & 0xFF);
    vdp_set_reg(20, words >> 8);
    vdp_set_reg(21, (src >> 1) & 0xFF);
    vdp_set_reg(22, (src >> 9) & 0xFF);
    vdp_set_reg(23, (src >> 17) & 0x7F);
    /* command as two word writes from registers; the second one starts the DMA */
    VDP_CTRL = 0x4000 | (dest & 0x3FFF);
    VDP_CTRL = 0x0080 | (dest >> 14);
}

void vdp_dma_vram(const void *src, u16 dest, u16 words) {
    u32 s = (u32)src;
    while (words) {
        u32 room = (0x20000 - (s & 0x1FFFF)) >> 1;
        u16 n = words < room ? words : (u16)room;
        dma_raw(s, dest, n);
        s += (u32)n << 1; dest += n << 1; words -= n;
    }
}

void vdp_load_tiles(const void *src, u16 tile, u16 count) {
    vdp_dma_vram(src, tile << 5, count << 4);
}

void vdp_set_palette(u16 pal, const u16 *colors) {
    u16 i;
    for (i = 0; i < 16; i++) cram_shadow[pal * 16 + i] = colors[i];
    cram_dirty = 1;
}

void vdp_set_color(u16 index, u16 color) { cram_shadow[index] = color; cram_dirty = 1; }

void vdp_set_tile(u16 plane, u16 x, u16 y, u16 value) {
    vdp_vram_addr(plane + ((y * PLANE_W + x) << 1));
    VDP_DATA = value;
}

void vdp_set_plane_rect(u16 plane, u16 x, u16 y, u16 w, u16 h, const u16 *map) {
    u16 i, j;
    for (j = 0; j < h; j++) {
        vdp_vram_addr(plane + (((y + j) * PLANE_W + x) << 1));
        for (i = 0; i < w; i++) VDP_DATA = *map++;
    }
}

void vdp_fill_plane(u16 plane, u16 value) {
    u16 i;
    vdp_vram_addr(plane);
    for (i = 0; i < PLANE_W * 32; i++) VDP_DATA = value;
}

void spr_clear(void) { sprite_count = 0; }

void spr_add(s16 x, s16 y, u16 w, u16 h, u16 attr) {
    Sprite *s;
    if (sprite_count >= 80) return;
    if (x <= -32 || x >= 320 || y <= -32 || y >= 224) return;
    s = &sprite_table[sprite_count];
    s->y = y + 128;
    s->size_link = (((w - 1) << 10) | ((h - 1) << 8)) | (sprite_count + 1);
    s->attr = attr;
    s->x = x + 128;
    sprite_count++;
}

void dma_queue(const void *src, u16 dest, u16 words) {
    if (dma_count < 32) { dma_jobs[dma_count].src = (u32)src; dma_jobs[dma_count].dest = dest; dma_jobs[dma_count].words = words; dma_count++; }
}

void dma_flush(void) {
    u16 i;
    for (i = 0; i < dma_count; i++) vdp_dma_vram((const void *)dma_jobs[i].src, dma_jobs[i].dest, dma_jobs[i].words);
    dma_count = 0;
}

static void upload_sprites(void) {
    if (sprite_count == 0) {
        /* one off-screen sprite terminating the list */
        sprite_table[0].y = 0; sprite_table[0].size_link = 0; sprite_table[0].attr = 0; sprite_table[0].x = 0;
        vdp_dma_vram(sprite_table, VRAM_SPRITES, 4);
        return;
    }
    sprite_table[sprite_count - 1].size_link &= 0xFF00;
    vdp_dma_vram(sprite_table, VRAM_SPRITES, sprite_count * 4);
}

/* The interrupt only counts frames: all VDP work happens in the main loop right after
 * vblank starts, so the interrupt can never land in the middle of a control-port sequence. */
void vblank_handler(void) {
    frame_counter++;
    hint_count = 0;
}

/* Wait for vblank, then commit this frame: palette, sprite list and queued DMA. */
void vdp_wait_vblank(void) {
    u16 c = frame_counter, i, sr;
    while (c == frame_counter) {}
    sr = ints_off();
    if (cram_dirty) {
        vdp_cram_addr(0);
        for (i = 0; i < 64; i++) VDP_DATA = cram_shadow[i];
        cram_dirty = 0;
    }
    upload_sprites();
    dma_flush();
    ints_restore(sr);
}
