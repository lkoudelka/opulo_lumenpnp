# Preflight > Pick safety on OpenPnP's simulated machine (stock config), headless: proposals from log lines, the
# window's tables, Apply (body size, size check, part-on high, part-off) on real OpenPnP objects.
#   tests/run_picksafety_sim.sh
import os
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sys.path.insert(0, HERE)
sandbox = sys.argv[1]

from java.io import File
from java.lang import System as _Sys
from org.openpnp.model import Configuration, Package, Part, Footprint, LengthUnit

Configuration.initialize(File(sandbox))
Configuration.get().load()
cfg = Configuration.get()
machine = cfg.getMachine()
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    _Sys.out.println("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


from lumen import picksafety as ps, picksafetyui as ui, uihelp
import test_picksafety_lines as tl                      # the synthetic pick log of tests/test_picksafety.py

n1 = machine.getDefaultHead().getNozzles()[0]
tip = n1.getNozzleTip()
for pid, part in (("RES_0603", "RES_0603-10k"), ("CAPC_2220", "CAP 2220 1kV")):
    pk = Package(pid)
    pk.setFootprint(Footprint())
    cfg.addPackage(pk)
    p = Part(part)
    p.setPackage(pk)
    cfg.addPart(p)
d = os.path.join(sandbox, "project")
os.makedirs(d)
board = os.path.join(d, "t.board.xml")
with open(board, "w") as f:
    f.write('''<openpnp-board version="1.1" name="t.board.xml"><dimensions units="Millimeters" x="0.0" y="0.0" z="0.0" rotation="0.0"/>
<placements>
<placement version="1.4" side="Top" id="R8" part-id="RES_0603-10k" type="Placement" enabled="true" rank="0"><location units="Millimeters" x="1.0" y="6.0" z="0.0" rotation="0.0"/></placement>
<placement version="1.4" side="Top" id="C11" part-id="CAP 2220 1kV" type="Placement" enabled="true" rank="0"><location units="Millimeters" x="5.0" y="6.0" z="0.0" rotation="0.0"/></placement>
</placements></openpnp-board>''')
jobfile = os.path.join(d, "t.board.job.xml")
with open(jobfile, "w") as f:
    f.write('''<openpnp-job version="2.0"><root-panel version="2.0"><dimensions units="Millimeters" x="0.0" y="0.0" z="0.0" rotation="0.0"/>
<placements/><children><object class="org.openpnp.model.BoardLocation" side="Top" id="Brd1" file-name="%s" check-fiducials="false" locally-enabled="true">
<location units="Millimeters" x="100.0" y="100.0" z="0.0" rotation="0.0"/></object></children><pseudo-placement-ids/></root-panel></openpnp-job>''' % board)
job = cfg.loadJob(File(jobfile))
check("bottom camera mm/px read the way OpenPnP's size check converts", ps.bottom_upp(machine) > 0, ps.bottom_upp(machine))
sense = ps.sense_names(machine)
lines = [l.replace("VAC1", sense.get("N1", "VAC1")) for l in tl.LINES if " N2" not in l and "VAC2" not in l]


class Frame(object):
    def __init__(self, t=""):
        self.content = None

    def __getattr__(self, n):
        return lambda *a, **k: None

    def setContentPane(self, c):
        self.content = c


class Pane(object):
    OK_OPTION = 0
    OK_CANCEL_OPTION = 2
    shown = []

    @classmethod
    def showMessageDialog(cls, p, m, *a):
        cls.shown.append(m)

    @classmethod
    def showConfirmDialog(cls, p, m, *a):
        cls.shown.append(m)
        return 0


class Tab(object):
    def getJob(self):
        return job


class G(object):
    def getJobTab(self):
        return Tab()


class Scr(object):
    def getScriptsDirectory(self):
        return File(os.path.join(sandbox, "scripts"))


ui.JFrame = Frame
ui.JOptionPane = Pane
logged = []
ps_log_lines = ps.log_lines
ps.log_lines = lambda d: lines
w = ui.PickSafety(machine, G(), Scr(), None, logged.append)
frame_content = w.frame.content
check("every button / column / option of the window described", not uihelp.missing(frame_content, "pick_safety"),
      uihelp.missing(frame_content, "pick_safety")[:5])
rows = dict((x["id"], x) for x in w.smodel.rows)
check("size table: one row per job package; RES_0603 learned and ticked (no body size yet), CAPC_2220 too few picks",
      sorted(rows) == ["CAPC_2220", "RES_0603"] and rows["RES_0603"]["apply"] and not rows["CAPC_2220"]["apply_ok"]
      and "EMPTY" in rows["RES_0603"]["note"], [(k, x["apply"], x["note"]) for k, x in sorted(rows.items())])
v = w.vmodel.rows[0]
check("vacuum row of N1: no proposal before free air is measured, says so", v["high"] is None and "free air" in v["why_on"], v["why_on"])
w.free[str(n1.getName())] = [(t, 254 - 0.02 * t) for t in range(50, 1500, 25)]
w.vmodel.rows = ui.vacuum_rows(machine, w.parsed, w.free)
v = w.vmodel.rows[0]
tip.setVacuumLevelPartOnLow(215.0)
tip.setVacuumLevelPartOnHigh(232.0)
w.vmodel.rows = ui.vacuum_rows(machine, w.parsed, w.free)
v = w.vmodel.rows[0]
v["off"] = True
check("after measuring: part-on high and part-off proposed (part-off NOT ticked by default)",
      v["high"] is not None and v["probe"] is not None and w.vmodel.rows[0]["off_ok"], (v["high"], v["probe"], v["why_off"]))
done = w.apply(ask=False)
fp = cfg.getPackage("RES_0603").getFootprint()
u = ps.bottom_upp(machine)
check("Apply: RES_0603 body = measured 38 x 21 px x the bottom camera's mm/px (orientation as measured)",
      abs(fp.getBodyWidth() - round(38 * u, 2)) < 0.006 and abs(fp.getBodyHeight() - round(21 * u, 2)) < 0.006,
      (fp.getBodyWidth(), fp.getBodyHeight(), 38 * u, 21 * u))
bvs = [s for k, (s, parts) in ps.size_check_settings(job, machine).items()]
check("Apply: the job's bottom-vision settings use BodySize %d %%" % ps.TOLERANCE_PERCENT,
      bvs and all(str(s.getCheckPartSizeMethod()) == "BodySize" and s.getCheckSizeTolerancePercent() == ps.TOLERANCE_PERCENT
                  for s in bvs), [(str(s.getCheckPartSizeMethod()), s.getCheckSizeTolerancePercent()) for s in bvs])
check("Apply: part-on high set, part-off Absolute with probing, dwell 0, after place",
      tip.getVacuumLevelPartOnHigh() == v["high"] and str(tip.getMethodPartOff()) == "Absolute"
      and tip.getPartOffProbingMilliseconds() == v["probe"] and tip.getPartOffDwellMilliseconds() == 0
      and tip.isPartOffCheckAfterPlace() and tip.getVacuumLevelPartOffLow() == v["low"], done)
check("every change logged with the old value", len(logged) == len(done) and all("(was" in x for x in logged), logged)
check("CAPC_2220 (too few picks) untouched", cfg.getPackage("CAPC_2220").getFootprint().getBodyWidth() == 0.0)
# free air: the valve gets actuate(boolean), not actuate(double) (bench 26 Nov: "VAC1.actuate(1.0)" sent nothing).
# A real ReferenceActuator (value type Boolean) remembers which overload it got.
from org.openpnp.spi.base.AbstractActuator import ActuatorCoordinationEnumType as _Coord
valve = n1.getVacuumActuator()
valve.setCoordinatedBeforeActuateEnum(_Coord.None)     # actuated outside a machine task here
machine.setEnabled(True)
valve.actuate(True)
plain = valve.getLastActuationValue()
ps._actuate(valve, True)
on = valve.getLastActuationValue()
ps._actuate(valve, False)
off = valve.getLastActuationValue()
check("free air: valve switched through actuate(boolean) (a plain Jython actuate(True) gives the double 1.0)",
      str(valve.getValueType()) == "Boolean" and str(plain) == "1.0" and str(on).lower() == "true" and str(off).lower() == "false",
      (str(plain), str(on), str(off)))

_Sys.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
_Sys.exit(0 if all(results) else 1)
