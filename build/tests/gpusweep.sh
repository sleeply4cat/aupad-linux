#!/bin/sh
# Pin the GPU to each OPP in turn and run gpustress: gpusweep.sh [seconds] [loops].  Runs on the tablet.
S=${1:-14}; L=${2:-40}
D=/sys/class/devfreq/5900000.gpu
temp() { for z in /sys/class/thermal/thermal_zone*; do echo "$(cat $z/temp) $(cat $z/type)"; done | sort -n | tail -1; }
echo userspace > $D/governor
for f in $(cat $D/available_frequencies); do
    echo 1 > $D/min_freq; echo $f > $D/max_freq; echo $f > $D/min_freq
    r=$(timeout $((S + 12)) gpustress $S $L | tail -1)
    echo "$((f / 1000000)) MHz: cur $(($(cat $D/cur_freq) / 1000000)) | $r | hottest $(temp)"
done
echo simple_ondemand > $D/governor
echo 1 > $D/min_freq
echo $(sed 's/.* //' $D/available_frequencies) > $D/max_freq
dmesg | grep -E "hangcheck|gpu fault|recover|SMMU.*fault|Internal error" | cut -c1-120 | tail -4
