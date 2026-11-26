# -*- coding: utf-8 -*-
"""Feeder part check (Jython, OpenPnP): look at a feeder's pick location with the top camera and
find the tape pockets and parts (lumen.tapevision).  Moves only the camera (at safe Z)."""
from __future__ import absolute_import, division, print_function

import math
import os
import time

from lumen import tapevision


def _units():
    from org.openpnp.model import LengthUnit
    return LengthUnit.Millimeters


def check_feeder(machine, feeder, save_dir=None):
    """Camera to the pick location, capture, analyse.  Call inside a machine task.
    Returns {feeder, pick, pocket_dx, pocket_dy, part_at_pick, parts_visible, pockets, pitch_mm,
    configured_pitch, image, upp (mm/px x, y), size (w, h px), error}.  The image centre is the pick location."""
    from org.openpnp.model import Length, Location
    from org.openpnp.util import MovableUtils
    mm = _units()
    res = {"feeder": feeder.getName(), "error": None}
    if hasattr(feeder, "findSlotAddress") and feeder.getSlotAddress() is None:
        feeder.findSlotAddress()                         # ask the bus where this Photon feeder sits
    if hasattr(feeder, "getSlotAddress"):
        res["slot"] = feeder.getSlotAddress()
    try:
        pick = feeder.getPickLocation().convertToUnits(mm)
    except Exception as e:
        res["error"] = "pick location not configured: %s" % e
        return res
    res["pick"] = [pick.getX(), pick.getY(), pick.getZ(), pick.getRotation()]
    cam = machine.getDefaultHead().getDefaultCamera()
    MovableUtils.moveToLocationAtSafeZ(cam, Location(mm, pick.getX(), pick.getY(), pick.getZ(), 0))
    img = cam.settleAndCapture()
    upp = cam.getUnitsPerPixel(Length(pick.getZ(), mm)).convertToUnits(mm)
    u = upp.getX()
    w, h = img.getWidth(), img.getHeight()
    res["upp"] = (u, upp.getY())                         # for 'Set offset by hand' (click in the saved photo)
    res["size"] = (w, h)
    pitch = feeder.getPartPitch() if hasattr(feeder, "getPartPitch") else None
    res["configured_pitch"] = pitch
    # 1. centring from the sprocket holes (any tape: paper, clear, black; any part size)
    holes = tapevision.holes_java(img, u)
    e = tapevision.eia_pocket(holes, (w, h), u, pitch or 4.0)
    res["holes"] = holes or []
    if e.get("error"):
        res["error"] = e["error"]
    else:
        res["method"] = "sprocket holes, %d mm tape" % {3.5: 8, 5.5: 12, 7.5: 16, 11.5: 24}[e["F"]]
        res["F"] = e["F"]
        res["pocket_px"] = (e["x"], e["y"])
        res["pocket_dx"] = (e["x"] - w / 2.0) * u
        res["pocket_dy"] = -(e["y"] - h / 2.0) * upp.getY()
    # 2. part present: paper tape analysis (bright band), only where its pocket matches the hole geometry
    r = tapevision.analyse_java(img, u)
    res["pitch_mm"] = r.get("pitch_mm")
    res["part_at_pick"] = None
    if not r.get("error") and not e.get("error"):
        near = [q for q in r["pockets"] if ((q["x"] - e["x"]) ** 2 + (q["y"] - e["y"]) ** 2) ** 0.5 * u < 0.3]
        if near:
            res["part_at_pick"] = bool(near[0]["part"])
            res["parts_visible"] = len([q for q in r["pockets"] if q["part"]])
            res["pockets"] = len(r["pockets"])
            res["scores"] = [q["score"] for q in r["pockets"]]
    res["tape"] = "paper" if not r.get("error") else "clear/black (part presence not detected)"
    if save_dir:
        tag = str(feeder.getHardwareId()) if hasattr(feeder, "getHardwareId") and feeder.getHardwareId() else feeder.getName()
        res["image"] = _save(img, r, save_dir, "slot%s-%s" % (res.get("slot", "x"), "".join(c for c in tag if c.isalnum())),
                             holes, res.get("pocket_px"))
    return res


def _save(img, r, save_dir, name, holes=None, pocket=None):
    from java.awt import BasicStroke, Color, Font
    from java.awt.image import BufferedImage
    from java.io import File
    from javax.imageio import ImageIO
    from java.awt import Graphics2D
    if not os.path.isdir(save_dir):
        os.makedirs(save_dir)
    out = BufferedImage(img.getWidth(), img.getHeight(), BufferedImage.TYPE_INT_RGB)
    g = out.createGraphics()
    G = Graphics2D                                       # Java 17: call through the public interface
    G.drawImage(g, img, 0, 0, None)
    G.setStroke(g, BasicStroke(4))
    for x, y, d in r.get("holes", []):
        G.setColor(g, Color.YELLOW)
        G.drawOval(g, int(x - d / 2), int(y - d / 2), int(d), int(d))
    for q in r.get("pockets", []):
        G.setColor(g, Color(0, 200, 0) if q.get("part") else Color.RED)
        G.drawRect(g, int(q["x"] - q["w"] / 2), int(q["y"] - q["h"] / 2), int(q["w"]), int(q["h"]))
    G.setColor(g, Color.CYAN)
    for x, y, d in holes or []:
        G.drawOval(g, int(x - d), int(y - d), int(2 * d), int(2 * d))
    w2, h2 = img.getWidth() // 2, img.getHeight() // 2
    G.setColor(g, Color.RED)                              # current pick location = image centre
    G.drawLine(g, w2 - 80, h2, w2 + 80, h2)
    G.drawLine(g, w2, h2 - 80, w2, h2 + 80)
    if pocket:
        G.setColor(g, Color.GREEN)                        # pocket centre from the sprocket holes
        x, y = int(pocket[0]), int(pocket[1])
        G.drawLine(g, x - 70, y - 70, x + 70, y + 70)
        G.drawLine(g, x - 70, y + 70, x + 70, y - 70)
    G.setColor(g, Color.MAGENTA)
    G.setFont(g, Font("SansSerif", Font.BOLD, 40))
    G.drawString(g, "%s  %s" % (name, r.get("error") or "pitch %.2f mm" % (r.get("pitch_mm") or 0)), 20, 50)
    G.dispose(g)
    path = os.path.join(save_dir, "%s-%s.png" % (name, time.strftime("%Y%m%d-%H%M%S")))
    ImageIO.write(out, "png", File(path))
    return path


def click_offset(ix, iy, size, upp):
    """Image pixel clicked (the pocket centre) -> (dx, dy) mm from the pick location (= image centre),
    machine frame (image Y down = machine Y minus)."""
    return (ix - size[0] / 2.0) * upp[0], -(iy - size[1] / 2.0) * upp[1]


def _shifted(loc, dx, dy):
    from org.openpnp.model import Location
    mm = _units()
    loc = loc.convertToUnits(mm)
    return Location(mm, loc.getX() + dx, loc.getY() + dy, loc.getZ(), loc.getRotation())


def offset_kind(feeder):
    """How apply_pocket_offset moves this feeder's pick location: 'photon' (feeder offset in the slot frame),
    'strip' (both reference holes), 'location' (tray and other feeders with one location), or None."""
    if hasattr(feeder, "getSlot") and hasattr(feeder, "getOffset") and hasattr(feeder, "setOffset"):
        return "photon"
    if hasattr(feeder, "getReferenceHoleLocation") and hasattr(feeder, "getLastHoleLocation"):
        return "strip"
    if hasattr(feeder, "getLocation") and hasattr(feeder, "setLocation"):
        return "location"
    return None


def apply_pocket_offset(feeder, dx, dy, limit_mm=2.0):
    """Move the pick location by (dx, dy) mm (machine frame) onto the pocket centre.
    - Photon: the feeder offset changes (pick = slot location + offset rotated by the slot);
    - strip feeder: both reference holes move (the whole strip);
    - tray and other feeders: the feeder location (first part) moves, so every tray position moves with it.
    The result is read back and reverted if it does not land where intended.  Returns (old, new) pick.
    limit_mm guards the automatic (measured) offset; None = no limit (set by hand, confirmed)."""
    from org.openpnp.model import Location
    mm = _units()
    if limit_mm is not None and math.hypot(dx, dy) > limit_mm:
        raise ValueError("offset %.2f mm larger than %.1f mm: check the feeder by hand" % (math.hypot(dx, dy), limit_mm))
    kind = offset_kind(feeder)
    if kind is None:
        raise ValueError("%s (%s): no location this tool can move" % (feeder.getName(), feeder.__class__.__name__))
    before = feeder.getPickLocation().convertToUnits(mm)
    target = (before.getX() + dx, before.getY() + dy)
    if kind == "photon":
        old = feeder.getOffset()
        rot = 0.0
        if feeder.getSlot() is not None and feeder.getSlot().getLocation() is not None:
            rot = feeder.getSlot().getLocation().getRotation()
        a = math.radians(-rot)                               # machine frame -> slot frame
        ox, oy = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
        o = old.convertToUnits(mm)
        feeder.setOffset(Location(mm, o.getX() + ox, o.getY() + oy, o.getZ(), o.getRotation()))

        def revert():
            feeder.setOffset(old)
    elif kind == "strip":
        old = (feeder.getReferenceHoleLocation(), feeder.getLastHoleLocation())
        feeder.setReferenceHoleLocation(_shifted(old[0], dx, dy))
        feeder.setLastHoleLocation(_shifted(old[1], dx, dy))

        def revert():
            feeder.setReferenceHoleLocation(old[0])
            feeder.setLastHoleLocation(old[1])
    else:
        old = feeder.getLocation()
        feeder.setLocation(_shifted(old, dx, dy))

        def revert():
            feeder.setLocation(old)
    after = feeder.getPickLocation().convertToUnits(mm)
    if math.hypot(after.getX() - target[0], after.getY() - target[1]) > 0.01:
        revert()
        raise RuntimeError("offset did not move the pick location as intended (reverted)")
    return before, after


def photo_at(machine, x, y, z):
    """Top camera to (x, y) at safe Z, one picture: (image copy, (upp_x, upp_y) mm/px at height z).
    Camera only.  Call inside a machine task."""
    from org.openpnp.model import Length, LengthUnit, Location
    from org.openpnp.util import MovableUtils
    from lumen import zoomview
    mm = LengthUnit.Millimeters
    cam = machine.getDefaultHead().getDefaultCamera()
    MovableUtils.moveToLocationAtSafeZ(cam, Location(mm, x, y, z, 0.0))
    img = zoomview.copy_image(cam.settleAndCapture())
    u = cam.getUnitsPerPixel(Length(z, mm)).convertToUnits(mm)
    return img, (u.getX(), u.getY())


def slot_xy(feeder):
    """(x, y) mm of a Photon feeder's slot location (the rough feeder position captured at set-up), or None."""
    try:
        s = feeder.getSlot()
        loc = s.getLocation() if s is not None else None
        if loc is None:
            return None
        loc = loc.convertToUnits(_units())
        return loc.getX(), loc.getY()
    except Exception:
        return None


# The round marks on the feeder nose (tapevision.fiducial_pattern) relative to the pick location.  opulo_feeder CAD
# (assembly-8 and assembly-12): fiducial board centre at X 78.1 / Y -7.6, indexing wheel at X 64.95 with its teeth
# (the sprocket hole line) at Y -3.5.  So the centre mark is ~13 mm from the pick location towards the nose
# (+- 2 mm: which pocket next to the wheel tooth is picked) and 4.1 mm from the hole line, the pocket F mm.
FID_ALONG_MM = 13.15
FID_FROM_HOLES_MM = 4.1
FID_RECENTRE_MM = 0.15


def nose_sign(pick_y, res=None, slot_ys=()):
    """+1: the feeder nose points to +Y (front rail), -1: to -Y (rear rail).  From the check photo when it has the
    sprocket holes (they are left of the pocket, seen along the nose), else the nose points to the middle of
    the feeder slot locations (both rails), else +1."""
    res = res or {}
    holes, pocket = res.get("holes"), res.get("pocket_px")
    if holes and pocket:
        hx = sum(h[0] for h in holes) / float(len(holes))
        return 1 if hx < pocket[0] else -1
    ys = list(slot_ys)
    if ys and max(ys) - min(ys) > 100.0:
        return 1 if pick_y < (max(ys) + min(ys)) / 2.0 else -1
    return 1


def fiducial_nominal(pick_xy, sign, F=None):
    """(x, y) mm where the feeder's centre fiducial should be (CAD), from the pick location."""
    F = F or tapevision.POCKET_TO_HOLES_MM
    return pick_xy[0] + sign * (FID_FROM_HOLES_MM - F), pick_xy[1] + sign * FID_ALONG_MM


def all_slot_ys(machine):
    out = []
    for f in machine.getFeeders():
        s = slot_xy(f) if hasattr(f, "getSlot") else None
        if s is not None:
            out.append(s[1])
    return out


def go_to_fiducial(machine, feeder, res=None):
    """Top camera (safe Z) over the round marks on the feeder nose: to the CAD position from the pick location, find
    the centre mark there, and centre the camera on it.  Camera only.  Call inside a machine task.
    Returns {img, upp, at (photo centre mm), nominal (mm), sign, found: None or {x, y (mm), sides, side_mm}}."""
    from org.openpnp.model import LengthUnit
    mm = LengthUnit.Millimeters
    if hasattr(feeder, "findSlotAddress") and feeder.getSlotAddress() is None:
        feeder.findSlotAddress()
    pick = feeder.getPickLocation().convertToUnits(mm)
    sign = nose_sign(pick.getY(), res, all_slot_ys(machine))
    nominal = fiducial_nominal((pick.getX(), pick.getY()), sign, (res or {}).get("F"))
    at, found = nominal, None
    for attempt in range(2):
        img, upp = photo_at(machine, at[0], at[1], pick.getZ())
        hit = tapevision.fiducial_java(img, upp[0])
        if hit is None:
            break                                        # (a mark found in the first photo stays found)
        w, h = img.getWidth(), img.getHeight()
        fx, fy = at[0] + (hit["x"] - w / 2.0) * upp[0], at[1] - (hit["y"] - h / 2.0) * upp[1]
        found = {"x": fx, "y": fy, "sides": hit["sides"], "side_mm": hit["side_mm"]}
        if attempt or math.hypot(fx - at[0], fy - at[1]) <= FID_RECENTRE_MM:
            break
        at = (fx, fy)                                    # second photo centred on the mark
    return {"img": img, "upp": upp, "at": at, "nominal": nominal, "sign": sign, "found": found}


def look(machine, feeder):
    """Top camera over the pick location, one picture: (image copy, (upp_x, upp_y) mm/px, pick).  The image
    centre is the pick location.  Camera only.  Call inside a machine task."""
    from org.openpnp.model import Length, LengthUnit
    from lumen import zoomview
    mm = LengthUnit.Millimeters
    pick = go_to(machine, feeder)
    cam = machine.getDefaultHead().getDefaultCamera()
    img = zoomview.copy_image(cam.settleAndCapture())
    u = cam.getUnitsPerPixel(Length(pick.getZ(), mm)).convertToUnits(mm)
    return img, (u.getX(), u.getY()), pick


def go_to(machine, feeder):
    """Top camera over the feeder's pick location (safe Z).  Call inside a machine task."""
    from org.openpnp.model import LengthUnit, Location
    from org.openpnp.util import MovableUtils
    mm = LengthUnit.Millimeters
    if hasattr(feeder, "findSlotAddress") and feeder.getSlotAddress() is None:
        feeder.findSlotAddress()
    pick = feeder.getPickLocation().convertToUnits(mm)
    cam = machine.getDefaultHead().getDefaultCamera()
    MovableUtils.moveToLocationAtSafeZ(cam, Location(mm, pick.getX(), pick.getY(), pick.getZ(), 0.0))
    return pick


IDENTIFY_FEEDER = 0xC1


def identify(machine, feeder, transport=None):
    """Photon IDENTIFY_FEEDER (0xC1 + UUID): the feeder blinks its LED white 3 times.  No motion.
    Works with every Photon firmware.  Returns the slot address."""
    from lumen import oppnp, photon
    hw = str(feeder.getHardwareId())
    uuid = [int(hw[i:i + 2], 16) for i in range(0, 24, 2)]
    if hasattr(feeder, "findSlotAddress") and feeder.getSlotAddress() is None:
        feeder.findSlotAddress()
    addr = feeder.getSlotAddress()
    if addr is None:
        raise RuntimeError("slot address of %s not known (feeder not on the bus?)" % feeder.getName())
    bus = photon.Bus(transport or oppnp.ActuatorTransport(machine))
    r = bus.transact(int(addr), IDENTIFY_FEEDER, uuid, retries=1)
    if not r or r[0] != 0:
        raise RuntimeError("feeder at address %s did not confirm IDENTIFY (%s)" % (addr, r))
    return int(addr)
