#include "input.h"

Pad pads[2];
#define DATA(p) (*(volatile u8 *)(0xA10003 + (p) * 2))
#define CTRL(p) (*(volatile u8 *)(0xA10009 + (p) * 2))

void input_init(void) {
    CTRL(0) = 0x40; CTRL(1) = 0x40;
    DATA(0) = 0x40; DATA(1) = 0x40;
}

static u16 read_pad(u16 p) {
    u8 hi, lo, ext;
    u16 v;
    DATA(p) = 0x40; __asm__ volatile("nop\n nop");
    hi = DATA(p);                      /* ?1CBRLDU */
    DATA(p) = 0x00; __asm__ volatile("nop\n nop");
    lo = DATA(p);                      /* ?0SA00DU */
    v = (~hi & 0x3F) | ((~lo & 0x30) << 2);
    /* 6-button probe: two more pulses; on the third low cycle, D-pad bits read 0000 */
    DATA(p) = 0x40; __asm__ volatile("nop\n nop");
    DATA(p) = 0x00; __asm__ volatile("nop\n nop");
    DATA(p) = 0x40; __asm__ volatile("nop\n nop");
    DATA(p) = 0x00; __asm__ volatile("nop\n nop");
    if ((DATA(p) & 0x0F) == 0) {
        DATA(p) = 0x40; __asm__ volatile("nop\n nop");
        ext = DATA(p);                 /* ?1CBMXYZ */
        v |= (~ext & 0x0F) << 8;
        DATA(p) = 0x00; __asm__ volatile("nop\n nop");
    }
    DATA(p) = 0x40;
    return v;
}

/* OPTIONS / CONTROL: which button throws (and slides) and which lobs. The game reads BTN_A as
 * throw and BTN_B as lob; the remaining button lobs too. */
u16 control_type;
static u16 remap(u16 v) {
    u16 a = v & BTN_A, b = v & BTN_B, c = v & BTN_C, out = v & ~(BTN_A | BTN_B | BTN_C);
    switch (control_type) {
    case 1:  if (b) out |= BTN_A; if (c | a) out |= BTN_B; break;     /* B throws, C lobs */
    case 2:  if (c) out |= BTN_A; if (b | a) out |= BTN_B; break;     /* C throws, B lobs */
    default: if (a) out |= BTN_A; if (b | c) out |= BTN_B; break;     /* A throws, B lobs (arcade) */
    }
    return out;
}

void input_update(void) {
    u16 p;
    for (p = 0; p < 2; p++) {
        u16 now = remap(read_pad(p));
        pads[p].pressed = now & ~pads[p].held;
        pads[p].released = ~now & pads[p].held;
        pads[p].held = now;
    }
}
