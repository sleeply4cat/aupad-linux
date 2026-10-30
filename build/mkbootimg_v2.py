#!/usr/bin/env python3
"""Minimal Android boot image header v2 packer (kernel + ramdisk + dtb)."""
import argparse, hashlib, struct

p = argparse.ArgumentParser()
p.add_argument('--kernel', required=True)
p.add_argument('--ramdisk', required=True)
p.add_argument('--dtb', required=True)
p.add_argument('--cmdline', default='')
p.add_argument('--base', type=lambda x: int(x, 0), default=0)
p.add_argument('--kernel_offset', type=lambda x: int(x, 0), default=0x8000)
p.add_argument('--ramdisk_offset', type=lambda x: int(x, 0), default=0x1000000)
p.add_argument('--tags_offset', type=lambda x: int(x, 0), default=0x100)
p.add_argument('--dtb_offset', type=lambda x: int(x, 0), default=0x1f00000)
p.add_argument('--pagesize', type=int, default=4096)
p.add_argument('--os_version', default='15.0.0')
p.add_argument('--os_patch_level', default='2025-05')
p.add_argument('-o', '--output', required=True)
a = p.parse_args()

kernel, ramdisk, dtb = (open(f, 'rb').read() for f in (a.kernel, a.ramdisk, a.dtb))
x, y, z = (int(v) for v in a.os_version.split('.'))
yy, mm = (int(v) for v in a.os_patch_level.split('-'))
os_version = (x << 25) | (y << 18) | (z << 11) | ((yy - 2000) << 4) | mm

cmd = a.cmdline.encode()
assert len(cmd) < 512 + 1024, 'cmdline too long'
cmd_main, cmd_extra = cmd[:511], cmd[511:]

sha = hashlib.sha1()
for blob in (kernel, ramdisk, b'', b'', dtb):   # kernel, ramdisk, second, recovery_dtbo, dtb
    sha.update(blob)
    sha.update(struct.pack('<I', len(blob)))

HDR_SIZE = 1660
hdr = b'ANDROID!'
hdr += struct.pack('<10I', len(kernel), a.base + a.kernel_offset, len(ramdisk),
                   a.base + a.ramdisk_offset, 0, 0, a.base + a.tags_offset,
                   a.pagesize, 2, os_version)
hdr += b'\0' * 16                                   # name
hdr += cmd_main.ljust(512, b'\0')
hdr += sha.digest().ljust(32, b'\0')
hdr += cmd_extra.ljust(1024, b'\0')
hdr += struct.pack('<IQI', 0, 0, HDR_SIZE)          # recovery dtbo size/offset, header size
hdr += struct.pack('<IQ', len(dtb), a.base + a.dtb_offset)
assert len(hdr) == HDR_SIZE, len(hdr)

def pad(b):
    return b + b'\0' * (-len(b) % a.pagesize)

with open(a.output, 'wb') as f:
    for blob in (hdr, kernel, ramdisk, dtb):
        f.write(pad(blob))
