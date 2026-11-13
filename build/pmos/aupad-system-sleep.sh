#!/bin/sh
# elogind system-sleep hook for the AuPad.
#
# Suspend only survives with the ADSP sensor pipeline stopped: on resume the
# frozen sensorspd trips a frpc_dsp fatal and, nine seconds later, an SError
# in swrm_wait_for_wr_fifo_done takes the whole system down (PORT.md,
# "Suspend and power").  Formalise the manual workaround: stop the two
# services before sleep, bring them back after.
#
# Install to /etc/elogind/system-sleep/aupad.sh, mode 0755.

case "$1/$2" in
pre/suspend)
	rc-service iio-sensor-proxy --ifstarted stop
	rc-service hexagonrpcd-adsp-sensorspd --ifstarted stop
	;;
post/resume)
	rc-service hexagonrpcd-adsp-sensorspd --ifstarted start
	rc-service iio-sensor-proxy --ifstarted start
	;;
esac
