#!/usr/bin/env python3
"""Record the kernel log from EUD COM, across reboots: eudlog.py   Run with venv/bin/python, leave it running.
Needs a stub built with -DSTUB_EUD and earlycon=qcom_eud,0x1610000 keep_bootcon on the kernel command line
(drop keep_bootcon if you boot with console=ttyEUD0: two writers on one FIFO).
Prints what arrives and appends it to logs/eud/<date>.log with the host's time; --raw also dumps every
unparsed transfer to <date>.raw.  Records that don't parse are counted, reported in passing and skipped,
never fed to the console.
Offers the console to other tools as a pty at /tmp/aupad-eud: what they write goes to the tablet as COM packets,
one at a time, each after the tablet acknowledged the last (an ID 0x91 packet, from the ttyEUD driver).
On connect it sends a hello, an ID 0x91 packet: a stub built with -DSTUB_EUD waits for it before going on.
While /tmp/aupad-eud-pause exists it lets go of the device, for scripts that drive 9505 themselves."""
import atexit
import codecs
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
FIFO, RECORD = 14, 16
ID, ACK_ID, HELLO_BYTE, ACK_BYTE = 0x90, 0x91, 0x05, 0x06
# Past this much unacknowledged input stop reading the pty, so a writing client waits
TX_HIGH_WATER = 64 * 1024
# A NOP realigns the endpoint's data toggle; one that still fails after ~1 s of that means
# the device is gone or wedged, which is the reconnect loop's business, not ours
RESYNC_TRIES, RESYNC_SLEEP = 100, 0.01
# COM peripheral commands from github.com/quic/eud (com_eud.h).  A packet nobody reads within RX_TMOUT
# (little-endian ms) is dropped and leaves RX dead until PORT_RESET.  0xffff stops RX events altogether.
COM_CMD_NOP, COM_CMD_RX_TMOUT, COM_CMD_PORT_RESET = 0, 2, 3
RX_TMOUT_MS = 0xFFFE
RAW = "--raw" in sys.argv


class Console:
    """The pty other tools see at LINK.  With no client the master shows POLLHUP and nothing
    is queued for a later one."""

    def __init__(self):
        master, slave = pty.openpty()
        tty.setraw(slave)
        os.set_blocking(master, False)
        if os.path.lexists(LINK):
            os.unlink(LINK)
        os.symlink(os.ttyname(slave), LINK)
        os.close(slave)
        self.master, self.hup = master, select.poll()
        self.hup.register(master, select.POLLIN)

    def client(self):
        return not any(ev & select.POLLHUP for _, ev in self.hup.poll(0))

    def read(self):
        return os.read(self.master, 4096)    # raises until there is input: pump suppresses

    def write(self, text):
        if self.client():
            with contextlib.suppress(BlockingIOError, OSError):
                os.write(self.master, text.encode())


console = None    # the Console, once main() has made one


def out(log, text):
    if console:
        console.write(text)
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

    def __init__(self, dev, read_input):
        self.dev, self.read_input, self.buf, self.sent = dev, read_input, b"", None
        self.reset()

    def reset(self):
        self.command(bytes([COM_CMD_PORT_RESET]))
        self.command(bytes([COM_CMD_RX_TMOUT]) + struct.pack("<I", RX_TMOUT_MS))
        self.dev.write(0x02, bytes([ACK_ID, 1, HELLO_BYTE]), timeout=1000)    # the hello a stub waits for
        self.sent = time.monotonic()

    def command(self, pkt):
        self.dev.write(0x02, pkt, timeout=1000)

    def resync(self):
        # After a failed transfer the endpoint's data toggle can be off by one: a NOP realigns it
        # whether the device takes it or drops it as a repeat.  A device that keeps failing has
        # gone or wedged: let go of it and let the outer loop rediscover it.
        for _ in range(RESYNC_TRIES):
            try:
                self.dev.clear_halt(0x02)
                self.command(bytes([COM_CMD_NOP]))
                return
            except (usb.core.USBTimeoutError, usb.core.NoDeviceError):
                raise
            except usb.core.USBError:
                time.sleep(RESYNC_SLEEP)
        usb.util.dispose_resources(self.dev)
        raise usb.core.USBError(f"endpoint 0x02 still failing after {RESYNC_TRIES} NOPs")

    def pump(self):
        # Backpressure: past the high-water mark leave the input where it is, so a writing client waits
        if len(self.buf) < TX_HIGH_WATER:
            with contextlib.suppress(BlockingIOError, OSError):
                self.buf += self.read_input()
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
        except (usb.core.USBTimeoutError, usb.core.NoDeviceError):
            raise
        except usb.core.USBError:
            self.resync()
            return
        self.buf, self.sent = self.buf[FIFO:], time.monotonic()

    def ack(self):
        self.sent = None


class Rx:
    """What the tablet sends: transfers of 16-byte records, each [ID, length, up to 14 bytes], only
    the last record of a transfer short.  A length past 14 or past the end of the transfer, an unknown
    ID, or an ACK that isn't exactly [0x91, 1, 0x06] counts as malformed and is skipped: a garbled
    record must not leak padding into the log or free a packet the tablet hasn't read yet.  UTF-8 is
    decoded incrementally, so a character split across packets survives."""

    def __init__(self):
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.text, self.acks, self.malformed = "", 0, 0

    def feed(self, data):
        for i in range(0, len(data) - 1, RECORD):
            length = data[i + 1]
            if length > FIFO or i + 2 + length > len(data):
                self.malformed += 1
            elif data[i] == ID:
                self.text += self.decoder.decode(data[i + 2:i + 2 + length])
            elif data[i] == ACK_ID and length == 1 and data[i + 2] == ACK_BYTE:
                self.acks += 1
            else:
                self.malformed += 1


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


def stream(dev, log, raw):
    dev.set_configuration()
    tx = Tx(dev, console.read)
    rx = Rx()
    bad = 0
    while not os.path.exists(PAUSE):
        tx.pump()
        try:
            data = bytes(dev.read(0x81, 16384, timeout=20))
        except usb.core.USBTimeoutError:
            continue
        if raw:
            raw.write(data)
        rx.feed(data)
        if rx.text:
            out(log, rx.text)
            rx.text = ""
        if rx.acks:
            tx.ack()
            rx.acks = 0
        if rx.malformed > bad:
            if rx.malformed <= 10 or rx.malformed % 100 == 0:
                out(log, f"=== eudlog: {rx.malformed} malformed COM records\n")
            bad = rx.malformed


def main():
    global console
    console = Console()
    atexit.register(lambda: os.path.lexists(LINK) and os.unlink(LINK))
    os.makedirs(LOGS, exist_ok=True)
    while True:
        with open(os.path.join(LOGS, time.strftime("%Y%m%d.log")), "a") as f:
            raw = open(os.path.join(LOGS, time.strftime("%Y%m%d.raw")), "ab") if RAW else None
            try:
                dev = None
                try:
                    dev = behind_hub(COM)
                    if os.path.exists(PAUSE):
                        time.sleep(0.2)
                        continue
                    if dev:
                        out(f, "=== eudlog: connected\n")
                        stream(dev, f, raw)
                        usb.util.dispose_resources(dev)
                        out(f, "=== eudlog: paused\n")
                    elif not enable():
                        time.sleep(0.05)
                        continue
                    time.sleep(0.05)
                except (usb.core.USBError, ValueError):
                    # Whatever broke, don't hold the device: back to discovery
                    if dev:
                        with contextlib.suppress(usb.core.USBError):
                            usb.util.dispose_resources(dev)
                    out(f, "\n=== eudlog: lost the device\n")
                    time.sleep(0.2)
            finally:
                if raw:
                    raw.close()


if __name__ == "__main__":
    main()
