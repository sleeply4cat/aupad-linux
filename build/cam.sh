#!/bin/bash
# Camera bring-up loop: install this build's modules beside the running ones, RAM-boot it: cam.sh [secs]
set -e
cd "$(dirname "$0")/.."
N=172.16.42.1
SSHO="-q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o ConnectTimeout=4"
M="make -C linux O=../build/out ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-"
ST=$PWD/build/pmos/modroot
rm -rf "$ST"
$M INSTALL_MOD_PATH="$ST" INSTALL_MOD_STRIP=1 modules_install >/dev/null
rm -f "$ST"/lib/modules/*/build "$ST"/lib/modules/*/source
R=$(ls "$ST/lib/modules")
tar -C "$ST" -cz lib | ssh $SSHO root@$N "rm -rf /lib/modules/$R; tar -xz -C / && sync"
rm -rf "$ST"
CMDLINE="earlycon=qcom_geni,0x4a90000 console=ttyMSM0,115200n8 ignore_loglevel clk_ignore_unused pd_ignore_unused rdinit=/init panic=10 root=pmos" build/mkboot.sh build/boot-cam.img >/dev/null
ssh $SSHO root@$N reboot || true
# ub.sh types `rb recovery` at a live gadget and its spaces abort fastboot: drive the handover here instead
for _ in $(seq 120); do lsusb | grep -q 18d1:d001 || break; sleep 0.5; done
venv/bin/python tools/ubstop.py 22 || true
sleep 2
venv/bin/python tools/ubfast.py
timeout 60 build/ub.sh build/boot-cam.img "${1:-30}" | tail -2
for _ in $(seq 30); do ssh $SSHO root@$N true && break; sleep 1; done
ssh $SSHO root@$N 'uname -r; uptime'
