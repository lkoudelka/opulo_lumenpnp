# -*- coding: utf-8 -*-
"""Photon feeder bus + firmware update over Marlin M485 (bus loader "PBL").

Runs in OpenPnP's Jython 2.7 and in CPython 3 (tests).  Transport-agnostic:
a transport has one method  transact_hex(hex_string) -> reply hex string
(without "rs485-reply: ") or None on timeout.

Protocol and procedure are the same as photon_busflash.py in the photon
firmware repo (busflash/), which is tested end-to-end against the PBL core.
"""
from __future__ import absolute_import, division, print_function

import re
import time
import zlib

APP_MAX = 31 * 1024
PAGE = 1024
WRITE_MAX = 24
ENTER_MAGIC = [0x50, 0x42, 0x4C, 0x21]          # "PBL!"
PBL_HEADER_MAGIC = b"PBL1"

ST_ARMED, ST_COMMITTED, ST_RECOVERY = 0x01, 0x02, 0x04
BL_STATUS, BL_ERASE, BL_WRITE, BL_COMMIT, BL_RESET = 0xB0, 0xB1, 0xB2, 0xB3, 0xB4
BL_E_CMD = 0x15
ERRORS = {0x00: "OK", 0x05: "FLASH", 0x10: "RANGE", 0x11: "ALIGN", 0x12: "NOT_ERASED",
          0x13: "VERIFY", 0x14: "CRC", 0x15: "UNKNOWN_CMD"}

GET_FEEDER_ID, INITIALIZE_FEEDER, VENDOR_OPTIONS = 0x01, 0x02, 0xBF
VENDOR_PBL_INFO, VENDOR_PBL_ENTER, VENDOR_LED = 0x20, 0x21, 0x10

T_ERASE = 0.045
T_COMMIT = 0.40
T_ENTER = 0.10
T_BOOT = 1.5


class BusError(Exception):
    pass


class Cancelled(Exception):
    pass


def crc8(data):
    """Photon CRC-8: poly 0x07, init 0."""
    crc = 0
    for b in data:
        crc ^= (b & 0xFF) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc ^= 0x1070 << 3
            crc <<= 1
    return (crc >> 8) & 0xFF


def to_hex(data):
    return "".join("%02X" % (b & 0xFF) for b in data)


def from_hex(s):
    return [int(s[i:i + 2], 16) for i in range(0, len(s) - 1, 2)]


def err_name(code):
    return ERRORS.get(code, "0x%02X" % code)


class Bus(object):
    def __init__(self, transport, sleep=time.sleep):
        self.t = transport
        self.sleep = sleep
        self.pid = 0
        self.packets = 0
        self.retries = 0

    def transact(self, addr, cmd, payload=(), retries=5, retry_delay=0.03):
        """One Photon packet; returns reply payload [status, data...] or None."""
        payload = list(payload)
        for attempt in range(retries + 1):
            self.pid = (self.pid + 1) & 0xFF
            hdr = [addr, 0x00, self.pid, len(payload) + 1]
            body = [cmd] + payload
            pkt = hdr + [crc8(hdr + body)] + body
            if len(pkt) > 32:
                raise ValueError("packet > 32 B (Marlin RS485_SEND_BUFFER_SIZE)")
            self.packets += 1
            r = self.t.transact_hex(to_hex(pkt))
            if r and r.strip().upper() != "TIMEOUT":
                try:
                    rb = from_hex(r.strip())
                except ValueError:
                    rb = []
                if (len(rb) >= 6 and rb[0] == 0 and rb[1] == addr and rb[2] == self.pid
                        and rb[3] == len(rb) - 5 and crc8(rb[:4] + rb[5:]) == rb[4]):
                    return rb[5:]
            if attempt < retries:
                self.retries += 1
                self.sleep(retry_delay)
        return None


class FeederInfo(object):
    def __init__(self, addr, mode):
        self.addr = addr
        self.mode = mode          # "app" | "pbl"
        self.uuid = []
        self.version = ""
        self.entry = False        # application has the bus-update entry
        self.pbl_version = 0      # 0 = loader not installed
        self.pbl_state = 0
        self.pbl_err = 0

    @property
    def uuid_hex(self):
        return to_hex(self.uuid).lower()

    @property
    def updatable(self):
        return self.mode == "pbl" or (self.entry and self.pbl_version > 0)

    def update_status(self):
        if self.mode == "pbl":
            return "in bus loader (recover)"
        if self.entry and self.pbl_version:
            return "ready"
        if self.entry:
            return "no bus loader installed"
        return "old firmware: manual flash needed once"


class Feeder(object):
    def __init__(self, bus, addr):
        self.bus = bus
        self.addr = addr

    def app(self, cmd, payload=(), retries=3):
        return self.bus.transact(self.addr, cmd, payload, retries=retries)

    def vendor(self, sub, args=()):
        opts = ([sub] + list(args) + [0] * 20)[:20]
        return self.app(VENDOR_OPTIONS, opts)

    def initialize(self, uuid):
        r = self.app(INITIALIZE_FEEDER, uuid)
        return bool(r) and r[0] == 0

    def set_led(self, red, green, blue):
        """Existing firmware feature VENDOR 0x10 (needs an initialized feeder)."""
        mask = 0x08 | (4 if red else 0) | (2 if green else 0) | (1 if blue else 0)
        r = self.vendor(VENDOR_LED, [mask])
        return bool(r) and r[0] == 0

    def read_version(self):
        out = []
        for chunk in range(16):
            r = self.vendor(chunk)
            if not r or r[0] != 0:
                break
            data = r[1:21]
            if 0 in data:
                out += data[:data.index(0)]
                break
            out += data
        return "".join(chr(c) for c in out)

    def pbl(self, cmd, payload=(), retries=5):
        r = self.bus.transact(self.addr, cmd, payload, retries=retries, retry_delay=T_ERASE)
        if r is None:
            raise BusError("addr %d: no reply to bus-loader command 0x%02X" % (self.addr, cmd))
        return r

    def pbl_status(self, retries=5):
        r = self.pbl(BL_STATUS, retries=retries)
        if len(r) < 9:
            raise BusError("addr %d: short bus-loader status %s" % (self.addr, to_hex(r)))
        crc = r[5] | (r[6] << 8) | (r[7] << 16) | (r[8] << 24)
        return r[1], r[2], r[3], crc            # version, state, err, last crc

    def probe(self, quick=False):
        r = self.app(GET_FEEDER_ID, retries=0 if quick else 2)
        if r is None:
            return None
        if r[0] == BL_E_CMD and len(r) == 1:          # bus loader answers app commands with E_CMD
            self.pbl_status()                         # clears the E_CMD this probe caused
            ver, state, err, _ = self.pbl_status()
            info = FeederInfo(self.addr, "pbl")
            info.pbl_version, info.pbl_state, info.pbl_err = ver, state, err
            return info
        if r[0] != 0 or len(r) < 13:
            return None
        info = FeederInfo(self.addr, "app")
        info.uuid = r[1:13]
        if not self.initialize(info.uuid):
            raise BusError("addr %d: INITIALIZE failed" % self.addr)
        info.version = self.read_version()
        r = self.vendor(VENDOR_PBL_INFO)
        if r and r[0] == 0 and r[1:4] == [0x50, 0x42, 0x4C]:
            info.entry = True
            info.pbl_version = r[5]
        return info


VERSION_RE = re.compile(br"(v\d+\.\d+\.\d+[0-9A-Za-z.+\-]*)\x00")


class Image(object):
    """Firmware image (.bin, linked at 0x08000000) for the bus update."""

    def __init__(self, path, data):
        self.path = path
        self.problems = []
        if len(data) > APP_MAX:
            self.problems.append("size %d B > %d B: would overwrite the bus loader page "
                                 "(factory image?)" % (len(data), APP_MAX))
        if len(data) >= 8:
            sp = bytearray(data[0:4])
            rv = bytearray(data[4:8])
            sp = sp[0] | sp[1] << 8 | sp[2] << 16 | sp[3] << 24
            rv = rv[0] | rv[1] << 8 | rv[2] << 16 | rv[3] << 24
            if not (0x20000000 < sp <= 0x20002000):
                self.problems.append("initial SP 0x%08X not in SRAM: not a Photon .bin?" % sp)
            if not (rv & 1 and 0x08000000 <= rv < 0x08000000 + len(data)):
                self.problems.append("reset vector 0x%08X outside the image" % rv)
        else:
            self.problems.append("file too short")
        if len(data) & 1:
            data = data + b"\xff"
        self.data = bytearray(data)
        m = VERSION_RE.search(bytes(self.data))
        self.version = m.group(1).decode("ascii") if m else ""
        self.has_entry = bytes(bytearray(ENTER_MAGIC)) in bytes(self.data)
        self.crc32 = zlib.crc32(bytes(self.data)) & 0xFFFFFFFF

    @classmethod
    def load(cls, path):
        f = open(path, "rb")
        try:
            return cls(path, f.read())
        finally:
            f.close()

    def describe(self):
        return "%s, %d B, entry %s, crc32 %08X" % (self.version or "version ?", len(self.data),
                                                  "yes" if self.has_entry else "NO", self.crc32)


def _le(v, n):
    return [(v >> (8 * i)) & 0xFF for i in range(n)]


def flash_one(bus, addr, img, progress=None, cancelled=None, allow_no_entry=False, sleep=time.sleep):
    """Update one feeder.  progress(stage, fraction, text); cancelled() -> True to stop
    (honoured only before the application is erased).  Returns the FeederInfo after update."""
    def report(stage, frac, text):
        if progress:
            progress(stage, frac, text)

    def check_cancel():
        if cancelled and cancelled():
            raise Cancelled("cancelled before erasing - feeder unchanged")

    fd = Feeder(bus, addr)
    t0 = time.time()
    report("probe", 0.0, "identifying")
    info = fd.probe()
    if info is None:
        raise BusError("addr %d: no feeder answers" % addr)
    if info.mode == "app":
        if not info.entry:
            raise BusError("addr %d: firmware '%s' has no bus-update entry: one manual "
                           "(dongle) flash of the factory image is needed first" % (addr, info.version))
        if not info.pbl_version:
            raise BusError("addr %d: bus loader not installed: one manual (dongle) flash of "
                           "the factory image is needed first" % addr)
        if not img.has_entry and not allow_no_entry:
            raise BusError("image has no bus-update entry: afterwards this feeder could only be "
                           "updated manually again")
        check_cancel()
        report("enter", 0.02, "entering bus loader (was %s)" % info.version)
        r = fd.vendor(VENDOR_PBL_ENTER, ENTER_MAGIC)
        if r is not None and r[0] != 0:
            raise BusError("addr %d: feeder refused to enter the bus loader (status %d)" % (addr, r[0]))
        sleep(T_ENTER)
    else:
        report("enter", 0.02, "already in bus loader (recovery)")

    ver, state, err, _ = fd.pbl_status(retries=10)
    check_cancel()
    data = img.data
    npages = (len(data) + PAGE - 1) // PAGE
    first = 1 if state & ST_ARMED else 0          # keep an existing recovery stub
    for p in range(first, npages):
        fd.pbl(BL_ERASE, [p])
        sleep(T_ERASE)
        report("erase", 0.03 + 0.10 * (p + 1) / npages, "erasing page %d/%d" % (p + 1, npages))
    _, state, err, _ = fd.pbl_status()
    if err or not state & ST_ARMED:
        raise BusError("addr %d: erase failed (err=%s, state=0x%02X)" % (addr, err_name(err), state))

    chunks = [off for off in range(0, len(data), WRITE_MAX)
              if any(b != 0xFF for b in data[off:off + WRITE_MAX])]
    for i, off in enumerate(chunks):
        r = fd.pbl(BL_WRITE, _le(off, 2) + list(data[off:off + WRITE_MAX]))
        if r[0] != 0:
            raise BusError("addr %d: write @0x%04X failed (%s)" % (addr, off, err_name(r[0])))
        if i % 16 == 0 or i == len(chunks) - 1:
            report("write", 0.13 + 0.77 * (i + 1) / len(chunks), "writing %d/%d" % (i + 1, len(chunks)))

    _, _, err, _ = fd.pbl_status()
    if err:
        raise BusError("addr %d: error before commit (%s)" % (addr, err_name(err)))
    report("commit", 0.92, "verifying CRC and committing")
    fd.pbl(BL_COMMIT, _le(len(data), 2) + _le(img.crc32, 4))
    sleep(T_COMMIT)
    _, state, err, got = fd.pbl_status(retries=20)
    if err or not state & ST_COMMITTED or got != img.crc32:
        raise BusError("addr %d: commit failed (err=%s, feeder crc %08X, image %08X); the feeder "
                       "waits in the bus loader (magenta LED): update it again" % (addr, err_name(err), got, img.crc32))
    try:
        fd.pbl(BL_RESET, retries=1)
    except BusError:
        pass
    report("restart", 0.96, "restarting feeder")
    sleep(T_BOOT)
    after = None
    for _ in range(5):
        after = fd.probe()
        if after and after.mode == "app":
            break
        sleep(0.5)
    if not after or after.mode != "app":
        raise BusError("addr %d: application did not come back after reset" % addr)
    if info.mode == "app" and after.uuid != info.uuid:
        raise BusError("addr %d: UUID changed after update?!" % addr)
    report("done", 1.0, "done in %.1f s: %s" % (time.time() - t0, after.version))
    return after


def scan(bus, addresses, progress=None):
    """Probe the given addresses; returns {addr: FeederInfo}."""
    found = {}
    addresses = list(addresses)
    for i, a in enumerate(addresses):
        if progress:
            progress("scan", (i + 1.0) / len(addresses), "address %d" % a)
        try:
            info = Feeder(bus, a).probe(quick=True)
        except BusError:
            info = None
        if info:
            found[a] = info
    return found
