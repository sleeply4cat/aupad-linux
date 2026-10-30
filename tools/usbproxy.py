#!/usr/bin/env python3
"""HTTP/CONNECT proxy for the tablet, listening on the USB link only.  usage: usbproxy.py [seconds]"""
import select, socket, sys, threading, time

BIND = ('172.16.42.2', 8888)


def pump(a, b):
    socks = [a, b]
    while True:
        r, _, _ = select.select(socks, [], [], 120)
        if not r:
            return
        for s in r:
            data = s.recv(65536)
            if not data:
                return
            (b if s is a else a).sendall(data)


def serve(c):
    try:
        head = b''
        while b'\r\n\r\n' not in head:
            d = c.recv(65536)
            if not d:
                return
            head += d
        line = head.split(b'\r\n', 1)[0].decode()
        method, url, _ = line.split(' ')
        if method == 'CONNECT':
            host, port = url.rsplit(':', 1)
            u = socket.create_connection((host, int(port)), timeout=30)
            c.sendall(b'HTTP/1.1 200 OK\r\n\r\n')
        else:
            hostport = url.split('/')[2]
            host, port = (hostport.rsplit(':', 1) + ['80'])[:2]
            u = socket.create_connection((host, int(port)), timeout=30)
            path = '/' + url.split('/', 3)[3]
            u.sendall(head.replace(url.encode(), path.encode(), 1))
        pump(c, u)
        u.close()
    except Exception as e:
        print('proxy:', e, flush=True)
    finally:
        c.close()


s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(BIND)
s.listen(16)
s.settimeout(1)
end = time.time() + float(sys.argv[1] if len(sys.argv) > 1 else 3600)
while time.time() < end:
    try:
        c, _ = s.accept()
    except socket.timeout:
        continue
    threading.Thread(target=serve, args=(c,), daemon=True).start()
