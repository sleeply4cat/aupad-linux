#!/usr/bin/env python3
"""Get an idle U-Boot prompt into fastboot.  The first command after a stall often aborts, so repeat until USB shows up."""
import os, subprocess, sys, time, tty

def up():
    return b'18d1:4ee0' in subprocess.check_output(['lsusb'])

f = os.open('/tmp/aupad-uart', os.O_RDWR | os.O_NOCTTY)
tty.setraw(f)
for _ in range(5):
    if up():
        sys.exit(0)
    for c in b'run fastboot\r':
        os.write(f, bytes([c]))
        time.sleep(0.06)
    end = time.time() + 10
    while time.time() < end:
        if up():
            sys.exit(0)
        time.sleep(0.25)
sys.exit(1)
