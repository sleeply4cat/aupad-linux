#!/bin/sh
# EUD-off link test, take 3: eudoff.ko does the sanctioned disable (SCM mode_mgr2=0
# + CTLOUT=0, mirroring the stub's enable sequence), then freeze 45 s (RTC alarm)
# and watch the UDC for 20 s without touching anything; rebind only if needed.
# -> /root/eudoff.txt, marker /root/eudoff.done
OUT=/root/eudoff.txt
{
echo "=== EUD-off link test (scm), kernel $(uname -r), $(date)"
dmesg | grep -a "EUD is enabled\|EUD CTLOUT"
echo "UDC pre: $(cat /sys/class/udc/*/state)"
} > $OUT

insmod /root/eudoff.ko
sleep 2
dmesg | grep -a "eudoff:" >> $OUT

j=0
while [ $j -lt 15 ]; do
	echo "C+$j $(cat /sys/class/udc/*/state 2>/dev/null)" >> $OUT
	sleep 1
	j=$((j+1))
done
sync

sleep 5			# settle before the freeze
E=$(cat /sys/class/rtc/rtc0/since_epoch)
echo $((E+45)) > /sys/class/rtc/rtc0/wakealarm
echo "FREEZE $(date +%s)" >> $OUT
echo freeze > /sys/power/state
echo "WAKE $(date +%s)" >> $OUT
echo 0 > /sys/class/rtc/rtc0/wakealarm
sync

i=0
while [ $i -lt 20 ]; do
	S=$(cat /sys/class/udc/*/state 2>/dev/null)
	echo "T+$i $S" >> $OUT
	[ "$S" = "configured" ] && break
	sleep 1
	i=$((i+1))
done

if [ "$(cat /sys/class/udc/*/state 2>/dev/null)" = "configured" ]; then
	echo "RESULT: link up at T+$i" >> $OUT
else
	echo "RESULT: link down at T+20, rebinding" >> $OUT
	echo "4ef8800.usb" > /sys/bus/platform/drivers/dwc3-qcom-legacy/unbind
	sleep 2
	echo "4ef8800.usb" > /sys/bus/platform/drivers/dwc3-qcom-legacy/bind
	sleep 5
	echo "after rebind: $(cat /sys/class/udc/*/state 2>/dev/null)" >> $OUT
fi
dmesg | grep -aiE "eudoff|ep0out|dwc3" | tail -10 >> $OUT
sync
echo done > /root/eudoff.done
