#!/bin/sh
# Put back misc's original 32-byte command field, so ABL boots Android again.
for i in $(seq 40); do ls /sys/class/block | grep -q '^sd[a-z][0-9]' && break; sleep 0.5; done
u=$(grep -l '^PARTNAME=misc$' /sys/class/block/sd*/uevent)
[ "$(echo "$u" | wc -l)" = 1 ] || { echo "misc not unique: $u"; exit 1; }
n=$(basename $(dirname $u)); p=/dev/$n
echo "misc is $p, command was: $(head -c 32 $p | tr -d '\000')"
dd if=/bin/misc.head of=$p bs=32 count=1 conv=fsync,notrunc 2>&1 | tail -1
blockdev --flushbufs $p
echo 3 > /proc/sys/vm/drop_caches
[ "$(head -c 32 $p | md5sum | cut -d' ' -f1)" = "$(md5sum /bin/misc.head | cut -d' ' -f1)" ] && echo "BCB RESTORED" || echo "BCB RESTORE FAILED"
