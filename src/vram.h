#pragma once
/* VRAM tile allocation (tile indexes; 32 bytes each) */
#define VRAM_BG_TILES      1      /* 1..1079: current background (court or menu screen) */
#define VRAM_FONT          1080   /* 64 glyphs, ASCII 0x20..0x5F */
#define VRAM_FX            1080   /* super shot effects (up to 64 tiles) borrow the font's tiles */
#define VRAM_PLAYER0       1152   /* 128 tiles per player, streamed per animation frame */
#define VRAM_PLAYER1       1280
#define VRAM_DISC          1408   /* 36 tiles (window plane area, unused as a plane) */
#define VRAM_UI            1408   /* 64 tiles: sprites over still images (menus, no disc then) */
#define VRAM_SHADOW        1444   /* 2 tiles disc shadow + 8 tiles player shadow */
#define VRAM_HUD_BOX       1454   /* 16 tiles: the TIME box of the last seconds (the result screen reuses them) */

#define VRAM_HUD           1664   /* match HUD (0xD000-0xDFFF, free outside movies), 128 tiles max: */
#define VRAM_HUD_SET_BAR   (VRAM_HUD + 53)     /* digits + glyphs (53), set lamp (3), */
#define VRAM_HUD_FLAGS     (VRAM_HUD + 56)     /* the two players' flags (8), */
#define VRAM_HUD_TIME      (VRAM_HUD + 64)     /* the TIME box shown (4) */
#define VRAM_FENCE         1920   /* 128 tiles: the fence that is shaking (0xF000) */

/* palette 1 layout shared by all screens (see tools/extract.py); 8 and 9 in a match: HUD colours */
#define PAL1_HUD    8             /* 8, 9 */
#define PAL1_DISC   10            /* 10..13 */
#define PAL1_BLACK  14
#define PAL1_WHITE  15
