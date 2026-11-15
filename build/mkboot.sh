#!/bin/bash
# Pack mainline Image.gz + AuPad DTB + busybox initramfs into a header-v2 boot image for stock ABL.
# usage: mkboot.sh [out.img]     default: boot-mainline.img     (flash to boot_b only)
set -e
HERE=$(dirname "$(readlink -f "$0")")
OUT=$HERE/out
export AUPAD_BUILD=$HERE
IMG=${1:-$HERE/boot-mainline.img}
# clk/pd_ignore_unused dropped 2026-11-15: with the smd-rpm handoff votes gone
# (0045) audio comes up at boot and the GPU survives suspend cycles clean
# (PORT.md, "Power day 3").
CMDLINE=${CMDLINE:-"earlycon=qcom_geni,0x4a90000 console=ttyMSM0,115200n8 ignore_loglevel rdinit=/init panic=10"}

# Two console modes on the EUD COM, never both: keep_bootcon keeps the boot console and
# console=ttyEUD0 hands over to the real one; together they leave two writers on one FIFO.
case "$CMDLINE" in
*keep_bootcon*console=ttyEUD0*|*console=ttyEUD0*keep_bootcon*)
	echo "mkboot: keep_bootcon with console=ttyEUD0 leaves two writers on the EUD COM:" >&2
	echo "mkboot:   earlycon=qcom_eud,0x1610000 keep_bootcon   (boot console stays)" >&2
	echo "mkboot:   earlycon=qcom_eud,0x1610000 console=ttyEUD0 (clean handover)" >&2
	exit 1;;
esac

"$OUT/usr/gen_init_cpio" "$HERE/initramfs.list" | gzip -9 > "$HERE/initramfs.cpio.gz"

"$HERE/../venv/bin/python" "$HERE/mkbootimg_v2.py" \
    --kernel "${KERNEL:-$OUT/arch/arm64/boot/Image}" \
    --ramdisk "$HERE/initramfs.cpio.gz" \
    --dtb "${DTB:-$OUT/arch/arm64/boot/dts/qcom/sm6225-chuwi-aupad.dtb}" \
    --cmdline "$CMDLINE" \
    --base 0x00000000 --kernel_offset 0x00008000 --ramdisk_offset 0x01000000 \
    --tags_offset 0x00000100 --dtb_offset 0x01f00000 --pagesize 4096 \
    --os_version 15.0.0 --os_patch_level 2025-05 \
    -o "$IMG"
ls -l "$IMG"
