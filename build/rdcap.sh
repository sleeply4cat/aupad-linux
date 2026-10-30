#!/bin/bash
# Capture a ramdump (05c6:900e), then leave it: dump table, status blocks, kernel log, reset.  Writes logs/rd-<time>/.
# Raw USB only (tools/rdraw.py, rdscan.py): edl's read path hangs, and an abort leaves Sahara refusing everything until
# a USB reset.  The log is found by its text, because U-Boot puts the kernel at 0x80600000 and System.map may be newer.
set -u
cd "$(dirname "$0")/.."
E=${EDL_PYTHON:-python3}     # needs pyusb
exec 9>logs/.rdcap.lock; flock -n 9 || exit 0
D=logs/rd-$(date +%m%d-%H%M%S); mkdir -p "$D"
: > "$D/table.txt"
timeout 120 $E tools/rdraw.py "$D" 0 0x1000 > "$D/status.log" 2>&1
timeout 240 $E tools/rdscan.py "$D" 0x80000000 0x90000000 --reset > "$D/scan.log" 2>&1
echo "$D: $(wc -l < "$D/klog.txt" 2>/dev/null) log lines, $(tail -1 "$D/scan.log")"
tail -30 "$D/klog.txt" 2>/dev/null
