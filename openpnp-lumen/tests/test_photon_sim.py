#!/usr/bin/env python3
"""lib/lumen/photon.py against the Marlin + feeder-bus simulator of the photon repo
(busflash/sim: real PBL core built for Linux + Python model of the Photon app).

    PHOTON_BUSFLASH=~/claude/opulo/_dev/photon/dev/busflash \
        python3 tests/test_photon_sim.py photon-lumenpnp-v1.0.7.bin
Needs pyserial.
"""
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from lumen import photon  # noqa: E402

BF = os.path.expanduser(os.environ.get("PHOTON_BUSFLASH", "~/claude/opulo/_dev/photon/dev/busflash"))
sys.path.insert(0, os.path.join(BF, "tests"))
import run_sim_tests as rst  # noqa: E402  (make_app, flash_file helpers)

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


class SerialTransport(object):
    """Minimal Marlin M485 transport (what the OpenPnP actuator does: M485 {Value} -> rs485-reply)."""

    def __init__(self, port):
        import serial
        self.s = serial.Serial(port, 115200, timeout=0.05)
        self.lines = 0

    def transact_hex(self, hexs):
        self.s.write(("M485 " + hexs + "\n").encode())
        buf, end, reply = b"", time.time() + 3, None
        while time.time() < end:
            buf += self.s.read(self.s.in_waiting or 1)
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.decode().strip()
                if line.startswith("rs485-reply:"):
                    reply = line.split(":", 1)[1].strip()
                elif line.startswith("ok"):
                    return reply
        return None


def start_sim(work, feeders, extra=()):
    pf = os.path.join(work, "port")
    if os.path.exists(pf):
        os.remove(pf)
    args = [sys.executable, os.path.join(BF, "sim", "marlin_sim.py"), "--port-file", pf] + list(extra)
    for f in feeders:
        args += ["--feeder", f]
    p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=open(os.path.join(work, "sim.log"), "a"))
    for _ in range(100):
        if os.path.exists(pf) and open(pf).read():
            break
        time.sleep(0.05)
    return p, open(pf).read()


def main():
    release = open(sys.argv[1], "rb").read()
    pbl = open(os.path.join(BF, "bootloader", "build", "pbl.bin"), "rb").read()
    work = tempfile.mkdtemp(prefix="lumen-photon-", dir=os.environ.get("SIM_WORKDIR"))
    cur = rst.make_app(release, "v1.1.8")
    new = rst.make_app(release, "v1.1.9")
    newbin = os.path.join(work, "new.bin")
    open(newbin, "wb").write(new)

    def fresh():
        rst.flash_file(os.path.join(work, "f1.bin"), release)
        rst.flash_file(os.path.join(work, "f2.bin"), cur, pbl)
        rst.flash_file(os.path.join(work, "f3.bin"), cur, pbl)
        return ["%d:%s" % (a, os.path.join(work, "f%d.bin" % a)) for a in (1, 2, 3)]

    def region(a):
        return open(os.path.join(work, "f%d.bin" % a), "rb").read()[:len(new)]

    img = photon.Image.load(newbin)
    check("image accepted", not img.problems and img.version == "v1.1.9" and img.has_entry, img.describe())
    big = photon.Image(newbin, new + b"\0" * 200)
    check("oversized image flagged", big.problems)

    print("L1 scan + update + cancel")
    p, port = start_sim(work, fresh())
    bus = photon.Bus(SerialTransport(port))
    found = photon.scan(bus, range(1, 6))
    check("scan finds 3", sorted(found) == [1, 2, 3])
    check("old fw not updatable", not found[1].updatable and "manual" in found[1].update_status())
    check("migrated feeder ready", found[2].updatable and found[2].update_status() == "ready")
    stages = []
    after = photon.flash_one(bus, 2, img, progress=lambda s, f, t: stages.append((s, f)))
    check("update addr 2", after.version == "v1.1.9" and region(2) == new)
    check("progress reported 0..1", stages[0][1] == 0.0 and stages[-1] == ("done", 1.0)
          and all(stages[i][1] <= stages[i + 1][1] for i in range(len(stages) - 1)))
    try:
        photon.flash_one(bus, 3, img, cancelled=lambda: True)
        check("cancel before erase", False)
    except photon.Cancelled:
        check("cancel before erase leaves feeder unchanged", region(3) == cur and photon.Feeder(bus, 3).probe().mode == "app")
    try:
        photon.flash_one(bus, 1, img)
        check("old fw refused", False)
    except photon.BusError as e:
        check("old fw refused", "manual" in str(e))
    p.terminate(); p.wait()

    print("L2 10 % lost replies + power cut -> recover")
    p, port = start_sim(work, fresh(), ["--drop", "0.10", "--seed", "3", "--cut", "3:300"])
    bus = photon.Bus(SerialTransport(port))
    after = photon.flash_one(bus, 2, img)
    check("update with lost replies", after.version == "v1.1.9" and region(2) == new and bus.retries > 0,
          "(%d packets, %d retries)" % (bus.packets, bus.retries))
    try:
        photon.flash_one(bus, 3, img)
    except photon.BusError:
        pass
    info = photon.Feeder(bus, 3).probe()
    check("cut feeder found in bus loader", info and info.mode == "pbl" and info.pbl_state & photon.ST_RECOVERY)
    after = photon.flash_one(bus, 3, img)
    check("recovery update", after.version == "v1.1.9" and region(3) == new)
    p.terminate(); p.wait()

    print("\n%d/%d checks passed" % (sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
