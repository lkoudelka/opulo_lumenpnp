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


def part_placements(job, part_id):
    """[(boardLocation, placement, placed)] of one part in the job: not yet placed first, job order otherwise."""
    out = [(bl, pl, placed) for bl, pl, placed in job_placements(job)
           if (pl.getPart().getId() if pl.getPart() else "(no part: %s)" % pl.getId()) == part_id]
    return [x for x in out if not x[2]] + [x for x in out if x[2]]


def feeders_to_look_at(row):
    """The row's feeders for the camera: usable ones first, then the others (may lack a location)."""
    return list(row["enabled_feeders"]) + [f for f in row["feeders"] if f not in row["enabled_feeders"]]


def part_height_mm(part):
    try:
        return part.getHeight().convertToUnits(LengthUnit.Millimeters).getValue()
    except Exception:
        return 0.0


def tip_issue(part, machine):
    """None, or why no nozzle can take this part with the tips loaded now.  OpenPnP's job then plans an automatic
    nozzle tip change; without a tip changer (Lumen) that move goes to the unset changer location and the job stops
    with "Can't move y to -110.698mm, lower than soft limit" - no part, package or tip named (bench 2026-11-26:
    C11, CAPC_2220, only N24 ticked)."""
    pk = part.getPackage() if part is not None else None
    if pk is None:
        return None
    nozzles = [n for n in machine.getDefaultHead().getNozzles()]
    loaded = [(n.getName(), n.getNozzleTip()) for n in nozzles]
    tips = list(pk.getCompatibleNozzleTips())
    if any(t is not None and t in tips for _, t in loaded):
        return None
    now = ", ".join("%s has %s" % (n, t.getName() if t is not None else "no tip") for n, t in loaded)
    if not tips:
        return ("package %s has no compatible nozzle tip (%s): tick one in Packages > %s > Nozzle Tips"
                % (pk.getId(), now, pk.getId()))
    return ("package %s needs nozzle tip %s, not loaded (%s): the job would try an automatic tip change and stop with "
            "\"Can't move ... soft limit\". Tick a loaded tip in Packages > %s > Nozzle Tips, or load %s by hand"
            % (pk.getId(), " / ".join(t.getName() for t in tips), now, pk.getId(),
               " / ".join(t.getName() for t in tips)))


def tip_problems(job, machine):
    """[(part id, references not placed yet, issue)] for the open job's parts no loaded nozzle tip suits."""
    parts = {}
    for bl, pl, placed in job_placements(job):
        part = pl.getPart()
        if placed or part is None:
            continue
        parts.setdefault(part.getId(), (part, []))[1].append(pl.getId())
    out = []
    for pid in sorted(parts):
        part, refs = parts[pid]
        issue = tip_issue(part, machine)
        if issue:
            out.append((pid, refs, issue))
    return out


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
        tip = tip_issue(part, machine) if part is not None and r["remaining"] > 0 else None
        if tip:
            issues.append(tip)
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


def tour(job, machine):
    """The job's feeders for a camera round, one row each in slot order (front rail, then rear):
    {feeder, slot, part_id, refs [not placed first], remaining, status ('ready' or why not)}; parts that no feeder
    holds come last with feeder None."""
    rows, lost = [], []
    for r in readiness(job, machine) if job is not None else []:
        refs = [pl.getId() for _, pl, _ in part_placements(job, r["part_id"])]
        fs = feeders_to_look_at(r)
        if not fs:
            lost.append({"feeder": None, "slot": None, "part_id": r["part_id"], "refs": refs,
                         "remaining": r["remaining"], "status": "; ".join(r["issues"]) or "no feeder"})
        for f in fs:
            slot = f.getSlotAddress() if hasattr(f, "getSlotAddress") else None
            status = ("disabled: %s" % unusable_reason(f)) if not f.isEnabled() else ("; ".join(r["issues"]) or "ready")
            rows.append({"feeder": f, "slot": int(slot) if slot is not None else None, "part_id": r["part_id"],
                         "refs": refs, "remaining": r["remaining"], "status": status})
    rows.sort(key=lambda x: (x["slot"] is None, x["slot"] or 0, x["feeder"].getName()))
    return rows + sorted(lost, key=lambda x: x["part_id"])


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
