# -*- coding: utf-8 -*-
"""Machine calibration in the order of the Opulo LumenPnP V4.1 guide (Jython, OpenPnP GUI).

https://docs.opulo.io/openpnp/v4-1/issues-solutions/fundamental/primary-cal-fid-pos/ and the pages after it.
Every calibration is done by OpenPnP's own Issues & Solutions routine (the same code as its Accept
button: Solutions.Issue.setState(Solved)); this module only does what the person does in the guide:
move the camera / nozzle to the right place, measure the touching Z, change nozzle tips, carry the
calibration target, and check the result.  Nothing in OpenPnP or machine.xml is patched; the settings
changed are the ones the Opulo guide changes.

Safety rules (all steps):
- every move goes at safe Z; Z is lowered only by the vacuum contact probe (lumen.zprobe: 0.05 mm steps,
  slow, stops at the first contact, max 2.5 mm travel), to the measured contact Z (last 0.5 mm slow), at
  the bottom camera to the calibration fiducial Z, and inside OpenPnP's own routines;
- before any homing: every nozzle at safe Z, and the visual home is checked to be free of the
  calibration target (camera), or the person confirms it with a picture when the machine is not homed;
- the calibration target is never left on the visual home: it is carried back to its park spot and
  checked; if it cannot be found there, the calibration stops before anything else moves.
Pure helpers (no OpenPnP) are at the top, for tests in CPython.
"""
from __future__ import absolute_import, division, print_function

import math
import os
import time

DOC = "https://docs.opulo.io/openpnp/v4-1/"
DEFAULT_PARK = (240.624, 189.420)          # target park spot (bench 2026-11-06), setting "target_park"
NOMINAL_FIDUCIAL_MM = 1.0                  # Opulo datum board fiducials, used only if OpenPnP has none yet
PROBE_ABOVE = 1.5                          # contact probe starts this far above the stored fiducial Z
PROBE_TRAVEL = 2.5                         # and goes at most this far down
MAX_Z_CHANGE = 1.0                         # a measured fiducial Z further from the stored one is asked first
HOME_TOL_MM = 0.1                          # after homing the primary fiducial must be this close


class Step(object):
    def __init__(self, key, title, kind, doc, what, moves, manual=""):
        self.key, self.title, self.kind, self.doc = key, title, kind, doc
        self.what, self.moves, self.manual = what, moves, manual


STEPS = [
    Step("prepare", "Safety check, backup, homing", "setup", DOC + "preflight/homing-prep/",
         "Backs up machine.xml, checks no job runs, nozzles to safe Z, checks the visual home is free of the "
         "calibration target, homes the machine if it is not homed.",
         "Z up; homing.", "Only if not homed: confirm nozzles up and the target at its park spot (picture)."),
    Step("primary_fid", "Primary calibration fiducial position & initial camera calibration", "fundamental",
         DOC + "issues-solutions/fundamental/primary-cal-fid-pos/",
         "Camera over the primary fiducial, feature diameter from the known fiducial size (checked by detection), "
         "OpenPnP's Accept: preliminary camera calibration and the exact fiducial X/Y.",
         "Camera only (small calibration pattern around the fiducial).",
         "Only if the detection does not match: check the green circle in the camera view."),
    Step("secondary_fid", "Secondary calibration fiducial position", "fundamental",
         DOC + "issues-solutions/fundamental/secondary-cal-fid-pos/",
         "Same for the secondary fiducial (3D camera calibration).", "Camera only."),
    Step("n1_primary", "Nozzle N1 offsets for the primary fiducial", "fundamental",
         DOC + "issues-solutions/fundamental/n1-offset/",
         "N1 over the primary fiducial, touching Z measured by vacuum contact, OpenPnP's Accept: the primary "
         "fiducial Z (and N1 X/Y only if they were more than half a fiducial off).",
         "N1 goes down slowly onto the fiducial (contact probe) and back to safe Z.",
         "Option 'Z by hand': you jog N1 down until it touches, as in the Opulo guide."),
    Step("n1_secondary", "Nozzle N1 offsets for the secondary fiducial", "fundamental",
         DOC + "issues-solutions/fundamental/n1-offset-secondary/",
         "Same on the secondary fiducial: its Z.", "N1 goes down slowly onto the secondary fiducial."),
    Step("n2_primary", "Nozzle N2 offsets for the primary fiducial", "fundamental",
         DOC + "issues-solutions/fundamental/n2-offset/",
         "N2 over the primary fiducial, touching Z by vacuum contact, Accept: N2 Z equalised to N1.",
         "N2 goes down slowly onto the fiducial."),
    Step("bottom_cam", "Up-looking (bottom) camera position & initial calibration", "fundamental",
         DOC + "issues-solutions/fundamental/bottom-cam-pos/",
         "N1 with the tip it has (default) or, with the option 'swap', the N08 tip as in the Opulo guide, goes over "
         "the bottom camera at the primary fiducial Z ('Use nozzle Z', never auto focus), Accept: bottom camera "
         "position and the tip's vision diameter.  Then homing method ResetToFiducialLocation with the homing "
         "fiducial = primary fiducial X/Y.",
         "N1 over the bottom camera, down to the fiducial Z (with 'swap': the tip change position first).",
         "Only with the option 'swap': tip change N045 -> N08 by hand (picture)."),
    Step("tips_back", "Nozzle tips back as before", "setup", DOC + "preflight/nozzle-prep/",
         "Loads the tips that were on the nozzles before the bottom camera step (runout calibration if set).",
         "Tip change position; bottom camera for the runout calibration.", "Tip change by hand (picture)."),
    Step("precise", "Precise camera <-> nozzle N1 and N2 offsets (calibration target)", "fundamental",
         DOC + "issues-solutions/fundamental/n1-offset-precise/",
         "The calibration target is carried from its park spot onto the primary fiducial, OpenPnP's precise "
         "offset calibration runs for every nozzle, the target is carried back and checked at its park spot.",
         "Picks and places the calibration target (OpenPnP's calibration Z, no vacuum probing).",
         "Only if the target is not at its park spot: put it there (picture)."),
    Step("settle_top", "Adaptive camera settling (top camera)", "fundamental",
         DOC + "issues-solutions/fundamental/camera-settling-top/",
         "OpenPnP's Accept; already done when the camera is not on 'FixedTime'.", "Camera over the primary fiducial."),
    Step("settle_bottom", "Adaptive camera settling (bottom camera)", "fundamental",
         DOC + "issues-solutions/fundamental/camera-settling-bottom/",
         "OpenPnP's Accept; already done when the camera is not on 'FixedTime'.", "N1 over the bottom camera."),
    Step("backlash_x", "Backlash compensation X", "optional", DOC + "issues-solutions/optional/x-backlash/",
         "OpenPnP's Accept: measures X backlash on the primary fiducial (up to 15 minutes).",
         "Camera moves back and forth around the primary fiducial."),
    Step("backlash_y", "Backlash compensation Y", "optional", DOC + "issues-solutions/optional/y-backlash/",
         "Same for Y (up to 15 minutes).", "Camera moves back and forth around the primary fiducial."),
    Step("homing_prep", "Prepare for homing: homing fiducial, runout calibration on tip change", "setup",
         DOC + "prepare-for-homing/",
         "Homing method ResetToFiducialLocation, homing fiducial X/Y = primary fiducial X/Y, nozzle tip runout "
         "calibration 'NozzleTipChange' for every tip with calibration enabled.", "Nothing."),
    Step("verify", "Home, verify, save", "setup", DOC + "controlled-validation-test/introduction/",
         "Nozzles to safe Z, visual home checked free, homing (visual homing), the primary fiducial must be within "
         "0.1 mm of the camera centre.  Then the configuration is saved (you confirm).",
         "Z up; homing; camera to the primary fiducial."),
]
BY_KEY = dict((s.key, s) for s in STEPS)


# ---------------------------------------------------------------------------------------------- pure helpers
def check_detection(found_px, expected_px, offset_px, frame_px, tol=0.3):
    """Detected circle vs. the expected feature: (ok, reason).  found/expected = diameters in pixels,
    offset_px = distance of the circle centre from the image centre, frame_px = min(width, height)."""
    if found_px is None:
        return False, "nothing detected"
    if expected_px <= 0:
        return False, "no expected size known - check it by eye"
    r = found_px / float(expected_px)
    if abs(r - 1.0) > tol:
        return False, "detected %.0f px, expected %.0f px (%+.0f %%)" % (found_px, expected_px, (r - 1) * 100)
    if offset_px > frame_px / 4.0:
        return False, "detected %.0f px from the image centre - not the feature under the camera" % offset_px
    return True, "detected %.0f px (expected %.0f), %.0f px from the centre" % (found_px, expected_px, offset_px)


def probe_window(stored_z, safe_z, above=PROBE_ABOVE, travel=PROBE_TRAVEL):
    """(z_start, z_floor) for the contact probe from the stored fiducial Z, or None when the stored Z is
    not usable (not set, or not below safe Z) - then the person brings the nozzle close first."""
    if stored_z is None or math.isnan(stored_z) or stored_z == 0.0:
        return None
    start = stored_z + above
    if safe_z is not None and start >= safe_z:
        start = safe_z - 0.5
    if start <= stored_z:
        return None
    return start, start - travel


def z_change_ok(old_z, new_z, limit=MAX_Z_CHANGE):
    if old_z is None or old_z == 0.0 or math.isnan(old_z):
        return True
    return abs(new_z - old_z) <= limit


def issue_title(key, nozzle="N1", camera="Bottom", axis="x"):
    """OpenPnP's Issues & Solutions issue text for a step (OpenPnP 2.x develop, 2026)."""
    return {
        "primary_fid": "Primary calibration fiducial position and initial camera calibration.",
        "secondary_fid": "Secondary calibration fiducial position.",
        "n1_primary": "Nozzle %s offsets for the primary fiducial." % nozzle,
        "n1_secondary": "Nozzle %s offsets for the secondary fiducial." % nozzle,
        "n2_primary": "Nozzle %s offsets for the primary fiducial." % nozzle,
        "bottom_cam": "Determine the up-looking camera %s position and initial calibration." % camera,
        "precise": u"Calibrate precise camera ↔ nozzle %s offsets." % nozzle,
        "settle": "Use an adaptive camera settling method.",
        "backlash": "Calibrate backlash compensation for axis %s." % axis,
    }[key]


def manual_change_text(e):
    """OpenPnP's instructions from a manual nozzle tip change (ManualLoadException), or None."""
    texts = []
    while e is not None and len(texts) < 5:
        name = e.getClass().getName() if hasattr(e, "getClass") else type(e).__name__
        msg = getattr(e, "getMessage", None)
        msg = msg() if callable(msg) else str(e)
        texts.append((str(name), str(msg or "")))
        e = e.getCause() if hasattr(e, "getCause") else None
    if not any("ManualLoad" in n or "manual nozzle tip" in m for n, m in texts):
        return None
    for n, m in texts:
        if "manual nozzle tip" in m:
            return m.replace("Task interrupted: ", "").strip()
    return "Change the nozzle tip by hand."


def diff_rows(before, after):
    """[(name, before, after)] for the values that changed (snapshot dicts of strings)."""
    return [(k, before.get(k), after.get(k)) for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)]


def fmt_loc(loc):
    if loc is None:
        return "-"
    return "%.3f / %.3f / %.3f" % tuple(loc[:3])


# ---------------------------------------------------------------------------------------------- OpenPnP part
def _mm():
    from org.openpnp.model import LengthUnit
    return LengthUnit.Millimeters


def _xyz(loc):
    l = loc.convertToUnits(_mm())
    return (l.getX(), l.getY(), l.getZ())


def visual_home_xy(head):
    h = head.getHomingFiducialLocation().convertToUnits(_mm())
    if h.getX() == 0 and h.getY() == 0:
        h = head.getCalibrationPrimaryFiducialLocation().convertToUnits(_mm())
    return h.getX(), h.getY()


def target_on_visual_home(machine):
    """Top camera on the visual home: the calibration target seen there, or None.  Machine task, homed."""
    from lumen import nozzlecal
    head = machine.getDefaultHead()
    x, y = visual_home_xy(head)
    t = head.getCalibrationTestObjectDiameter()
    dia = t.convertToUnits(_mm()).getValue() if t is not None else 0.0
    if dia <= 0 or (x == 0 and y == 0):
        return None                                 # no calibration target / no visual home configured
    z = head.getCalibrationPrimaryFiducialLocation().convertToUnits(_mm()).getZ()
    d, _ = nozzlecal.look_disc(machine, x, y, z, dia)
    return d


def safe_home(machine, confirmed_unhomed=False):
    """Homing with the Lumen safety rules, inside a machine task: homed -> every nozzle to safe Z and the
    visual home checked free of the calibration target first; not homed -> only if the person confirmed
    (nozzles up, target parked).  After homing the visual home is checked again.  Returns a detail text,
    raises Stop."""
    if machine.isHomed():
        machine.getDefaultHead().moveToSafeZ()
        if target_on_visual_home(machine):
            raise Stop("the camera sees the calibration target on the visual home - put it on its park spot first")
    elif not confirmed_unhomed:
        raise Stop("not homed: confirm that the nozzles are up and the calibration target is parked")
    machine.home()
    if not machine.isHomed():
        raise Stop("homing did not complete")
    if target_on_visual_home(machine):
        raise Stop("after homing the camera sees the calibration target on the visual home - coordinates may be off")
    return "homed (nozzles at safe Z, visual home free)"


class Stop(Exception):
    """The person cancelled, or a safety check failed: nothing else moves."""


class Calibrator(object):
    """Runs the steps.  ui: say(text), ask(title, html, pictures, buttons) -> pressed button text,
    visual_check(issue, camera, expected_px, reason) -> 'accept' | 'cancel', stop_requested() -> bool.
    options: z_method 'probe'|'hand', pause_each (bool), optional (bool), park (x, y),
    swap_tip (bool, default False: the bottom camera step uses the tip on N1), bottom_tip ('N08', used with swap_tip)."""

    def __init__(self, machine, ui, options, lumen_dir=None):
        self.machine, self.ui, self.opt = machine, ui, options
        self.lumen_dir = lumen_dir
        self.head = machine.getDefaultHead()
        self.cam = self.head.getDefaultCamera()
        self.nozzles = list(self.head.getNozzles())
        self.n1 = self.nozzles[0]
        self.up = None
        from org.openpnp.spi import Camera
        for c in machine.getCameras():
            if c.getLooking() == Camera.Looking.Up:
                self.up = c
                break
        self.tips_before = None
        self.before = None

    # ---------------------------------------------------------------- plumbing
    def say(self, s):
        self.ui.say(s)

    def task(self, fn):
        from lumen import oppnp
        return oppnp.run_machine_task(self.machine, fn)

    def on_edt(self, fn):
        """Run fn on the Swing thread and wait; exceptions come back to the caller."""
        from java.lang import Runnable, Throwable
        from javax.swing import SwingUtilities
        box = {}

        class R(Runnable):
            def run(self):
                try:
                    box["r"] = fn()
                except (Exception, Throwable) as e:       # Python and Java exceptions
                    box["e"] = e
        if SwingUtilities.isEventDispatchThread():
            R().run()
        else:
            SwingUtilities.invokeAndWait(R())
        if "e" in box:
            raise box["e"]
        return box.get("r")

    def ask(self, title, html, pictures, buttons, must=None):
        """Question to the person (blocks this worker thread).  must: any other answer stops the run."""
        a = self.ui.ask(title, html, pictures, buttons)
        if must is not None and a != must:
            raise Stop("%s: %s" % (title, a or "closed"))
        return a

    def check_stop(self):
        if self.ui.stop_requested():
            raise Stop("stopped by you")

    # ---------------------------------------------------------------- snapshot / backup
    def snapshot(self):
        """The values the calibration may change, as strings (for the before/after table)."""
        h, mm = self.head, _mm()
        out = {}

        def loc(l):
            l = l.convertToUnits(mm)
            return "%.3f, %.3f, %.3f" % (l.getX(), l.getY(), l.getZ())
        out["primary fiducial"] = loc(h.getCalibrationPrimaryFiducialLocation())
        out["secondary fiducial"] = loc(h.getCalibrationSecondaryFiducialLocation())
        out["homing fiducial"] = loc(h.getHomingFiducialLocation())
        out["homing method"] = str(h.getVisualHomingMethod())
        for n in self.nozzles:
            out["%s head offsets" % n.getName()] = loc(n.getHeadOffsets())
            t = n.getNozzleTip()
            out["%s tip" % n.getName()] = t.getName() if t is not None else "-"
        for c in self.machine.getCameras():
            out["%s head offsets / location" % c.getName()] = loc(c.getHeadOffsets())
            u = c.getUnitsPerPixel().convertToUnits(mm)
            out["%s units per pixel" % c.getName()] = "%.6f, %.6f" % (u.getX(), u.getY())
            out["%s settle method" % c.getName()] = str(getattr(c, "getSettleMethod", lambda: "-")())
        for t in self.machine.getNozzleTips():
            try:
                cal = t.getCalibration()
                out["tip %s runout recalibration" % t.getName()] = str(cal.getRecalibrationTrigger())
                out["tip %s vision diameter" % t.getName()] = "%.3f" % cal.getCalibrationTipDiameter().convertToUnits(mm).getValue()
            except Exception:
                pass
        for a in self.machine.getAxes():
            try:
                out["axis %s backlash" % a.getName()] = "%s %.4f" % (a.getBacklashCompensationMethod(),
                                                                    a.getBacklashOffset().convertToUnits(mm).getValue())
            except Exception:
                pass
        return out

    def backup(self):
        import shutil
        from org.openpnp.model import Configuration
        src = os.path.join(str(Configuration.get().getConfigurationDirectory()), "machine.xml")
        d = os.path.join(self.lumen_dir or os.path.dirname(src), "calibration")
        if not os.path.isdir(d):
            os.makedirs(d)
        dst = os.path.join(d, "machine-before-%s.xml" % time.strftime("%Y%m%d-%H%M%S"))
        shutil.copy2(src, dst)
        return dst

    # ---------------------------------------------------------------- Issues & Solutions
    def solutions(self):
        return self.machine.getSolutions()

    def issues(self):
        sol = self.solutions()

        def find():
            from org.openpnp.model import Solutions
            if not sol.isTargeting(Solutions.Milestone.Calibration):
                sol.setTargetMilestone(Solutions.Milestone.Calibration)
            sol.findIssues()
            sol.publishIssues()
            return list(sol.getIssues())
        return self.on_edt(find)

    def issue(self, title, subject=None):
        for i in self.issues():
            if i.getIssue() == title and (subject is None or i.getSubject() == subject):
                return i
        return None

    def need_issue(self, title, subject=None):
        found = self.issues()
        for i in found:
            if i.getIssue() == title and (subject is None or i.getSubject() == subject):
                return i
        offered = [str(i.getIssue()) for i in found if str(i.getState()) != "Solved"][:8]
        raise Stop("OpenPnP does not offer '%s' (Issues & Solutions) - an earlier step is missing. Open issues: %s"
                   % (title, "; ".join(offered) or "none"))

    def accept(self, issue, label):
        """OpenPnP's Accept (setState Solved), then wait until its machine task and UI callback ran."""
        from org.openpnp.model import Solutions
        sol = self.solutions()
        if sol.isSolutionsIssueSolved(issue) or issue.getState() == Solutions.State.Solved:
            # re-open first (restores the values captured by findIssues = the current ones), so that
            # "solved" afterwards means this Accept worked
            self.on_edt(lambda: issue.setState(Solutions.State.Open))
            self.on_edt(lambda: sol.setSolutionsIssueSolved(issue, False))
        self.say("  OpenPnP Accept: %s" % issue.getIssue())
        self.on_edt(lambda: issue.setState(Solutions.State.Solved))
        self.task(lambda: None)                          # FIFO: after OpenPnP's own task
        self.on_edt(lambda: None)                        # after its success / error callback
        self.on_edt(lambda: None)
        if not sol.isSolutionsIssueSolved(issue):
            raise Stop("%s: OpenPnP did not solve it - read OpenPnP's error message" % label)

    def feature_px(self, issue, px=None):
        p = issue.getProperties()[0]
        if px is not None:
            p.set(int(round(px)))                       # also shows OpenPnP's detection in the camera view
        return p.get()

    def detect(self, camera, px):
        """OpenPnP's own circle detection at the camera's current position: (diameter_px, offset_px) or None."""
        from java.lang import Throwable
        from org.openpnp.vision.pipeline import CvStage
        vs = self.machine.getVisionSolutions()
        try:
            c = vs.getSubjectPixelLocation(camera, None, CvStage.Result.Circle(0, 0, px), 0.05,
                                           "Lumen check %d px - score {score}" % int(px), None, False)
        except (Exception, Throwable):
            return None
        dx = c.getX() - camera.getWidth() / 2.0
        dy = c.getY() - camera.getHeight() / 2.0
        return c.getDiameter(), math.hypot(dx, dy)

    def vision_accept(self, issue, camera, expected_mm, label):
        upp = camera.getUnitsPerPixel().convertToUnits(_mm()).getX()
        expected_px = expected_mm / upp if (upp > 0 and expected_mm) else 0
        px = expected_px or self.feature_px(issue)
        self.feature_px(issue, px)
        found = self.detect(camera, px)
        ok, why = check_detection(found[0] if found else None, expected_px, found[1] if found else 0,
                                  min(camera.getWidth(), camera.getHeight()))
        self.say("  detection: %s" % why)
        if found:
            self.feature_px(issue, found[0])
        if not ok or self.opt.get("pause_each"):
            if self.ui.visual_check(issue, camera, expected_px, why) != "accept":
                raise Stop("%s: cancelled at the visual check" % label)
        self.accept(issue, label)

    # ---------------------------------------------------------------- motion helpers
    def move(self, hm, x, y, z=None):
        from org.openpnp.model import Location
        from org.openpnp.util import MovableUtils
        mm = _mm()
        zz = float("nan") if z is None else z
        self.task(lambda: MovableUtils.moveToLocationAtSafeZ(hm, Location(mm, x, y, zz, 0.0)))

    def all_safe_z(self):
        self.task(lambda: self.head.moveToSafeZ())

    def target_at(self, x, y):
        """The calibration target seen by the top camera at x, y: (x, y, d, circ) or None."""
        from lumen import nozzlecal
        dia = self.head.getCalibrationTestObjectDiameter().convertToUnits(_mm()).getValue()
        z = self.head.getCalibrationPrimaryFiducialLocation().convertToUnits(_mm()).getZ()
        d, _ = self.task(lambda: nozzlecal.look_disc(self.machine, x, y, z, dia))
        return d

    def visual_home_xy(self):
        return visual_home_xy(self.head)

    def ensure_home_free(self):
        """Camera on the visual home: the calibration target must not lie there (homing would use it)."""
        x, y = self.visual_home_xy()
        return self.ensure_free_at(x, y, "visual home")

    def ensure_free_at(self, x, y, where):
        """True if the target had to be removed from (x, y) (the caller then homes again)."""
        if not self.target_at(x, y):
            return False
        a = self.ask("Calibration target on the %s" % where,
                     "<p>The camera sees the <b>calibration target on the %s</b> (first picture). Homing or calibrating "
                     "now would use the target instead of the fiducial: every coordinate would be off by about 2 mm.</p>"
                     "<p>Put the target on its <b>park spot</b> by hand (second picture), then press <i>Done</i>; the "
                     "machine homes again. If the OpenPnP camera view clearly shows the bare fiducial (third picture), "
                     "the detection was wrong: press <i>It is free</i>.</p>" % where,
                     ["cal-home-disc.png", "cal-disc-park.png", "cal-home-free.png"],
                     ["Done", "It is free", "Cancel"])
        if a == "Cancel":
            raise Stop("cancelled: calibration target on the %s" % where)
        if a == "It is free":
            self.say("  you confirmed the %s is free (detection overruled)" % where)
            return False
        if self.target_at(x, y):
            raise Stop("the calibration target is still on the %s" % where)
        return True

    def home(self):
        """Home with every nozzle at safe Z and the visual home free."""
        if self.machine.isHomed():
            self.all_safe_z()
            self.ensure_home_free()
        self.say("  homing ...")
        self.task(lambda: self.machine.home())
        x, y = self.visual_home_xy()
        if self.target_at(x, y):
            raise Stop("after homing the camera sees the calibration target on the visual home - put it on its "
                       "park spot and home again")

    def load_tip(self, nozzle, tip, calibrate):
        """OpenPnP's nozzle tip change; for a manual change OpenPnP moves to the change position and asks."""
        if nozzle.getNozzleTip() == tip:
            return
        from java.lang import Throwable
        self.say("  %s: load tip %s" % (nozzle.getName(), tip.getName()))
        try:
            self.task(lambda: nozzle.loadNozzleTip(tip, calibrate))
            return
        except (Exception, Throwable) as e:              # ManualLoadException is a Java exception
            text = manual_change_text(e)
            if text is None:
                raise
        self.ask("Change the nozzle tip by hand",
                    "<p>OpenPnP moved %s to the tip change position.</p><p><b>%s</b></p>"
                    "<p>Pull the old tip straight down, put it into its holder slot, push the new tip on until it sits "
                    "straight. Then press <i>Done</i>.</p>" % (nozzle.getName(), text.replace("\n", "<br>")),
                    ["cal-tip-swap.png"], ["Done", "Cancel"], must="Done")
        self.task(lambda: nozzle.loadNozzleTip(tip, calibrate))

    def tip_by_name(self, name):
        for t in self.machine.getNozzleTips():
            if t.getName() == name:
                return t
        return None

    def contact_z(self, nozzle, x, y, stored_z, label):
        """Touching Z on a fiducial: vacuum contact probe (default) or jogged by the person."""
        from lumen import zprobe
        if self.opt.get("z_method") == "hand":
            self.move(nozzle, x, y)
            self.ask("%s: jog %s down until it touches" % (label, nozzle.getName()),
                        "<p>%s is over the fiducial at safe Z. Jog it <b>down in small steps</b> (1 mm, then 0.1 mm, then "
                        "0.01 mm) until the tip just touches the fiducial, as in the Opulo guide. Do not jog X/Y unless the "
                        "tip is clearly not centred. Then press <i>Done</i>.</p>" % nozzle.getName(),
                        ["cal-z-contact.png"], ["Done", "Cancel"], must="Done")
            return nozzle.getLocation().convertToUnits(_mm()).getZ()
        safe = nozzle.getSafeZ().convertToUnits(_mm()).getValue() if nozzle.getSafeZ() else None
        w = probe_window(stored_z, safe)
        if w is None:
            self.move(nozzle, x, y)
            self.ask("%s: bring %s close to the fiducial" % (label, nozzle.getName()),
                        "<p>OpenPnP has no fiducial Z yet. Jog %s down to about <b>1-2 mm above</b> the fiducial (not "
                        "touching), then press <i>Done</i>. The vacuum contact probe measures from there.</p>"
                        % nozzle.getName(), ["cal-z-contact.png"], ["Done", "Cancel"], must="Done")
            cur = nozzle.getLocation().convertToUnits(_mm()).getZ()
            w = (cur, cur - 3.0)
        r = self.task(lambda: zprobe.probe(nozzle, x, y, w[0], w[1], max_travel=w[0] - w[1], log=self.say))
        return r["z"]

    def lower_to(self, nozzle, x, y, z):
        """Nozzle onto a measured contact Z: at safe Z over x, y, down to z + 0.5, the last 0.5 mm slow."""
        from org.openpnp.model import Location
        mm = _mm()
        self.move(nozzle, x, y, z + 0.5)
        self.task(lambda: nozzle.moveTo(Location(mm, x, y, z, nozzle.getLocation().getRotation()), 0.05))

    # ---------------------------------------------------------------- steps
    def run(self, key):
        self.check_stop()
        return getattr(self, "step_" + key)()

    def _tips_file(self):
        d = os.path.join(self.lumen_dir or ".", "calibration")
        if not os.path.isdir(d):
            os.makedirs(d)
        return os.path.join(d, "tips-before.json")

    def remember_tips(self, overwrite):
        """The tips on the nozzles before this run, kept in a file so 'tips back' works after a restart."""
        import json
        p = self._tips_file()
        if overwrite or not os.path.isfile(p):
            names = dict((n.getName(), n.getNozzleTip().getName() if n.getNozzleTip() is not None else None)
                         for n in self.nozzles)
            with open(p, "w") as f:
                json.dump(names, f)
        with open(p) as f:
            names = json.load(f)
        self.tips_before = dict((k, self.tip_by_name(v)) for k, v in names.items() if v)

    def step_prepare(self):
        if self.before is None:
            self.before = self.snapshot()
        self.remember_tips(True)
        b = self.backup()
        self.say("  backup of machine.xml (as saved on disk): %s" % b)
        if not self.machine.isHomed():
            self.ask("Before homing",
                        "<p>The machine is not homed. Check by eye:</p><ol>"
                        "<li>Both nozzles are <b>up and level</b> (first picture). If one hangs low, push it up gently.</li>"
                        "<li>The <b>calibration target lies on its park spot</b>, not on the visual home (second and "
                        "third picture).</li></ol><p>Then press <i>Home</i>.</p>",
                        ["cal-nozzles-level.png", "cal-home-free.png", "cal-disc-park.png"], ["Home", "Cancel"],
                        must="Home")
            self.home()
            return "homed"
        self.all_safe_z()
        if self.ensure_home_free():
            self.home()
            return "target removed from the visual home, homed again"
        return "already homed; nozzles at safe Z, visual home free"

    def _fiducial(self, key, primary):
        h = self.head
        loc = h.getCalibrationPrimaryFiducialLocation() if primary else h.getCalibrationSecondaryFiducialLocation()
        x, y, z = _xyz(loc)
        if x == 0 and y == 0:
            self.ask("Camera over the %s fiducial" % ("primary" if primary else "secondary"),
                        "<p>OpenPnP has no position for this fiducial yet. Jog the <b>top camera</b> over it (cross-hairs "
                        "roughly on the white dot), then press <i>Done</i>.</p>", ["cal-home-free.png"],
                        ["Done", "Cancel"], must="Done")
        else:
            self.move(self.cam, x, y, z)
        if primary:
            cx, cy = _xyz(self.cam.getLocation())[:2]
            if self.ensure_free_at(cx, cy, "primary fiducial"):
                self.home()
                self.move(self.cam, cx, cy, z)
        dia = (h.getCalibrationPrimaryFiducialDiameter() if primary else h.getCalibrationSecondaryFiducialDiameter())
        dmm = dia.convertToUnits(_mm()).getValue() if dia is not None else 0
        issue = self.need_issue(issue_title(key))
        self.vision_accept(issue, self.cam, dmm or NOMINAL_FIDUCIAL_MM, BY_KEY[key].title)
        new = h.getCalibrationPrimaryFiducialLocation() if primary else h.getCalibrationSecondaryFiducialLocation()
        nx, ny, nz = _xyz(new)
        return "fiducial at %.3f / %.3f (moved %.3f mm)" % (nx, ny, math.hypot(nx - x, ny - y))

    def step_primary_fid(self):
        return self._fiducial("primary_fid", True)

    def step_secondary_fid(self):
        return self._fiducial("secondary_fid", False)

    def _nozzle_fid(self, key, nozzle, primary):
        h = self.head
        loc = h.getCalibrationPrimaryFiducialLocation() if primary else h.getCalibrationSecondaryFiducialLocation()
        x, y, z_old = _xyz(loc)
        label = BY_KEY[key].title.replace("N1", nozzle.getName()).replace("N2", nozzle.getName())
        issue = self.need_issue(issue_title(key, nozzle=nozzle.getName()))
        try:
            z = self.contact_z(nozzle, x, y, z_old, label)
            self.say("  %s touches at Z %.3f (stored fiducial Z %.3f)" % (nozzle.getName(), z, z_old))
            if not z_change_ok(z_old, z):
                if self.ask("Fiducial Z changes a lot",
                               "<p>Measured Z %.3f, OpenPnP has %.3f (difference %.2f mm). Accept the measured Z?</p>"
                               % (z, z_old, z - z_old), ["cal-z-contact.png"], ["Accept", "Cancel"]) != "Accept":
                    raise Stop("%s: measured Z not accepted" % label)
            if self.opt.get("z_method") != "hand":
                self.lower_to(nozzle, x, y, z)
            if self.opt.get("pause_each"):
                if self.ask("%s: check the tip" % label,
                               "<p>%s touches the fiducial. Check from the front and the side that the tip is centred on "
                               "it (you may jog X/Y in OpenPnP, never Z). Then <i>Accept</i>.</p>" % nozzle.getName(),
                               ["cal-z-contact.png"], ["Accept", "Cancel"]) != "Accept":
                    raise Stop("%s: cancelled" % label)
            self.accept(issue, label)
        finally:
            self.task(lambda: nozzle.moveToSafeZ())
        nz = _xyz(h.getCalibrationPrimaryFiducialLocation() if primary else h.getCalibrationSecondaryFiducialLocation())[2]
        return "Z %.3f -> %.3f; %s head offsets %s" % (z_old, nz, nozzle.getName(), fmt_loc(_xyz(nozzle.getHeadOffsets())))

    def step_n1_primary(self):
        return self._nozzle_fid("n1_primary", self.n1, True)

    def step_n1_secondary(self):
        return self._nozzle_fid("n1_secondary", self.n1, False)

    def step_n2_primary(self):
        if len(self.nozzles) < 2:
            return "skipped: only one nozzle"
        return self._nozzle_fid("n2_primary", self.nozzles[1], True)

    def step_bottom_cam(self):
        from org.openpnp.spi.base.AbstractHead import VisualHomingMethod
        from org.openpnp.model import Location
        if self.up is None:
            return "skipped: no up-looking camera"
        if self.tips_before is None:
            self.remember_tips(False)
        if self.opt.get("swap_tip"):
            tip = self.tip_by_name(self.opt.get("bottom_tip", "N08"))
            if tip is None:
                raise Stop("nozzle tip %s not found in the configuration" % self.opt.get("bottom_tip", "N08"))
            self.load_tip(self.n1, tip, False)           # runout calibration needs this step first
        else:
            tip = self.n1.getNozzleTip()                 # no swap: the tip N1 has now
            if tip is None or getattr(tip, "isUnloadedNozzleTipStandin", lambda: False)():
                raise Stop("N1 has no nozzle tip loaded - load one, or tick 'swap'")
            self.say("  no tip swap: bottom camera with the tip on N1 (%s)" % tip.getName())
        prim = _xyz(self.head.getCalibrationPrimaryFiducialLocation())
        bx, by, bz = _xyz(self.up.getLocation())
        issue = self.need_issue(issue_title("bottom_cam", camera=self.up.getName()), self.up)
        try:
            if bx == 0 and by == 0:
                self.ask("N1 over the bottom camera",
                            "<p>OpenPnP has no bottom camera position yet. Jog N1 over the bottom camera, tip in the middle "
                            "of the bottom camera view, at the primary fiducial Z %.2f. Then press <i>Done</i>.</p>" % prim[2],
                            ["cal-bottom-circle.png"], ["Done", "Cancel"], must="Done")
            else:
                self.move(self.n1, bx, by, prim[2])
            self.on_edt(lambda: issue.setChoice(False))  # "Use nozzle Z" - never auto focus (Opulo guide)
            dmm = tip.getCalibration().getCalibrationTipDiameter().convertToUnits(_mm()).getValue()
            self.vision_accept(issue, self.up, dmm, BY_KEY["bottom_cam"].title)
        finally:
            self.task(lambda: self.n1.moveToSafeZ())
        h = self.head
        old_home = _xyz(h.getHomingFiducialLocation())
        p = _xyz(h.getCalibrationPrimaryFiducialLocation())
        self.on_edt(lambda: h.setHomingFiducialLocation(Location(_mm(), p[0], p[1], old_home[2], 0.0)))
        self.on_edt(lambda: h.setVisualHomingMethod(VisualHomingMethod.ResetToFiducialLocation))
        nb = _xyz(self.up.getLocation())
        return "bottom camera at %s; homing fiducial %.3f / %.3f -> %.3f / %.3f (ResetToFiducialLocation)" % (
            fmt_loc(nb), old_home[0], old_home[1], p[0], p[1])

    def step_tips_back(self):
        if self.tips_before is None and os.path.isfile(self._tips_file()):
            self.remember_tips(False)
        if not self.tips_before:
            return "nothing to do (tips were not changed in this run)"
        done = []
        for n in self.nozzles:
            t = self.tips_before.get(n.getName())
            if t is not None and n.getNozzleTip() != t:
                self.load_tip(n, t, True)
                done.append("%s %s" % (n.getName(), t.getName()))
        return ("loaded " + ", ".join(done)) if done else "tips already as before"

    def step_precise(self):
        from lumen import nozzlecal
        park = tuple(self.opt.get("park") or DEFAULT_PARK)
        if not self.target_at(park[0], park[1]):
            self.ask("Calibration target to its park spot",
                        "<p>The camera does not see the calibration target at its park spot %.2f / %.2f. Put it there "
                        "(picture), then press <i>Done</i>.</p>" % park, ["cal-disc-park.png"], ["Done", "Cancel"],
                        must="Done")
            if not self.target_at(park[0], park[1]):
                raise Stop("calibration target not found at its park spot")
        r = self.task(lambda: nozzlecal.calibrate_openpnp(self.machine, self.nozzles, park, self.n1, log=self.say))
        if r.get("final") is None:
            raise Stop("the calibration target was not found back at its park spot - check the visual home by eye "
                       "and put it on its park spot BEFORE homing")
        sol = self.solutions()
        for n in self.nozzles:
            i = self.issue(issue_title("precise", nozzle=n.getName()), n)
            if i is not None:
                self.on_edt(lambda i=i: sol.setSolutionsIssueSolved(i, True))
        return "; ".join("%s %s" % (k, fmt_loc(_xyz(v[1]))) for k, v in sorted(r["offsets"].items()))

    def _settle(self, camera):
        if camera is None:
            return "skipped: no such camera"
        i = self.issue(issue_title("settle"), camera)
        if i is None:
            return "nothing to do: OpenPnP offers no settling change (method %s)" % getattr(
                camera, "getSettleMethod", lambda: "?")()
        self.accept(i, "camera settling %s" % camera.getName())
        return "settle method %s" % getattr(camera, "getSettleMethod", lambda: "?")()

    def step_settle_top(self):
        return self._settle(self.cam)

    def step_settle_bottom(self):
        return self._settle(self.up)

    def _backlash(self, axis):
        if not self.opt.get("optional", True):
            return "skipped (optional steps off)"
        if axis is None:
            return "skipped: no axis"
        i = self.need_issue(issue_title("backlash", axis=axis.getName()))
        self.accept(i, "backlash %s" % axis.getName())
        return "%s %.4f mm" % (axis.getBacklashCompensationMethod(), axis.getBacklashOffset().convertToUnits(_mm()).getValue())

    def step_backlash_x(self):
        return self._backlash(self.cam.getAxisX())

    def step_backlash_y(self):
        return self._backlash(self.cam.getAxisY())

    def step_homing_prep(self):
        from org.openpnp.spi.base.AbstractHead import VisualHomingMethod
        from org.openpnp.machine.reference.ReferenceNozzleTipCalibration import RecalibrationTrigger
        from org.openpnp.model import Location
        h, out = self.head, []
        if h.getVisualHomingMethod() != VisualHomingMethod.ResetToFiducialLocation:
            self.on_edt(lambda: h.setVisualHomingMethod(VisualHomingMethod.ResetToFiducialLocation))
            out.append("homing method ResetToFiducialLocation")
        p, o = _xyz(h.getCalibrationPrimaryFiducialLocation()), _xyz(h.getHomingFiducialLocation())
        if math.hypot(p[0] - o[0], p[1] - o[1]) > 0.001:
            self.on_edt(lambda: h.setHomingFiducialLocation(Location(_mm(), p[0], p[1], o[2], 0.0)))
            out.append("homing fiducial = primary fiducial X/Y")
        tips = []
        for t in self.machine.getNozzleTips():
            cal = getattr(t, "getCalibration", lambda: None)()
            if cal is not None and cal.isEnabled() and cal.getRecalibrationTrigger() != RecalibrationTrigger.NozzleTipChange:
                self.on_edt(lambda cal=cal: cal.setRecalibrationTrigger(RecalibrationTrigger.NozzleTipChange))
                tips.append(t.getName())
        if tips:
            out.append("runout calibration on tip change: " + ", ".join(tips))
        return "; ".join(out) if out else "already set"

    def step_verify(self):
        from org.openpnp.model import Configuration
        self.home()
        p = _xyz(self.head.getCalibrationPrimaryFiducialLocation())
        self.move(self.cam, p[0], p[1], p[2])
        d = self.head.getCalibrationPrimaryFiducialDiameter()
        dia = (d.convertToUnits(_mm()).getValue() if d is not None else 0) or NOMINAL_FIDUCIAL_MM
        upp = self.cam.getUnitsPerPixel().convertToUnits(_mm()).getX()
        found = self.detect(self.cam, dia / upp)
        if not found:
            raise Stop("after homing the primary fiducial is not found under the camera")
        off = found[1] * upp
        self.say("  primary fiducial %.3f mm from the camera centre after homing" % off)
        if off > HOME_TOL_MM:
            raise Stop("after homing the primary fiducial is %.3f mm off (limit %.2f)" % (off, HOME_TOL_MM))
        self.all_safe_z()
        after = self.snapshot()
        rows = diff_rows(self.before or {}, after)
        table = "".join("<tr><td>%s</td><td>%s</td><td><b>%s</b></td></tr>" % r for r in rows) or \
            "<tr><td colspan=3>no value changed</td></tr>"
        if self.ask("Save the configuration?",
                       "<p>Homing verified: primary fiducial %.3f mm from the camera centre.</p>"
                       "<table border=1 cellpadding=3><tr><th>value</th><th>before</th><th>after</th></tr>%s</table>"
                       "<p><i>Save</i> writes machine.xml now (OpenPnP also saves on exit). The backup from the first "
                       "step stays in ~/.openpnp2/lumen/calibration/.</p>" % (off, table),
                       [], ["Save", "Do not save"]) == "Save":
            self.on_edt(lambda: Configuration.get().save())
            return "verified (%.3f mm), %d value(s) changed, configuration saved" % (off, len(rows))
        return "verified (%.3f mm), %d value(s) changed, NOT saved" % (off, len(rows))
