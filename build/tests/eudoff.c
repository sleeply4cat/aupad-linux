// eudoff: turn the EUD off the way the stub turned it on (stub/main.c): mode_mgr2
// over the SCM, CTLOUT direct.  A plain write to 0x1612000 is a non-secure access to a
// secure register and kills the kernel; the SCM call is the sanctioned path (stock eud.ko).
#include <linux/module.h>
#include <linux/io.h>
#include <linux/firmware/qcom/qcom_scm.h>

#define EUD_MODE_MGR2	0x01612000
#define EUD_CTL_OUT	0x01611014

static int __init eudoff_init(void)
{
	void __iomem *mm = ioremap(EUD_MODE_MGR2, 4), *ctlo = ioremap(EUD_CTL_OUT, 4);
	int ret;

	if (!mm || !ctlo) {
		ret = -ENOMEM;
		goto out;
	}
	ret = qcom_scm_io_writel(EUD_MODE_MGR2, 0);
	writel(0, ctlo);
	pr_info("eudoff: mode_mgr2 -> 0 ret %d reads 0x%x, ctl_out now 0x%x\n",
		ret, readl(mm), readl(ctlo));
out:
	if (mm)
		iounmap(mm);
	if (ctlo)
		iounmap(ctlo);
	return ret;
}
module_init(eudoff_init);
MODULE_LICENSE("GPL");
