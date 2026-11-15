// votes_nrq: print the RPM sleep-stats client votes around s2idle.  syscore
// callbacks never run for freeze (suspend_enter() short-circuits s2idle before
// syscore_suspend()), and a userspace read after wake is always too late - the
// kernel re-votes during device resume, before tasks thaw.  freeze_noirq is the
// last observation before the idle, resume_noirq the first one after the wake,
// before any driver has re-voted.  Layout mirrors drivers/soc/qcom/qcom_stats.c:
// dynamic stats offset at +0x14, records of 32-byte sleep_stats + 16-byte
// appended_stats, client_votes first; also dump the stat_type/count of both
// records to see what RPM wrote while we slept.
#include <linux/module.h>
#include <linux/io.h>
#include <linux/platform_device.h>

#define RPM_STATS_BASE	0x04690000
#define DYN_ADDR_OFF	0x14
#define VOTES_OFF	32		/* client_votes sits right after sleep_stats */
#define REC_STRIDE	48		/* sleep_stats + appended_stats */

static void __iomem *regs;

static void votes_dump(const char *when)
{
	u32 off = readl(regs + DYN_ADDR_OFF) & 0xffff;
	void __iomem *v = regs + off, *m = v + REC_STRIDE;

	pr_info("votes_nrq: %s vlow type %#x cnt %u votes %#x | vmin type %#x cnt %u votes %#x\n",
		when, readl(v), readl(v + 4), readl(v + VOTES_OFF),
		readl(m), readl(m + 4), readl(m + VOTES_OFF));
}

static int votes_suspend_noirq(struct device *dev)
{
	votes_dump("freeze");
	return 0;
}

static int votes_resume_noirq(struct device *dev)
{
	votes_dump("resume");
	return 0;
}

static const struct dev_pm_ops votes_pm = {
	.suspend_noirq = votes_suspend_noirq,
	.resume_noirq = votes_resume_noirq,
	.freeze_noirq = votes_suspend_noirq,
	.thaw_noirq = votes_resume_noirq,
};

static int votes_probe(struct platform_device *pdev)
{
	return 0;
}

static struct platform_driver votes_driver = {
	.probe = votes_probe,
	.driver = {
		.name = "votes-snap",
		.pm = &votes_pm,
	},
};

static struct platform_device *votes_dev;

static int __init votes_init(void)
{
	int ret;

	regs = ioremap(RPM_STATS_BASE, 0x10000);
	if (!regs)
		return -ENOMEM;
	ret = platform_driver_register(&votes_driver);
	if (ret)
		return ret;
	votes_dev = platform_device_register_simple("votes-snap", -1, NULL, 0);
	if (IS_ERR(votes_dev)) {
		platform_driver_unregister(&votes_driver);
		return PTR_ERR(votes_dev);
	}
	pr_info("votes_nrq: armed, stats off %#x\n", readl(regs + DYN_ADDR_OFF) & 0xffff);
	return 0;
}
module_init(votes_init);

static void __exit votes_exit(void)
{
	platform_device_unregister(votes_dev);
	platform_driver_unregister(&votes_driver);
	iounmap(regs);
}
module_exit(votes_exit);
MODULE_LICENSE("GPL");
