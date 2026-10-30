#!/usr/bin/env python3
"""Read a ramdump (05c6:900e) over raw USB with real timeouts; edl's read path can hang forever.
usage: rdraw.py <outdir> <log_buf offset from _text> <log_buf size> [--reset]    needs an open memory-debug session
Saves the small dump regions listed in <outdir>/table.txt and logbuf.bin, then klog.txt."""
import os, re, struct, sys, time, faulthandler, usb.core, usb.util
faulthandler.dump_traceback_later(200, exit=True)
out, off, size = sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3], 0)
d = usb.core.find(idVendor=0x05c6, idProduct=0x900e) or sys.exit('no ramdump device')
d.reset()       # restarts Sahara with a fresh HELLO, RAM stays as it is
time.sleep(1.5)
d = usb.core.find(idVendor=0x05c6, idProduct=0x900e) or sys.exit('device gone after USB reset')
intf = d.get_active_configuration()[(0, 0)]
if d.is_kernel_driver_active(0):
    d.detach_kernel_driver(0)
EPI = usb.util.find_descriptor(intf, custom_match=lambda e: e.bEndpointAddress & 0x80)
EPO = usb.util.find_descriptor(intf, custom_match=lambda e: not e.bEndpointAddress & 0x80)
usb.util.claim_interface(d, 0)


def drain():
    try:
        while True:
            EPI.read(0x80000, timeout=300)
    except usb.core.USBTimeoutError:
        pass


def rd(addr, length):
    data = b''
    while length:
        n = min(length, 0x10000)
        EPO.write(struct.pack('<IIQQ', 0x11, 0x18, addr + len(data), n), timeout=1000)
        chunk = b''
        # no short packet ends an exact multiple of 512, so ask for no more than will come
        while len(chunk) < n:
            chunk += bytes(EPI.read((n - len(chunk) + 511) & ~511, timeout=3000))
        data += chunk[:n]
        length -= n
        if n % 512 == 0:        # the zero-length packet, or the next command stalls
            try:
                EPI.read(512, timeout=100)
            except usb.core.USBTimeoutError:
                pass
    return data


hello = bytes(EPI.read(0x1000, timeout=3000))
if struct.unpack('<I', hello[:4])[0] != 1:
    sys.exit('no HELLO: ' + hello[:16].hex())
EPO.write(struct.pack('<IIIIII6I', 2, 0x30, 2, 1, 0, 2, 0, 0, 0, 0, 0, 0), timeout=1000)
dbg = bytes(EPI.read(0x1000, timeout=3000))
cmd = struct.unpack('<I', dbg[:4])[0]
if cmd != 0x10:
    sys.exit('no 64-bit memory debug: ' + dbg[:24].hex())
tbl, tlen = struct.unpack('<QQ', dbg[8:24])
raw = rd(tbl, tlen)
with open(f'{out}/table.txt', 'w') as f:
    for i in range(0, len(raw) - 63, 64):
        _, base, ln = struct.unpack('<QQQ', raw[i:i + 24])
        desc = raw[i + 24:i + 44].rstrip(b'\0').decode(errors='replace')
        name = raw[i + 44:i + 64].rstrip(b'\0').decode(errors='replace')
        f.write(f'{base:#012x} {ln:#012x} {name} {desc}\n')
for base in (0x40000000, 0x40080000, 0x40200000):
    data = rd(base + off, size)
    if b'Linux version' in data:
        print(f'log_buf at {base + off:#x}', flush=True)
        open(f'{out}/logbuf.bin', 'wb').write(data)
        with open(f'{out}/klog.txt', 'w') as f:
            for s in re.findall(rb'[\x20-\x7e\n]{8,}', data):
                f.write(s.decode() + '\n')
        break
else:
    print('no log_buf found')
for line in open(f'{out}/table.txt', errors='ignore'):
    m = re.match(r'(0x[0-9a-f]+) (0x[0-9a-f]+) (\S+)', line)
    # hardware regions (DCC, IPA, RPM) can stall the session, so only the status blocks in DDR
    if not m or m[3].split('.')[0] not in ('PMIC_PON', 'PMON_HIS', 'RST_STAT', 'FSM_STS', 'FSM_CTRL', 'CD_STRCT'):
        continue
    try:
        open(f'{out}/{m[3]}', 'wb').write(rd(int(m[1], 16), int(m[2], 16)))
        print('saved', m[3], flush=True)
    except usb.core.USBError as e:
        print('failed', m[3], e, flush=True)
        drain()
if '--reset' in sys.argv:
    EPO.write(struct.pack('<II', 0x07, 8), timeout=1000)
    print('reset sent')
