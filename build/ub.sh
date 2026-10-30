#!/bin/bash
# RAM-boot an image through U-Boot, with no flashing and no Android: ub.sh <image> [max_seconds]
# Needs U-Boot in recovery_b and boot-recovery in misc.  
set -u
cd "$(dirname "$0")/.."
mkdir -p logs
IMG=$1; MAX=${2:-120}
E=${EDL_PYTHON:-python3}
UART=$(ls /dev/serial/by-id/usb-Nordic_nanobridge_*-if00)
fb() { timeout 1 fastboot devices 2>/dev/null | grep -q .; }
T0=$(date +%s)
# U-Boot autoboots pmOS after 1 s unless stopped
fb || { venv/bin/python tools/ubstop.py 60 & STOP=$!; }
for _ in $(seq 60); do
    fb && break
    case "$(lsusb | grep -oE '05c6:900e|18d1:d001|18d1:4e[0-9a-f]{2}|05c6:f000' | head -1)" in
        05c6:900e) $E tools/sahara_reset.py >/dev/null 2>&1; sleep 3 ;;
        18d1:d001) printf 'rb recovery\r' > $UART; sleep 3 ;;
        18d1:4ee0) ;;
        18d1:4e*)  adb reboot; sleep 3 ;;
        05c6:f000) echo "tablet in off-mode charging: press power" ;;
    esac
    sleep 1
done
kill ${STOP:-} 2>/dev/null; wait ${STOP:-} 2>/dev/null
fb || { echo "=== NOFASTBOOT after $(( $(date +%s) - T0 ))s"; exit 1; }
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
