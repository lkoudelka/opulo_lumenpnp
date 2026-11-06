# -*- coding: utf-8 -*-
"""What the open job needs: parts, quantities, feeders, blocking issues (Jython in OpenPnP)."""
from __future__ import absolute_import, division, print_function

from org.openpnp.model import LengthUnit
from org.openpnp.model import Placement


def _side_ok(bl, pl):
    try:
        return pl.getSide() == bl.getGlobalSide()
    except Exception:
        return True


def job_placements(job):
    """[(boardLocation, placement, placed)] that this job would place (enabled board, enabled
    placement of type Placement on the board's side)."""
    out = []
    for bl in job.getBoardLocations():
        if not bl.isEnabled():
            continue
        for pl in bl.getPlacementsHolder().getPlacements():
            if pl.getType() != Placement.Type.Placement or not pl.isEnabled() or not _side_ok(bl, pl):
                continue
            out.append((bl, pl, bool(job.retrievePlacedStatus(bl, pl.getId()))))
    return out


def part_height_mm(part):
    try:
        return part.getHeight().convertToUnits(LengthUnit.Millimeters).getValue()
    except Exception:
        return 0.0


def readiness(job, machine, lumen_profile=None):
    """One row per part used by the job:
    {part, part_id, package, height, total, remaining, feeders: [feeder], enabled_feeders, issues: [str]}"""
    from org.openpnp.machine.photon import PhotonFeeder
    if lumen_profile is None:
        from lumen.oppnp import active_profile
        lumen_profile = active_profile(machine) == "lumen"
    rows = {}
    for bl, pl, placed in job_placements(job):
        part = pl.getPart()
        key = part.getId() if part else "(no part: %s)" % pl.getId()
        r = rows.get(key)
        if r is None:
            r = rows[key] = {"part": part, "part_id": key, "total": 0, "remaining": 0,
                             "package": part.getPackage().getId() if part and part.getPackage() else "",
                             "height": part_height_mm(part) if part else 0.0, "notes": []}
        r["total"] += 1
        if not placed:
            r["remaining"] += 1
    feeders = list(machine.getFeeders())
    for r in rows.values():
        part = r["part"]
        r["feeders"] = [f for f in feeders if part is not None and f.getPart() == part]
        r["enabled_feeders"] = [f for f in r["feeders"] if f.isEnabled()]
        issues = []
        if part is None:
            issues.append("placement has no part")
        elif not r["feeders"]:
            issues.append("no feeder has this part (Feeder Assistant finds set-up feeders by name)")
        elif not r["enabled_feeders"]:
            issues.append("no usable feeder: " + "; ".join(
                "%s: %s" % (f.getName(), unusable_reason(f)) for f in r["feeders"]))
        if part is not None and r["height"] <= 0:
            if not lumen_profile:
                issues.append("part height unknown")
            else:
                r["notes"].append("height unknown: probed on first pick (lumen)")
        if lumen_profile and part is not None and r["package"]:
            try:
                fp = part.getPackage().getFootprint()
                if fp is None or fp.getBodyWidth() <= 0 or fp.getBodyHeight() <= 0:
                    issues.append("package %s has no body size: the bottom-vision size check (lumen) would "
                                  "reject it" % r["package"])
            except Exception:
                pass
        r["issues"] = issues
    return sorted(rows.values(), key=lambda r: (not r["issues"], r["part_id"]))


def unusable_reason(f):
    """Why OpenPnP will not use this feeder.  PhotonFeeder.isEnabled() is true only when it
    is switched on AND has hardware id, part, slot address, pick offset and slot location."""
    from org.openpnp.machine.photon import PhotonFeeder
    if f.isEnabled():
        return "OK"
    if isinstance(f, PhotonFeeder):
        missing = []
        if f.getHardwareId() is None:
            missing.append("not found on the bus yet (Feeders: Search)")
        if f.getSlotAddress() is None:
            missing.append("no slot address")
        elif f.getSlot() is None or f.getSlot().getLocation() is None:
            missing.append("slot %d has no location" % f.getSlotAddress())
        if f.getOffset() is None:
            missing.append("pick offset not set")
        if missing:
            return ", ".join(missing)
    return "switched off"


def feeder_text(f):
    from org.openpnp.machine.photon import PhotonFeeder
    t = f.getName()
    # PhotonFeeder.getName() already ends with "(Slot: N)" once it has a slot address
    if isinstance(f, PhotonFeeder) and f.getSlotAddress() is not None and "Slot" not in t:
        t += " (Slot: %d)" % f.getSlotAddress()
    if not f.isEnabled():
        t += " (not usable: %s)" % unusable_reason(f)
    return t
