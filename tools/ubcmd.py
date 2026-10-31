#!/usr/bin/env python3
"""Send a line to the UART one character at a time, keeping the pty open: ubcmd.py <text> <listen seconds>"""
import os,sys,time,tty
f=os.open('/tmp/aupad-uart',os.O_RDWR|os.O_NOCTTY); tty.setraw(f); os.set_blocking(f,False)
for c in sys.argv[1].encode().decode('unicode_escape').encode():
    os.write(f,bytes([c])); time.sleep(.06)
b=b''; t=time.time()
while time.time()-t<float(sys.argv[2]):
    try: b+=os.read(f,4096)
    except BlockingIOError: pass
    time.sleep(.05)
print(b[-400:])
