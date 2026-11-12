#!/usr/bin/env python3
"""Stop U-Boot's autoboot over the EUD COM pty and start fastboot.  usage: ubstop.py [seconds]
tools/eudlog.py must be running, it creates /tmp/aupad-eud."""
import sys, time, serial

try:
	port = serial.Serial('/tmp/aupad-eud', 115200, timeout=0.05)
except serial.SerialException as e:
	sys.exit(f'{e}\nno /tmp/aupad-eud: is tools/eudlog.py running?')
end = time.time() + float(sys.argv[1] if len(sys.argv) > 1 else 40)
seen = b''
while time.time() < end:
    port.write(b' ')
    time.sleep(0.25)   # the link queues: a flood reaches U-Boot late and aborts fastboot
    seen = (seen + port.read(4096))[-64:]
    if b'=> ' in seen:
        port.write(b'\x15run fastboot\r')
        sys.exit(0)
sys.exit(1)
