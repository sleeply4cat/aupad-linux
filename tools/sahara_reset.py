#!/usr/bin/env python3
"""Send a raw Sahara RESET_REQ (works on a wedged memory-dump session). Needs bkerler's edl: set EDL_DIR and run it with that Python."""
import logging, os, sys
from struct import pack
sys.path.insert(0, os.environ.get('EDL_DIR', '.'))
from edlclient.Config.usb_ids import default_ids
from edlclient.Library.Connection.usblib import usb_class
from edlclient.Library.sahara_defs import cmd_t

cdc = usb_class(portconfig=default_ids, loglevel=logging.INFO)
if not cdc.connect():
    sys.exit('no Sahara device')
try:
    cdc.read(0x1000, timeout=1)
except Exception:
    pass
cdc.write(pack('<II', cmd_t.SAHARA_RESET_REQ, 8))
try:
    print('response', bytes(cdc.read(0x100, timeout=2)[:8]).hex())
except Exception as e:
    print('no response:', e)
