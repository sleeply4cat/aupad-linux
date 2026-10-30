#!/bin/bash
# Push a rootfs image into the pmos partition of a tablet running the mainline initramfs: flr.sh [image]
cd "$(dirname "$0")/.."
mkdir -p logs
IMG=${1:-build/pmos/rootfs.img}
N=fe80::2aa:55ff:fe00:2%enx02aa55000001
for i in $(seq 15); do ping -6 -c1 -W1 $N >/dev/null 2>&1 && break; done
LOG=logs/flr-$(date +%m%d-%H%M%S).log
venv/bin/python tools/uartlog.py "$LOG" 150 &
LP=$!
venv/bin/python tools/flpush.py "$IMG" 5556 || { kill $LP; exit 1; }
for i in $(seq 140); do grep -aqE "FLASH (ROOT OK|FAILED)" "$LOG" && break; sleep 1; done
kill $LP 2>/dev/null; wait 2>/dev/null
grep -aoE "FLASH (ROOT OK|FAILED).*" "$LOG" | tail -1
grep -aq "FLASH ROOT OK" "$LOG"
