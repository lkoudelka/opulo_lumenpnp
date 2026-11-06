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
    configured_pitch, image, error}."""
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
        G.setColor(g, Color(0, 200, 0) if q["part"] else Color.RED)
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


def apply_pocket_offset(feeder, dx, dy, limit_mm=2.0):
    """Move the pick location by (dx, dy) mm (machine frame) onto the pocket centre.  Photon:
    the feeder offset changes (pick = slot location + offset rotated by the slot); the result is
    read back and reverted if it does not land where intended.  Returns (old, new) pick."""
    from org.openpnp.model import Location
    mm = _units()
    if math.hypot(dx, dy) > limit_mm:
        raise ValueError("offset %.2f mm larger than %.1f mm: check the feeder by hand" % (math.hypot(dx, dy), limit_mm))
    before = feeder.getPickLocation().convertToUnits(mm)
    target = (before.getX() + dx, before.getY() + dy)
    old = feeder.getOffset()
    rot = 0.0
    if hasattr(feeder, "getSlot") and feeder.getSlot() is not None and feeder.getSlot().getLocation() is not None:
        rot = feeder.getSlot().getLocation().getRotation()
    a = math.radians(-rot)                               # machine frame -> slot frame
    ox, oy = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
    o = old.convertToUnits(mm)
    feeder.setOffset(Location(mm, o.getX() + ox, o.getY() + oy, o.getZ(), o.getRotation()))
    after = feeder.getPickLocation().convertToUnits(mm)
    if math.hypot(after.getX() - target[0], after.getY() - target[1]) > 0.01:
        feeder.setOffset(old)
        raise RuntimeError("offset did not move the pick location as intended (reverted)")
    return before, after
