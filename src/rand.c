#include "rand.h"
static u16 state = 0xACE1;
void rand_seed(u16 s) { state = s ? s : 0xACE1; }
u16 rand16(void) {      /* 16-bit xorshift */
    state ^= state << 7;
    state ^= state >> 9;
    state ^= state << 8;
    return state;
}
