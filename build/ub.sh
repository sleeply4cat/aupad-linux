#!/bin/bash
# RAM-boot an image through U-Boot, with no flashing and no Android: ub.sh <image> [max_seconds]
# Needs U-Boot in recovery_b and boot-recovery in misc.  Same verdicts as run.sh.
set -u
cd "$(dirname "$0")/.."
IMG=$1; MAX=${2:-120}
E=/home/kirill/repo/edl/venv/bin/python
UART=$(ls /tmp/aupad-uart 2>/dev/null || ls /dev/serial/by-id/usb-Nordic_nanobridge_*-if00)
# tools/tab.py types only at a confirmed U-Boot prompt and checks that fastboot enumerates: any stray character
# while U-Boot is in fastboot aborts it, which is what made the old ubstop.py loop miss
T0=$(date +%s)
venv/bin/python tools/tab.py fastboot || { echo "=== NOFASTBOOT after $(( $(date +%s) - T0 ))s"; exit 1; }
LOG=logs/ub-$(date +%m%d-%H%M%S).log
venv/bin/python tools/uartlog.py "$LOG" "$MAX" &
LP=$!
sleep 0.3
timeout 20 fastboot boot "$IMG" >/dev/null 2>&1 || echo "fastboot boot failed"
verdict=timeout
while kill -0 $LP 2>/dev/null; do
    sleep 0.5
    if grep -aq "TESTDONE\|Kernel panic - not syncing" "$LOG"; then verdict=done; break; fi
    if grep -aq "Format: Log Type\|must RESET\|Synchronous Abort" "$LOG"; then verdict=HANG; break; fi
done
kill $LP 2>/dev/null; wait 2>/dev/null
echo "=== $verdict after $(( $(date +%s) - T0 ))s  ($LOG)"
grep -aE "TESTSTART|\] T: |TESTDONE|must RESET|Kernel panic|Internal error|Unable to handle" "$LOG" | sed 's/^\[[ 0-9.]*\] //' | tail -40
[ $verdict = done ]
