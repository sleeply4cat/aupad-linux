#!/usr/bin/env python3
"""Capture the nanobridge tablet UART with host timestamps. usage: uartlog.py <log> <seconds>"""
import glob, sys, time, serial

out, secs = sys.argv[1], float(sys.argv[2])
port = serial.Serial(glob.glob('/dev/serial/by-id/usb-Nordic_nanobridge_*-if00')[0], 115200, timeout=0.1)
t0 = time.time()
line = b''
with open(out, 'wb') as f:
    while time.time() - t0 < secs:
        for c in port.read(4096):
            line += bytes([c])
            if c == 10:
                f.write(b'[%8.3f] ' % (time.time() - t0) + line)
                f.flush()
                line = b''
    if line:
        f.write(b'[%8.3f] ' % (time.time() - t0) + line + b'\n')
