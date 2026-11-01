#!/usr/bin/env python3
"""Record the kernel log from EUD COM, across reboots: eudlog.py   Run with venv/bin/python, leave it running.
Needs a stub built with -DSTUB_EUD and earlycon=qcom_eud,0x1610000 keep_bootcon on the kernel command line.
Prints what arrives and appends it to logs/eud/<date>.log with the host's time."""
import contextlib
import os
import struct
import sys
import time

import usb.core
import usb.util

VID, HUB, CTL, COM = 0x05C6, 0x9500, 0x9501, 0x9505
CTLOUT_SET, COM_EN = 7, 1 << 5
LOGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "eud")


def behind_hub(pid):
    # Other devices on this host reuse 05c6:9501
    return usb.core.find(idVendor=VID, idProduct=pid, custom_match=lambda d: d.parent and d.parent.idProduct == HUB)


def enable():
    ctl = behind_hub(CTL)
    if not ctl:
        return False
    with contextlib.suppress(usb.core.USBError):
        ctl.set_configuration()
    ctl.write(0x02, bytes([CTLOUT_SET]) + struct.pack("<I", COM_EN), timeout=1000)
    usb.util.dispose_resources(ctl)
    return True


def out(log, text):
    sys.stdout.write(text)
    sys.stdout.flush()
    for line in text.splitlines(keepends=True):
        log.write(time.strftime("[%H:%M:%S] ") + line if out.fresh else line)
        out.fresh = line.endswith("\n")
    log.flush()


out.fresh = True


def stream(dev, log):
    dev.set_configuration()
    while True:
        try:
            data = bytes(dev.read(0x81, 16384, timeout=500))
        except usb.core.USBTimeoutError:
            continue
        # 16-byte packets: ID 0x90, length, up to 14 bytes
        for i in range(0, len(data) - 1, 16):
            if data[i] == 0x90:
                out(log, data[i + 2:i + 2 + data[i + 1]].decode(errors="replace"))


os.makedirs(LOGS, exist_ok=True)
while True:
    with open(os.path.join(LOGS, time.strftime("%Y%m%d.log")), "a") as f:
        try:
            dev = behind_hub(COM)
            if dev:
                out(f, "=== eudlog: connected\n")
                stream(dev, f)
            elif not enable():
                time.sleep(0.05)
                continue
            time.sleep(0.05)
        except (usb.core.USBError, ValueError):
            out(f, "\n=== eudlog: lost the device\n")
            time.sleep(0.2)
