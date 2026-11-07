# -*- coding: utf-8 -*-
"""Test placement for orientation doubts (Orientation Setup > "Test placement on the PCB...").

One part of a placement the user is not sure about is fed, picked, aligned and placed on its real
pads exactly like the job would do it - on a board WITHOUT solder paste - and photographed with the
top camera.  The user marks pin 1 in the photo (the same 4 corner dots as in Check); the photo is
compared with where pin 1 has to be (CAD pin 1 turned by the placement rotation, or the board marking
the user clicks).  Then the part is picked up again from the board and RECYCLED into its feeder with
OpenPnP's own Feeder.takeBackPart():
  - Photon (and push-pull) feeders: back into its pocket, the next feed is skipped (SkipNext): the
    tape does not move, the next pick takes this same part;
  - strip / tray / rotated tray / blinds feeders: back into its pocket, feed count - 1;
  - other feeders: whatever OpenPnP supports for them; if the feeder cannot take it back, the part is
    discarded (discard location) and that is reported.
Nothing is wasted in the normal case and nothing in the machine configuration changes unless the
user applies a corrected feeder rotation (after the part is back in the feeder - never before:
the take-back uses the rotation the part was picked with).

Pure functions (CPython 3 and Jython 2.7): the mark / rotation arithmetic, the camera proposal from
golden-sample scores, the pick-back correction.  The OpenPnP part (Jython, inside a machine task):
run_test(), photo(), recycle().
"""
from __future__ import absolute_import, division, print_function

import math
import os
import time

from lumen.orientation import DOTS, norm, rotate_dot

TURNS = (0.0, 90.0, 180.0, -90.0)
LIMITS = {"pickback_mm": 0.4,        # body found further away than this: pick back at the nominal location
          "pickback_deg": 10.0,      # body turned more than this: no rotation correction for the pick-back
          "golden_margin": 0.10,     # golden score of the best turn must beat the second by this
          "golden_min": 0.45,        # ... and reach this
          "off90_deg": 15.0}         # placement rotation further from a multiple of 90: marks are approximate

# how OpenPnP's takeBackPart() recycles, by feeder class (OpenPnP 2.6, checked in the jar)
RECYCLE = {
    "PhotonFeeder": "back into its pocket; the next feed is skipped (SkipNext): the tape does not move",
    "ReferencePushPullFeeder": "back into its pocket; the next feed is skipped (SkipNext)",
    "ReferenceStripFeeder": "back into its pocket; feed count - 1",
    "ReferenceTrayFeeder": "back into its pocket; feed count - 1",
    "ReferenceRotatedTrayFeeder": "back into its pocket; feed count - 1",
    "BlindsFeeder": "back into its pocket; feed count - 1",
    "ReferenceAutoFeeder": "back into its pocket only if the feeder has 'recycle support' on, else discarded",
    "ReferenceLoosePartFeeder": "back to the loose-part pick location",
    "AdvancedLoosePartFeeder": "back to the loose-part pick location",
    "ReferenceHeapFeeder": "back into its heap",
}


def recycle_text(class_name):
    return RECYCLE.get(class_name, "this feeder type cannot take parts back: the part would be DISCARDED (wasted)")


def round90(a):
    return norm(round(float(a) / 90.0) * 90.0)


def off90(a):
    """How far the rotation is from a multiple of 90 deg."""
    return abs(norm(float(a) - round90(a)))


def board_mark(cad_dot, placement_rot):
    """Where pin 1 has to be on the board (machine frame, seen from above) for this placement."""
    if cad_dot not in DOTS:
        return None
    return rotate_dot(cad_dot, round90(placement_rot))


def cad_from_board(board_dot, placement_rot):
    """CAD pin 1 (footprint at 0 deg) from the board marking seen at the placement rotation."""
    if board_dot not in DOTS:
        return None
    return rotate_dot(board_dot, -round90(placement_rot))


def turn(part_dot, board_dot):
    """How much the placed part is turned against where it should be (deg CCW, 0/90/180/-90)."""
    if part_dot not in DOTS or board_dot not in DOTS:
        return None
    return norm(DOTS[part_dot] - DOTS[board_dot])


def evaluate(part_dot, board_dot, feeder_rot):
    """{turn, ok, new_rotation, text}.  The part sat in the feeder turned by `turn` against what the
    feeder rotation says, so the correct feeder rotation is the current one + turn."""
    t = turn(part_dot, board_dot)
    if t is None:
        return {"turn": None, "ok": None, "new_rotation": None,
                "text": "Mark pin 1 of the placed part%s in the photo." % ("" if board_dot else " and pin 1 of the board")}
    if t == 0:
        return {"turn": 0.0, "ok": True, "new_rotation": None if feeder_rot is None else norm(feeder_rot),
                "text": "CORRECT: the part sits as the board wants it - the feeder rotation is right."}
    new = None if feeder_rot is None else round90(feeder_rot + t)
    txt = "WRONG: the part is turned %+.0f deg" % t
    if new is not None:
        txt += " - feeder rotation must be %+.0f deg (now %+.0f deg)" % (new, norm(feeder_rot))
    return {"turn": t, "ok": False, "new_rotation": new, "text": txt}


def feeder_dot_for(cad_dot, rotation):
    """Pin 1 of the part in the feeder (machine frame) for a known-correct feeder rotation."""
    if cad_dot not in DOTS or rotation is None:
        return None
    return rotate_dot(cad_dot, round90(rotation))


def propose_turn(scores, margin=None, minimum=None):
    """scores {turn: golden-sample score} -> (turn or None, why).  Only a clear winner is proposed."""
    margin = LIMITS["golden_margin"] if margin is None else margin
    minimum = LIMITS["golden_min"] if minimum is None else minimum
    if not scores:
        return None, "no golden sample for this package (make one in Placement Inspection)"
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best, s = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else -1.0
    table = ", ".join("%+.0f: %.2f" % (t, v) for t, v in sorted(scores.items()))
    if s < minimum:
        return None, "golden sample does not match well at any turn (%s)" % table
    if s - second < margin:
        return None, "golden sample: no clear winner (%s)" % table
    return norm(best), "golden sample matches best turned %+.0f deg (%s)" % (best, table)


def pickback_correction(body, limits=None):
    """(dx, dy, drot, why): where the part really lies against the placement location (top camera body
    search), so the nozzle picks it back in the same grip it was placed with."""
    lim = limits or LIMITS
    if not body or not body.get("found"):
        return 0.0, 0.0, 0.0, "body not found in the photo: pick back at the place location"
    d = math.hypot(body["dx"], body["dy"])
    if d > lim["pickback_mm"]:
        return 0.0, 0.0, 0.0, "body found %.2f mm away (> %.2f): not trusted, pick back at the place location" % (
            d, lim["pickback_mm"])
    da = body.get("angle_err") or 0.0
    if abs(da) > lim["pickback_deg"]:
        return body["dx"], body["dy"], 0.0, "pick back %.2f mm off the place location (turn %.0f deg not corrected)" % (d, da)
    return body["dx"], body["dy"], da, "pick back %.2f mm / %+.1f deg off the place location (body in the photo)" % (d, da)


def pickback_location(nozzle_at, centre, dx, dy, da):
    """Nozzle (x, y, rot) to pick the part back in the same grip: the part centre moved from `centre`
    by (dx, dy) and turned by da about itself, so the nozzle moves along (orbits the part centre)."""
    rx, ry = nozzle_at[0] - centre[0], nozzle_at[1] - centre[1]
    a = math.radians(da)
    return (centre[0] + dx + rx * math.cos(a) - ry * math.sin(a),
            centre[1] + dy + rx * math.sin(a) + ry * math.cos(a), nozzle_at[2] + da)


def placement_choices(cands):
    """cands [(label, placed)] -> index of the default: the first one not placed yet."""
    for i, (_, placed) in enumerate(cands):
        if not placed:
            return i
    return 0


def split_rows(rows):
    """Selected rows -> (to test, skipped): parts marked 'orientation not relevant' are not worth a test."""
    keep = [r for r in rows if r.get("matters") is not False]
    return keep, [r for r in rows if r.get("matters") is False]


def view_check(length, width, upp, w_px, h_px):
    """None when the body fits the square photo crop (short side of the camera image), else a warning."""
    if not length or not upp:
        return None
    view = min(w_px, h_px) * upp
    size = max(length, width or 0.0)
    if size <= 0.9 * view:
        return None
    return ("The part (%.1f mm) is about as big as the camera view (%.1f mm): pin 1 may be outside the photo, "
            "check it in the camera view of OpenPnP" % (size, view))


# ---------------------------------------------------------------------------------------
# OpenPnP side (Jython, inside a machine task)
# ---------------------------------------------------------------------------------------
def _errors():
    """Python and Java exceptions (Jython does not catch Java ones with 'except Exception')."""
    try:
        from java.lang import Throwable
        return (Exception, Throwable)
    except ImportError:
        return (Exception,)


class TestError(Exception):
    """A step of the test failed; .where says where the part is now."""

    def __init__(self, msg, where):
        Exception.__init__(self, msg)
        self.where = where


def _forget_feed(nozzle):
    """The Lumen Nozzle.AfterPick hook (pick vacuum check) judges job picks by the last job feed of
    this nozzle; a test pick is not a job pick."""
    from java.lang import System
    System.clearProperty("lumen.lastfeed." + str(nozzle.getId()))


def compatible_nozzles(machine, part):
    """Empty nozzles whose LOADED tip suits the part's package (no automatic tip change)."""
    pk = part.getPackage() if part is not None else None
    tips = set(pk.getCompatibleNozzleTips()) if pk is not None else set()
    return [n for n in machine.getDefaultHead().getNozzles()
            if n.getNozzleTip() is not None and n.getNozzleTip() in tips and n.getPart() is None]


def problems(machine, bl, pl, feeder, nozzle):
    """Reasons the test cannot run (empty list = ok).  No motion."""
    out = []
    if hasattr(machine, "isHomed") and not machine.isHomed():
        out.append("the machine is not homed (home it first)")
    part = pl.getPart() if pl is not None else None
    if part is None:
        out.append("the placement has no part")
    if feeder is None:
        out.append("no feeder has this part")
    else:
        if not feeder.isEnabled():
            out.append("feeder %s is disabled" % feeder.getName())
        if part is not None and feeder.getPart() != part:
            out.append("feeder %s holds %s, not %s" % (feeder.getName(), feeder.getPart().getId() if feeder.getPart() else "-",
                                                       part.getId()))
    if nozzle is None:
        out.append("no empty nozzle with a compatible nozzle tip loaded (load it first; no automatic tip change)")
    elif nozzle.getPart() is not None:
        out.append("nozzle %s holds a part" % nozzle.getName())
    if bl is not None and str(bl.getGlobalSide()) != "Top":
        out.append("the board is placed bottom side up: test placement supports the top side only")
    if part is not None and part.getHeight().getValue() <= 0 and (
            nozzle is None or nozzle.getClass().getSimpleName() != "ContactProbeNozzle"):
        out.append("part %s has no height (the place Z would be wrong)" % part.getId())
    return out


def placement_location(nominal, offsets):
    """The job's place location (ReferencePnpJobProcessor.getPlacementLocation, OpenPnP 2.6)."""
    from org.openpnp.model import LengthUnit, Location
    if offsets is None:
        return nominal
    if offsets.getPreRotated():
        return nominal.subtractWithRotation(offsets.getLocation())
    a = offsets.getLocation()
    loc = Location(LengthUnit.Millimeters).rotateXyCenterPoint(a, nominal.getRotation() - a.getRotation())
    loc = loc.derive(None, None, None, nominal.getRotation() - a.getRotation())
    return loc.add(nominal).subtract(a)


def _part_on(nozzle):
    from org.openpnp.spi import Nozzle
    return not nozzle.isPartOnEnabled(Nozzle.PartOnStep.AfterPick) or nozzle.isPartOn()


def _part_off_after_place(nozzle):
    from org.openpnp.spi import Nozzle
    return not nozzle.isPartOffEnabled(Nozzle.PartOffStep.AfterPlace) or nozzle.isPartOff()


def _give_back(feeder, nozzle):
    """Part still on the nozzle (never on the board): back into the feeder, else discard."""
    from org.openpnp.spi.base import AbstractPnpJobProcessor
    why = "the feeder cannot take it back now"
    try:
        if feeder.canTakeBackPart():
            feeder.takeBackPart(nozzle)
            return "returned to %s (%s)" % (feeder.getName(), recycle_text(feeder.getClass().getSimpleName()))
    except _errors() as e:
        why = "take-back failed: %s" % e
    AbstractPnpJobProcessor.discard(nozzle)
    return "discarded (%s)" % why


def run_test(machine, bl, pl, feeder, nozzle, align=True, log=print):
    """Feed, pick, align, place on the board (no paste), nozzle up.  Returns the state for photo() and
    recycle().  On an error before the place, the part is given back to the feeder (or discarded)."""
    from org.openpnp.machine.reference.vision import AbstractPartAlignment
    from org.openpnp.spi import Nozzle
    from org.openpnp.util import Utils2D, VisionUtils
    from org.openpnp.spi.base import AbstractPnpJobProcessor
    part = pl.getPart()
    st = {"part": str(part.getId()), "ref": str(pl.getId()), "feeder": feeder.getName(), "nozzle": nozzle.getName(),
          "on_board": False, "t": time.strftime("%Y-%m-%dT%H:%M:%S")}
    _forget_feed(nozzle)
    if nozzle.isPartOffEnabled(Nozzle.PartOffStep.BeforePick):
        nozzle.moveToSafeZ()
        if not nozzle.isPartOff():
            raise TestError("vacuum says nozzle %s is not empty - check it" % nozzle.getName(), "nothing moved")
    st["count_before"] = feeder.getFeedCount() if hasattr(feeder, "getFeedCount") else None
    feeder.feed(nozzle)
    log("test placement %s (%s): fed %s" % (st["ref"], st["part"], feeder.getName()))
    nominal = Utils2D.calculateBoardPlacementLocation(bl, pl.getLocation())
    try:
        nozzle.prepareForPickAndPlaceArticulation(feeder.getPickLocation(), nominal)
        nozzle.moveToPickLocation(feeder)
        nozzle.pick(part, feeder)
        nozzle.moveToSafeZ()
        feeder.postPick(nozzle)
    except _errors() as e:
        try:
            AbstractPnpJobProcessor.discard(nozzle)
        except _errors():
            pass
        raise TestError("pick failed: %s" % e, "nozzle emptied at the discard location (if anything was on it)")
    if not _part_on(nozzle):
        AbstractPnpJobProcessor.discard(nozzle)
        raise TestError("no part on the nozzle after the pick (vacuum)", "the part is still in the feeder or lost: check")
    try:
        offsets = None
        if align:
            al = AbstractPartAlignment.getPartAlignment(part)
            if al is not None:
                offsets = VisionUtils.findPartAlignmentOffsets(al, part, bl, pl, nozzle)
                st["alignment"] = str(offsets)
            else:
                st["alignment"] = "no enabled bottom vision for this part"
        loc = placement_location(nominal, offsets)
        if not _part_on(nozzle):
            raise RuntimeError("part lost after the alignment (vacuum)")
        nozzle.moveToPlacementLocation(loc, part)
        at = nozzle.getLocation()
    except _errors() as e:
        where = _give_back(feeder, nozzle) if nozzle.getPart() is not None else "lost (not on the nozzle any more)"
        raise TestError("before the place: %s" % e, "part " + where)
    nozzle.place()
    nozzle.moveToSafeZ()
    st["on_board"] = True
    st["at"] = [at.getX(), at.getY(), at.getZ(), at.getRotation(), str(at.getUnits())]
    st["_at"] = at
    st["_loc"] = loc
    st["_nominal"] = nominal
    st["nominal"] = [nominal.getX(), nominal.getY(), nominal.getRotation()]
    st["placement_rot"] = nominal.getRotation()
    if not _part_off_after_place(nozzle):
        st["warning"] = "vacuum still sees a part after the place: the part may have stayed on the nozzle"
    log("test placement %s: placed at %s with %s (%s)" % (st["ref"], loc, nozzle.getName(), st.get("alignment", "no alignment")))
    return st


def photo(machine, bl, pl, st, golden_root=None, save_dir=None):
    """Top camera over the placed part; body search and golden-sample turns (lumen.inspect)."""
    from org.openpnp.model import Length, LengthUnit, Location
    from org.openpnp.util import MovableUtils
    from lumen import inspect as ins
    mm = LengthUnit.Millimeters
    part = pl.getPart()
    pkg = part.getPackage()
    n = st["_nominal"].convertToUnits(mm)          # the part centre belongs here (alignment compensated)
    z = bl.getLocation().convertToUnits(mm).getZ() + part.getHeight().convertToUnits(mm).getValue()
    cam = machine.getDefaultHead().getDefaultCamera()
    MovableUtils.moveToLocationAtSafeZ(cam, Location(mm, n.getX(), n.getY(), z, 0.0))
    img = cam.settleAndCapture()
    upp = cam.getUnitsPerPixel(Length(z, mm)).convertToUnits(mm).getX()
    length, width, src = ins.body_size(pkg)
    rot = st["placement_rot"]
    fp = pkg.getFootprint() if pkg is not None else None
    axis = rot + (90.0 if fp is not None and fp.getBodyHeight() > fp.getBodyWidth() else 0.0)
    res = {"upp": upp, "size_source": src, "image": None}
    if length:
        try:
            res["body"] = ins.find_body(img, upp, length, width, axis)
        except _errors() as e:                              # shown; the user still judges
            res["body"] = {"found": False, "why": "body search failed: %s" % e}
    g = ins.load_golden(golden_root, str(pkg.getId())) if golden_root and pkg is not None else None
    if g is not None:
        try:
            res["golden_turns"] = ins.match_golden_turns(img, upp, g, axis, TURNS)
        except _errors() as e:
            res["golden_error"] = str(e)
    res["proposal"], res["proposal_why"] = propose_turn(res.get("golden_turns"))
    res["axis_rot"], res["length"], res["width"] = axis, length, width
    res["view_warning"] = view_check(length, width, upp, img.getWidth(), img.getHeight())
    crop_mm = max(2.0, 3.0 * (length or 1.0))
    s = int(min(crop_mm / upp, img.getWidth(), img.getHeight()))
    res["crop_mm"] = s * upp
    res["crop"] = img.getSubimage(img.getWidth() // 2 - s // 2, img.getHeight() // 2 - s // 2, s, s)
    res["_image"] = img
    if save_dir:
        from java.io import File
        from javax.imageio import ImageIO
        if not os.path.isdir(save_dir):
            os.makedirs(save_dir)
        p = os.path.join(save_dir, "test-%s-%s.png" % (ins._safe(st["ref"]), time.strftime("%Y%m%d-%H%M%S")))
        ImageIO.write(img, "png", File(p))
        res["image"] = p
    return res


def recycle(machine, feeder, nozzle, pl, st, mode="return", body=None, log=print):
    """Pick the test part up from the board and give it back.  mode: "return" (feeder, recommended),
    "discard" (discard location), "leave" (stays on the board - the user removes it).  Returns the
    text of what happened; raises TestError if the part could not be picked up from the board."""
    from org.openpnp.util import MovableUtils
    from org.openpnp.spi.base import AbstractPnpJobProcessor
    part = pl.getPart()
    if mode == "leave":
        st["on_board"] = False
        return "left on the board (%s) - remove it by hand" % st["ref"]
    at = st["_at"]
    dx, dy, da, why = pickback_correction(body)
    if dx or dy or da:
        from org.openpnp.model import LengthUnit, Location
        mm = LengthUnit.Millimeters
        a, c = at.convertToUnits(mm), st["_nominal"].convertToUnits(mm)
        x, y, r = pickback_location((a.getX(), a.getY(), a.getRotation()), (c.getX(), c.getY()), dx, dy, da)
        at = Location(mm, x, y, a.getZ(), r)
    _forget_feed(nozzle)
    MovableUtils.moveToLocationAtSafeZ(nozzle, at)
    nozzle.pick(part, feeder)
    nozzle.moveToSafeZ()
    if not _part_on(nozzle):
        nozzle.place()                                     # vacuum off again, nothing held
        raise TestError("the part was not picked up from the board (vacuum, %s)" % why, "still on the board at %s: remove it by hand"
                        % st["ref"])
    st["on_board"] = False
    log("test placement %s: picked back from the board (%s)" % (st["ref"], why))
    if mode == "discard" or not feeder.canTakeBackPart():
        reason = "as chosen" if mode == "discard" else "feeder %s cannot take it back now (%s)" % (
            feeder.getName(), recycle_text(feeder.getClass().getSimpleName()))
        AbstractPnpJobProcessor.discard(nozzle)
        return "DISCARDED at the discard location (%s)" % reason
    before = feeder.getFeedCount() if hasattr(feeder, "getFeedCount") else None
    try:
        feeder.takeBackPart(nozzle)
    except _errors() as e:
        if nozzle.getPart() is not None:                  # failed before putting it down: still held
            AbstractPnpJobProcessor.discard(nozzle)
            return "take-back into %s failed (%s): DISCARDED at the discard location" % (feeder.getName(), e)
        raise TestError("take-back into %s failed after putting the part down: %s" % (feeder.getName(), e),
                        "probably in the feeder pocket, maybe still on the nozzle tip: check both before the next feed")
    txt = "returned to %s: %s" % (feeder.getName(), recycle_text(feeder.getClass().getSimpleName()))
    if before is not None and hasattr(feeder, "getFeedCount"):
        txt += " (feed count %d -> %d)" % (before, feeder.getFeedCount())
    if hasattr(feeder, "getFeedOptions"):
        txt += " [feed option %s]" % feeder.getFeedOptions().name()
    return txt
