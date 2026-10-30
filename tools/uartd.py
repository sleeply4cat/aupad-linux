#!/usr/bin/env python3
"""Keep the tablet UART recorded and ramdumps captured, all the time.  Start once, in the background.

Owns the nanobridge port, logs every line to logs/uart/<date>.log with wall-clock time, and offers the port
to the other tools as a pty at /tmp/aupad-uart.  A ramdump (05c6:900e) runs build/rdcap.sh by itself."""
import atexit, glob, os, pty, select, serial, subprocess, sys, termios, time, tty

LINK = '/tmp/aupad-uart'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.makedirs(f'{ROOT}/logs/uart', exist_ok=True)

master, slave = pty.openpty()
tty.setraw(slave)
os.set_blocking(master, False)
name = os.ttyname(slave)
os.close(slave)      # with no client the master shows POLLHUP and nothing is queued for a later one
if os.path.lexists(LINK):
    os.unlink(LINK)
os.symlink(name, LINK)
atexit.register(lambda: os.path.lexists(LINK) and os.unlink(LINK))


def client(p):
    return not any(ev & select.POLLHUP for _, ev in p.poll(0))


def ramdump():
    return any(open(f).read().strip() == '05c6' and open(f.replace('idVendor', 'idProduct')).read().strip() == '900e'
               for f in glob.glob('/sys/bus/usb/devices/*/idVendor'))


def log(data):
    with open(f'{ROOT}/logs/uart/{time.strftime("%Y%m%d")}.log', 'ab') as f:
        f.write(time.strftime('[%H:%M:%S] ').encode() + data + b'\n')


p = select.poll()
p.register(master, select.POLLIN)
line, port, seen = b'', None, False
next_usb = 0
while True:
    if time.time() > next_usb:
        next_usb = time.time() + 1
        now = ramdump()
        if now and not seen:
            log(b'=== uartd: ramdump, capturing')
            r = subprocess.run([f'{ROOT}/build/rdcap.sh'], capture_output=True)
            log(b'=== uartd: ' + r.stdout.splitlines()[0] if r.stdout else b'=== uartd: rdcap gave no output')
        seen = now
    if port is None:
        try:
            port = serial.Serial(glob.glob('/dev/serial/by-id/usb-Nordic_nanobridge_*-if00')[0], 115200, timeout=0.05)
        except (IndexError, OSError):
            time.sleep(1)
            continue
    try:
        data = port.read(4096)
        if data and client(p):
            try:
                os.write(master, data)
            except BlockingIOError:
                pass
        if client(p):
            try:
                out = os.read(master, 4096)
                if out:
                    port.write(out)
            except (BlockingIOError, OSError):
                pass
    except (OSError, serial.SerialException):
        port = None
        continue
    line += data
    while b'\n' in line:
        l, line = line.split(b'\n', 1)
        log(l.rstrip(b'\r'))
