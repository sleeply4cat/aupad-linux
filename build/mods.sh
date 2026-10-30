#!/bin/bash
# Install this build's stripped kernel modules on running pmOS.  Run before kup.sh, same build.
set -e
cd "$(dirname "$0")/.."
N=172.16.42.1
SSHO="-q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o ConnectTimeout=4"
ST=$PWD/build/pmos/modroot
rm -rf "$ST"
make -C linux O=../build/out ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- INSTALL_MOD_PATH="$ST" INSTALL_MOD_STRIP=1 modules_install >/dev/null
rm -f "$ST"/lib/modules/*/build "$ST"/lib/modules/*/source
du -sh "$ST"
tar -C "$ST" -cz lib | ssh $SSHO root@$N 'rm -rf /lib/modules/*; tar -xz -C / && sync'
ssh $SSHO root@$N 'ls /lib/modules; du -sh /lib/modules/*'
rm -rf "$ST"
