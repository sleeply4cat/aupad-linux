#!/bin/sh
# flash <boot.img>: write it to recovery_b, verify by reading back, reboot into it.
# recovery_b is the only partition this ever writes.
say() { echo "FLASH $*" > /dev/kmsg; }
die() { say "FAILED: $*"; exit 1; }

f=$1
[ "$(dd if=$f bs=8 count=1 2>/dev/null)" = "ANDROID!" ] || die "not a boot image"
u=$(grep -l '^PARTNAME=recovery_b$' /sys/class/block/sd*/uevent) || die "no recovery_b"
[ "$(echo "$u" | wc -l)" = 1 ] || die "several recovery_b"
n=$(basename $(dirname $u))
p=/dev/$n
d=/dev/${n%%[0-9]*}
size=$(wc -c < $f)
[ $size -le $(( $(cat /sys/class/block/$n/size) * 512 )) ] || die "image too big"

want=$(md5sum $f | cut -d' ' -f1)
blockdev --setrw $d
blockdev --setrw $p
w=$(dd if=$f of=$p bs=1M conv=fsync 2>&1)
blockdev --flushbufs $p
blockdev --setro $p
echo "$w" | grep -q "^$size bytes" || die "short write: $(echo "$w" | tail -1)"
echo 3 > /proc/sys/vm/drop_caches
got=$(head -c $size $p | md5sum | cut -d' ' -f1)
[ "$got" = "$want" ] || die "verify: wrote $want read $got"
say "OK $size bytes $got, rebooting"
sleep 0.2
rb recovery
