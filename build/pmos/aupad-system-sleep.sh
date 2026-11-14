#!/bin/sh
# elogind system-sleep hook for the AuPad.
#
# Suspend only survives with the ADSP sensor pipeline stopped: on resume the
# frozen sensorspd trips a frpc_dsp fatal and, nine seconds later, an SError
# in swrm_wait_for_wr_fifo_done takes the whole system down (PORT.md,
# "Suspend and power").  Formalise the manual workaround: stop the two
# services before sleep, bring them back after.
#
# The gadget link never re-ups after s2idle, and "configured" in the UDC means
# nothing: on 2026-11-14 the system resumed clean (wlan back, RTC-exact wake)
# with the UDC claiming configured while the host side saw no device at all.
# Rebind unconditionally - it costs a two-second link blip.  The unbind write
# has taken a SIGBUS in the writing process (an el0 sync trace, same day), so
# each sysfs write goes through a child shell that can die for it.
#
# Install to /etc/elogind/system-sleep/aupad.sh, mode 0755.

LOG=/var/log/aupad-sleep.log
echo "$(date '+%F %T') $1/$2 begin" >> $LOG

# elogind calls this with ("pre"|"post") and the VERB ("suspend", ...), never
# "resume" - a post/resume) case would match nothing and silently do no work.
case "$1/$2" in
pre/suspend)
	rc-service iio-sensor-proxy --ifstarted stop
	rc-service hexagonrpcd-adsp-sensorspd --ifstarted stop
	;;
post/suspend)
	( sh -c 'echo 4ef8800.usb > /sys/bus/platform/drivers/dwc3-qcom-legacy/unbind' )
	sleep 2
	( sh -c 'echo 4ef8800.usb > /sys/bus/platform/drivers/dwc3-qcom-legacy/bind' )
	sleep 3
	echo "$(date '+%F %T') rebind done, udc $(cat /sys/class/udc/*/state 2>/dev/null)" >> $LOG
	rc-service hexagonrpcd-adsp-sensorspd --ifstarted start
	rc-service iio-sensor-proxy --ifstarted start
	;;
esac
echo "$(date '+%F %T') $1/$2 end" >> $LOG
