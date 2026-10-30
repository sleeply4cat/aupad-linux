#!/usr/bin/env python3
"""Stop U-Boot's autoboot, run commands one by one, then boot on.  usage: ubcmd.py <seconds> <cmd>..."""
import glob, sys, time, serial

port = serial.Serial((glob.glob('/tmp/aupad-uart') or glob.glob('/dev/serial/by-id/usb-Nordic_nanobridge_*-if00'))[0], 115200, timeout=0.05)
end = time.time() + float(sys.argv[1])
seen = b''
while b'=> ' not in seen[-64:]:
    if time.time() > end:
        sys.exit('no prompt')
    port.write(b' ')
    seen += port.read(4096)
port.write(b'\x15')
for c in sys.argv[2:]:
    port.write(c.encode() + b'\r')
    seen = b''
    t = time.time() + 3
    while b'=> ' not in seen and time.time() < t:
        seen += port.read(4096)
    print(seen.decode(errors='replace').replace('\r', ''), end='')
port.write(b'boot\r')
