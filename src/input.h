#pragma once
#include "types.h"

#define BTN_UP    0x0001
#define BTN_DOWN  0x0002
#define BTN_LEFT  0x0004
#define BTN_RIGHT 0x0008
#define BTN_B     0x0010
#define BTN_C     0x0020
#define BTN_A     0x0040
#define BTN_START 0x0080
#define BTN_Z     0x0100
#define BTN_Y     0x0200
#define BTN_X     0x0400
#define BTN_MODE  0x0800

typedef struct { u16 held, pressed, released; } Pad;
extern Pad pads[2];
void input_init(void);
void input_update(void);

extern u16 control_type;               /* 0: A throws, B lobs; 1: B throws, C lobs; 2: C throws, B lobs */
