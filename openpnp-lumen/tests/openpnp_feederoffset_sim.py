# feedercheck.apply_pocket_offset on real OpenPnP feeder classes (stock simulated machine, headless): tray, strip,
# Photon - the pick location moves by exactly the given offset, a feeder kind it cannot move is refused.
#   tests/run_feederoffset_sim.sh
import os
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sandbox = sys.argv[1]

from java.io import File
from java.lang import System as _Sys
from org.openpnp.model import Configuration, Location, LengthUnit

Configuration.initialize(File(sandbox))
Configuration.get().load()
machine = Configuration.get().getMachine()
mm = LengthUnit.Millimeters
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    _Sys.out.println("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


from lumen import feedercheck
from org.openpnp.machine.reference.feeder import ReferenceTrayFeeder, ReferenceStripFeeder


def moved(f, dx, dy):
    b = f.getPickLocation().convertToUnits(mm)
    before, after = feedercheck.apply_pocket_offset(f, dx, dy, limit_mm=None)
    a = f.getPickLocation().convertToUnits(mm)
    return abs(a.getX() - b.getX() - dx) < 1e-6 and abs(a.getY() - b.getY() - dy) < 1e-6, (b, a)

tray = ReferenceTrayFeeder()
tray.setName("tray-test")
tray.setLocation(Location(mm, 100.0, 50.0, -1.0, 90.0))
tray.setOffsets(Location(mm, 4.0, 4.0, 0, 0))
tray.setTrayCountX(3)
tray.setTrayCountY(2)
check("tray: offset kind 'location'", feedercheck.offset_kind(tray) == "location", feedercheck.offset_kind(tray))
for fc in (0, 4):
    tray.setFeedCount(fc)
    ok, d = moved(tray, 0.3, -0.2)
    check("tray, feed count %d: pick moves by +0.30 / -0.20 (whole tray, Z and rotation kept)" % fc,
          ok and tray.getLocation().getZ() == -1.0 and tray.getLocation().getRotation() == 90.0, d)
tray.setFeedCount(5)
p5 = tray.getPickLocation()
tray.setFeedCount(1)
p1 = tray.getPickLocation()
check("tray: the other positions moved with it (feed 5 still two 4 mm pitches from feed 1, location moved 0.6 / -0.4)",
      abs(p5.getX() - p1.getX() - 8.0) < 1e-6 and abs(p5.getY() - p1.getY()) < 1e-6
      and abs(p1.getX() - 100.6) < 1e-6 and abs(p1.getY() - 49.6) < 1e-6, (p1, p5))

strips = [f for f in machine.getFeeders() if isinstance(f, ReferenceStripFeeder)]
s = strips[0]
check("strip: offset kind 'strip'", feedercheck.offset_kind(s) == "strip", s.getName())
h0, l0 = s.getReferenceHoleLocation(), s.getLastHoleLocation()
ok, d = moved(s, -0.4, 0.25)
check("strip: pick moves by -0.40 / +0.25, both reference holes by the same", ok
      and abs(s.getReferenceHoleLocation().getX() - h0.getX() + 0.4) < 1e-6
      and abs(s.getLastHoleLocation().getY() - l0.getY() - 0.25) < 1e-6, d)

try:
    from org.openpnp.machine.photon import PhotonFeeder
    check("Photon: offset kind 'photon' (feeder offset in the slot frame)",
          feedercheck.offset_kind(PhotonFeeder()) == "photon")
except Exception as e:
    check("Photon class available", False, e)


class Odd(object):
    def getName(self):
        return "odd"
try:
    feedercheck.apply_pocket_offset(Odd(), 0.1, 0.1, limit_mm=None)
    err = None
except ValueError as e:
    err = str(e)
check("a feeder without a movable location: refused with a reason", err and "no location" in err, err)
try:
    feedercheck.apply_pocket_offset(tray, 3.0, 0.0)
    err = None
except ValueError as e:
    err = str(e)
check("automatic offsets still limited to 2 mm", err and "larger than" in err, err)
_Sys.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
_Sys.exit(0 if all(results) else 1)
