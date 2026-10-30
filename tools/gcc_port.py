#!/usr/bin/env python3
"""Convert downstream gcc-khaje.c into a mainline driver.  Register data is copied, never edited.
usage: gcc_port.py <gcc-khaje.c> <mainline gcc-sm6115.c> <out.c>"""
import re, sys

src = open(sys.argv[1]).read()
sm6115 = open(sys.argv[2]).read()

# Downstream voltage voting: mainline has nothing like it
src = re.sub(r'static DEFINE_VDD_REGULATORS\(.*?\);\n', '', src)
src = re.sub(r'[ \t]*\.vdd_class = &\w+,\n', '', src)
src = re.sub(r'[ \t]*\.num_rate_max = \w+,\n', '', src)
src = re.sub(r'[ \t]*\.rate_max = \(unsigned long\[\w+\]\) \{.*?\},\n', '', src, flags=re.S)

start = src.index('enum {')
body = src[start:src.index('static const struct clk_rcg_dfs_data gcc_dfs_clocks')]

# What kind of object each clock name is, for forward declarations and hw pointers
objs = {}
for typ, name in re.findall(r'^static struct (clk_alpha_pll_postdiv|clk_alpha_pll|clk_rcg2|clk_branch|'
                            r'clk_regmap_div|clk_regmap_mux) (\w+) = \{', body, re.M):
    objs[name] = typ
# .name can differ from the C identifier
names = {}
for m in re.finditer(r'^static struct \w+ (\w+) = \{(.*?)^\};', body, re.M | re.S):
    n = re.search(r'\.name = "(\w+)"', m[2])
    if n:
        names[n[1]] = m[1]
for m in re.finditer(r'^static struct clk_init_data (\w+)_init = \{(.*?)^\};', body, re.M | re.S):
    names[re.search(r'\.name = "(\w+)"', m[2])[1]] = m[1]

EXTERNAL = {'bi_tcxo', 'sleep_clk', 'usb3_phy_wrapper_gcc_usb30_pipe_clk', 'ufs_phy_rx_symbol_0_clk',
            'ufs_phy_rx_symbol_1_clk', 'ufs_phy_tx_symbol_0_clk'}


def pdata(n):
    if n in EXTERNAL:
        return f'{{ .fw_name = "{n}" }}'
    return f'{{ .hw = &{names[n]}.clkr.hw }}'


# Parent name arrays become parent_data arrays
def arr(m):
    entries = re.findall(r'"(\w+)"', m[2])
    lines = ''.join(f'\t{pdata(e)},\n' for e in entries)
    return f'static const struct clk_parent_data gcc_parent_data_{m[1]}[] = {{\n{lines}}};\n'


body = re.sub(r'static const char \* const gcc_parent_names_(\w+)\[\] = \{(.*?)\};\n', arr, body, flags=re.S)
body = re.sub(r'\.parent_names = gcc_parent_names_(\w+),', r'.parent_data = gcc_parent_data_\1,', body)
body = re.sub(r'ARRAY_SIZE\(gcc_parent_names_(\w+)\)', r'ARRAY_SIZE(gcc_parent_data_\1)', body)


# Inline single parents
def single(m):
    n = re.search(r'"(\w+)"', m[2])[1]
    ind = m[1]
    if n in EXTERNAL:
        return (f'{ind}.parent_data = &(const struct clk_parent_data){{\n'
                f'{ind}\t.fw_name = "{n}",\n{ind}}},\n')
    return (f'{ind}.parent_hws = (const struct clk_hw*[]) {{\n'
            f'{ind}\t&{names[n]}.clkr.hw,\n{ind}}},\n')


body = re.sub(r'([ \t]*)\.parent_names =\s*\(const char \*\[\]\)\{(.*?)\},\n', single, body, flags=re.S)
left = re.findall(r'.*parent_names.*', body); assert not left, left[:4]

# RCG ops: mainline's choice for that name, else shared ops where downstream parks at XO
ops = {}
for m in re.finditer(r'\.name = "(\w+_clk_src)",.*?\.ops = &(clk_rcg2\w*)', sm6115, re.S):
    ops[m[1]] = m[2]


def rcgfix(m):
    block = m[0]
    safe = '.enable_safe_config = true,' in block
    block = re.sub(r'[ \t]*\.enable_safe_config = true,\n', '', block)
    n = re.search(r'\.name = "(\w+)"', block)
    if n:
        op = ops.get(n[1], 'clk_rcg2_shared_ops' if safe else 'clk_rcg2_ops')
        block = block.replace('.ops = &clk_rcg2_ops', f'.ops = &{op}')
    return block


body = re.sub(r'^static struct clk_rcg2 \w+ = \{.*?^\};', rcgfix, body, flags=re.M | re.S)
assert 'enable_safe_config' not in body

# sdcc1 is eMMC, unused here, and mainline has no hand-off flag
body = body.replace(' | CLK_ENABLE_HAND_OFF', '')

gd = ''.join(re.findall(r'^static struct gdsc \w+ = \{.*?^\};\n\n', sm6115, re.M | re.S))
gdtab = re.search(r'static struct gdsc \*gcc_sm6115_gdscs\[\] = \{.*?\};\n', sm6115, re.S)[0]
gdtab = gdtab.replace('gcc_sm6115_gdscs', 'gcc_sm6225_gdscs')
dfs = re.search(r'static const struct clk_rcg_dfs_data gcc_dfs_clocks.*?\};\n', src, re.S)[0]

fwd = ''.join(f'static struct {t} {n};\n' for n, t in objs.items())
body = re.sub(r'gcc_khaje', 'gcc_sm6225', body)
body = re.sub(r'static struct regmap_config.*?\};\n', '', body, flags=re.S)

head = '''// SPDX-License-Identifier: GPL-2.0-only
/*
 * Global clock controller for Qualcomm SM6225 (khaje).
 * Data from the downstream gcc-khaje.c, Copyright (c) 2021, The Linux Foundation.
 */

#include <linux/clk-provider.h>
#include <linux/err.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/regmap.h>

#include <dt-bindings/clock/qcom,gcc-sm6115.h>

#include "clk-alpha-pll.h"
#include "clk-branch.h"
#include "clk-rcg.h"
#include "clk-regmap.h"
#include "clk-regmap-divider.h"
#include "clk-regmap-mux.h"
#include "common.h"
#include "gdsc.h"
#include "reset.h"

'''
tail = gd + gdtab + '\n' + dfs + '''
static const struct regmap_config gcc_sm6225_regmap_config = {
	.reg_bits = 32,
	.reg_stride = 4,
	.val_bits = 32,
	.max_register = 0xc7000,
	.fast_io = true,
};

static const struct qcom_cc_desc gcc_sm6225_desc = {
	.config = &gcc_sm6225_regmap_config,
	.clks = gcc_sm6225_clocks,
	.num_clks = ARRAY_SIZE(gcc_sm6225_clocks),
	.resets = gcc_sm6225_resets,
	.num_resets = ARRAY_SIZE(gcc_sm6225_resets),
	.gdscs = gcc_sm6225_gdscs,
	.num_gdscs = ARRAY_SIZE(gcc_sm6225_gdscs),
};

static const struct of_device_id gcc_sm6225_match_table[] = {
	{ .compatible = "qcom,sm6225-gcc" },
	{ }
};
MODULE_DEVICE_TABLE(of, gcc_sm6225_match_table);

static int gcc_sm6225_probe(struct platform_device *pdev)
{
	struct regmap *regmap;
	int ret;

	regmap = qcom_cc_map(pdev, &gcc_sm6225_desc);
	if (IS_ERR(regmap))
		return PTR_ERR(regmap);

	/* Keep these always on: camera and display XO, CPUSS GNOC, GPU CFG AHB */
	regmap_update_bits(regmap, 0x17028, BIT(0), BIT(0));
	regmap_update_bits(regmap, 0x2b004, BIT(0), BIT(0));
	regmap_update_bits(regmap, 0x1702c, BIT(0), BIT(0));
	regmap_update_bits(regmap, 0x36004, BIT(0), BIT(0));

	ret = qcom_cc_register_rcg_dfs(regmap, gcc_dfs_clocks, ARRAY_SIZE(gcc_dfs_clocks));
	if (ret)
		return ret;

	clk_lucid_pll_configure(&gpll10, regmap, &gpll10_config);
	clk_lucid_pll_configure(&gpll11, regmap, &gpll11_config);
	clk_lucid_pll_configure(&gpll8, regmap, &gpll8_config);
	clk_zonda_pll_configure(&gpll9, regmap, &gpll9_config);

	return qcom_cc_really_probe(&pdev->dev, &gcc_sm6225_desc, regmap);
}

static struct platform_driver gcc_sm6225_driver = {
	.probe = gcc_sm6225_probe,
	.driver = {
		.name = "gcc-sm6225",
		.of_match_table = gcc_sm6225_match_table,
	},
};

static int __init gcc_sm6225_init(void)
{
	return platform_driver_register(&gcc_sm6225_driver);
}
subsys_initcall(gcc_sm6225_init);

static void __exit gcc_sm6225_exit(void)
{
	platform_driver_unregister(&gcc_sm6225_driver);
}
module_exit(gcc_sm6225_exit);

MODULE_DESCRIPTION("Qualcomm SM6225 Global Clock Controller");
MODULE_LICENSE("GPL");
'''
open(sys.argv[3], 'w').write(head + fwd + '\n' + body + tail)
