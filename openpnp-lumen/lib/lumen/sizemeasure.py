# -*- coding: utf-8 -*-
"""Measure a package's body size with the bottom camera (Job Readiness: a package without body size).

A package without body size fails OpenPnP's bottom-vision size check on every part ("Part ... width too large:
nominal 0.000, limit 0.000, measured 2.447") as soon as its vision settings check the body size.  Here one part is
fed and picked from its feeder and shown to the bottom camera SHOTS times, the nozzle turned 0 / 90 / 180 / 270 / 0
degrees, with the part's own bottom-vision pipeline - the same rectangle OpenPnP's size check compares with the
footprint (width = footprint X, height = footprint Y at every turn).  The part then goes back into its feeder
(Feeder.takeBackPart, as the test placement does; discarded only if the feeder cannot take it back).  Nothing in
the configuration changes here: the operator sees the shots and confirms, then the caller applies the median
(picksafety.apply_size).

Pure (CPython 3 / Jython): summarize().  OpenPnP side (Jython, inside a machine task): measure().
"""
from __future__ import absolute_import, division, print_function

ANGLES = (0.0, 90.0, 180.0, 270.0, 0.0)
SPREAD = 0.10            # max (max - min) / median of the good shots, per side
MIN_GOOD = 4             # good shots of the 5 needed for a proposal
EMPTY_MM = 0.15          # a side this small: nothing on the nozzle


def median(v):
    v = sorted(v)
    n = len(v)
    return None if n == 0 else v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def summarize(shots):
    """shots: [{angle, w, h (mm) or error}] -> {w, h (mm, 2 decimals), n, ok, why}."""
    good = [s for s in shots if s.get("w") is not None and min(s["w"], s["h"]) > EMPTY_MM]
    out = {"n": len(good), "w": None, "h": None, "ok": False}
    if len(good) < MIN_GOOD:
        empty = len([s for s in shots if s.get("w") is not None and min(s["w"], s["h"]) <= EMPTY_MM])
        out["why"] = "only %d good shot(s) of %d%s" % (len(good), len(shots),
                                                     " (%d with nothing on the nozzle)" % empty if empty else "")
        return out
    mw, mh = median([s["w"] for s in good]), median([s["h"] for s in good])
    sw = (max(s["w"] for s in good) - min(s["w"] for s in good)) / mw
    sh = (max(s["h"] for s in good) - min(s["h"] for s in good)) / mh
    out.update(w=round(mw, 2), h=round(mh, 2), spread=max(sw, sh))
    if max(sw, sh) > SPREAD:
        out["why"] = ("the shots differ by %.0f %% (more than %.0f %%): width and height swap with the nozzle turn, or "
                      "the part is not seen cleanly - not proposed" % (100 * max(sw, sh), 100 * SPREAD))
        return out
    out["ok"] = True
    out["why"] = "median of %d shots, they agree within %.0f %%" % (len(good), 100 * max(sw, sh))
    return out


# ---------------------------------------------------------------------------------------
# OpenPnP side (Jython, inside a machine task)
# ---------------------------------------------------------------------------------------
def _rect(bv, settings, cam, part, nozzle, angle):
    """Nozzle over the bottom camera turned to angle; OpenPnP's pipeline result rectangle (px).  The private
    ReferenceBottomVision.processPipelineAndGetResult is what findOffsets runs before its size check (OpenPnP 2.6)."""
    from org.openpnp.machine.reference.vision import ReferenceBottomVision
    from org.openpnp.model import BottomVisionSettings, Location, Part
    from org.openpnp.spi import Camera, Nozzle
    from org.openpnp.vision.pipeline import CvPipeline
    loc = bv.getCameraLocationAtPartHeight(part, cam, nozzle, angle)
    m = ReferenceBottomVision.getDeclaredMethod("processPipelineAndGetResult", [
        CvPipeline, Camera, Part, Nozzle, Location, Location, BottomVisionSettings])
    m.setAccessible(True)
    pipeline = settings.getPipeline()
    try:
        return m.invoke(bv, [pipeline, cam, part, nozzle, loc, loc, settings])
    finally:
        pipeline.close()


def measure(machine, part, feeder, nozzle, log=print, angles=ANGLES):
    """Feed + pick one part, the shots, the part back into the feeder.  Returns {shots, back, summary}."""
    from org.openpnp.machine.reference.vision import AbstractPartAlignment
    from org.openpnp.model import LengthUnit
    from org.openpnp.spi.base import AbstractPnpJobProcessor
    from lumen import testplace as tp
    mm = LengthUnit.Millimeters
    bv = AbstractPartAlignment.getPartAlignment(part)
    settings = AbstractPartAlignment.getInheritedVisionSettings(part, True)
    if bv is None or settings is None or not hasattr(bv, "getCameraLocationAtPartHeight"):
        raise tp.TestError("no enabled bottom vision for %s" % part.getId(), "nothing moved")
    cam = None
    for c in machine.getCameras():
        if str(c.getLooking()) == "Up":
            cam = c
    if cam is None:
        raise tp.TestError("no bottom camera", "nothing moved")
    tp._forget_feed(nozzle)
    feeder.feed(nozzle)
    log("size measurement %s: fed %s" % (part.getId(), feeder.getName()))
    try:
        nozzle.prepareForPickAndPlaceArticulation(feeder.getPickLocation(), feeder.getPickLocation())
        nozzle.moveToPickLocation(feeder)
        nozzle.pick(part, feeder)
        nozzle.moveToSafeZ()
        feeder.postPick(nozzle)
    except tp._errors() as e:
        try:
            AbstractPnpJobProcessor.discard(nozzle)
        except tp._errors():
            pass
        raise tp.TestError("pick failed: %s" % e, "nozzle emptied at the discard location (if anything was on it)")
    if not tp._part_on(nozzle):
        AbstractPnpJobProcessor.discard(nozzle)
        raise tp.TestError("no part on the nozzle after the pick (vacuum)", "the part is still in the feeder or lost")
    shots = []
    try:
        for a in angles:
            try:
                r = _rect(bv, settings, cam, part, nozzle, a)
                upp = cam.getUnitsPerPixelAtZ()
                ux, uy = upp.getLengthX().convertToUnits(mm).getValue(), upp.getLengthY().convertToUnits(mm).getValue()
                s = {"angle": a, "w": abs(r.size.width * ux), "h": abs(r.size.height * uy), "rect_angle": r.angle}
            except tp._errors() as e:
                s = {"angle": a, "w": None, "h": None, "error": str(e)}
            shots.append(s)
            log("size measurement %s: %s" % (part.getId(), s))
    finally:
        nozzle.moveToSafeZ()
        back = tp._give_back(feeder, nozzle) if nozzle.getPart() is not None else "not on the nozzle any more: check"
        log("size measurement %s: part %s" % (part.getId(), back))
    return {"shots": shots, "back": back, "summary": summarize(shots)}
