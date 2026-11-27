# Job Readiness > Measure body size (lib/lumen/sizemeasure.py) on OpenPnP's SIMULATED machine (stock config:
# NullDriver, SimulatedUpCamera draws the part on the nozzle), real OpenPnP classes, headless.
# A package without body size: one part fed + picked from a tray, 5 bottom-vision shots (0/90/180/270/0 deg) with
# OpenPnP's own pipeline, the part back into the tray (feed count as before), nothing applied.
#   tests/run_sizemeasure_sim.sh
import os
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sandbox = sys.argv[1]

from java.io import File
from java.lang import System as _Sys
from org.openpnp.model import Configuration, Footprint, Length, LengthUnit, Location, Package, Part
from org.openpnp.machine.reference.feeder import ReferenceTrayFeeder
Configuration.initialize(File(sandbox))
Configuration.get().load()
cfg = Configuration.get()
machine = cfg.getMachine()
mm = LengthUnit.Millimeters
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    _Sys.out.println("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


from lumen import jobinfo, oppnp, sizemeasure as sm

# pure part
S = lambda *wh: [{"angle": a, "w": w, "h": h} for a, (w, h) in zip(sm.ANGLES, wh)]
r = sm.summarize(S((2.70, 1.60), (2.72, 1.62), (2.69, 1.59), (2.71, 1.61), (2.70, 1.60)))
check("summarize: 5 agreeing shots -> median, ok", r["ok"] and r["w"] == 2.70 and r["h"] == 1.60, r)
r = sm.summarize(S((2.70, 1.60), (1.60, 2.70), (2.70, 1.60), (1.60, 2.70), (2.70, 1.60)))
check("summarize: width / height swap with the turn -> not proposed", not r["ok"] and "differ" in r["why"], r)
r = sm.summarize(S((2.70, 1.60), (0.05, 0.02), (0.0, 0.0), (2.70, 1.60), (2.70, 1.60)))
check("summarize: 2 empty-nozzle shots -> only 3 good, not proposed", not r["ok"] and "nothing on the nozzle" in r["why"], r)
r = sm.summarize(S((2.70, 1.60), (2.72, 1.62), (2.69, 1.59), (2.71, 1.61)) + [{"angle": 0.0, "w": None, "h": None,
                                                                              "error": "No result found"}])
check("summarize: 4 good + 1 failed shot -> ok", r["ok"] and r["n"] == 4, r)

# simulated machine: package with pads but NO body size, tray 1 x 5
head = machine.getDefaultHead()
n1 = head.getNozzles()[0]
pk = Package("SOD-NOSIZE")
fp = Footprint()
for name, x in (("1", -1.6), ("2", 1.6)):
    p = Footprint.Pad()
    p.setName(name)
    p.setX(x)
    p.setY(0.0)
    p.setWidth(0.8)
    p.setHeight(1.0)
    fp.addPad(p)
pk.setFootprint(fp)
pk.addCompatibleNozzleTip(n1.getNozzleTip())
cfg.addPackage(pk)
part = Part("D-NOSIZE")
part.setHeight(Length(1.0, mm))
part.setPackage(pk)
cfg.addPart(part)
tray = ReferenceTrayFeeder()
tray.setName("TRAY-N")
tray.setPart(part)
tray.setLocation(Location(mm, 100, 150, -20, 0))
tray.setOffsets(Location(mm, 4, 4, 0, 0))
tray.setTrayCountX(5)
tray.setTrayCountY(1)
tray.setFeedCount(1)
tray.setEnabled(True)
machine.addFeeder(tray)
machine.setEnabled(True)
oppnp.run_machine_task(machine, lambda: machine.home())
check("simulated machine homed", machine.isHomed())
log = []
res = oppnp.run_machine_task(machine, lambda: sm.measure(machine, part, tray, n1, log.append))
shots = res["shots"]
check("5 shots at 0/90/180/270/0 deg", [s["angle"] for s in shots] == list(sm.ANGLES), shots)
check("every shot measured a rectangle", all(s.get("w") for s in shots), shots)
s0 = res["summary"]
check("the shots agree (same width / height at every turn: OpenPnP's orientation)", s0["ok"], s0)
check("measured size plausible for pads 4.0 x 1.0 mm (the simulated camera draws the pads)",
      s0["w"] and 3.0 < s0["w"] < 5.0 and 0.6 < s0["h"] < 1.6, s0)
check("part back into the tray: feed count as before (1), nozzle empty", tray.getFeedCount() == 1
      and n1.getPart() is None and "returned" in res["back"], (tray.getFeedCount(), res["back"]))
check("nothing applied: package still without body size", pk.getFootprint().getBodyWidth() == 0.0)
_Sys.out.println("\n".join("    log: " + l for l in log))

# end to end: OpenPnP's own size check (BodySize) rejects the part without body size, accepts it after applying
from org.openpnp.machine.reference.vision import AbstractPartAlignment, ReferenceBottomVision
from org.openpnp.model import Abstract2DLocatable, Board, BoardLocation, Placement
from lumen import picksafety, testplace
bvs = AbstractPartAlignment.getInheritedVisionSettings(part, True)
bvs.setCheckPartSizeMethod(ReferenceBottomVision.PartSizeCheckMethod.BodySize)
bvs.setCheckSizeTolerancePercent(20)
board = Board()
pl = Placement("D1")
pl.setPart(part)
pl.setLocation(Location(mm, 10, 10, 0, 90.0))
pl.setSide(Abstract2DLocatable.Side.Top)
board.addPlacement(pl)
bl = BoardLocation(board)
bl.setGlobalSide(Abstract2DLocatable.Side.Top)
bl.setLocation(Location(mm, 50.0, 50.0, -10.0, 0.0))


def align():
    tray.feed(n1)
    n1.moveToPickLocation(tray)
    n1.pick(part, tray)
    n1.moveToSafeZ()
    try:
        AbstractPartAlignment.getPartAlignment(part).findOffsets(part, bl, pl, n1)
        return "aligned"
    except testplace._errors() as e:                 # Java exceptions too
        return "refused: %s" % e
    finally:
        testplace._give_back(tray, n1)


before = oppnp.run_machine_task(machine, align)
check("OpenPnP size check without body size: refused (width too large ... nominal 0)", "too large" in before, before)
picksafety.apply_size(pk, s0["w"], s0["h"])
after = oppnp.run_machine_task(machine, align)
check("... after applying the measured %.2f x %.2f mm: OpenPnP aligns the part (placement at 90 deg)" % (s0["w"], s0["h"]),
      after == "aligned", after)
check("tray count unchanged after both trials", tray.getFeedCount() == 1, tray.getFeedCount())
_Sys.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
_Sys.exit(0 if all(results) else 1)
