# Machine Calibration on OpenPnP's SIMULATED machine (stock config, NullDriver), real OpenPnP objects, headless.
#   tests/run_machinecal_sim.sh
# Real: machine, head, nozzle, nozzle tips (manual tip change -> ManualLoadException), homing, motion, Swing EDT,
# configuration save, head / tip settings written by the steps.  Faked (they need OpenPnP's main window or the
# real cameras / vacuum): the Issues & Solutions list (fake issues that behave like OpenPnP's: Accept submits a
# machine task, the success / error callback runs on the Swing thread), circle detection, target detection,
# vacuum contact probe, OpenPnP's precise nozzle offset routine.
import os
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "lib"))
sandbox = sys.argv[1]

from java.io import File
from java.lang import Runnable, System as _Sys
from java.util.concurrent import Callable
from javax.swing import SwingUtilities
from org.openpnp.model import Configuration, LengthUnit, Location
from org.openpnp.machine.reference import ReferenceNozzleTip
from org.openpnp.spi.base.AbstractHead import VisualHomingMethod
from org.openpnp.machine.reference.ReferenceNozzleTipCalibration import RecalibrationTrigger

Configuration.initialize(File(sandbox))
Configuration.get().load()
machine = Configuration.get().getMachine()
mm = LengthUnit.Millimeters
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    _Sys.out.println("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


from lumen import machinecal, nozzlecal, oppnp, zprobe

head = machine.getDefaultHead()
n1 = head.getNozzles()[0]
cam = head.getDefaultCamera()
up = [c for c in machine.getCameras() if str(c.getLooking()) == "Up"][0]
nt1 = n1.getNozzleTip()
n08 = ReferenceNozzleTip()
n08.setName("N08")
machine.addNozzleTip(n08)
n1.addCompatibleNozzleTip(n08)
n08.getCalibration().setEnabled(True)
n1.setManualNozzleTipChangeLocation(Location(mm, 20, 20, 0, 0))
SAFE = n1.getSafeZ().convertToUnits(mm).getValue() if n1.getSafeZ() is not None else 0.0
PZ, SZ = SAFE - 12.0, SAFE - 14.5
head.setCalibrationPrimaryFiducialLocation(Location(mm, 60, 60, PZ, 0))
head.setCalibrationSecondaryFiducialLocation(Location(mm, 60, 20, SZ, 0))
up.setHeadOffsets(Location(mm, 120, 40, PZ + 1.0, 0))
_Sys.out.println("sim: safe Z %.2f, primary Z %.2f, secondary Z %.2f, tips %s / N08" % (SAFE, PZ, SZ, nt1.getName()))
machine.setEnabled(True)
oppnp.run_machine_task(machine, lambda: machine.home())
check("simulated machine homed", machine.isHomed())


# ------------------------------------------------------------------ fakes that behave like OpenPnP
class _Call(Callable):
    def __init__(self, fn):
        self.fn = fn

    def call(self):
        return self.fn()


class _Run(Runnable):
    def __init__(self, fn):
        self.fn = fn

    def run(self):
        self.fn()


class FakeSolutions(object):
    def isSolutionsIssueSolved(self, i):
        return i.solved

    def setSolutionsIssueSolved(self, i, v):
        i.solved = bool(v)


class Prop(object):
    def __init__(self, v):
        self.v = v

    def get(self):
        return self.v

    def set(self, v):
        self.v = v


class FakeIssue(object):
    """Accept = OpenPnP's submitUiMachineTask: the effect runs as a machine task, then the success
    (solved) or error (state restored, not solved) callback on the Swing thread."""
    def __init__(self, title, subject, effect=None):
        self.title, self.subject, self.effect = title, subject, effect
        self.state, self.solved, self.choice, self.accepts = "Open", False, None, 0
        self.props = [Prop(20)]

    def getIssue(self):
        return self.title

    def getSubject(self):
        return self.subject

    def getState(self):
        return self.state

    def getProperties(self):
        return self.props

    def setChoice(self, c):
        self.choice = c

    def setState(self, st):
        if str(st) != "Solved":
            self.state = str(st)
            return
        self.accepts += 1
        box = {}

        def work():
            try:
                if self.effect:
                    self.effect(self)
                box["ok"] = True
            except Exception as e:
                box["e"] = e
            def cb():
                if "ok" in box:
                    self.state, self.solved = "Solved", True
                else:
                    log.append(("openpnp error", str(box["e"])))
            SwingUtilities.invokeLater(_Run(cb))
        machine.submit(_Call(work))                  # returns at once, like OpenPnP's Accept


log = []


def at_accept(name):
    def eff(issue):
        l = None
        if name.startswith("nozzle"):
            n = issue.subject
            l = n.getLocation().convertToUnits(mm)
            if name == "nozzle-primary" and n == n1:
                p = head.getCalibrationPrimaryFiducialLocation()
                head.setCalibrationPrimaryFiducialLocation(p.derive(l, False, False, True, False))
            if name == "nozzle-secondary":
                p = head.getCalibrationSecondaryFiducialLocation()
                head.setCalibrationSecondaryFiducialLocation(p.derive(l, False, False, True, False))
        elif name == "bottom":
            l = n1.getLocation().convertToUnits(mm)
            if issue.choice is not False:
                raise Exception("auto focus would be used")
        else:
            l = cam.getLocation().convertToUnits(mm)
        log.append(("accept", name, getattr(issue.subject, "getName", lambda: "")(), round(l.getX(), 3),
                    round(l.getY(), 3), round(l.getZ(), 3), n1.getNozzleTip().getName(), issue.props[0].get()))
    return eff


T = machinecal.issue_title
ISSUES = [
    FakeIssue(T("primary_fid"), cam, at_accept("primary")),
    FakeIssue(T("secondary_fid"), cam, at_accept("secondary")),
    FakeIssue(T("n1_primary", nozzle="N1"), n1, at_accept("nozzle-primary")),
    FakeIssue(T("n1_secondary", nozzle="N1"), n1, at_accept("nozzle-secondary")),
    FakeIssue(T("bottom_cam", camera=up.getName()), up, at_accept("bottom")),
    FakeIssue(T("precise", nozzle="N1"), n1),
    FakeIssue(T("settle"), up, at_accept("settle-bottom")),          # top camera: no issue = already adaptive
    FakeIssue(T("backlash", axis=cam.getAxisX().getName()), cam, at_accept("backlash-x")),
    FakeIssue(T("backlash", axis=cam.getAxisY().getName()), cam, at_accept("backlash-y")),
]


class UI(object):
    def __init__(self, answers):
        self.answers, self.asked, self.stop = answers, [], False

    def say(self, s):
        _Sys.out.println("    | " + s)

    def ask(self, title, html, pictures, buttons):
        self.asked.append((title, list(pictures), list(buttons)))
        for k, v in self.answers.items():
            if title.startswith(k):
                return v
        return buttons[-1]                            # unknown question: the last button (Cancel)

    def visual_check(self, issue, camera, expected_px, reason):
        self.asked.append(("visual check", camera.getName(), reason))
        return self.answers.get("visual check", "cancel")

    def stop_requested(self):
        return self.stop


TARGET = {"home_calls": 0, "on_home_first": True}
moves, homes, probes = [], [], []


class Cal(machinecal.Calibrator):
    def solutions(self):
        return FakeSolutions()

    def issues(self):
        return list(ISSUES)

    def detect(self, camera, px):
        if camera == cam and self.det_wrong.get("secondary") and abs(cam.getLocation().getY() - 20) < 0.01:
            self.det_wrong["secondary"] = False
            return (px * 1.8, 3.0)                    # another ring: must go to the visual check
        return (px, 2.0)

    def target_at(self, x, y):
        TARGET["home_calls"] += 1
        hx, hy = self.visual_home_xy()
        if abs(x - hx) < 0.01 and abs(y - hy) < 0.01 and TARGET["on_home_first"]:
            TARGET["on_home_first"] = False
            return (x, y, 5.36, 0.95)                 # first look: the target lies on the visual home
        park = self.opt.get("park")
        if park and abs(x - park[0]) < 0.01 and abs(y - park[1]) < 0.01:
            return (x, y, 5.36, 0.95)
        return None

    def move(self, hm, x, y, z=None):
        moves.append((hm.getName(), x, y, z))
        machinecal.Calibrator.move(self, hm, x, y, z)

    def home(self):
        zs = [(n.getName(), n.getLocation().convertToUnits(mm).getZ()) for n in self.nozzles]
        homes.append({"zs": zs, "looked": TARGET["home_calls"]})
        m = head.getVisualHomingMethod()
        head.setVisualHomingMethod(VisualHomingMethod.None)    # no fiducial in the simulated image
        try:
            machinecal.Calibrator.home(self)
        finally:
            head.setVisualHomingMethod(m)


def fake_probe(nozzle, x, y, z_start, z_floor, max_travel=2.0, log=None, **k):
    probes.append((nozzle.getName(), x, y, z_start, z_floor))
    return {"z": z_start - 1.55, "readings": []}
zprobe.probe = fake_probe


def fake_precise(machine_, nozzles, park, carrier, log=None, save=None):
    log_ = [n.getName() for n in nozzles]
    precise_calls.append((log_, park, carrier.getName(), n1.getNozzleTip().getName()))
    return {"offsets": dict((n.getName(), (n.getHeadOffsets(), n.getHeadOffsets())) for n in nozzles), "final": park}
precise_calls = []
nozzlecal.calibrate_openpnp = fake_precise

# ------------------------------------------------------------------ full run
ui = UI({"Calibration target on the visual home": "Done", "Change the nozzle tip by hand": "Done",
         "Save the configuration?": "Save", "visual check": "accept"})
opts = {"z_method": "probe", "optional": True, "pause_each": False, "swap_tip": True, "bottom_tip": "N08",
        "park": (100.0, 100.0)}
cal = Cal(machine, ui, opts, os.path.join(sandbox, "lumen"))
cal.det_wrong = {"secondary": True}
mxml = os.path.join(sandbox, "machine.xml")
mtime0 = os.path.getmtime(mxml)
out = {}
for s in machinecal.STEPS:
    try:
        out[s.key] = cal.run(s.key)
        _Sys.out.println("  %-14s %s" % (s.key, out[s.key]))
    except machinecal.Stop as e:
        out[s.key] = "STOP %s" % e
        _Sys.out.println("  %-14s STOP %s" % (s.key, e))
        break
SwingUtilities.invokeAndWait(_Run(lambda: None))

check("all 15 steps ran to the end", len(out) == len(machinecal.STEPS) and not any(v.startswith("STOP") for v in out.values()),
      [k for k, v in out.items() if v.startswith("STOP")])
check("backup of machine.xml written", any(f.startswith("machine-before-") for f in os.listdir(os.path.join(sandbox, "lumen", "calibration"))))
check("target on the visual home: asked with pictures, then homed again",
      ui.asked[0][0].startswith("Calibration target on the visual home") and "cal-home-disc.png" in ui.asked[0][1]
      and out["prepare"].startswith("target removed"), out["prepare"])
check("every homing: all nozzles at safe Z and the visual home looked at first",
      homes and all(z >= SAFE - 0.01 for h in homes for _, z in h["zs"]) and all(h["looked"] > 0 for h in homes), homes)
acc = [l for l in log if l[0] == "accept"]
names = [a[1] for a in acc]
check("OpenPnP Accept in the guide's order",
      names == ["primary", "secondary", "nozzle-primary", "nozzle-secondary", "bottom", "settle-bottom", "backlash-x", "backlash-y"],
      names)
a = dict((x[1], x) for x in acc)
check("camera at the primary fiducial at Accept", a["primary"][3:5] == (60.0, 60.0), a["primary"])
check("wrong secondary detection -> visual check, then accepted",
      any(q[0] == "visual check" for q in ui.asked) and "secondary" in a)
check("feature diameter set from the known fiducial size", a["primary"][7] > 3, a["primary"][7])
check("probe window from the stored Z (start +1.5, 2.5 mm travel)",
      probes[0][3] == PZ + 1.5 and abs(probes[0][4] - (PZ - 1.0)) < 1e-9, probes[0])
check("N1 at the measured contact Z at Accept (primary)", abs(a["nozzle-primary"][5] - (PZ + 1.5 - 1.55)) < 0.01, a["nozzle-primary"])
check("secondary probed at the secondary fiducial", probes[1][1:3] == (60.0, 20.0) and probes[1][3] == SZ + 1.5, probes[1])
check("one nozzle only: N2 step skipped", out["n2_primary"].startswith("skipped"), out["n2_primary"])
check("N08 tip loaded by hand for the bottom camera (OpenPnP's manual change, picture)",
      a["bottom"][6] == "N08" and any(q[0] == "Change the nozzle tip by hand" and "cal-tip-swap.png" in q[1] for q in ui.asked))
check("bottom camera: N1 over the camera at the primary fiducial Z, 'use nozzle Z' (no auto focus)",
      a["bottom"][3:5] == (120.0, 40.0) and abs(a["bottom"][5] - head.getCalibrationPrimaryFiducialLocation().getZ()) < 0.01, a["bottom"])
check("tips back as before", n1.getNozzleTip() == nt1 and out["tips_back"].startswith("loaded"), out["tips_back"])
check("precise offsets: after the tips are back, carrier N1, park spot", precise_calls == [(["N1"], (100.0, 100.0), "N1", nt1.getName())],
      precise_calls)
check("top camera: OpenPnP offers no settling change -> no Accept", out["settle_top"].startswith("nothing to do"), out["settle_top"])
p = head.getCalibrationPrimaryFiducialLocation().convertToUnits(mm)
hf = head.getHomingFiducialLocation().convertToUnits(mm)
check("homing: ResetToFiducialLocation, homing fiducial = primary X/Y",
      head.getVisualHomingMethod() == VisualHomingMethod.ResetToFiducialLocation
      and abs(hf.getX() - p.getX()) < 1e-6 and abs(hf.getY() - p.getY()) < 1e-6)
check("runout calibration on tip change for the enabled tip", n08.getCalibration().getRecalibrationTrigger() == RecalibrationTrigger.NozzleTipChange)
check("verify: homed, fiducial within 0.1 mm, saved", out["verify"].startswith("verified") and "saved" in out["verify"]
      and os.path.getmtime(mxml) >= mtime0, out["verify"])
contact = dict(((x, y), zs - 1.55) for _, x, y, zs, _ in probes)
pz_now = head.getCalibrationPrimaryFiducialLocation().convertToUnits(mm).getZ()
bad = [m for m in moves if m[0] != cam.getName() and m[3] is not None
       and not ((m[1], m[2]) in contact and m[3] >= contact[(m[1], m[2])] + 0.5 - 1e-6)
       and not ((m[1], m[2]) == (120.0, 40.0) and abs(m[3] - pz_now) < 1e-6)]
check("nozzle lowered only to 0.5 mm above a measured contact (then slow) or over the bottom camera at the fiducial Z",
      not bad and len([m for m in moves if m[0] != cam.getName() and m[3] is not None]) == 3, (bad, moves))
check("all nozzles back at safe Z", all(n.getLocation().convertToUnits(mm).getZ() >= SAFE - 0.01 for n in head.getNozzles()))

# ------------------------------------------------------------------ an OpenPnP error is reported, not ignored
bad = FakeIssue("x", cam, lambda i: (_ for _ in ()).throw(Exception("Subject not found.")))
try:
    cal.accept(bad, "test")
    check("OpenPnP error -> Stop", False)
except machinecal.Stop as e:
    check("OpenPnP error -> Stop", "did not solve" in str(e), str(e))
again = FakeIssue("y", cam)
again.solved, again.state = True, "Solved"
cal.accept(again, "again")
check("an already solved issue is reopened and accepted again", again.accepts == 1 and again.solved)

# ------------------------------------------------------------------ cancel: nothing moves after it
machine.setEnabled(False)
machine.setEnabled(True)
ui2 = UI({"Before homing": "Cancel"})
cal2 = Cal(machine, ui2, opts, os.path.join(sandbox, "lumen"))
n_homes = len(homes)
try:
    cal2.run("prepare")
    check("not homed + Cancel at 'Before homing' -> Stop", False)
except machinecal.Stop:
    check("not homed + Cancel at 'Before homing' -> Stop, no homing",
          len(homes) == n_homes and ui2.asked[0][0] == "Before homing" and "cal-nozzles-level.png" in ui2.asked[0][1])
ui3 = UI({"Before homing": "Home"})
cal3 = Cal(machine, ui3, opts, os.path.join(sandbox, "lumen"))
TARGET["on_home_first"] = False
check("not homed + Home -> homed", cal3.run("prepare") == "homed" and machine.isHomed())

ui4 = UI({"Calibration target on the primary fiducial": "It is free"})
cal4 = Cal(machine, ui4, opts, os.path.join(sandbox, "lumen"))
cal4.det_wrong = {}
TARGET["on_home_first"] = True
r = cal4.run("primary_fid")
check("detection overruled by you ('It is free') -> step continues", r.startswith("fiducial at")
      and ui4.asked[0][0] == "Calibration target on the primary fiducial", (r, ui4.asked[:1]))

ui5 = UI({"Change the nozzle tip by hand": "Done", "visual check": "accept"})
cal5 = Cal(machine, ui5, opts, os.path.join(sandbox, "lumen"))
cal5.run("bottom_cam")
cal6 = Cal(machine, UI({"Change the nozzle tip by hand": "Done"}), opts, os.path.join(sandbox, "lumen"))
r = cal6.run("tips_back")
check("after a restart between bottom camera and 'tips back' the tips before are still known",
      n1.getNozzleTip() == nt1 and r.startswith("loaded"), r)

# no swap (default): the bottom camera step uses the tip on N1, nobody is asked to change a tip
log[:] = []
ui7 = UI({"visual check": "accept"})
o7 = dict(opts)
o7["swap_tip"] = False
cal7 = Cal(machine, ui7, o7, os.path.join(sandbox, "lumen"))
r = cal7.run("bottom_cam")
acc7 = [l for l in log if l[0] == "accept" and l[1] == "bottom"]
check("no swap (default): bottom camera with the tip on N1, no tip change asked",
      acc7 and acc7[0][6] == nt1.getName() and n1.getNozzleTip() == nt1
      and not any(q[0].startswith("Change the nozzle tip") for q in ui7.asked), (r, acc7, ui7.asked))
check("no swap: 'tips back' has nothing to do", cal7.run("tips_back") == "tips already as before")

# Nozzle Offset Calibration runs at 50 % machine speed and puts the previous speed back (nozzlecal.at_speed)
seen = []
machine.setSpeed(0.98)
oppnp.run_machine_task(machine, lambda: nozzlecal.at_speed(machine, 0.5, lambda: seen.append(machine.getSpeed()), log=lambda t: None))
check("nozzle cal: runs at 50 % speed, 98 % restored afterwards", seen == [0.5] and abs(machine.getSpeed() - 0.98) < 1e-9,
      (seen, machine.getSpeed()))


def _fail():
    seen.append(machine.getSpeed())
    raise RuntimeError("calibration stopped")
try:
    oppnp.run_machine_task(machine, lambda: nozzlecal.at_speed(machine, 0.5, _fail, log=lambda t: None))
except RuntimeError:
    pass
check("nozzle cal: speed restored also when the calibration stops", seen[-1] == 0.5 and abs(machine.getSpeed() - 0.98) < 1e-9,
      machine.getSpeed())
machine.setSpeed(0.3)
oppnp.run_machine_task(machine, lambda: nozzlecal.at_speed(machine, 0.5, lambda: seen.append(machine.getSpeed()), log=lambda t: None))
check("nozzle cal: a slower speed set by the person is kept (never faster)", seen[-1] == 0.3 and machine.getSpeed() == 0.3)
machine.setSpeed(1.0)

_Sys.out.println("%d/%d passed" % (sum(results), len(results)))
machine.setEnabled(False)
_Sys.exit(0 if all(results) else 1)
