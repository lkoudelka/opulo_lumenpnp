# -*- coding: utf-8 -*-
"""Nozzle offset calibration with a physical target (round disc) - Jython, OpenPnP.

C = disc centre seen by the top camera.  Pick at C, rotate the nozzle 180 deg, place at C; the
disc lands at C + 2e, where e is the nozzle's offset error (nozzle axis vs. where OpenPnP thinks it
is).  e = (D - C) / 2.  Then pick at D and place at C WITHOUT rotating: the disc returns to C
whatever e is.  All Z approaches are slow vacuum-contact steps (lumen.zprobe rules).
"""
from __future__ import absolute_import, division, print_function

import math
import time

from lumen import zprobe


def _mm():
    from org.openpnp.model import LengthUnit
    return LengthUnit.Millimeters


def find_disc(image, upp, cam_xy, diameter_mm, tol=0.2):
    """Bright round disc in a top-camera image -> (x, y, d_mm, circularity) in machine mm, or None."""
    from lumen.tapevision import _ensure_opencv
    _ensure_opencv()
    from java.util import ArrayList
    from org.opencv.core import Mat, MatOfPoint2f, Point, Size
    from org.opencv.imgproc import Imgproc
    from org.openpnp.util import OpenCvUtils
    import jarray
    mat = OpenCvUtils.toMat(image)
    g = Mat()
    Imgproc.cvtColor(mat, g, Imgproc.COLOR_BGR2GRAY)
    Imgproc.GaussianBlur(g, g, Size(7, 7), 0)
    b = Mat()
    Imgproc.threshold(g, b, 0, 255, Imgproc.THRESH_BINARY + Imgproc.THRESH_OTSU)
    k = int(round(0.3 / upp)) | 1                         # opening removes thin bright lines (fiducial grid)
    Imgproc.morphologyEx(b, b, Imgproc.MORPH_OPEN, Imgproc.getStructuringElement(Imgproc.MORPH_ELLIPSE, Size(k, k)))
    cs = ArrayList()
    Imgproc.findContours(b, cs, Mat(), Imgproc.RETR_EXTERNAL, Imgproc.CHAIN_APPROX_NONE)
    w, h = g.cols(), g.rows()
    best = None
    for c in cs:
        c2 = MatOfPoint2f(c.toArray())
        center = Point()
        radius = jarray.zeros(1, "f")
        Imgproc.minEnclosingCircle(c2, center, radius)
        r = float(radius[0])
        if r <= 0:
            continue
        d = 2 * r * upp
        circ = Imgproc.contourArea(c) / (math.pi * r * r)
        if abs(d - diameter_mm) > tol * diameter_mm or circ < 0.85:
            continue
        x = cam_xy[0] + (center.x - w / 2.0) * upp
        y = cam_xy[1] - (center.y - h / 2.0) * upp
        dist = math.hypot(center.x - w / 2.0, center.y - h / 2.0)
        if best is None or dist < best[0]:
            best = (dist, (x, y, d, circ))
    return best[1] if best else None


def look_disc(machine, x, y, z, diameter_mm):
    from org.openpnp.model import Length, Location
    from org.openpnp.util import MovableUtils
    mm = _mm()
    cam = machine.getDefaultHead().getDefaultCamera()
    MovableUtils.moveToLocationAtSafeZ(cam, Location(mm, x, y, z, 0))
    img = cam.settleAndCapture()
    upp = cam.getUnitsPerPixel(Length(z, mm)).convertToUnits(mm).getX()
    loc = cam.getLocation().convertToUnits(mm)
    return find_disc(img, upp, (loc.getX(), loc.getY()), diameter_mm), img


def pick(nozzle, x, y, rot, z_start, z_floor, log=None):
    """Slow vacuum-contact approach at (x, y, rot); on contact keep the vacuum, lift 1 mm slowly and
    check the disc is held.  Returns contact Z.  On any failure: vacuum off, safe Z, raise."""
    from org.openpnp.model import Location
    from org.openpnp.util import MovableUtils
    mm = _mm()
    say = log or (lambda s: None)
    va = nozzle.getVacuumActuator()
    held = False
    try:
        MovableUtils.moveToLocationAtSafeZ(nozzle, Location(mm, x, y, float("nan"), rot))
        zprobe.actuate(va, True)
        time.sleep(0.8)
        free, sd, _ = zprobe.read_level(nozzle, 8)
        thr = max(5.0, 6 * sd)
        nozzle.moveTo(Location(mm, x, y, z_start, rot))
        time.sleep(0.2)
        if free - zprobe.read_level(nozzle, 2, 0.04)[0] > thr:
            raise RuntimeError("covered already at the start Z %.2f" % z_start)
        z, hit = z_start, None
        while z - 0.05 >= z_floor - 1e-9:
            z -= 0.05
            nozzle.moveTo(Location(mm, x, y, z, rot), 0.05)
            time.sleep(0.2)
            if free - zprobe.read_level(nozzle, 2, 0.04)[0] > thr:
                hit = z
                break
        if hit is None:
            raise RuntimeError("no contact down to %.2f: disc not there?" % z_floor)
        time.sleep(0.4)                                   # let the vacuum build under the disc
        nozzle.moveTo(Location(mm, x, y, hit + 1.0, rot), 0.05)
        time.sleep(0.3)
        lvl = zprobe.read_level(nozzle, 3, 0.05)[0]
        if free - lvl <= thr:
            raise RuntimeError("disc not held after lifting (level %.1f, free air %.1f)" % (lvl, free))
        say("  picked at %.3f/%.3f rot %.0f: contact Z %.3f, held (level %.1f, free %.1f)" % (x, y, rot, hit, lvl, free))
        held = True
        nozzle.moveToSafeZ()
        return hit
    finally:
        if not held:
            try:
                zprobe.actuate(va, False)
            finally:
                nozzle.moveToSafeZ()


def place(nozzle, x, y, rot, z_contact, log=None):
    """Put the held disc down at (x, y, rot): fast to 0.5 mm above the contact height, slowly down to
    it, vacuum off, wait, lift slowly, safe Z."""
    from org.openpnp.model import Location
    from org.openpnp.util import MovableUtils
    mm = _mm()
    say = log or (lambda s: None)
    va = nozzle.getVacuumActuator()
    try:
        MovableUtils.moveToLocationAtSafeZ(nozzle, Location(mm, x, y, float("nan"), rot))
        nozzle.moveTo(Location(mm, x, y, z_contact + 0.5, rot))
        nozzle.moveTo(Location(mm, x, y, z_contact, rot), 0.05)
        time.sleep(0.2)
        zprobe.actuate(va, False)
        time.sleep(0.5)
        nozzle.moveTo(Location(mm, x, y, z_contact + 1.0, rot), 0.05)
        say("  placed at %.3f/%.3f rot %.0f (Z %.3f)" % (x, y, rot, z_contact))
    finally:
        try:
            zprobe.actuate(va, False)
        finally:
            nozzle.moveToSafeZ()


def bottom_image(machine, nozzle, rot):
    """The held disc over the bottom camera (image for the record)."""
    from org.openpnp.model import Location
    from org.openpnp.util import MovableUtils
    mm = _mm()
    bottom = [c for c in machine.getCameras() if str(c.getLooking()) == "Up"]
    if not bottom:
        return None, None
    cam = bottom[0]
    loc = cam.getLocation().convertToUnits(mm)
    MovableUtils.moveToLocationAtSafeZ(nozzle, Location(mm, loc.getX(), loc.getY(), loc.getZ(), rot))
    img = cam.settleAndCapture()
    nozzle.moveToSafeZ()
    return img, cam


def calibrate(machine, nozzle, c_guess, diameter_mm, z_view, z_start, z_floor, log=None, save=None):
    """Full sequence -> dict {C, D, e, final, contact_z, ...}.  Call inside a machine task."""
    say = log or (lambda s: None)
    out = {"nozzle": nozzle.getName()}
    c, img = look_disc(machine, c_guess[0], c_guess[1], z_view, diameter_mm)
    if not c:
        raise RuntimeError("target disc not found by the top camera")
    out["C"] = c[:2]
    if save:
        save("cal-%s-before" % nozzle.getName(), img)
    say("  disc C %.3f/%.3f (d %.2f mm, circularity %.2f)" % c)
    rot0 = 0.0
    zc = pick(nozzle, c[0], c[1], rot0, z_start, z_floor, say)
    out["contact_z"] = zc
    bimg, _ = bottom_image(machine, nozzle, rot0)
    if save and bimg is not None:
        save("cal-%s-bottom" % nozzle.getName(), bimg)
    place(nozzle, c[0], c[1], rot0 + 180.0, zc, say)
    d, img = look_disc(machine, c[0], c[1], z_view, diameter_mm)
    if save:
        save("cal-%s-after180" % nozzle.getName(), img)
    if not d:
        raise RuntimeError("disc not found after the 180 deg place - check the machine")
    out["D"] = d[:2]
    out["e"] = ((d[0] - c[0]) / 2.0, (d[1] - c[1]) / 2.0)
    say("  disc D %.3f/%.3f -> nozzle offset error e = %+.3f / %+.3f mm" % (d[0], d[1], out["e"][0], out["e"][1]))
    # return the disc to C in its original orientation: pick at D (rot 180), turn back to rot 0 and
    # place at C - 2e (turning back moves the disc by +2e relative to the commanded position)
    restore(nozzle, d[:2], c[:2], rot0 + 180.0, rot0, out["e"], zc + 1.5, z_floor, say)
    f, img = look_disc(machine, c[0], c[1], z_view, diameter_mm)
    if save:
        save("cal-%s-returned" % nozzle.getName(), img)
    out["final"] = f[:2] if f else None
    if f:
        say("  disc back at %.3f/%.3f (%.3f mm from C)" % (f[0], f[1], math.hypot(f[0] - c[0], f[1] - c[1])))
    return out


def restore(nozzle, at_xy, to_xy, rot_from, rot_to, e, z_start, z_floor, log=None):
    """Move the disc from at_xy (picked with rotation rot_from) to to_xy with rotation rot_to.
    A rotation of 180 deg between pick and place shifts the disc by 2e; compensated."""
    turn = (rot_to - rot_from) % 360.0
    k = 1.0 if abs(turn - 180.0) < 1.0 else 0.0
    zc = pick(nozzle, at_xy[0], at_xy[1], rot_from, z_start, z_floor, log)
    place(nozzle, to_xy[0] - 2 * k * e[0], to_xy[1] - 2 * k * e[1], rot_to, zc, log)
    return zc


# ---------------------------------------------------------------------------------------
# OpenPnP's own nozzle offset calibration, with the target carried to and from its park spot
# ---------------------------------------------------------------------------------------
def openpnp_nozzle_offsets(machine, nozzle):
    """Run OpenPnP's CalibrationSolutions.calibrateNozzleOffsets(head, camera, nozzle) (the routine
    behind Issues & Solutions > Calibration > nozzle offsets).  It sets the head offsets itself."""
    from org.openpnp.machine.reference import ReferenceHead, ReferenceNozzle
    from org.openpnp.machine.reference.camera import ReferenceCamera
    from org.openpnp.machine.reference.solutions import CalibrationSolutions
    from java.lang.reflect import InvocationTargetException
    head = machine.getDefaultHead()
    m = CalibrationSolutions.getDeclaredMethod("calibrateNozzleOffsets", [ReferenceHead, ReferenceCamera, ReferenceNozzle])
    m.setAccessible(True)
    try:
        m.invoke(machine.getCalibrationSolutions(), [head, head.getDefaultCamera(), nozzle])
    except InvocationTargetException as e:
        raise RuntimeError("OpenPnP nozzle offset calibration failed: %s" % e.getCause())


def calibrate_openpnp(machine, nozzles, park_xy, carrier, log=None, save=None):
    """Target from its park spot onto the calibration primary fiducial (visual home), OpenPnP's
    nozzle offset calibration for each nozzle, target back to park_xy.  Only OpenPnP settings and
    routines (pick/place at the calibration Z, OpenPnP's own vision centring inside its routine).
    Returns {offsets: {nozzle: (old, new)}, final}.  Call inside a machine task, GUI running.
    Never home the machine while the target lies on the visual home: visual homing would lock on
    the target (bench 2026-11-06: coordinates off by ~2 mm)."""
    mm = _mm()
    say = log or (lambda s: None)
    head = machine.getDefaultHead()
    prim = head.getCalibrationPrimaryFiducialLocation().convertToUnits(mm)
    dia = head.getCalibrationTestObjectDiameter().convertToUnits(mm).getValue()
    z = prim.getZ()
    home = (prim.getX(), prim.getY())
    out = {"offsets": {}}
    c0, img = look_disc(machine, park_xy[0], park_xy[1], z, dia)
    if not c0:
        raise RuntimeError("target (%.2f mm) not found at its park spot %.3f/%.3f" % (dia, park_xy[0], park_xy[1]))
    if save:
        save("ocal-park-before", img)
    say("target at park %.3f/%.3f (%.3f mm from the park spot)" % (c0[0], c0[1], math.hypot(c0[0] - park_xy[0], c0[1] - park_xy[1])))
    carry(machine, carrier, c0[:2], home, z, say)
    try:
        for n in nozzles:
            old = n.getHeadOffsets()
            say("%s: OpenPnP nozzle offset calibration ..." % n.getName())
            openpnp_nozzle_offsets(machine, n)
            new = n.getHeadOffsets()
            out["offsets"][n.getName()] = (old, new)
            say("%s head offsets %s -> %s" % (n.getName(), old, new))
    finally:
        d, img = look_disc(machine, home[0], home[1], z, dia)
        if save:
            save("ocal-home-after", img)
        if not d:
            say("TARGET NOT FOUND on the visual home - move it back by hand BEFORE homing the machine")
            out["final"] = None
        else:
            carry(machine, carrier, d[:2], park_xy, z, say)
            f, img = look_disc(machine, park_xy[0], park_xy[1], z, dia)
            if save:
                save("ocal-park-after", img)
            out["final"] = f[:2] if f else None
            say("target back at park: %s" % ("%.3f/%.3f (%.3f mm from the park spot)" % (
                f[0], f[1], math.hypot(f[0] - park_xy[0], f[1] - park_xy[1])) if f else "NOT FOUND - check"))
    return out


def carry(machine, nozzle, from_xy, to_xy, z, log=None):
    """Move the target with OpenPnP's own pick and place (no vacuum Z sensing): a 0.01 mm test
    part picked and placed at the calibration Z, exactly like OpenPnP's nozzle offset calibration.
    No rotation between pick and place, so the target lands where commanded."""
    from org.openpnp.model import Length, Location, Package, Part
    from org.openpnp.machine.reference.feeder import ReferenceTubeFeeder
    mm = _mm()
    say = log or (lambda s: None)
    part = Part("LUMEN-TARGET")
    part.setHeight(Length(0.01, mm))
    part.setPackage(Package("LUMEN-TARGET-PACKAGE"))
    feeder = ReferenceTubeFeeder()
    feeder.setPart(part)
    feeder.setLocation(Location(mm, from_xy[0], from_xy[1], z, 0.0))
    dest = Location(mm, to_xy[0], to_xy[1], z, 0.0)
    try:
        nozzle.prepareForPickAndPlaceArticulation(feeder.getPickLocation(), dest)
        nozzle.moveToPickLocation(feeder)
        nozzle.pick(part, feeder)
        nozzle.moveToPlacementLocation(dest, part)
        nozzle.place()
        say("  carried target %.3f/%.3f -> %.3f/%.3f (OpenPnP pick/place at Z %.2f)" % (tuple(from_xy) + tuple(to_xy) + (z,)))
    finally:
        nozzle.moveToSafeZ()
