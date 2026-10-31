#!/bin/bash
# Second half of a fresh OS, run after mkrootfs.sh, flr.sh and stage2 with pmOS up: the Phosh system and everything hand-made.
# Rerunnable.  Needs tools/usbproxy.py on the host and build/pmos/overlay.tar.gz (build/mkoverlay.py).
set -e
cd "$(dirname "$0")/.."
N=172.16.42.1
SSHO="-q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o ConnectTimeout=6 -o ServerAliveInterval=15"
scp $SSHO build/pmos/world build/pmos/overlay.tar.gz build/pmos/greetd/default.pa root@$N:/tmp/
ssh $SSHO root@$N sh -e <<'R'
export http_proxy=http://172.16.42.2:8888 https_proxy=http://172.16.42.2:8888
apk update | tail -1
apk add --no-progress $(cat /tmp/world) | tail -2
tar -xzf /tmp/overlay.tar.gz -C /
id user >/dev/null 2>&1 || adduser -D -u 10000 -s /bin/sh user
for g in wheel audio dialout input video netdev users seat feedbackd plugdev; do addgroup user $g 2>/dev/null || true; done
sed -i '/^user:/d' /etc/shadow; cat /etc/aupad-user-shadow >> /etc/shadow; rm /etc/aupad-user-shadow
mkdir -p /var/lib/greetd/.config/pulse; cp /tmp/default.pa /var/lib/greetd/.config/pulse/
chown -R greetd:greetd /var/lib/greetd/.config
chown -R fastrpc:fastrpc /usr/share/qcom
chmod 600 /etc/NetworkManager/system-connections/*
for s in dbus cgroups elogind apk-polkit-server udev-postmount bluetooth pd-mapper tqftpserv rmtfs nftables haveged wpa_supplicant \
         networkmanager chronyd greetd hexagonrpcd-adsp-sensorspd iio-sensor-proxy modemmanager openrc-settingsd \
         postmarketos-zram-swap rfkill sleep-inhibitor sshd local; do
    rc-update add $s default >/dev/null
done
rc-update del sddm default 2>/dev/null || true; rc-update del tinydm default 2>/dev/null || true
apk audit --system 2>/dev/null | head -3 || true
sync
rc-update show default | wc -l; apk info | wc -l; df -h / | tail -1
R
