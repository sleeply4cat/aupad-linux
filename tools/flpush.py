#!/usr/bin/env python3
"""Send a boot image to the tablet's flash loader.  usage: flpush.py <image> [port]"""
import socket, sys, time

ADDR = 'fe80::2aa:55ff:fe00:2%enx02aa55000001'
data = open(sys.argv[1], 'rb').read()
t0 = time.time()
s = socket.create_connection((ADDR, int(sys.argv[2]) if len(sys.argv) > 2 else 5555), timeout=5)
s.settimeout(120)
s.sendall(data)
s.shutdown(socket.SHUT_WR)
if s.recv(32).strip() != str(len(data)).encode():
    sys.exit('flpush: short transfer')
print(f'pushed {len(data) >> 20} MB in {time.time() - t0:.1f}s')
