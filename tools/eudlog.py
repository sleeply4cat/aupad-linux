#!/usr/bin/env python3
"""Record the kernel log from EUD COM, across reboots: eudlog.py   Run with venv/bin/python, leave it running.
Needs a stub built with -DSTUB_EUD and earlycon=qcom_eud,0x1610000 keep_bootcon on the kernel command line.
Prints what arrives and appends it to logs/eud/<date>.log with the host's time.
Offers the console to other tools as a pty at /tmp/aupad-eud: what they write goes to the tablet as COM packets,
one at a time, each after the tablet acknowledged the last (an ID 0x91 packet, from the ttyEUD driver).
On connect it sends a hello, an ID 0x91 packet: a stub built with -DSTUB_EUD waits for it before going on.
While /tmp/aupad-eud-pause exists it lets go of the device, for scripts that drive 9505 themselves."""
import atexit
import contextlib
import os
import pty
import select
import struct
import sys
import time
import tty

import usb.core
import usb.util

VID, HUB, CTL, COM = 0x05C6, 0x9500, 0x9501, 0x9505
CTLOUT_SET, COM_EN = 7, 1 << 5
LOGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "eud")
LINK = "/tmp/aupad-eud"
PAUSE = "/tmp/aupad-eud-pause"
FIFO = 14
ID, ACK_ID = 0x90, 0x91
# COM peripheral commands from github.com/quic/eud (com_eud.h).  A packet nobody reads within RX_TMOUT
# (little-endian ms) is dropped and leaves RX dead until PORT_RESET.  0xffff stops RX events altogether.
COM_CMD_NOP, COM_CMD_RX_TMOUT, COM_CMD_PORT_RESET = 0, 2, 3
RX_TMOUT_MS = 0xFFFE

master, slave = pty.openpty()
tty.setraw(slave)
os.set_blocking(master, False)
name = os.ttyname(slave)
os.close(slave)      # with no client the master shows POLLHUP and nothing is queued for a later one
if os.path.lexists(LINK):
    os.unlink(LINK)
os.symlink(name, LINK)
atexit.register(lambda: os.path.lexists(LINK) and os.unlink(LINK))
hup = select.poll()
hup.register(master, select.POLLIN)


def client():
    return not any(ev & select.POLLHUP for _, ev in hup.poll(0))


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
    if client():
        with contextlib.suppress(BlockingIOError):
            os.write(master, text.encode())
    sys.stdout.write(text)
    sys.stdout.flush()
    for line in text.splitlines(keepends=True):
        log.write(time.strftime("[%H:%M:%S] ") + line if out.fresh else line)
        out.fresh = line.endswith("\n")
    log.flush()


out.fresh = True


class Tx:
    """Input waiting for the tablet.  Only one packet may be pending there: a transfer that hits a pending
    packet fails, and one that collides with the tablet reading it can shorten or drop it."""

    def __init__(self, dev):
        self.dev, self.buf, self.sent = dev, b"", None
        self.reset()

    def reset(self):
        self.command(bytes([COM_CMD_PORT_RESET]))
        self.command(bytes([COM_CMD_RX_TMOUT]) + struct.pack("<I", RX_TMOUT_MS))
        self.dev.write(0x02, bytes([ACK_ID, 1, 0x05]), timeout=1000)
        self.sent = time.monotonic()

    def command(self, pkt):
        self.dev.write(0x02, pkt, timeout=1000)

    def resync(self):
        # After a failed transfer the endpoint's data toggle can be off by one: a NOP realigns it
        # whether the device takes it or drops it as a repeat
        while True:
            self.dev.clear_halt(0x02)
            try:
                self.command(bytes([COM_CMD_NOP]))
                return
            except usb.core.USBTimeoutError:
                raise
            except usb.core.USBError:
                time.sleep(0.001)

    def pump(self):
        if client():
            with contextlib.suppress(BlockingIOError, OSError):
                self.buf += os.read(master, 4096)
        if self.sent is not None:
            if time.monotonic() - self.sent < RX_TMOUT_MS / 1000 + 1:
                return
            # Nobody read it in time: the tablet dropped it and RX is dead until a reset
            self.reset()
            return
        if not self.buf:
            return
        chunk = self.buf[:FIFO]
        try:
            self.dev.write(0x02, bytes([ID, len(chunk)]) + chunk, timeout=1000)
        except usb.core.USBTimeoutError:
            raise
        except usb.core.USBError:
            self.resync()
            return
        self.buf, self.sent = self.buf[FIFO:], time.monotonic()

    def ack(self):
        self.sent = None


def stream(dev, log):
    dev.set_configuration()
    tx = Tx(dev)
    while not os.path.exists(PAUSE):
        tx.pump()
        try:
            data = bytes(dev.read(0x81, 16384, timeout=20))
        except usb.core.USBTimeoutError:
            continue
        # Packets of ID, length, up to 14 bytes; only the last one of a transfer is short
        for i in range(0, len(data) - 1, 16):
            if data[i] == ID:
                out(log, data[i + 2:i + 2 + data[i + 1]].decode(errors="replace"))
            elif data[i] == ACK_ID:
                tx.ack()


os.makedirs(LOGS, exist_ok=True)
while True:
    with open(os.path.join(LOGS, time.strftime("%Y%m%d.log")), "a") as f:
        try:
            dev = behind_hub(COM)
            if os.path.exists(PAUSE):
                time.sleep(0.2)
                continue
            if dev:
                out(f, "=== eudlog: connected\n")
                stream(dev, f)
                usb.util.dispose_resources(dev)
                out(f, "=== eudlog: paused\n")
            elif not enable():
                time.sleep(0.05)
                continue
            time.sleep(0.05)
        except (usb.core.USBError, ValueError):
            out(f, "\n=== eudlog: lost the device\n")
            time.sleep(0.2)
