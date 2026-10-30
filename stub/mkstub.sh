#!/bin/bash
# Glue stub.bin (padded to 64K) + kernel Image into one gzipped "kernel" for ABL,
# then pack it with build/mkboot.sh.   usage: mkstub.sh [out.img]
set -e
HERE=$(dirname "$(readlink -f "$0")")
ROOT=$HERE/..
make -C "$HERE" -s
IMG=${PAYLOAD:-$ROOT/build/out/arch/arm64/boot/Image}
"$ROOT/venv/bin/python" - "$HERE/stub.bin" "$IMG" "$HERE/stub+Image" <<'PY'
import struct, sys
stub = open(sys.argv[1], 'rb').read()
img = open(sys.argv[2], 'rb').read()
assert len(stub) <= 0x10000 and img[0x38:0x3c] == b'ARMd'
ksize = struct.unpack_from('<Q', img, 0x10)[0]
out = bytearray(stub.ljust(0x10000, b'\0') + img)
struct.pack_into('<Q', out, 0x10, 0x10000 + ksize)   # stub header covers payload + its bss
open(sys.argv[3], 'wb').write(out)
PY
# ABL's gzip path never reaches the kernel entry: always ship it uncompressed.
KERNEL=$HERE/stub+Image "$ROOT/build/mkboot.sh" "${1:-$ROOT/build/boot-stub.img}"
