#!/usr/bin/env python3
"""Convert downstream dispcc-khaje.c or gpucc-khaje.c into a mainline driver.  Register data is copied.
usage: cc_port.py <dispcc|gpucc> <downstream.c> <mainline sm6115 driver> <out.c>"""
import re, sys

kind, srcf, refs, outf = sys.argv[1:5]
src = open(srcf).read()
ref = open(refs).read()
pre = {'dispcc': 'disp_cc', 'gpucc': 'gpu_cc'}[kind]

# Downstream voltage voting: mainline does this with OPP tables
src = re.sub(r'static DEFINE_VDD_REGULATORS\(.*?\);\n', '', src)
src = re.sub(r'[ \t]*\.vdd_class = &\w+,\n', '', src)
src = re.sub(r'[ \t]*\.num_rate_max = \w+,\n', '', src)
src = re.sub(r'[ \t]*\.rate_max = \(unsigned long\[\w+\]\) \{.*?\},\n', '', src, flags=re.S)

body = src[src.index('enum {'):src.index(f'static struct clk_regmap *{pre}_khaje_clocks')]
table = re.search(rf'static struct clk_regmap \*{pre}_khaje_clocks\[\] = \{{.*?\}};\n', src, re.S)[0]

objs = {n: t for t, n in re.findall(r'^static struct (clk_alpha_pll_postdiv|clk_alpha_pll|clk_rcg2|clk_branch|'
                                    r'clk_regmap_div) (\w+) = \{', body, re.M)}

# Order of the clocks property in sm6115.dtsi
if kind == 'dispcc':
    INDEX = {'bi_tcxo': 'DT_BI_TCXO', 'dsi0_phy_pll_out_byteclk': 'DT_DSI0_PHY_PLL_OUT_BYTECLK',
             'dsi0_phy_pll_out_dsiclk': 'DT_DSI0_PHY_PLL_OUT_DSICLK',
             'gcc_disp_gpll0_div_clk_src': 'DT_GPLL0_DISP_DIV'}
    dt = 'DT_BI_TCXO,\n\tDT_SLEEP_CLK,\n\tDT_DSI0_PHY_PLL_OUT_BYTECLK,\n\tDT_DSI0_PHY_PLL_OUT_DSICLK,\n\tDT_GPLL0_DISP_DIV,'
else:
    INDEX = {'bi_tcxo': 'DT_BI_TCXO', 'gcc_gpu_gpll0_clk_src': 'DT_GCC_GPU_GPLL0_CLK_SRC',
             'gcc_gpu_gpll0_div_clk_src': 'DT_GCC_GPU_GPLL0_DIV_CLK_SRC'}
    dt = 'DT_BI_TCXO,\n\tDT_GCC_GPU_GPLL0_CLK_SRC,\n\tDT_GCC_GPU_GPLL0_DIV_CLK_SRC,'


def pdata(n):
    return f'{{ .index = {INDEX[n]} }}' if n in INDEX else f'{{ .hw = &{n}.clkr.hw }}'


def arr(m):
    lines = ''.join(f'\t{pdata(e)},\n' for e in re.findall(r'"(\w+)"', m[2]))
    return f'static const struct clk_parent_data {pre}_parent_data_{m[1]}[] = {{\n{lines}}};\n'


body = re.sub(rf'static const char \* const {pre}_parent_names_(\w+)\[\] = \{{(.*?)\}};\n', arr, body, flags=re.S)
body = re.sub(rf'\.parent_names = {pre}_parent_names_(\w+),', rf'.parent_data = {pre}_parent_data_\1,', body)
body = re.sub(rf'ARRAY_SIZE\({pre}_parent_names_(\w+)\)', rf'ARRAY_SIZE({pre}_parent_data_\1)', body)


def single(m):
    n, ind = re.search(r'"(\w+)"', m[2])[1], m[1]
    if n in INDEX:
        return f'{ind}.parent_data = &(const struct clk_parent_data){{\n{ind}\t.index = {INDEX[n]},\n{ind}}},\n'
    return f'{ind}.parent_hws = (const struct clk_hw*[]) {{\n{ind}\t&{n}.clkr.hw,\n{ind}}},\n'


body = re.sub(r'([ \t]*)\.parent_names =\s*\(const char \*\[\]\)\{(.*?)\},\n', single, body, flags=re.S)
assert 'parent_names' not in body

# RCG ops and rate flags: mainline's choice for the same clock on sm6115
refblocks = {m[1]: m[0] for m in re.finditer(r'^static struct clk_rcg2 (\w+) = \{.*?^\};', ref, re.M | re.S)}


def rcgfix(m):
    block = re.sub(r'[ \t]*\.enable_safe_config = true,\n', '', m[0])
    name = re.search(r'\.name = "(\w+)"', block)[1]
    r = refblocks[name]
    block = block.replace('.ops = &clk_rcg2_ops', re.search(r'\.ops = &\w+', r)[0])
    if 'NOCACHE' in r:
        block = re.sub(r'\.flags = .*', re.search(r'\.flags = .*', r)[0], block)
    return block


body = re.sub(r'^static struct clk_rcg2 \w+ = \{.*?^\};', rcgfix, body, flags=re.M | re.S)
assert 'enable_safe_config' not in body

gd = ''.join(re.findall(r'^static struct gdsc \w+ = \{.*?^\};\n\n', ref, re.M | re.S))
gdtab = re.search(rf'static struct gdsc \*{pre}_sm6115_gdscs\[\] = \{{.*?\}};\n', ref, re.S)[0]
resets = re.search(rf'static const struct qcom_reset_map {pre}_sm6115_resets\[\] = \{{.*?\}};\n', ref, re.S)[0]
regcfg = re.search(rf'static const struct regmap_config {pre}_sm6115_regmap_config = \{{.*?\}};\n', ref, re.S)[0]
if kind == 'dispcc':
    assert '[DISP_CC_MDSS_CORE_BCR] = { 0x2000 }' in resets
    # khaje has sm6375's layout here: the stock DT node is gdsc@5f03000, but its reg is 0x5f01004
    resets = resets.replace('0x2000', '0x1000')
    assert '.gdscr = 0x3000' in gd
    gd = gd.replace('.gdscr = 0x3000', '.gdscr = 0x1004')
    keep = '\tregmap_update_bits(regmap, 0x5004, BIT(0), BIT(0));\n\tregmap_update_bits(regmap, 0x5008, BIT(0), BIT(0));\n\n'
    cfg = '\tclk_lucid_pll_configure(&disp_cc_pll0, regmap, &disp_cc_pll0_config);\n'
    extra = ''
    what = 'Display'
else:
    # Keep GPU_CC_GX_CXO_CLK on
    keep = '\tregmap_update_bits(regmap, 0x1060, BIT(0), BIT(0));\n\n'
    cfg = ('\tclk_zonda_pll_configure(&gpu_cc_pll0, regmap, &gpu_cc_pll0_config);\n'
           '\tclk_lucid_pll_configure(&gpu_cc_pll1, regmap, &gpu_cc_pll1_config);\n')
    extra = re.search(r'\n\t/\* Set recommended WAKEUP.*?force_periph_on[^\n]*\n', ref, re.S)[0]
    what = 'Graphics'

fwd = ''.join(f'static struct {t} {n};\n' for n, t in objs.items())
out = f'''// SPDX-License-Identifier: GPL-2.0-only
/*
 * {what} clock controller for Qualcomm SM6225 (khaje).
 * Data from the downstream {kind}-khaje.c, Copyright (c) 2021, The Linux Foundation.
 */

#include <linux/clk-provider.h>
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/regmap.h>

#include <dt-bindings/clock/qcom,sm6115-{kind}.h>

#include "clk-alpha-pll.h"
#include "clk-branch.h"
#include "clk-rcg.h"
#include "clk-regmap.h"
#include "clk-regmap-divider.h"
#include "common.h"
#include "gdsc.h"
#include "reset.h"

enum {{
	{dt}
}};

{fwd}
{body}{gd}{gdtab}
{table}
{resets}
{regcfg}
static const struct qcom_cc_desc {pre}_sm6225_desc = {{
	.config = &{pre}_sm6225_regmap_config,
	.clks = {pre}_sm6225_clocks,
	.num_clks = ARRAY_SIZE({pre}_sm6225_clocks),
	.resets = {pre}_sm6225_resets,
	.num_resets = ARRAY_SIZE({pre}_sm6225_resets),
	.gdscs = {pre}_sm6225_gdscs,
	.num_gdscs = ARRAY_SIZE({pre}_sm6225_gdscs),
}};

static const struct of_device_id {pre}_sm6225_match_table[] = {{
	{{ .compatible = "qcom,sm6225-{kind}" }},
	{{ }}
}};
MODULE_DEVICE_TABLE(of, {pre}_sm6225_match_table);

static int {pre}_sm6225_probe(struct platform_device *pdev)
{{
	struct regmap *regmap;

	regmap = qcom_cc_map(pdev, &{pre}_sm6225_desc);
	if (IS_ERR(regmap))
		return PTR_ERR(regmap);

{keep}{cfg}{extra}
	return qcom_cc_really_probe(&pdev->dev, &{pre}_sm6225_desc, regmap);
}}

static struct platform_driver {pre}_sm6225_driver = {{
	.probe = {pre}_sm6225_probe,
	.driver = {{
		.name = "sm6225-{kind}",
		.of_match_table = {pre}_sm6225_match_table,
	}},
}};
module_platform_driver({pre}_sm6225_driver);

MODULE_DESCRIPTION("Qualcomm SM6225 {what} Clock Controller");
MODULE_LICENSE("GPL");
'''
out = out.replace(f'{pre}_khaje', f'{pre}_sm6225').replace(f'{pre}_sm6115', f'{pre}_sm6225')
open(outf, 'w').write(out)
