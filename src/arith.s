| 32-bit multiply/divide helpers for a plain 68000.
| GCC calls these for 32-bit '*', '/' and '%'. They are in assembly on purpose:
| written in C, GCC recognises the idioms and compiles them back into calls to
| themselves. (The distro libgcc is built for 68020+ and can't be used.)
	.text

	.global	__mulsi3
__mulsi3:				| (a, b) -> a * b
	move.w	4(%sp), %d0		| ah
	mulu.w	10(%sp), %d0		| ah * bl
	move.w	8(%sp), %d1		| bh
	mulu.w	6(%sp), %d1		| bh * al
	add.w	%d1, %d0
	swap	%d0
	clr.w	%d0			| cross terms << 16
	move.w	6(%sp), %d1		| al
	mulu.w	10(%sp), %d1		| al * bl
	add.l	%d1, %d0
	rts

| udivmod: d0 = dividend, d1 = divisor -> d0 = quotient, d1 = remainder (d2/d3 preserved)
udivmod:
	movem.l	%d2-%d3, -(%sp)
	cmp.l	#0x10000, %d1
	bcc.s	.Lslow
	| divisor fits in 16 bits: two divu steps, neither can overflow
	move.l	%d0, %d2
	clr.w	%d2
	swap	%d2			| d2 = high word of dividend
	divu.w	%d1, %d2		| d2 = rem_hi : quot_hi
	move.l	%d2, %d3
	move.w	%d0, %d2		| d2 = rem_hi : low word of dividend
	divu.w	%d1, %d2		| d2 = rem : quot_lo
	swap	%d3
	move.w	%d2, %d3		| d3 = quot_hi : quot_lo
	clr.w	%d2
	swap	%d2
	move.l	%d2, %d1		| remainder
	move.l	%d3, %d0		| quotient
	movem.l	(%sp)+, %d2-%d3
	rts
.Lslow:	| restoring shift/subtract division, 32 steps
	moveq	#0, %d2			| running remainder
	moveq	#31, %d3
.Lloop:	add.l	%d0, %d0		| next dividend bit -> X
	addx.l	%d2, %d2
	bcs.s	.Lsub			| remainder overflowed 32 bits: certainly >= divisor
	cmp.l	%d1, %d2
	bcs.s	.Lnext
.Lsub:	sub.l	%d1, %d2
	addq.l	#1, %d0			| quotient bit
.Lnext:	dbra	%d3, .Lloop
	move.l	%d2, %d1
	movem.l	(%sp)+, %d2-%d3
	rts

	.global	__udivsi3
__udivsi3:
	move.l	4(%sp), %d0
	move.l	8(%sp), %d1
	beq.s	.Ldiv0
	bra.w	udivmod
.Ldiv0:	moveq	#-1, %d0
	rts

	.global	__umodsi3
__umodsi3:
	move.l	4(%sp), %d0
	move.l	8(%sp), %d1
	beq.s	.Lmod0
	bsr.w	udivmod
	move.l	%d1, %d0
	rts
.Lmod0:	move.l	4(%sp), %d0
	rts

	.global	__divsi3
__divsi3:				| quotient sign = sign(a) ^ sign(b)
	move.l	4(%sp), %d0
	move.l	8(%sp), %d1
	beq.s	.Ldiv0
	move.l	%d2, -(%sp)
	moveq	#0, %d2
	tst.l	%d0
	bpl.s	1f
	neg.l	%d0
	not.w	%d2
1:	tst.l	%d1
	bpl.s	2f
	neg.l	%d1
	not.w	%d2
2:	bsr.w	udivmod
	tst.w	%d2
	beq.s	3f
	neg.l	%d0
3:	move.l	(%sp)+, %d2
	rts

	.global	__modsi3
__modsi3:				| remainder sign = sign(a)
	move.l	4(%sp), %d0
	move.l	8(%sp), %d1
	beq.s	.Lmod0
	move.l	%d2, -(%sp)
	moveq	#0, %d2
	tst.l	%d0
	bpl.s	1f
	neg.l	%d0
	not.w	%d2
1:	tst.l	%d1
	bpl.s	2f
	neg.l	%d1
2:	bsr.w	udivmod
	move.l	%d1, %d0
	tst.w	%d2
	beq.s	3f
	neg.l	%d0
3:	move.l	(%sp)+, %d2
	rts
