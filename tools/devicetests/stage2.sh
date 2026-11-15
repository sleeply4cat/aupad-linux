#!/bin/sh
# test=stage2: finish the rootfs install on the tablet, where package scripts can run.  Safe to rerun.
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
u=$(grep -l '^PARTNAME=pmos$' /sys/class/block/sd*/uevent) || { echo "no pmos partition"; exit 1; }
n=$(basename $(dirname $u))
blockdev --setrw /dev/${n%%[0-9]*}; blockdev --setrw /dev/$n
mount -t ext4 /dev/$n /mnt || { echo "mount failed"; exit 1; }
R=/mnt
for m in proc sys dev dev/pts; do mount --bind /$m $R/$m; done

chroot $R apk add --no-network $(cat $R/etc/stage2-packages) > /tmp/apk.log 2>&1
echo "apk rc $?"
grep -iE "error|warn|fail" /tmp/apk.log | head -20
tail -3 /tmp/apk.log
chroot $R apk info | wc -l

echo aupad > $R/etc/hostname
# No login on the debug consoles while porting
sed -i -e '/^tty[2-6]::/d' -e '/^ttyMSM0::/d' -e '/^ttyGS0::/d' $R/etc/inittab
cat >> $R/etc/inittab <<I
ttyMSM0::respawn:/sbin/getty -n -l /bin/sh 115200 ttyMSM0 vt100
ttyGS0::respawn:/sbin/getty -n -l /bin/sh 115200 ttyGS0 vt100
I
cat > $R/etc/local.d/flash.start <<'L'
#!/bin/sh
# NetworkManager on the host drops the interface, link-local included, after 45 s without a lease.
# No router or DNS offered, so this doesn't touch the host's routes.  Not the unudhcpd service: it needs net,
# which nothing here provides.
unudhcpd -i usb0 -s 172.16.42.1 -c 172.16.42.2 >/dev/null 2>&1 &
# flash loader, same as in the initramfs: build/fl.sh pushes a boot image here
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
(while true; do
    rx 5555 /tmp/new.img && flash /tmp/new.img
    rm -f /tmp/new.img
done) &
L
chmod +x $R/etc/local.d/flash.start
[ -f /bin/authorized_keys ] && mkdir -p $R/root/.ssh && chmod 700 $R/root/.ssh && cp /bin/authorized_keys $R/root/.ssh/
for s in local sshd; do chroot $R rc-update add $s default; done
# No settable RTC yet: keep time across reboots in the file swclock saves at shutdown
mkdir -p $R/var/lib/misc
chroot $R rc-update del hwclock boot 2>/dev/null
chroot $R rc-update add swclock boot
chroot $R rc-update show 2>&1 | head -40
chroot $R resize2fs /dev/$n 2>&1 | tail -1
df -h $R
for m in dev/pts dev sys proc; do umount $R/$m; done
umount $R
sync
