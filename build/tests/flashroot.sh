#!/bin/sh
# flashroot <rootfs.img>: write an ext4 image to the pmos partition and verify it.  Writes nothing else.
say() { echo "FLASH $*" > /dev/kmsg; }
die() { say "FAILED: $*"; exit 1; }

f=$1
u=$(grep -l '^PARTNAME=pmos$' /sys/class/block/sd*/uevent) || die "no pmos partition"
[ "$(echo "$u" | wc -l)" = 1 ] || die "several pmos partitions"
n=$(basename $(dirname $u))
p=/dev/$n
d=/dev/${n%%[0-9]*}
grep -q "^$p " /proc/mounts && die "$p is mounted"
size=$(wc -c < $f)
[ $size -le $(( $(cat /sys/class/block/$n/size) * 512 )) ] || die "image too big"
want=$(md5sum $f | cut -d' ' -f1)
blockdev --setrw $d
blockdev --setrw $p
w=$(dd if=$f of=$p bs=1M conv=fsync 2>&1)
blockdev --flushbufs $p
echo "$w" | grep -q "^$size bytes" || die "short write: $(echo "$w" | tail -1)"
echo 3 > /proc/sys/vm/drop_caches
got=$(head -c $size $p | md5sum | cut -d' ' -f1)
[ "$got" = "$want" ] || die "verify: wrote $want read $got"
say "ROOT OK $size bytes $got on $p"
