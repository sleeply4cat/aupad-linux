#!/usr/bin/env python3
"""Reboot until the RPM enters its abort path, stop it there and dump everything.  hunt.py [cycles] [--here] [--fire]

Each boot: connect OpenOCD, arm hardware breakpoints on the IRQ 12 handler and the abort routine, and watch.  A hit
leaves the RPM halted at the fault, writes logs/hang/<time>/ and stops with the server still running, so GDB or
tools/ocd/oc can carry on from there.  A boot that survives AFTER_KERNEL seconds is rebooted over the UART.

--here   use the current boot, don't reboot first
--fire   rehearsal: pend IRQ 12 by hand once armed, as if the fault had happened
--release  dump the RPM only, resume into the abort, sample the Kryo cores from there and time the reset
Needs a boot-eud image.  Run with venv/bin/python.
"""
import contextlib
import glob
import os
import re
import socket
import subprocess
import sys
import time

import serial
import usb.core

VID = 0x05C6
HUB, CTL = 0x9500, 0x9501
AFTER_KERNEL = 45       # seconds after kernel start that a boot is watched
IRQ12, ABORT = 0x21EA2, 0x21B60     # rpm_b specific
STACKED = 0x90000, 0x14000          # RPM data RAM
RPM_REGS = "r0 r1 r2 r3 r4 r5 r6 r7 r8 r9 r10 r11 r12 sp lr pc xpsr msp psp primask basepri faultmask control"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
LOGS = os.path.join(ROOT, "logs", "hang")
SCB = {"ICSR": 0xE000ED04, "VTOR": 0xE000ED08, "SHCSR": 0xE000ED24, "CFSR": 0xE000ED28, "HFSR": 0xE000ED2C,
       "DFSR": 0xE000ED30, "MMFAR": 0xE000ED34, "BFAR": 0xE000ED38, "DHCSR": 0xE000EDF0, "DEMCR": 0xE000EDFC}
NVIC = {"ISER": 0xE000E100, "ISPR": 0xE000E200, "IABR": 0xE000E300}


def say(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def eud(pid):
    """Only functions behind the EUD hub: other devices on this host reuse 05c6:9501."""
    return usb.core.find(idVendor=VID, idProduct=pid,
                         custom_match=lambda d: pid == HUB or (d.parent and d.parent.idProduct == HUB))


class Ocd:
    def __init__(self):
        self.proc = subprocess.Popen([os.path.join(HERE, "server"), "-c", "init"], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=True)
        self.sock = None
        for _ in range(100):
            with contextlib.suppress(OSError):
                self.sock = socket.create_connection(("127.0.0.1", 6666), timeout=20)
                break
            if self.proc.poll() is not None:
                break
            time.sleep(0.1)
        if not self.sock:
            self.stop()
            raise OSError("server did not start")

    def cmd(self, c):
        self.sock.sendall(f"if {{[catch {{capture {{{c}}}}} r]}} {{return \"ERROR: $r\"}} else {{return $r}}".encode()
                          + b"\x1a")
        buf = b""
        while not buf.endswith(b"\x1a"):
            d = self.sock.recv(65536)
            if not d:
                raise OSError("server went away")
            buf += d
        return buf[:-1].decode(errors="replace").strip()

    def stop(self):
        with contextlib.suppress(OSError):
            if self.sock:
                self.cmd("shutdown")
        with contextlib.suppress(OSError):
            os.killpg(self.proc.pid, 15)
        self.proc.wait()


class Log:
    """What the UART printed since this object was made."""

    def __init__(self):
        self.path = max(glob.glob(os.path.join(ROOT, "logs", "uart", "*.log")), key=os.path.getmtime)
        self.pos = os.path.getsize(self.path)

    def new(self):
        with open(self.path, "rb") as f:
            f.seek(self.pos)
            return f.read()

    def since_kernel(self):
        """Seconds since the kernel started, by uartd's timestamp.  -1 if it hasn't yet."""
        m = re.search(rb"\[(\d\d):(\d\d):(\d\d)\] \[ +0\.000000\] Linux version", self.new())
        if not m:
            return -1.0
        h, mi, sec = map(int, m.groups())
        now = time.localtime()
        return (now.tm_hour - h) * 3600 + (now.tm_min - mi) * 60 + now.tm_sec - sec


def uart_cmd(cmd):
    port = serial.Serial("/tmp/aupad-uart", 115200, timeout=0.1)
    for ch in f"\r{cmd}\r":
        port.write(ch.encode())
        time.sleep(0.12)
    port.close()


def wait(test, secs):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if test():
            return True
        time.sleep(0.05)
    return False


def reboot():
    # Not reboot -f: with the compositor up it blocks in msm_kms_shutdown.
    uart_cmd("reboot")
    if wait(lambda: not eud(CTL), 30):
        return True
    uart_cmd("sync; echo b > /proc/sysrq-trigger")
    return wait(lambda: not eud(CTL), 15)


def connect():
    """Up to about 60 s: SWD comes up late on some boots."""
    for attempt in range(6):
        if not wait(lambda: eud(CTL), 6):
            hub = eud(HUB)
            if hub:
                with contextlib.suppress(usb.core.USBError):
                    hub.reset()
            continue
        try:
            o = Ocd()
        except OSError:
            continue
        if "412fc231" in o.cmd("mdw 0xE000ED00"):
            return o
        o.stop()
    return None


def arm(o):
    for a in IRQ12, ABORT:
        if "ERROR" in o.cmd(f"bp {a:#x} 2 hw"):
            return False
    # Any other fault in the RPM is worth stopping for as well.
    o.cmd("cortex_m vector_catch hard_err bus_err mm_err state_err chk_err nocp_err int_err")
    return True


def kryo(o, put):
    """Stop every core and read it.  Each is examined here, it can't be polled while it sleeps."""
    for i in range(8):
        put(f"cpu{i} examine", f"cpu{i} arp_examine")
        put(f"cpu{i} halt", f"cpu{i} arp_halt")
        put(f"cpu{i} wait", f"cpu{i} arp_waitstate halted 300")
        put(f"cpu{i} registers", f"targets cpu{i}; get_reg -force {{pc sp cpsr x0 x1 x2 x3 x29 x30}}")
    o.cmd("targets rpm")


def dump(o, path, cores):
    """Registers first, then what's cheap, then the RAM: a reset can still arrive while this runs."""
    t0 = time.monotonic()
    with open(os.path.join(path, "state.txt"), "w") as f:
        def put(title, c):
            print(f"== {title} ({time.monotonic() - t0:.2f} s)\n{o.cmd(c)}", file=f, flush=True)
        put("rpm registers", "rpm get_reg -force {" + RPM_REGS + "}")
        for name, a in SCB.items():
            put(name, f"rpm mdw {a:#x}")
        for name, a in NVIC.items():
            put(name, f"rpm mdw {a:#x} 4")
        sp = re.search(r"msp (0x[0-9a-f]+)", o.cmd("rpm get_reg -force {msp}"))
        if sp:
            put("stack, the frame is on top", f"rpm mdw {sp[1]} 64")
        put("crash record", "rpm mdw 0x90418 64")
        if cores:
            kryo(o, put)
        put("targets", "targets")
        a, n = STACKED
        put("rpm ram", f"targets rpm; dump_image {os.path.join(path, 'rpm-ram.bin')} {a:#x} {n:#x}")
    say(f"dump took {time.monotonic() - t0:.1f} s")


def report(path):
    with open(os.path.join(path, "state.txt")) as f:
        s = f.read()
    for name in "pc", "lr", "msp", "xpsr":
        m = re.search(rf"^{name} (0x[0-9a-f]+)", s, re.M)
        say(f"  {name} {m[1] if m else '?'}")
    m = re.search(r"== stack.*\n0x[0-9a-f]+: (.*)", s)
    if m:
        w = m[1].split()
        say(f"  interrupted at pc {w[6]} lr {w[5]}" if len(w) > 6 else "  short stack")
    for key in "ICSR", "CFSR", "HFSR", "ISPR", "IABR":
        m = re.search(rf"== {key}.*\n(.*)", s)
        say(f"  {key} {m[1] if m else '?'}")
    say("  cores:", " ".join(re.findall(r"^pc (0x[0-9a-f]+)", s, re.M)[0:]) or "none read")


def after(o, release, path):
    """Time how long the tablet lasts from here, which says what the reset is tied to."""
    t0 = time.monotonic()
    if release:
        o.cmd("rbp all")
        o.cmd("cortex_m vector_catch none")
        o.cmd("resume")
        say("released into the abort")
        time.sleep(3)
        say("rpm at", o.cmd("rpm mdw 0xE000101C"))
        with open(os.path.join(path, "kryo-after-release.txt"), "w") as f:
            def put(title, c):
                print(f"== {title} ({time.monotonic() - t0:.2f} s)\n{o.cmd(c)}", file=f, flush=True)
            kryo(o, put)
        with open(os.path.join(path, "kryo-after-release.txt")) as f:
            say("  cores:", " ".join(re.findall(r"^pc (0x[0-9a-f]+)", f.read(), re.M)))
    while time.monotonic() - t0 < 60:
        try:
            if "412fc231" not in o.cmd("rpm mdw 0xE000ED00"):
                break
        except OSError:
            break
        time.sleep(0.2)
    else:
        say("no reset in 60 s, tablet stays frozen here")
        return
    say(f"reset {time.monotonic() - t0:.1f} s after " + ("release" if release else "the dump"))
    o.stop()


def cycle(args):
    log = Log()
    if "--here" not in args and not reboot():
        return "not-rebooted", None
    o = connect()
    if not o:
        return ("no-swd" if b"Linux version" in log.new() else "no-kernel"), None
    if not arm(o):
        o.stop()
        return "arm-failed", None
    armed = log.since_kernel()
    say(f"armed, kernel at {armed:.0f} s")
    fired = False
    while True:
        state = o.cmd("rpm curstate")
        if "halted" in state:
            return "hit", o
        since = log.since_kernel() if "--here" not in args else AFTER_KERNEL + 1
        if "--fire" in args and not fired and since >= 0:
            o.cmd("rpm mww 0xE000E200 0x1000")
            fired = True
        if since > AFTER_KERNEL and (fired or "--fire" not in args):
            time.sleep(1)
            if "halted" not in o.cmd("rpm curstate"):
                o.stop()
                return "ok", None
        if b"Mem dump" in log.new():
            o.stop()
            return "missed", None
        time.sleep(0.1)


def main():
    args = sys.argv[1:]
    cycles = next((int(a) for a in args if a.isdigit()), 200)
    bad = 0
    for n in range(1, cycles + 1):
        try:
            r, o = cycle(args)
        except OSError as e:
            r, o = f"lost: {e}", None
        say(f"cycle {n}: {r}")
        if r == "hit":
            path = os.path.join(LOGS, time.strftime("%m%d-%H%M%S"))
            os.makedirs(path)
            dump(o, path, "--release" not in args)
            report(path)
            say(f"evidence in {os.path.normpath(path)}")
            after(o, "--release" in args, path)
            return 0
        if r == "missed":
            say("hang without a hit: the breakpoint didn't catch it")
            return 1
        bad = 0 if r == "ok" else bad + 1
        if bad == 3:
            say("3 bad cycles, stopping")
            return 1
        if "--here" in args:
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
