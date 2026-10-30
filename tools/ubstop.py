#!/usr/bin/env python3
"""Stop U-Boot's autoboot over the UART and start fastboot.  usage: ubstop.py [seconds]"""
import glob, sys, time, serial

port = serial.Serial(glob.glob('/dev/serial/by-id/usb-Nordic_nanobridge_*-if00')[0], 115200, timeout=0.05)
end = time.time() + float(sys.argv[1] if len(sys.argv) > 1 else 40)
seen = b''
while time.time() < end:
    port.write(b' ')
    seen = (seen + port.read(4096))[-64:]
    if b'=> ' in seen:
        port.write(b'\x15run fastboot\r')
        sys.exit(0)
sys.exit(1)
