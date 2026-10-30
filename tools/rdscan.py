#!/usr/bin/env python3
"""Find the printk text in a ramdump and save it.  usage: rdscan.py <outdir> <start> <end> [--reset]"""
import re, struct, sys, time, faulthandler, usb.core, usb.util
faulthandler.dump_traceback_later(500, exit=True)
out, start, end = sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3], 0)
d = usb.core.find(idVendor=0x05c6, idProduct=0x900e) or sys.exit('no ramdump device')
d.reset()
time.sleep(1.5)
d = usb.core.find(idVendor=0x05c6, idProduct=0x900e)
intf = d.get_active_configuration()[(0, 0)]
if d.is_kernel_driver_active(0):
    d.detach_kernel_driver(0)
EPI = usb.util.find_descriptor(intf, custom_match=lambda e: e.bEndpointAddress & 0x80)
EPO = usb.util.find_descriptor(intf, custom_match=lambda e: not e.bEndpointAddress & 0x80)
usb.util.claim_interface(d, 0)
EPI.read(0x1000, timeout=3000)
EPO.write(struct.pack('<IIIIII6I', 2, 0x30, 2, 1, 0, 2, 0, 0, 0, 0, 0, 0), timeout=1000)
EPI.read(0x1000, timeout=3000)


def rd(addr, n):
    EPO.write(struct.pack('<IIQQ', 0x11, 0x18, addr, n), timeout=1000)
    c = b''
    while len(c) < n:
        c += bytes(EPI.read((n - len(c) + 511) & ~511, timeout=3000))
    try:
        EPI.read(512, timeout=100)
    except usb.core.USBTimeoutError:
        pass
    return c


NEEDLE = b'AuPad mainline initramfs'
CH = 0x10000
t = time.time()
buf = None
for a in range(start, end, CH):
    c = rd(a, CH)
    p = c.find(NEEDLE)
    if p >= 0:
        print(f'found at {a + p:#x} after {time.time() - t:.0f}s', flush=True)
        lo = (a + p - 0x10000) & ~0xffff
        buf = b''.join(rd(x, CH) for x in range(lo, lo + 0x30000, CH))
        print(f'saved {lo:#x}', flush=True)
        break
    if (a - start) % 0x4000000 == 0:
        print(f'{a:#x} {time.time() - t:.0f}s', flush=True)
if buf:
    open(f'{out}/logbuf.bin', 'wb').write(buf)
    with open(f'{out}/klog.txt', 'w') as f:
        for s in re.findall(rb'[\x20-\x7e\n]{8,}', buf):
            f.write(s.decode() + '\n')
else:
    print('not found')
if '--reset' in sys.argv:
    EPO.write(struct.pack('<II', 0x07, 8), timeout=1000)
    # the device only goes on once its RESET_RSP has been read
    try:
        print('reset:', bytes(EPI.read(0x100, timeout=2000))[:8].hex())
    except usb.core.USBError as e:
        print('reset sent, no reply:', e)
