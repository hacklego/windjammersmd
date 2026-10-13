| Mega Drive startup: vector table, ROM header, hardware init, C runtime setup.
	.section .vectors,"ax"
	.long	0x00FFFE00		| initial SSP (top of RAM, below 512B scratch)
	.long	_start
	.long	exc_bus		| 2 bus error
	.long	exc_addr		| 3 address error
	.long	exc_illegal		| 4 illegal instruction
	.rept	19
	.long	exc_trap		| other errors
	.endr
	.long	exc_trap		| spurious
	.long	exc_trap		| IRQ1
	.long	ext_int			| IRQ2 external
	.long	exc_trap		| IRQ3
	.long	hblank_int		| IRQ4 hblank
	.long	exc_trap		| IRQ5
	.long	vblank_int		| IRQ6 vblank
	.long	exc_trap		| IRQ7
	.rept	32
	.long	exc_trap		| TRAP #n and reserved
	.endr

	.section .header,"ax"
	.ascii	"SEGA SSF        "	| Sega mapper (ROM pages above 4 MB, src/bank.h)
	.ascii	"(C)HOME 2026.OCT"
	.ascii	"WINDJAMMERS MD                                  "
	.ascii	"WINDJAMMERS MD                                  "
	.ascii	"GM 00000000-00"
	.word	0			| checksum, patched by tools/romfix.py
	.ascii	"J               "	| joypad
	.long	0x000000, 0x3FFFFF	| ROM range (patched)
	.long	0xFF0000, 0xFFFFFF	| RAM range
	.ascii	"            "		| no SRAM
	.ascii	"            "		| modem
	.ascii	"                                        "
	.ascii	"JUE             "

| Boot stage marker: turn the display on and fill the screen with one colour.
| Whatever colour stays on screen shows how far the boot got (see README).
	.macro	STAGE color
	move.w	#0x8004, 0xC00004	| reg 0: no hint
	move.w	#0x8144, 0xC00004	| reg 1: display on, mode 5, no interrupts
	move.w	#0x8700, 0xC00004	| reg 7: backdrop = colour 0
	move.l	#0xC0000000, 0xC00004	| CRAM write, address 0
	move.w	#\color, 0xC00000
	.endm

	.text
	.global	_start
_start:
	move.w	#0x2700, %sr
	| TMSS: write 'SEGA' if the console has a version > 0
	move.b	0xA10001, %d0
	andi.b	#0x0F, %d0
	beq.s	1f
	move.l	#0x53454741, 0xA14000
1:	tst.w	0xC00004		| clear pending VDP state
	STAGE	0x000E			| stage 1: RED - CPU started, VDP reachable
	| Z80: request bus and hold reset (sound code loads it later)
	move.w	#0x100, 0xA11100
	move.w	#0x100, 0xA11200
	| clear RAM
	lea	0xFF0000, %a0
	move.w	#0x3FFF, %d0
	moveq	#0, %d1
2:	move.l	%d1, (%a0)+
	dbra	%d0, 2b
	| copy .data from ROM
	lea	_etext, %a0
	lea	_sdata, %a1
	move.l	#_edata, %d0
	sub.l	#_sdata, %d0
	lsr.l	#1, %d0
	beq.s	4f
	subq.l	#1, %d0
3:	move.w	(%a0)+, (%a1)+
	dbra	%d0, 3b
4:	lea	0x00FFFE00, %sp
	STAGE	0x00E0			| stage 2: GREEN - RAM cleared, about to enter C
	jsr	main
	bra.s	4b

| crash info for debugging: 0xFFFF00 = kind, 0xFFFF02.. = exception stack frame
exc_bus:
	move.w	#2, 0xFFFF00
	bra.s	exc_grp0
exc_addr:
	move.w	#3, 0xFFFF00
exc_grp0:
	move.l	(%sp), 0xFFFF02
	move.l	4(%sp), 0xFFFF06
	move.l	8(%sp), 0xFFFF0A
	move.l	12(%sp), 0xFFFF0E
	bra.s	exc_show
exc_illegal:
	move.w	#4, 0xFFFF00
	bra.s	exc_save
exc_trap:
	move.w	#1, 0xFFFF00
exc_save:
	move.l	(%sp), 0xFFFF02
	move.l	4(%sp), 0xFFFF06
exc_show:
	move.w	#0x2700, %sr
	| make the background red so crashes are visible
	STAGE	0x0EEE			| crash: WHITE
5:	bra.s	5b

ext_int:
	rte

hblank_int:
	movem.l	%d0-%d1/%a0-%a1, -(%sp)
	jsr	hblank_handler
	movem.l	(%sp)+, %d0-%d1/%a0-%a1
	rte

vblank_int:
	movem.l	%d0-%d1/%a0-%a1, -(%sp)
	jsr	vblank_handler
	movem.l	(%sp)+, %d0-%d1/%a0-%a1
	rte
