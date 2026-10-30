#!/bin/bash
# Install a kernel on running pmOS, verified, and reboot into it: kup.sh [image]
# The previous one stays as /boot/boot.old.  A kernel that hangs is recovered by hand: ub.sh, then rerun this.
set -e
cd "$(dirname "$0")/.."
IMG=${1:-build/boot-pmos.img}
N=172.16.42.1
SSHO="-q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o ConnectTimeout=4"
scp $SSHO "$IMG" root@$N:/boot/boot.new
want=$(md5sum "$IMG" | cut -d' ' -f1)
ssh $SSHO root@$N "sync; [ \"\$(md5sum /boot/boot.new | cut -d' ' -f1)\" = $want ] && cp /boot/boot.img /boot/boot.old && mv /boot/boot.new /boot/boot.img && sync && reboot"
echo "installed $want, rebooting"
