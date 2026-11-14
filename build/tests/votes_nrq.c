// votes_nrq: print the RPM sleep-stats client votes as the system goes into
// s2idle.  syscore callbacks never run for freeze (suspend_enter() short-
// circuits s2idle before syscore_suspend()), and a userspace read after wake is
// always too late - the kernel re-votes during device resume, before tasks
// thaw.  suspend_noirq runs late in the freeze path, after every device has
// done suspend and suspend_late, so it is the last practical observation point.
// Layout mirrors drivers/soc/qcom/qcom_stats.c: dynamic stats offset at +0x14,
// records of 32-byte sleep_stats + 16-byte appended_stats, client_votes first.
#include <linux/module.h>
#include <linux/io.h>
#include <linux/platform_device.h>

#define RPM_STATS_BASE	0x04690000
#define DYN_ADDR_OFF	0x14
#define VOTES_OFF	32		/* client_votes sits right after sleep_stats */
#define REC_STRIDE	48		/* sleep_stats + appended_stats */

static void __iomem *regs;

static int votes_suspend_noirq(struct device *dev)
{
	u32 off = readl(regs + DYN_ADDR_OFF) & 0xffff;

	pr_info("votes_nrq: at noirq vlow %#x vmin %#x (stats off %#x)\n",
		readl(regs + off + VOTES_OFF), readl(regs + off + REC_STRIDE + VOTES_OFF), off);
	return 0;
}

static const struct dev_pm_ops votes_pm = {
	.suspend_noirq = votes_suspend_noirq,
	.freeze_noirq = votes_suspend_noirq,
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
