#!/bin/bash
# Stage 1 rootfs: Alpine minirootfs plus a signed package cache.  Scripts can't run on this host (no root,
# no user namespaces), so the tablet finishes the install itself with test=stage2.  usage: mkrootfs.sh [out.img]
set -e
cd "$(dirname "$0")/pmos"
OUT=${1:-$PWD/rootfs.img}
PKGS="postmarketos-base openssh e2fsprogs-extra"
APK="dl/sbin/apk.static --arch aarch64 --keys-dir $PWD/keys --repositories-file $PWD/repos --cache-dir $PWD/cache"

rm -rf probe modroot; mkdir -p probe/etc/apk cache
make -C ../../linux O=../build/out ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- INSTALL_MOD_PATH=$PWD/modroot INSTALL_MOD_STRIP=1 modules_install >/dev/null
rm -f modroot/lib/modules/*/build modroot/lib/modules/*/source
fakeroot $APK --root $PWD/probe --initdb --no-scripts --no-chown add $PKGS | tail -1
rm -rf probe

cat > mk.fr <<F
set -e
rm -rf root; mkdir root
tar -xzpf dl/alpine-minirootfs-*-aarch64.tar.gz -C root
cp keys/*.pub root/etc/apk/keys/
cp repos root/etc/apk/repositories
mkdir -p root/var/cache/apk
ln -sf /var/cache/apk root/etc/apk/cache
cp cache/* root/var/cache/apk/
echo "$PKGS" > root/etc/stage2-packages
cp deviceinfo root/etc/deviceinfo
cp aupad-modprobe.conf root/etc/modprobe.d/aupad.conf
mkdir -p root/boot
cp ../boot-pmos.img root/boot/boot.img
mkdir -p root/lib/modules
cp -a modroot/lib/modules/* root/lib/modules/
cp ../tests/rx ../tests/rb root/usr/sbin/
cp ../tests/flash.sh root/usr/sbin/flash
mkdir -p root/lib/firmware/qcom
cp ../../firmware/a630_sqe.fw ../../firmware/a610_zap.mdt ../../firmware/a610_zap.b0? root/lib/firmware/qcom/
rm -f "$OUT"
/usr/sbin/mkfs.ext4 -q -b 4096 -L pmos -d root "$OUT" 1G
F
fakeroot sh mk.fr
rm -rf root mk.fr modroot
/usr/sbin/e2fsck -fn "$OUT" | tail -1
ls -l "$OUT"; md5sum "$OUT"
