#!/bin/sh
# One RAW suspend cycle (no elogind path - it delays the first read past the
# re-voting) with Client-Votes snapshots, then a self-rebind of the gadget.
# usage: nohup sh sleepvote.sh <label> &    -> /root/sleepvote.txt
OUT=/root/sleepvote.txt
L=${1:-cycle}
D=/sys/bus/platform/drivers/dwc3-qcom-legacy
snap() {
	echo "--- $1 $L $(date +%T)"
	grep -H -E "^Count|^Client Votes" /sys/kernel/debug/qcom_stats/vlow /sys/kernel/debug/qcom_stats/vmin
}
{
snap awake-pre
E=$(cat /sys/class/rtc/rtc0/since_epoch)
echo 0 > /sys/class/rtc/rtc0/wakealarm
echo $((E+30)) > /sys/class/rtc/rtc0/wakealarm
echo freeze > /sys/power/state
snap wake-instant
echo 0 > /sys/class/rtc/rtc0/wakealarm
( sh -c "echo 4ef8800.usb > $D/unbind" ); sleep 2
( sh -c "echo 4ef8800.usb > $D/bind" )
sleep 5
snap settled
} >> $OUT 2>&1
sync
