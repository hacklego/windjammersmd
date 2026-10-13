#pragma once
#include "types.h"

/* Sega mapper ("SEGA SSF" in the header): 512 KB ROM pages mapped into 512 KB windows.
 * Window n (address n * 0x80000) is selected by the byte register 0xA130F1 + 2n. */
#define BANK_REG(n) (*(volatile u8 *)(0xA130F1 + 2 * (n)))

/* samples: 512 KB window at 0x180000 */
static inline void bank_map_sample(u16 page) { BANK_REG(3) = page; }
/* music streams: 1 MB window at 0x200000 */
static inline void bank_map_music(u16 page) { BANK_REG(4) = page; BANK_REG(5) = page + 1; }
/* movies and other big graphics: 1 MB window at 0x300000 */
static inline void bank_map_video(u16 page) { BANK_REG(6) = page; BANK_REG(7) = page + 1; }
