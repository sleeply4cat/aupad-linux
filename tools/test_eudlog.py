#!/usr/bin/env python3
"""Mock tests for tools/eudlog.py: record validation, the one-packet-outstanding rule, the
bounded resync, backpressure and the read-path disconnect, all against a scripted fake pyusb
(no device, no libusb — the fake is installed even when real pyusb is, so the tests stay
deterministic).  Run: venv/bin/python tools/test_eudlog.py"""
import contextlib
import io
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


class USBError(Exception):
    pass


class USBTimeoutError(USBError):
    pass


class NoDeviceError(USBError):
    pass


DISPOSED = []


def install_fake_usb():
    usb, core, util = types.ModuleType("usb"), types.ModuleType("usb.core"), types.ModuleType("usb.util")
    core.USBError, core.USBTimeoutError, core.NoDeviceError = USBError, USBTimeoutError, NoDeviceError
    util.dispose_resources = DISPOSED.append
    usb.core, usb.util = core, util
    sys.modules["usb"], sys.modules["usb.core"], sys.modules["usb.util"] = usb, core, util


install_fake_usb()

import eudlog    # noqa: E402  (needs the fake usb in place first)


def rec(pid, payload, short=False):
    """One COM record, [ID, length, payload]: 16 bytes padded, or the short last one of a transfer.
    The padding is 0xee on purpose: the parser must slice exactly 2 + length, never leak it."""
    body = bytes([pid, len(payload)]) + payload
    assert len(body) <= 16
    return body if short else body + b"\xee" * (16 - len(body))


class Input:
    """Stands in for Console.read: one queued chunk per call, counting the calls"""

    def __init__(self):
        self.queue, self.calls = [], 0

    def push(self, data):
        self.queue.append(bytes(data))

    def __call__(self):
        self.calls += 1
        if not self.queue:
            raise BlockingIOError()
        return self.queue.pop(0)


class Clock:
    """Stands in for the time module inside eudlog"""

    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, s):
        self.now += s

    def strftime(self, fmt):
        return "[test time] "


class FakeDev:
    """A usb.core.Device: scripted reads, writes that can be made to fail, clear_halt that can fail"""

    def __init__(self, reads=()):
        self.reads, self.writes = list(reads), []
        self.fail_writes, self.fail_clear_halt = [], None
        self.clear_halts, self.set_configurations = 0, 0

    def set_configuration(self):
        self.set_configurations += 1

    def write(self, ep, data, timeout=0):
        if self.fail_writes:
            raise self.fail_writes.pop(0)
        self.writes.append((ep, bytes(data)))

    def read(self, ep, size, timeout=0):
        if not self.reads:
            raise NoDeviceError("script exhausted: the device left")
        item = self.reads.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def clear_halt(self, ep):
        self.clear_halts += 1
        if self.fail_clear_halt:
            raise self.fail_clear_halt

    def out(self):
        return [data for _, data in self.writes]


class FakeConsole:
    """A Console that takes scripted input and goes nowhere"""

    def __init__(self):
        self.queue = []

    def client(self):
        return False

    def read(self):
        if not self.queue:
            raise BlockingIOError()
        return self.queue.pop(0)

    def write(self, text):
        pass


class EudlogTestCase(unittest.TestCase):
    PATCHED = ("time", "RESYNC_TRIES", "RESYNC_SLEEP", "TX_HIGH_WATER", "console", "PAUSE")

    def setUp(self):
        self.real = {name: getattr(eudlog, name) for name in self.PATCHED}
        self.clock = Clock()
        eudlog.time = self.clock
        eudlog.RESYNC_TRIES, eudlog.RESYNC_SLEEP = 3, 0
        eudlog.TX_HIGH_WATER = 64 * 1024
        eudlog.console = None
        eudlog.PAUSE = os.path.join(HERE, "no-such-pause-file")
        DISPOSED.clear()

    def tearDown(self):
        eudlog.__dict__.update(self.real)


class RxTest(EudlogTestCase):
    def rx(self, *transfers):
        rx = eudlog.Rx()
        for t in transfers:
            rx.feed(bytes(t))
        return rx

    def test_data_record(self):
        rx = self.rx(rec(0x90, b"hello"))
        self.assertEqual((rx.text, rx.acks, rx.malformed), ("hello", 0, 0))

    def test_two_records_one_transfer(self):
        rx = self.rx(rec(0x90, b"hello") + rec(0x90, b"world", short=True))
        self.assertEqual(rx.text, "helloworld")

    def test_short_final_record_claiming_more_than_sent(self):
        # A length past the end of the transfer must not read into padding or the next record
        rx = self.rx(rec(0x90, b"hello") + bytes([0x90, 6]) + b"worl")
        self.assertEqual(rx.text, "hello")
        self.assertEqual(rx.malformed, 1)

    def test_length_past_14(self):
        for bad in (15, 255):
            rx = self.rx(bytes([0x90, bad]) + b"x" * 14)
            self.assertEqual((rx.text, rx.malformed), ("", 1))

    def test_zero_length(self):
        rx = self.rx(bytes([0x90, 0]))
        self.assertEqual((rx.text, rx.acks, rx.malformed), ("", 0, 0))

    def test_ack_shapes(self):
        rx = self.rx(rec(0x91, b"\x06", short=True))
        self.assertEqual(rx.acks, 1)
        rx = self.rx(rec(0x91, b"\x07", short=True), rec(0x91, b"\x06\x06", short=True))
        self.assertEqual((rx.acks, rx.malformed), (0, 2))

    def test_unknown_id(self):
        rx = self.rx(rec(0x92, b"\x00", short=True))
        self.assertEqual(rx.malformed, 1)

    def test_utf8_split_across_records_and_transfers(self):
        word = "мир".encode()
        rx = self.rx(rec(0x90, word[:1]) + rec(0x90, word[1:3], short=True))
        rx.feed(rec(0x90, word[3:]))
        self.assertEqual(rx.text, "мир")


class TxTest(EudlogTestCase):
    def tx(self, dev):
        inp = Input()
        return eudlog.Tx(dev, inp), inp

    def test_reset_sends_commands_and_hello(self):
        dev = FakeDev()
        eudlog.Tx(dev, Input())
        self.assertEqual(dev.out(), [
            bytes([eudlog.COM_CMD_PORT_RESET]),
            bytes([eudlog.COM_CMD_RX_TMOUT]) + eudlog.RX_TMOUT_MS.to_bytes(4, "little"),
            bytes([0x91, 1, 0x05]),
        ])

    def test_input_goes_out_in_14_byte_packets(self):
        dev = FakeDev()
        tx, inp = self.tx(dev)
        tx.ack()
        inp.push(b"a" * 20)
        tx.pump()
        self.assertEqual(dev.out()[-1], bytes([0x90, 14]) + b"a" * 14)
        tx.pump()                       # still pending: no second packet until the ack
        self.assertEqual(len(dev.writes), 4)
        tx.ack()
        tx.pump()
        self.assertEqual(dev.out()[-1], bytes([0x90, 6]) + b"a" * 6)

    def test_unread_packet_times_out_into_a_reset(self):
        dev = FakeDev()
        tx, inp = self.tx(dev)
        tx.ack()
        inp.push(b"ping")
        tx.pump()
        self.assertEqual(dev.out()[-1], bytes([0x90, 4]) + b"ping")
        self.clock.now += eudlog.RX_TMOUT_MS / 1000 + 2
        tx.pump()
        self.assertEqual(dev.out()[-3:], [
            bytes([eudlog.COM_CMD_PORT_RESET]),
            bytes([eudlog.COM_CMD_RX_TMOUT]) + eudlog.RX_TMOUT_MS.to_bytes(4, "little"),
            bytes([0x91, 1, 0x05]),
        ])

    def test_failed_write_resyncs_and_resends(self):
        dev = FakeDev()
        tx, inp = self.tx(dev)
        tx.ack()
        inp.push(b"again")
        dev.fail_writes.append(USBError("data toggle off by one"))
        tx.pump()                       # the write fails, a NOP realigns, nothing is sent yet
        self.assertEqual(dev.out()[-1], bytes([eudlog.COM_CMD_NOP]))
        tx.pump()
        self.assertEqual(dev.out()[-1], bytes([0x90, 5]) + b"again")

    def test_resync_gives_up_disposes_and_raises(self):
        dev = FakeDev()
        tx, inp = self.tx(dev)
        tx.ack()
        inp.push(b"x")
        dev.fail_writes.extend([USBError("endpoint stalled")] * 6)
        with self.assertRaises(USBError) as cm:
            tx.pump()
        self.assertIn("NOPs", str(cm.exception))
        self.assertEqual(dev.clear_halts, eudlog.RESYNC_TRIES)
        self.assertEqual(DISPOSED, [dev])

    def test_nodevice_on_write_surfaces_immediately(self):
        dev = FakeDev()
        tx, inp = self.tx(dev)
        tx.ack()
        inp.push(b"x")
        dev.fail_writes.append(NoDeviceError("tablet gone"))
        with self.assertRaises(NoDeviceError):
            tx.pump()                   # no resync attempts on a device that isn't there
        self.assertEqual(dev.clear_halts, 0)
        self.assertEqual(DISPOSED, [])

    def test_nodevice_on_clear_halt_surfaces(self):
        dev = FakeDev()
        tx, inp = self.tx(dev)
        tx.ack()
        inp.push(b"x")
        dev.fail_writes.append(USBError("endpoint stalled"))
        dev.fail_clear_halt = NoDeviceError("tablet gone")
        with self.assertRaises(NoDeviceError):
            tx.pump()

    def test_timeout_write_is_not_swallowed(self):
        dev = FakeDev()
        tx, inp = self.tx(dev)
        tx.ack()
        inp.push(b"x")
        dev.fail_writes.append(USBTimeoutError())
        with self.assertRaises(USBTimeoutError):
            tx.pump()
        self.assertEqual(dev.clear_halts, 0)

    def test_input_backpressure(self):
        eudlog.TX_HIGH_WATER = 16
        dev = FakeDev()
        tx, inp = self.tx(dev)
        tx.ack()
        inp.push(b"a" * 20)
        inp.push(b"b" * 20)
        tx.pump()                       # reads one chunk, sends 14, keeps 6 pending
        tx.pump()                       # 6 < 16: reads the second chunk too, still pending
        self.assertEqual(inp.calls, 2)
        tx.pump()                       # 26 >= 16: the input stays where it is
        self.assertEqual(inp.calls, 2)
        tx.ack()
        tx.pump()
        self.assertEqual(dev.out()[-1], bytes([0x90, 14]) + b"a" * 6 + b"b" * 8)
        self.assertEqual(inp.calls, 2)


class StreamTest(EudlogTestCase):
    def setUp(self):
        super().setUp()
        self.dev = FakeDev()
        eudlog.console = FakeConsole()
        self.log = io.StringIO()

    def run_stream(self, raw=None):
        with contextlib.redirect_stdout(io.StringIO()):
            eudlog.stream(self.dev, self.log, raw)

    def test_text_ack_then_disconnect_during_read(self):
        self.dev.reads = [rec(0x90, b"hello") + rec(0x91, b"\x06", short=True)]
        with self.assertRaises(NoDeviceError):
            self.run_stream()
        self.assertIn("hello", self.log.getvalue())

    def test_input_roundtrip_with_timeout_and_ack(self):
        eudlog.console.queue = [b"date\n"]
        self.dev.reads = [USBTimeoutError(), rec(0x91, b"\x06", short=True)]
        with self.assertRaises(NoDeviceError):
            self.run_stream()
        self.assertIn(bytes([0x90, 5]) + b"date\n", self.dev.out())

    def test_malformed_record_is_reported(self):
        self.dev.reads = [bytes([0x90, 15]) + b"x" * 14]
        with self.assertRaises(NoDeviceError):
            self.run_stream()
        self.assertIn("malformed", self.log.getvalue())

    def test_raw_log_gets_the_transfers_untouched(self):
        raw = io.BytesIO()
        self.dev.reads = [rec(0x90, b"ab", short=True)]
        with self.assertRaises(NoDeviceError):
            self.run_stream(raw)
        self.assertEqual(raw.getvalue(), bytes(rec(0x90, b"ab", short=True)))


if __name__ == "__main__":
    unittest.main()
