#!/usr/bin/env python3
"""Drive the tablet through its boot states, checking each step.  Run with venv/bin/python.

  tab.py state             what the tablet is doing now
  tab.py fastboot          get to U-Boot fastboot from any state (pmOS, U-Boot prompt, ramdump, booting)
  tab.py ramboot IMG       fastboot, then "fastboot boot IMG"; with a stub image, waits for "jumping to kernel"
         [--attach N [--ocd CMD]...]
                           stub images with -DSTUB_EUD: hold the stub (eudlog paused, so no hello), attach OpenOCD to
                           Kryo core N, run each CMD (fails on any OpenOCD error), then let the stub go.  Test images
                           chained from a U-Boot without the dwc3 fix need -DSTUB_USB_OFF too.
  tab.py boot              from fastboot or a U-Boot prompt, run bootcmd and wait for pmOS
  tab.py pmos              wait until pmOS answers ssh

Needs uartd (the UART as /tmp/aupad-uart).  Exits 1 with the reason when a step fails, never leaves a half-typed
U-Boot command behind.  A ramdump (05c6:900e) is captured by uartd; this waits until it is done.
"""
import os
import select
import subprocess
import sys
import time

import usb.core

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UART = "/tmp/aupad-uart"
SSH = ["ssh", "-q", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "BatchMode=yes",
       "-o", "ConnectTimeout=3", "root@172.16.42.1"]
FASTBOOT, PMOS, RAMDUMP, CHARGER, EUD_HUB = (0x18D1, 0x4EE0), (0x18D1, 0xD001), (0x05C6, 0x900E), (0x05C6, 0xF000), \
    (0x05C6, 0x9500)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def fail(msg):
    log("FAIL: " + msg)
    sys.exit(1)


def present(ids):
    return usb.core.find(idVendor=ids[0], idProduct=ids[1]) is not None


def ssh_ok():
    return subprocess.run(SSH + ["true"], capture_output=True, timeout=10).returncode == 0


def fastboot_ok():
    r = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=5)
    return bool(r.stdout.strip())


class Uart:
    """The UART through uartd.  Keeps everything read, so a wait only matches text that arrived after it began."""

    def __init__(self):
        if not os.path.exists(UART):
            fail("no /tmp/aupad-uart: start tools/uartd.py")
        self.fd = os.open(UART, os.O_RDWR | os.O_NOCTTY)
        self.buf = b""
        self.drain(0.3)
        self.mark = len(self.buf)

    def drain(self, t):
        end = time.time() + t
        while time.time() < end:
            if select.select([self.fd], [], [], 0.05)[0]:
                self.buf += os.read(self.fd, 65536)

    def since(self):
        return self.buf[self.mark:]

    def wait(self, *texts, timeout):
        """Wait for the texts in order, after the mark; move the mark past the last one.  Returns success."""
        end = time.time() + timeout
        while True:
            pos = self.mark
            for t in texts:
                i = self.buf.find(t, pos)
                if i < 0:
                    break
                pos = i + len(t)
            else:
                self.mark = pos
                return True
            if time.time() >= end:
                return False
            if select.select([self.fd], [], [], 0.05)[0]:
                self.buf += os.read(self.fd, 65536)

    def type(self, text):
        # U-Boot drops characters that arrive too fast
        for c in text.encode():
            os.write(self.fd, bytes([c]))
            time.sleep(0.12)


def state():
    if fastboot_ok():
        return "fastboot"
    if present(RAMDUMP):
        return "ramdump"
    if present(CHARGER):
        return "charger"
    if present(PMOS) and ssh_ok():
        return "pmos"
    # Only reached when nothing else answers: a CR at a Linux console or during boot is harmless
    u = Uart()
    u.type("\r")
    if u.wait(b"=> ", timeout=2):
        return "uboot"
    return "other"


def wait_ramdump_done():
    log("ramdump: waiting for uartd to capture it")
    end = time.time() + 900
    while present(RAMDUMP):
        if time.time() > end:
            fail("still in ramdump after 15 min")
        time.sleep(2)
    log("ramdump done")


def uboot_fastboot(u):
    """At a U-Boot prompt: start fastboot and check that it enumerates; retry a few times."""
    for attempt in range(3):
        u.type("run fastboot\r")
        end = time.time() + 8
        while time.time() < end:
            if fastboot_ok():
                log(f"fastboot up (attempt {attempt + 1})")
                return
            time.sleep(0.5)
        # Any character aborts fastboot; wait for the prompt before trying again
        log(f"fastboot didn't enumerate (attempt {attempt + 1}), aborting it")
        u.mark = len(u.buf)
        u.type(" ")
        if not u.wait(b"=> ", timeout=5):
            fail("no U-Boot prompt after aborting fastboot")
    fail("fastboot never enumerated")


def catch_uboot(u, timeout):
    """Wait for U-Boot's banner and countdown on the UART, stop autoboot, wait for the prompt."""
    if not u.wait(b"U-Boot 20", b"stop autoboot", timeout=timeout):
        fail("no U-Boot countdown on the UART")
    u.type(" ")
    if not u.wait(b"=> ", timeout=5):
        fail("autoboot not stopped")
    log("at U-Boot prompt")


def to_fastboot():
    s = state()
    log(f"state: {s}")
    if s == "fastboot":
        return
    if s == "charger":
        fail("off-mode charging: press power")
    if s == "ramdump":
        wait_ramdump_done()
        s = "other"
    u = Uart()
    if s == "pmos":
        subprocess.run(SSH + ["reboot"], capture_output=True, timeout=15)
        log("rebooting pmOS")
        catch_uboot(u, 90)
    elif s != "uboot":
        log("waiting for a boot through U-Boot")
        catch_uboot(u, 120)
    uboot_fastboot(u)


PAUSE = "/tmp/aupad-eud-pause"


def attach(core, cmds):
    for _ in range(60):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools/ocd/up"), "--core", str(core)],
                           capture_output=True, text=True, timeout=180)
        if r.returncode == 0:
            break
        time.sleep(1)
    else:
        fail("OpenOCD: " + (r.stdout + r.stderr).strip().splitlines()[-1])
    log("OpenOCD: " + r.stdout.strip())
    # Before Linux only the boot core runs: breakpoints for the SMP group would fail on the others
    for c in ["aarch64 smp off", *cmds]:
        out = subprocess.run([os.path.join(ROOT, "tools/ocd/oc"), f"targets cpu{core}", c], capture_output=True,
                             text=True, timeout=30).stdout
        if "ERROR" in out or "rror" in out:
            fail(f"OpenOCD '{c}': {out.strip()}")
        log(f"ocd> {c}  {out.strip()}")


def ramboot(img, core=None, cmds=()):
    if not os.path.exists(img):
        fail(f"no {img}")
    to_fastboot()
    u = Uart()
    if core is not None:
        open(PAUSE, "w").close()
    try:
        r = subprocess.run(["fastboot", "boot", img], capture_output=True, text=True, timeout=60)
        if r.returncode:
            fail("fastboot boot: " + r.stderr.strip().splitlines()[-1])
        log(f"sent {os.path.basename(img)}")
        if core is not None:
            if not u.wait(b"EUD en", timeout=30):
                fail("stub didn't enable EUD (built without -DSTUB_EUD?)")
            attach(core, cmds)
    finally:
        if os.path.exists(PAUSE):
            os.unlink(PAUSE)
    # Stub images print this when they hand over; a hold for the EUD host can take up to STUB_EUD seconds
    if u.wait(b"jumping to kernel", timeout=90):
        log("stub jumped")
    else:
        log("no 'jumping to kernel' on the UART (not a stub image?)")


def boot():
    s = state()
    log(f"state: {s}")
    if s == "pmos":
        return
    u = Uart()
    if s == "fastboot":
        # Any character aborts fastboot
        u.type(" ")
        if not u.wait(b"=> ", timeout=5):
            fail("no U-Boot prompt after leaving fastboot")
    elif s != "uboot":
        fail(f"not at U-Boot ({s})")
    u.type("run bootcmd\r")
    wait_pmos()


def wait_pmos():
    end = time.time() + 300
    while time.time() < end:
        if present(RAMDUMP):
            wait_ramdump_done()
        if ssh_ok():
            log("pmOS up")
            return
        time.sleep(2)
    fail("pmOS didn't come up in 5 min")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "state":
        print(state())
    elif cmd == "fastboot":
        to_fastboot()
    elif cmd == "ramboot" and len(sys.argv) >= 3:
        a = sys.argv[3:]
        core = int(a[a.index("--attach") + 1]) if "--attach" in a else None
        cmds = [a[i + 1] for i, x in enumerate(a) if x == "--ocd"]
        ramboot(sys.argv[2], core, cmds)
    elif cmd == "boot":
        boot()
    elif cmd == "pmos":
        wait_pmos()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
