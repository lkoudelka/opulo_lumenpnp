# -*- coding: utf-8 -*-
"""Vacuum contact probing with a normal OpenPnP nozzle (no ContactProbeNozzle, no config change).

The nozzle goes down in small steps with the vacuum on; when the tip touches a flat surface the
opening is sealed and the vacuum sensor reading drops.  The step where that happens is the
surface Z.  A hard floor Z is never passed; the nozzle always returns to safe Z with the vacuum
off, also on errors.  Call inside a machine task (Jython, OpenPnP).
"""
from __future__ import absolute_import, division, print_function

import math
import time


def _mm():
    from org.openpnp.model import LengthUnit
    return LengthUnit.Millimeters


def actuate(actuator, on):
    """actuate(boolean) explicitly: Jython may pick the actuate(double) overload for a Python bool,
    and a Boolean actuator does nothing on a double (found on the bench, VAC1.actuate(1.0))."""
    from java.lang import Boolean
    from org.openpnp.spi import Actuator
    Actuator.getMethod("actuate", [Boolean.TYPE]).invoke(actuator, [Boolean(bool(on))])


def read_level(nozzle, n=5, pause=0.05):
    a = nozzle.getVacuumSenseActuator()
    vals = []
    for _ in range(n):
        vals.append(float(str(a.read()).strip()))
        time.sleep(pause)
    mean = sum(vals) / len(vals)
    sd = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
    return mean, sd, vals


def baseline(nozzle, n=10, settle=0.6):
    """Vacuum on in free air: (mean, sd, values).  The caller has the nozzle in free air."""
    va = nozzle.getVacuumActuator()
    actuate(va, True)
    try:
        time.sleep(settle)
        return read_level(nozzle, n)
    finally:
        actuate(va, False)


def probe(nozzle, x, y, z_start, z_floor, step=0.05, speed=0.05, min_drop=5.0, max_travel=2.0, log=None):
    """Surface Z under (x, y) -> dict {z, free_air, start_level, threshold, readings}.

    Safety (bench 2026-11-06: a baseline taken at the start height was already 'covered' and the
    nozzle was driven into the board):
    - the free-air level is read at SAFE Z, never at the start height;
    - at z_start the level must still be free air, else abort (already touching);
    - small steps (step mm) at low speed, stop at the FIRST drop of more than the threshold;
    - never more than max_travel below z_start and never below z_floor.
    The nozzle always returns to safe Z with the vacuum off (also on errors)."""
    from org.openpnp.model import Location
    from org.openpnp.util import MovableUtils
    mm = _mm()
    say = log or (lambda s: None)
    floor = max(z_floor, z_start - max_travel)
    if floor >= z_start:
        raise ValueError("floor %.2f must be below z_start %.2f" % (floor, z_start))
    va = nozzle.getVacuumActuator()
    out = {"x": x, "y": y, "readings": [], "floor": floor}
    rot = nozzle.getLocation().getRotation()
    try:
        MovableUtils.moveToLocationAtSafeZ(nozzle, Location(mm, x, y, float("nan"), rot))
        actuate(va, True)
        time.sleep(0.8)
        free, sd, _ = read_level(nozzle, 8)                   # at safe Z: certainly free air
        thr = max(min_drop, 6.0 * sd)
        out.update(free_air=free, sd=sd, threshold=thr)
        say("  probe %.3f/%.3f: free air %.1f (sd %.2f) at safe Z, contact = drop > %.1f, start %.2f, floor %.2f"
            % (x, y, free, sd, thr, z_start, floor))

        def level_at(z):
            nozzle.moveTo(Location(mm, x, y, z, rot), speed)
            time.sleep(0.2)
            v, _, _ = read_level(nozzle, 2, 0.04)
            out["readings"].append((round(z, 3), round(v, 1)))
            return v
        v0 = level_at(z_start)
        out["start_level"] = v0
        if free - v0 > thr:
            raise RuntimeError("already covered at the start Z %.2f (level %.1f, free air %.1f): surface is higher - "
                               "aborted" % (z_start, v0, free))
        z = z_start
        while z - step >= floor - 1e-9:
            z -= step
            if free - level_at(z) > thr:
                out["z"] = round(z, 3)
                say("  contact at Z %.3f (level %.1f)" % (z, out["readings"][-1][1]))
                return out
        raise RuntimeError("no contact down to Z %.2f (last level %.1f)" % (floor, out["readings"][-1][1]))
    finally:
        try:
            actuate(va, False)
        finally:
            nozzle.moveToSafeZ()


def plane_tilt(points):
    """points [(x, y, z)] -> (mean z, tilt = max-min, slope mm/100mm along x, along y) (least squares)."""
    n = len(points)
    mz = sum(p[2] for p in points) / n
    if n < 3:
        return mz, max(p[2] for p in points) - min(p[2] for p in points), None, None
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    sxx = sum((p[0] - mx) ** 2 for p in points)
    syy = sum((p[1] - my) ** 2 for p in points)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in points)
    sxz = sum((p[0] - mx) * (p[2] - mz) for p in points)
    syz = sum((p[1] - my) * (p[2] - mz) for p in points)
    det = sxx * syy - sxy * sxy
    if abs(det) < 1e-9:
        return mz, max(p[2] for p in points) - min(p[2] for p in points), None, None
    a = (sxz * syy - syz * sxy) / det
    b = (syz * sxx - sxz * sxy) / det
    return mz, max(p[2] for p in points) - min(p[2] for p in points), a * 100, b * 100
