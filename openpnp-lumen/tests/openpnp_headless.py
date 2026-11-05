# Headless test of the Lumen library against the REAL OpenPnP 2.6 classes (no GUI, no machine):
#   tests/run_openpnp_headless.sh
# Loads OpenPnP's stock (simulated) configuration from a sandbox copy, builds a job with
# boards/parts/feeders in code and exercises jobinfo, journal, oppnp.  Also byte-compiles
# every menu/event script with OpenPnP's Jython.
from __future__ import print_function
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "lib"))
sandbox = sys.argv[1]

from java.io import File
from org.openpnp.model import (Configuration, Board, BoardLocation, Job, Length, LengthUnit, Location,
                               Part, Placement)
from org.openpnp.model import Abstract2DLocatable
from org.openpnp.machine.photon import PhotonFeeder
from org.openpnp.machine.reference.feeder import ReferenceTubeFeeder

Configuration.initialize(File(sandbox))
Configuration.get().load()
machine = Configuration.get().getMachine()

from lumen import jobinfo, journal, oppnp

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


class FakeScripting(object):
    def getScriptsDirectory(self):
        return File(os.path.join(sandbox, "scripts"))


scripting = FakeScripting()
mm = LengthUnit.Millimeters
Top = Abstract2DLocatable.Side.Top

# parts: R1 with height + Photon feeder, C1 without height, U1 without feeder, D1 disabled feeder
parts = {}
for pid, h in (("R0402", 0.35), ("C0402", 0.0), ("U-SOIC8", 1.5), ("D-SOD123", 1.1)):
    p = Part(pid)
    p.setHeight(Length(h, mm))
    Configuration.get().addPart(p)
    parts[pid] = p

f1 = PhotonFeeder()
f1.setName("Photon R0402")
f1.setSlotAddress(5)
f1.setPart(parts["R0402"])
f1.setHardwareId("a0a0a0a0a0a0a0a0a0a0a0a0")
f1.setOffset(Location(mm, 0, 0, 0, 0))
f1.setEnabled(True)
machine.addFeeder(f1)
f1.getSlot().setLocation(Location(mm, 50, 20, 10, 0))      # slot 5 taught
f2 = PhotonFeeder()
f2.setName("Photon C0402 no slot")
f2.setPart(parts["C0402"])
f2.setEnabled(True)
machine.addFeeder(f2)
f3 = ReferenceTubeFeeder()
f3.setName("Tube diode")
f3.setPart(parts["D-SOD123"])
f3.setEnabled(False)
machine.addFeeder(f3)

board = Board()
board.setName("TestBoard")
for i, pid in enumerate(["R0402", "R0402", "R0402", "C0402", "U-SOIC8", "D-SOD123"]):
    pl = Placement("P%d" % (i + 1))
    pl.setPart(parts[pid])
    pl.setLocation(Location(mm, 10 + i, 5, 0, 90))
    pl.setSide(Top)
    board.addPlacement(pl)
fid = Placement("FID1")
fid.setType(Placement.Type.Fiducial)
fid.setSide(Top)
board.addPlacement(fid)
off = Placement("P99")
off.setPart(parts["R0402"])
off.setSide(Top)
off.setEnabled(False)
board.addPlacement(off)
bl = BoardLocation(board)
bl.setLocation(Location(mm, 100, 50, 0, 0))
bl.setGlobalSide(Top)
job = Job()
job.addBoardOrPanelLocation(bl)
job.setFile(File(os.path.join(sandbox, "test.job.xml")))

print("jobinfo")
pls = jobinfo.job_placements(job)
check("job_placements: 6 (fiducial + disabled excluded)", len(pls) == 6, [p.getId() for _, p, _ in pls])
job.storePlacedStatus(bl, "P1", True)
rows = dict((r["part_id"], r) for r in jobinfo.readiness(job, machine))
check("R0402 total 3, remaining 2, OK", rows["R0402"]["total"] == 3 and rows["R0402"]["remaining"] == 2
      and not rows["R0402"]["issues"], rows["R0402"]["issues"])
check("C0402: height unknown + precise Photon reason", "part height unknown" in rows["C0402"]["issues"]
      and any("not found on the bus" in i and "no slot address" in i for i in rows["C0402"]["issues"]), rows["C0402"]["issues"])
check("U-SOIC8: no feeder", rows["U-SOIC8"]["issues"] == ["no feeder has this part"])
check("D-SOD123: feeder switched off", rows["D-SOD123"]["issues"] == ["no usable feeder: Tube diode: switched off"],
      rows["D-SOD123"]["issues"])
check("feeder_text", jobinfo.feeder_text(f1) == "Photon R0402 (Slot: 5)" and "switched off" in jobinfo.feeder_text(f3),
      [jobinfo.feeder_text(f1), jobinfo.feeder_text(f3)])
check("photon_feeders by slot", sorted(oppnp.photon_feeders(machine)) == [5])

print("journal")
jf = str(job.getFile().getAbsolutePath())
for pid in ("P2", "P3"):
    pl = board.getPlacements().get(pid)
    journal.record(scripting, jf, pl.getPart(), machine.getDefaultHead().getDefaultNozzle(), pl, bl,
                   Location(mm, 111.0, 55.0, -1.0, 90.0))
journal.record(scripting, "/other/job.xml", parts["R0402"], None, board.getPlacements().get("P4"), bl, None)
t = journal.tail(scripting, jf)
check("tail: newest first, filtered by job", [r["placement"] for r in t] == ["P3", "P2"], [r["placement"] for r in t])
check("record content", t[0]["board"] == bl.getUniqueId() and t[0]["part"] == "R0402" and t[0]["location"][0] == 111.0, t[0])
check("lookup back to placement", bl.getPlacementsHolder().getPlacements().get(t[0]["placement"]) is not None)
job.storePlacedStatus(bl, "P3", True)
job.storePlacedStatus(bl, "P3", False)
check("mark not placed", not job.retrievePlacedStatus(bl, "P3"))
from org.openpnp.util import Utils2D
loc = Utils2D.calculateBoardPlacementLocation(bl, board.getPlacements().get("P2"))
check("go-to location = board origin + placement", abs(loc.getX() - 111.0) < 1e-6 and abs(loc.getY() - 55.0) < 1e-6, loc)

print("oppnp")
s = oppnp.Settings(scripting)
s.set("last_image", "/x/y.bin")
check("settings persist", oppnp.Settings(scripting).get("last_image") == "/x/y.bin")
lg = oppnp.FileLog(scripting, "test")
lg("hello")
check("file log written", "hello" in open(lg.path).read(), lg.path)


class FakeGui(object):
    def getJobTab(self):
        raise RuntimeError("no gui")


check("job_state without GUI -> Unknown", oppnp.job_state(FakeGui()) == "Unknown")
check("machine_ready: not enabled", "not enabled" in (oppnp.machine_ready(machine, FakeGui()) or ""))
t = oppnp.ActuatorTransport(machine)     # OpenPnP creates PhotonFeederData when a Photon feeder exists
check("PhotonFeederData actuator present", t.actuator.getName() == "PhotonFeederData")
machine.setEnabled(True)
box = []
oppnp.run_machine_task(machine, lambda: box.append(1))
check("run_machine_task executes", box == [1])
from lumen import photon


def boom():
    raise photon.BusError("addr 7: test error")


try:
    oppnp.run_machine_task(machine, boom)
    check("Python exception carried through machine task", False)
except photon.BusError as e:
    check("Python exception carried through machine task", "addr 7" in str(e))
r = t.transact_hex("0500010101AB")          # simulated driver: no Marlin -> must not raise
check("transport on a machine without Marlin returns cleanly", r is None or isinstance(r, str), repr(r))
machine.setEnabled(False)

print("compile all scripts with OpenPnP's Jython")
import py_compile
bad = []
for d in ("scripts/Lumen", "events", "lib/lumen"):
    for fn in sorted(os.listdir(os.path.join(ROOT, d))):
        if fn.endswith(".py"):
            try:
                compile(open(os.path.join(ROOT, d, fn)).read(), fn, "exec")
            except SyntaxError as e:
                bad.append("%s: %s" % (fn, e))
check("all scripts compile", not bad, bad)

print("\n%d/%d checks passed" % (sum(results), len(results)))
from java.lang import System
System.exit(0 if all(results) else 1)
