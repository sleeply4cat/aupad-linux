#!/bin/bash
# Replace recovery_b from a tablet running mainline: fl.sh <image> [max_seconds]
# Push over USB, it flashes itself and reboots.  Use only with a stub + U-Boot image.
set -u
cd "$(dirname "$0")/.."
mkdir -p logs
IMG=$1; MAX=${2:-120}
NET=fe80::2aa:55ff:fe00:2%enx02aa55000001
ping -6 -c 1 -W 1 $NET >/dev/null 2>&1 || { echo "tablet not reachable over USB"; exit 1; }

LOG=logs/fl-$(date +%m%d-%H%M%S).log
venv/bin/python tools/uartlog.py "$LOG" "$MAX" &
LP=$!
T0=$(date +%s); verdict=timeout
venv/bin/python tools/flpush.py "$IMG" || verdict=PUSHFAILED
while [ $verdict = timeout ] && kill -0 $LP 2>/dev/null; do
    sleep 0.5
    if grep -aq "FLASH FAILED" "$LOG"; then verdict=FLASHFAILED
    elif grep -aq "TESTDONE\|Kernel panic - not syncing" "$LOG"; then verdict=done
    elif [ "$(grep -ac "Format: Log Type" "$LOG")" -ge 2 ]; then verdict=HANG
    fi
done
kill $LP 2>/dev/null; wait 2>/dev/null
echo "=== $verdict after $(( $(date +%s) - T0 ))s  ($LOG)"
grep -aE "FLASH |TESTSTART|\] T: |TESTDONE|Kernel panic|Internal error|Unable to handle" "$LOG" | sed 's/^\[[ 0-9.]*\] //' | tail -40
[ $verdict = done ]
