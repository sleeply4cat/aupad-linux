// SPDX-License-Identifier: GPL-2.0
/*
 * Runs with MMU and caches off, straight after ABL.  Everything is
 * position independent (adrp/adr only), and every wait has a timeout so a
 * dead peripheral cannot wedge us silently.
 */
typedef unsigned long u64;
typedef unsigned int u32;
typedef unsigned char u8;

#define GCC_BASE		0x01400000UL
#define GCC_QUP_VOTE		(GCC_BASE + 0x7900c)	/* APCS branch vote, sm6115 layout */
#define QUP0_VOTE_BITS		((1 << 6) | (1 << 7) | (1 << 8) | (1 << 9) | (1 << 14))

#define UART_BASE		0x04a90000UL
#define GENI_FW_REVISION_RO	0x068
#define SE_GENI_STATUS		0x040
#define SE_UART_TX_TRANS_LEN	0x270
#define SE_GENI_TX_PACKING_CFG0	0x260
#define SE_GENI_M_CMD0		0x600
#define SE_GENI_M_CMD_CTRL_REG	0x604
#define SE_GENI_M_IRQ_STATUS	0x610
#define SE_GENI_M_IRQ_CLEAR	0x618
#define SE_GENI_TX_FIFOn	0x700
#define SE_GENI_TX_FIFO_STATUS	0x800

#define GENI_SER_M_CLK_CFG	0x048
#define GENI_IF_DISABLE_RO	0x064
#define SE_GENI_CLK_SEL		0x07c
#define SE_GENI_DMA_MODE_EN	0x258
#define SE_GENI_TX_PACKING_CFG1	0x264
#define SE_UART_TX_TRANS_CFG	0x25c
#define SE_UART_TX_WORD_LEN	0x268
#define SE_UART_TX_STOP_BIT_LEN	0x26c
#define SE_UART_TX_PARITY_CFG	0x2a4
#define SE_GENI_TX_WATERMARK_REG 0x80c
#define GCC_QUP0_S4_CBCR	(GCC_BASE + 0x1f604)

#define WDT_BASE		0x0f017000UL

extern u64 read_el(void), read_sctlr(void), read_cntpct(void);
extern u64 read_cntfrq(void), read_mpidr(void), read_daif(void);
extern char _stub_end[];
extern void reset_at(u64 deadline);
extern u64 smc_call(u64 fn, u64 a1, u64 a2, u64 a3);
#define PSCI_CPU_ON	0xc4000003UL
#define STUB_PROBE	0	/* 1: reset at +3 s instead of chainloading */

static inline u32 rd(u64 a) { return *(volatile u32 *)a; }
static inline void wr(u64 a, u32 v) { *(volatile u32 *)a = v; }

static u64 ticks_per_us;

/*
 * RAM log in the splash framebuffer (outside what XBL's ramdump code
 * clobbers): word 0 magic, word 1 stage, text from +0x100.
 */
#define RAMLOG		0x5c000000UL
#define RAMLOG_TEXT	(RAMLOG + 0x100)
#define RAMLOG_MAX	0xf00
static u32 ramlog_pos;

static void stage(u32 n)
{
	wr(RAMLOG + 4, n);
	__asm__ volatile("dsb sy" ::: "memory");
}

static int wait_bit(u64 reg, u32 mask, u64 us)
{
	u64 end = read_cntpct() + us * ticks_per_us;

	while (!(rd(reg) & mask))
		if (read_cntpct() > end)
			return 0;
	return 1;
}

static int uart_dead, uart_ok;

static void putc(char c)
{
	u64 end;

	if (ramlog_pos < RAMLOG_MAX) {
		*(volatile u8 *)(RAMLOG_TEXT + ramlog_pos++) = c;
		*(volatile u8 *)(RAMLOG_TEXT + ramlog_pos) = 0;
		__asm__ volatile("dsb sy" ::: "memory");
	}
	if (uart_dead || !uart_ok)
		return;
	end = read_cntpct() + 20000 * ticks_per_us;
	while (rd(UART_BASE + SE_GENI_STATUS) & 1)	/* M_GENI_CMD_ACTIVE */
		if (read_cntpct() > end) {
			wr(UART_BASE + SE_GENI_M_CMD_CTRL_REG, 1 << 1);	/* abort */
			break;
		}
	wr(UART_BASE + SE_GENI_M_IRQ_CLEAR, 0xffffffff);
	wr(UART_BASE + SE_UART_TX_TRANS_LEN, 1);
	wr(UART_BASE + SE_GENI_M_CMD0, 1u << 27);	/* UART_START_TX */
	/* Same byte in every lane: whatever the packing config, c goes out. */
	wr(UART_BASE + SE_GENI_TX_FIFOn, (u8)c * 0x01010101u);
	if (!wait_bit(UART_BASE + SE_GENI_M_IRQ_STATUS, 1, 20000))
		uart_dead = 1;
	wr(UART_BASE + SE_GENI_M_IRQ_CLEAR, 0xffffffff);
}

/* State as ABL left it, captured before uart_init() touches anything. */
static u32 abl_clk_cfg, abl_if_dis, abl_clk_sel, abl_dma, abl_pack0, abl_status, abl_cbcr;

/*
 * What qcom_geni_serial_earlycon_setup() does, plus the serial clock
 * divider, which earlycon leaves alone: SE4 runs off 7.3728 MHz, and
 * 115200 * 16 = 1.8432 MHz -> divider 4.
 */
static void uart_init(void)
{
	u64 u = UART_BASE;

	abl_cbcr = rd(GCC_QUP0_S4_CBCR);
	abl_clk_cfg = rd(u + GENI_SER_M_CLK_CFG);
	abl_if_dis = rd(u + GENI_IF_DISABLE_RO);
	abl_clk_sel = rd(u + SE_GENI_CLK_SEL);
	abl_dma = rd(u + SE_GENI_DMA_MODE_EN);
	abl_pack0 = rd(u + SE_GENI_TX_PACKING_CFG0);
	abl_status = rd(u + SE_GENI_STATUS);

	if (!(abl_clk_cfg & 1))
		wr(u + GENI_SER_M_CLK_CFG, (4 << 4) | 1);
	if (abl_status & 1) {
		wr(u + SE_GENI_M_CMD_CTRL_REG, 1 << 2);		/* cancel */
		if (!wait_bit(u + SE_GENI_M_IRQ_STATUS, 1 << 4, 20000))
			wr(u + SE_GENI_M_CMD_CTRL_REG, 1 << 1);	/* abort */
	}
	wr(u + SE_GENI_M_IRQ_CLEAR, 0xffffffff);
	wr(u + SE_GENI_TX_PACKING_CFG0, 0x4380e);	/* 8 bit, 4/word, LSB first */
	wr(u + SE_GENI_TX_PACKING_CFG1, 0xc3e0e);
	wr(u + SE_GENI_DMA_MODE_EN, abl_dma & ~1);	/* FIFO mode */
	wr(u + SE_GENI_TX_WATERMARK_REG, 4);
	wr(u + SE_UART_TX_TRANS_CFG, 1 << 1);		/* ignore CTS */
	wr(u + SE_UART_TX_PARITY_CFG, 0);
	wr(u + SE_UART_TX_WORD_LEN, 8);
	wr(u + SE_UART_TX_STOP_BIT_LEN, 0);
}

static void puts(const char *s)
{
	for (; *s; s++) {
		if (*s == '\n')
			putc('\r');
		putc(*s);
	}
}

static void puthex(u64 v)
{
	int i;

	puts("0x");
	for (i = 60; i >= 0; i -= 4)
		putc("0123456789abcdef"[(v >> i) & 0xf]);
}

static void kv(const char *k, u64 v)
{
	puts("  ");
	puts(k);
	puts(" = ");
	puthex(v);
	puts("\n");
}

static u32 be32(const void *p)
{
	const u8 *b = p;

	return (u32)b[0] << 24 | (u32)b[1] << 16 | (u32)b[2] << 8 | b[3];
}

static int streq(const char *a, const char *b)
{
	while (*a && *a == *b)
		a++, b++;
	return *a == *b;
}

static int prefix(const char *s, const char *p)
{
	while (*p)
		if (*s++ != *p++)
			return 0;
	return 1;
}

static u64 cell64(const u8 *p) { return (u64)be32(p) << 32 | be32(p + 4); }

static u64 initrd_start, initrd_end;

static void fdt_dump(const u8 *fdt)
{
	const u8 *st, *p, *end;
	const char *strs;
	const char *node = "";
	int depth = 0;

	if (be32(fdt) != 0xd00dfeed) {
		puts("  no FDT magic at x0\n");
		return;
	}
	kv("fdt totalsize", be32(fdt + 4));
	st = fdt + be32(fdt + 8);
	strs = (const char *)fdt + be32(fdt + 12);
	end = st + be32(fdt + 36);
	for (p = st; p < end;) {
		u32 tok = be32(p);

		p += 4;
		if (tok == 1) {			/* BEGIN_NODE */
			node = (const char *)p;
			depth++;
			while (*p)
				p++;
			p = (const u8 *)(((u64)p + 4) & ~3UL);
		} else if (tok == 2) {		/* END_NODE */
			depth--;
			node = "";
		} else if (tok == 3) {		/* PROP */
			u32 len = be32(p), noff = be32(p + 4);
			const char *name = strs + noff;
			const u8 *val = p + 8;

			if (depth == 2 && streq(node, "chosen")) {
				if (streq(name, "bootargs")) {
					puts("  bootargs: ");
					puts((const char *)val);
					puts("\n");
				} else if (streq(name, "linux,initrd-start")) {
					initrd_start = len == 8 ? cell64(val) : be32(val);
					kv("initrd-start", initrd_start);
				} else if (streq(name, "linux,initrd-end")) {
					initrd_end = len == 8 ? cell64(val) : be32(val);
					kv("initrd-end", initrd_end);
				}
			} else if (depth == 2 && prefix(node, "memory") && streq(name, "reg")) {
				u32 i;

				for (i = 0; i + 16 <= len && i < 16 * 6; i += 16) {
					puts("  mem ");
					puthex(cell64(val + i));
					puts(" + ");
					puthex(cell64(val + i + 8));
					puts("\n");
				}
			} else if (depth == 1 && streq(name, "model")) {
				puts("  model: ");
				puts((const char *)val);
				puts("\n");
			}
			p = (const u8 *)(((u64)val + len + 3) & ~3UL);
		} else if (tok == 9) {
			break;
		}
	}
}

static int overlaps(u64 a, u64 alen, u64 b, u64 blen)
{
	return a < b + blen && b < a + alen;
}

static void move(u64 dst, u64 src, u64 n)
{
	volatile u64 *d = (u64 *)dst;
	volatile u64 *s = (u64 *)src;
	u64 i, w = n / 8;

	if (dst < src)
		for (i = 0; i < w; i++)
			d[i] = s[i];
	else
		for (i = w; i-- > 0;)
			d[i] = s[i];
}

u64 stub_main(u64 dtb, u64 base, u64 x1, u64 x2, u64 x3)
{
	u32 vote, i;
	u64 kimg, ksize, dst, t0, t_entry = read_cntpct(), cpuon;

	stage(2);
	ticks_per_us = read_cntfrq() / 1000000;
	if (!ticks_per_us)
		ticks_per_us = 19;
	puts("stub: entered\n");
	/* A visible band under the breadcrumbs, so the screen shows we ran. */
	for (i = 0x10000; i < 0x90000; i += 4)
		wr(RAMLOG + i, 0xffff00ff);
	stage(3);
	vote = rd(GCC_QUP_VOTE);
	stage(4);
	wr(GCC_QUP_VOTE, vote | QUP0_VOTE_BITS);
	stage(5);
	uart_init();
	stage(6);
	uart_ok = 1;

	puts("\n\n=== aupad stub ===\n");
	stage(7);
	kv("base", base);
	kv("x0/dtb", dtb);
	kv("x1", x1);
	kv("x2", x2);
	kv("x3", x3);
	kv("CurrentEL", read_el());
	kv("SCTLR", read_sctlr());
	kv("DAIF", read_daif());
	kv("MPIDR", read_mpidr());
	kv("CNTFRQ", read_cntfrq());
	kv("CNTPCT", read_cntpct());
	kv("GCC QUP vote (before)", vote);
	kv("GENI fw rev", rd(UART_BASE + GENI_FW_REVISION_RO));
	kv("ABL SE4 CBCR", abl_cbcr);
	kv("ABL SER_M_CLK_CFG", abl_clk_cfg);
	kv("ABL IF_DISABLE", abl_if_dis);
	kv("ABL CLK_SEL", abl_clk_sel);
	kv("ABL DMA_MODE_EN", abl_dma);
	kv("ABL TX_PACKING0", abl_pack0);
	kv("ABL GENI_STATUS", abl_status);
	kv("WDT en", rd(WDT_BASE + 0x08));
	kv("WDT sts", rd(WDT_BASE + 0x0c));
	kv("WDT bark", rd(WDT_BASE + 0x10));
	kv("WDT bite", rd(WDT_BASE + 0x14));
	fdt_dump((const u8 *)dtb);
	stage(8);
	/*
	 * Timing side channel: CPU1 resets the board at +6 s, CPU0 at +3 s.
	 * Probe mode only: the parked CPU1 is unusable for Linux.
	 */
	if (STUB_PROBE) {
		cpuon = smc_call(PSCI_CPU_ON, 1, (u64)reset_at,
				 t_entry + 6000000 * ticks_per_us);
		kv("PSCI CPU_ON(1)", cpuon);
		puts("probe mode: reset at +3 s\n");
		reset_at(t_entry + 3000000 * ticks_per_us);
	}

#ifdef STUB_SPIN
	/* Busy-wait with no WFI and no kernel: does the SoC survive sustained load? */
	for (t0 = 1; t0 <= STUB_SPIN; t0++) {
		u64 end = read_cntpct() + 1000000 * ticks_per_us;

		while (read_cntpct() < end)
			;
		kv("spin s", t0);
	}
	puts("TESTDONE spin\n");
	smc_call(0x84000009UL, 0, 0, 0);	/* never park: no way to reset it remotely */
	return 0;
#endif

#ifdef STUB_WDT
	/*
	 * Nothing resets a stuck CPU here, and the PWR line doesn't work, so
	 * anything chainloaded runs under the APSS watchdog (32.768 kHz).
	 */
	wr(WDT_BASE + 0x08, 0);
	wr(WDT_BASE + 0x04, 1);
	wr(WDT_BASE + 0x10, STUB_WDT * 32768);
	wr(WDT_BASE + 0x14, STUB_WDT * 32768);
	wr(WDT_BASE + 0x08, 1);
	kv("WDT armed, s", STUB_WDT);
#ifdef STUB_WDT_TEST
	/* PSCI backstop at twice the bite time: tells which of the two fired. */
	reset_at(read_cntpct() + 2 * STUB_WDT * 1000000 * ticks_per_us);
#endif
#endif

	kimg = (u64)_stub_end;	/* adrp: runtime address */
	if (be32((u8 *)kimg + 0x38) != 0x41524d64) {	/* "ARMd" */
		puts("no payload Image, parking\n");
		return 0;
	}
	ksize = *(volatile u64 *)(kimg + 0x10);
	kv("payload", kimg);
	kv("payload image_size", ksize);

	dst = 0x40200000;
	if (overlaps(dst, ksize, dtb, 0x100000) ||
	    overlaps(dst, ksize, initrd_start, initrd_end - initrd_start))
		dst = 0x64000000;
	kv("moving Image to", dst);
	t0 = read_cntpct();
	move(dst, kimg, ksize);
	kv("move took us", (read_cntpct() - t0) / ticks_per_us);
	puts("jumping to kernel\n");
	return dst;
}
