#!/bin/bash
# Pack mainline Image.gz + AuPad DTB + busybox initramfs into a header-v2 boot image for stock ABL.
# usage: mkboot.sh [out.img]     default: boot-mainline.img     (flash to boot_b only)
set -e
HERE=$(dirname "$(readlink -f "$0")")
OUT=$HERE/out
export AUPAD_BUILD=$HERE
IMG=${1:-$HERE/boot-mainline.img}
CMDLINE=${CMDLINE:-"earlycon=qcom_geni,0x4a90000 console=ttyMSM0,115200n8 ignore_loglevel clk_ignore_unused pd_ignore_unused rdinit=/init panic=10"}

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
