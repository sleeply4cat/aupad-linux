/*
 * AuPad bring-up stub.  ABL loads this as "the kernel" (arm64 Image
 * header) and jumps here with MMU off, x0 = DTB.  stub_main() talks to
 * the debug UART directly and returns the entry point of the payload
 * Image (or 0 to park).
 */
	.section .text.head, "ax"
	.globl	_start
_start:
	b	entry			/* code0 */
	.long	0			/* code1 */
	.quad	0			/* text_offset */
	.quad	_image_size		/* image_size, incl. bss and stack */
	.quad	0xa			/* LE, 4K pages, place anywhere */
	.quad	0, 0, 0
	.ascii	"ARM\x64"
	.long	0

entry:
	/* RAM breadcrumb before touching anything else: magic, stage 1, x0. */
	ldr	x9, =0x5c000000
	ldr	w10, =0x44505541	/* "AUPD" */
	str	w10, [x9]
	mov	w10, #1
	str	w10, [x9, #4]
	str	x0, [x9, #8]
	mrs	x10, CurrentEL
	str	x10, [x9, #16]
	dsb	sy
	mov	x19, x0			/* DTB */
	mov	x20, x1
	mov	x21, x2
	mov	x22, x3

	adrp	x0, __bss_start
	add	x0, x0, :lo12:__bss_start
	adrp	x1, __bss_end
	add	x1, x1, :lo12:__bss_end
1:	cmp	x0, x1
	b.hs	2f
	str	xzr, [x0], #8
	b	1b
2:
	adrp	x0, stack_top
	add	x0, x0, :lo12:stack_top
	mov	sp, x0

	mov	x0, x19
	adr	x1, _start
	mov	x2, x20
	mov	x3, x21
	mov	x4, x22
	bl	stub_main
	cbz	x0, park

	mov	x4, x0
	ic	iallu
	dsb	sy
	isb
	mov	x0, x19
	mov	x1, xzr
	mov	x2, xzr
	mov	x3, xzr
	br	x4

park:
	wfe
	b	park

	.globl	read_el
read_el:
	mrs	x0, CurrentEL
	lsr	x0, x0, #2
	ret

	.globl	read_sctlr
read_sctlr:
	mrs	x1, CurrentEL
	cmp	x1, #(2 << 2)
	b.eq	1f
	mrs	x0, sctlr_el1
	ret
1:	mrs	x0, sctlr_el2
	ret

	.globl	read_cntpct
read_cntpct:
	isb
	mrs	x0, cntpct_el0
	ret

	.globl	read_cntfrq
read_cntfrq:
	mrs	x0, cntfrq_el0
	ret

	.globl	read_mpidr
read_mpidr:
	mrs	x0, mpidr_el1
	ret

	.globl	read_daif
read_daif:
	mrs	x0, daif
	ret

/* x0 = cntpct deadline.  PSCI CPU_ON entry used as an independent timer. */
	.globl	reset_at
reset_at:
	isb
	mrs	x1, cntpct_el0
	cmp	x1, x0
	b.lo	reset_at
	.globl	psci_reset
psci_reset:
	ldr	x0, =0x84000009	/* SYSTEM_RESET */
	smc	#0
	b	.

/* x0 = fn, x1..x3 = args */
	.globl	smc_call
smc_call:
	smc	#0
	ret
