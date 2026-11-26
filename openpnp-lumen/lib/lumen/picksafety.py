# -*- coding: utf-8 -*-
"""Pick safety from what the machine already measured (Scripts > Lumen > Preflight > Pick safety).

Bench 2026-11-26: the nozzle came down on the cover foil of a cut strip, nothing was picked, and the part was
"placed" anyway:
- vacuum part-on check: empty nozzle on foil read 232, range 215..232, free air 233..234 -> passed;
- bottom vision: a 1 x 0 px rect was accepted - the package had no body size, the size check was off;
- part-off after place: off.
Typing body sizes and vacuum levels for every part is not practical, so this module LEARNS them from OpenPnP's
log and one no-motion measurement, and proposes; nothing changes without the person's OK:
- body sizes: bottom vision measures every good pick very consistently (RES_0603 1.45 x 0.80 mm in 10 of 10
  picks; empty picks 0.04 mm).  The median per package becomes its footprint body size, in the orientation
  OpenPnP's size check compares (rect width -> body width, height -> body height, not sorted); the size check
  (BodySize, generous tolerance) is switched on in the bottom-vision settings the job's parts use.  An empty
  nozzle then fails bottom vision ("Invalid measured size" / "too small") and OpenPnP retries the pick.
- part-on high limit: between the highest good-pick level and free air (measured with the nozzle empty).
- part-off check: OpenPnP turns the vacuum on for 'probing' ms and reads; a part still on the nozzle seals it
  (lower level), an empty nozzle reads like free air.  The probing time is where the measured free-air
  build-up and the good-pick build-up (log) are clearly apart.
The parsing and the proposals are pure Python (tests run them in CPython); apply_* and measure_* use OpenPnP.
"""
from __future__ import absolute_import, division, print_function

import re

EMPTY_PX = 2              # a rect side <= this many pixels: nothing on the nozzle (bench: 1 x 0)
KEEP = 0.35               # good rects within +-35 % of the package median count
MIN_PICKS = 3
TOLERANCE_PERCENT = 40    # size check tolerance: generous, only an empty / wrong / tilted part fails
PART_ON_MARGIN = 3        # counts between the highest good pick and free air needed for a part-on limit
PART_OFF_SEPARATION = 5   # counts between free air and the good-pick build-up at the probing time

_TS = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}) ")
_RECT = re.compile(r"Bottom vision part (.+?) result rect \{ \{[^}]*\} ([\d.]+)x([\d.]+) \* ([-\d.eE]+) \}")
_ALIGN = re.compile(r"Align id (.+?), name .*? with (\S+) ")
_PICK = re.compile(r" (\S+)\.pick\(\)")
_ACT = re.compile(r" (\S+)\.actuate\((true|false)\)")
_READ = re.compile(r" (\S+)\.read\(\): ([\d.]+)")
_TIP = re.compile(r" (\S+)\.(?:un)?loadNozzleTip\(")
KEYS = ("pick()", ".actuate(", ".read(): ", "Nozzle.AfterPick", "Bottom vision part", "Align id", "NozzleTip(")


def _ms(stamp):
    """'2026-11-26 10:26:00.442' -> milliseconds (only differences are used)."""
    d, t = stamp.split(" ")
    y, mo, da = [int(x) for x in d.split("-")]
    h, mi, s = t.split(":")
    return ((((y * 400 + mo * 31 + da) * 24 + int(h)) * 60 + int(mi)) * 60 + float(s)) * 1000.0


def parse_log(lines, sense_of):
    """OpenPnP log lines -> {"rects": [{part, w, h, nozzle}], "picks": {nozzle: [{level, curve [(ms, v)], ok}]}}.
    sense_of: nozzle name -> vacuum (sense) actuator name, e.g. {"N1": "VAC1"}.  Picks before the last nozzle tip
    change of a nozzle are dropped (other tip, other levels).  Zero readings (sensor not ready) are ignored."""
    act_of = dict((v, k) for k, v in sense_of.items())
    rects, picks = [], dict((n, []) for n in sense_of)
    state = {}                 # nozzle -> {"stage": picking / on / after, "t0", "pick"}
    last_rect = None
    for line in lines:
        if not any(k in line for k in KEYS):
            continue
        m = _TS.match(line)
        t = _ms(m.group(1)) if m else None
        m = _TIP.search(line)
        if m and m.group(1) in picks:
            picks[m.group(1)] = []
            state.pop(m.group(1), None)
            continue
        m = _PICK.search(line)
        if m and m.group(1) in picks:
            p = {"level": None, "curve": [], "ok": None}
            picks[m.group(1)].append(p)
            state[m.group(1)] = {"stage": "picking", "t0": None, "pick": p}
            continue
        m = _ACT.search(line)
        if m and m.group(1) in act_of:
            st = state.get(act_of[m.group(1)])
            if st and m.group(2) == "true" and st["stage"] == "picking" and st["t0"] is None:
                st["t0"] = t
            elif st and m.group(2) == "false":
                st["stage"] = "done"
            continue
        if "Scripting.on Nozzle.AfterPick" in line:
            for st in state.values():
                if st["stage"] == "picking":
                    st["stage"] = "after"
            continue
        m = _READ.search(line)
        if m and m.group(1) in act_of:
            st = state.get(act_of[m.group(1)])
            v = float(m.group(2))
            if st is None or v <= 0:
                continue
            if st["stage"] == "picking" and st["t0"] is not None and t is not None:
                st["pick"]["curve"].append((t - st["t0"], v))
            elif st["stage"] == "after" and st["pick"]["level"] is None:
                st["pick"]["level"] = v
                if t is not None and st["t0"] is not None:
                    st["pick"]["curve"].append((t - st["t0"], v))
            continue
        m = _RECT.search(line)
        if m:
            last_rect = {"part": m.group(1), "w": float(m.group(2)), "h": float(m.group(3)), "nozzle": None}
            rects.append(last_rect)
            continue
        m = _ALIGN.search(line)
        if m and last_rect is not None and last_rect["nozzle"] is None:
            last_rect["nozzle"] = m.group(2)
            st = state.get(m.group(2))
            if st and st["pick"]["ok"] is None:
                st["pick"]["ok"] = min(last_rect["w"], last_rect["h"]) > EMPTY_PX
    return {"rects": rects, "picks": picks}


def median(v):
    v = sorted(v)
    n = len(v)
    return None if n == 0 else v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def learn_sizes(rects, upp, package_of):
    """Per package: {n, empties, w, h (mm, OpenPnP's orientation), ok, why}.  upp: bottom camera mm per pixel.
    package_of: part id -> package id (unknown parts are skipped)."""
    by = {}
    for r in rects:
        pk = package_of(r["part"])
        if pk is None:
            continue
        e = by.setdefault(pk, {"good": [], "empties": 0, "parts": set()})
        e["parts"].add(r["part"])
        if min(r["w"], r["h"]) <= EMPTY_PX:
            e["empties"] += 1
        else:
            e["good"].append((r["w"] * upp, r["h"] * upp))
    out = {}
    for pk, e in by.items():
        g = e["good"]
        res = {"n": len(g), "empties": e["empties"], "w": None, "h": None, "ok": False, "parts": sorted(e["parts"])}
        if len(g) < MIN_PICKS:
            res["why"] = "only %d good pick(s) in the log (needs %d)" % (len(g), MIN_PICKS)
        else:
            wide = len([1 for w, h in g if w >= h])
            if 0 < wide < len(g) and min(wide, len(g) - wide) > 0.2 * len(g):
                res["why"] = "measured orientation varies (%d of %d wider than high): not proposed" % (wide, len(g))
            else:
                mw, mh = median([w for w, h in g]), median([h for w, h in g])
                keep = [(w, h) for w, h in g if abs(w - mw) <= KEEP * mw and abs(h - mh) <= KEEP * mh]
                res.update(w=round(median([w for w, h in keep]), 2), h=round(median([h for w, h in keep]), 2),
                           n=len(keep), ok=True, why="median of %d good pick(s)%s" % (
                               len(keep), "" if len(keep) == len(g) else " (%d outlier(s) left out)" % (len(g) - len(keep))))
        out[pk] = res
    return out


def good_levels(picks):
    """Part-on levels of good picks: bottom vision saw a part afterwards.  Picks without a vision result (rejected by
    OpenPnP's own part-on check, aborted) do not count; without any vision result at all, every pick counts."""
    seen = [p for p in picks if p["ok"] is not None]
    use = [p for p in seen if p["ok"]] if seen else picks
    return [p["level"] for p in use if p["level"] is not None]


def good_curves(picks):
    seen = [p for p in picks if p["ok"] is not None]
    return [p["curve"] for p in (([p for p in seen if p["ok"]]) if seen else picks)]


def steady(curve, from_ms=1000.0):
    """Free-air level: median of the readings after from_ms."""
    v = [x for t, x in curve if t >= from_ms] or [x for t, x in curve[-5:]]
    return median(v)


def propose_part_on(levels, free_air, low_now, high_now):
    """(new_high or None, why).  High limit halfway between the highest good pick and free air."""
    if not levels:
        return None, "no good pick with a vacuum reading in the log"
    if free_air is None:
        return None, "free air not measured"
    top = max(levels)
    if free_air - top < PART_ON_MARGIN:
        return None, ("good picks reach %.0f, free air %.0f: too close for a vacuum part-on check (tip / filter / "
                      "tubing?)" % (top, free_air))
    new = float(int((top + free_air) / 2.0))
    if new < low_now:
        return None, "the proposed high %.0f is below the low limit %.0f" % (new, low_now)
    if abs(new - high_now) < 0.5:
        return None, "already %.0f (good picks up to %.0f, free air %.0f)" % (high_now, top, free_air)
    return new, "good picks %.0f..%.0f (%d), free air %.0f -> high %.0f (now %.0f)" % (
        min(levels), top, len(levels), free_air, new, high_now)


def _at(curve, t):
    """Linear interpolation of [(ms, v)] at t (None outside the measured range)."""
    pts = sorted(curve)
    if not pts or t < pts[0][0] or t > pts[-1][0]:
        return None
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            return v0 if t1 == t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return pts[-1][1]


def propose_part_off(pick_curves, free_curve, max_ms=1500, step=50):
    """(probing_ms, low_limit, why) or (None, None, why).  The earliest probing time where the free-air build-up
    is at least PART_OFF_SEPARATION counts above every good pick's build-up; limit halfway between."""
    curves = [c for c in pick_curves if len(c) >= 2]
    if len(curves) < MIN_PICKS:
        return None, None, "only %d good pick(s) with a vacuum curve in the log" % len(curves)
    if not free_curve:
        return None, None, "free air not measured"

    def apart(t):
        f = _at(free_curve, t)
        ps = [p for p in [_at(c, t) for c in curves] if p is not None]
        return (f, ps) if f is not None and len(ps) >= MIN_PICKS and f - max(ps) >= PART_OFF_SEPARATION else None
    for t in range(step, max_ms + 1, step):
        if apart(t) and apart(t + step):                 # apart at two steps in a row (sensor moves in ~5-count steps)
            f, ps = apart(t)
            low = float(int((f + max(ps)) / 2.0))
            return t, low, ("after %d ms of vacuum: empty nozzle %.0f, part on the nozzle up to %.0f (%d picks) -> "
                            "part off when >= %.0f" % (t, f, max(ps), len(ps), low))
    return None, None, ("empty nozzle and part on the nozzle not clearly apart within %d ms: no part-off check "
                        "proposed" % max_ms)


# ---------------------------------------------------------------------------------------------------------------
# OpenPnP side (Jython)
# ---------------------------------------------------------------------------------------------------------------
def log_lines(config_dir):
    """Lines of OpenPnP's current log (the newest file), keys only (fast)."""
    import os
    p = os.path.join(config_dir, "log", "OpenPnP.log")
    out = []
    f = open(p)
    try:
        for line in f:
            if any(k in line for k in KEYS):
                out.append(line)
    finally:
        f.close()
    return out


def sense_names(machine):
    out = {}
    for n in machine.getDefaultHead().getNozzles():
        a = n.getVacuumSenseActuator() if hasattr(n, "getVacuumSenseActuator") else None
        if a is not None:
            out[str(n.getName())] = str(a.getName())
    return out


def bottom_upp(machine):
    """mm per pixel of the up-looking camera, the way OpenPnP's size check converts (VisionUtils.toPixels)."""
    from org.openpnp.model import Length, LengthUnit
    from org.openpnp.spi import Camera
    from org.openpnp.util import VisionUtils
    for c in machine.getCameras():
        if c.getLooking() == Camera.Looking.Up:
            return 1.0 / VisionUtils.toPixels(Length(1.0, LengthUnit.Millimeters), c)
    return None


def measure_free_air(machine, nozzle, ms=1500):
    """Vacuum on with the EMPTY nozzle (no motion), read as fast as possible for ms, vacuum off.  [(ms, v)].
    Call inside a machine task; the person confirmed the nozzle is empty."""
    import time
    if nozzle.getPart() is not None:
        raise RuntimeError("%s holds a part" % nozzle.getName())
    valve = nozzle.getVacuumActuator() if hasattr(nozzle, "getVacuumActuator") else None
    sense = nozzle.getVacuumSenseActuator()
    if valve is None or sense is None:
        raise RuntimeError("%s has no vacuum valve / sensor actuator" % nozzle.getName())
    curve = []
    t0 = time.time()
    valve.actuate(True)
    try:
        while (time.time() - t0) * 1000.0 < ms:
            v = float(str(sense.read()))
            if v > 0:
                curve.append(((time.time() - t0) * 1000.0, v))
    finally:
        valve.actuate(False)
    return curve


def size_check_settings(job, machine):
    """{vision settings id: (settings, [part ids])} of the bottom-vision settings the job's parts use."""
    from org.openpnp.machine.reference.vision import AbstractPartAlignment
    from lumen import jobinfo
    out = {}
    for bl, pl, placed in jobinfo.job_placements(job):
        part = pl.getPart()
        if part is None:
            continue
        s = AbstractPartAlignment.getInheritedVisionSettings(part, True)
        if s is not None:
            e = out.setdefault(str(s.getId()), (s, []))
            if part.getId() not in e[1]:
                e[1].append(part.getId())
    return out


def apply_size(package, w, h):
    """Footprint body size (mm) of the package; returns the old (w, h) in mm."""
    from org.openpnp.model import Footprint, LengthUnit
    fp = package.getFootprint()
    if fp is None:
        fp = Footprint()
        package.setFootprint(fp)
    f = 1.0 if fp.getUnits() == LengthUnit.Millimeters else 25.4
    old = (fp.getBodyWidth() * f, fp.getBodyHeight() * f)
    fp.setBodyWidth(w / f)
    fp.setBodyHeight(h / f)
    return old


def apply_size_check(settings, tolerance=TOLERANCE_PERCENT):
    from org.openpnp.machine.reference.vision import ReferenceBottomVision
    old = (str(settings.getCheckPartSizeMethod()), settings.getCheckSizeTolerancePercent())
    settings.setCheckPartSizeMethod(ReferenceBottomVision.PartSizeCheckMethod.BodySize)
    settings.setCheckSizeTolerancePercent(int(tolerance))
    return old


def apply_part_on_high(tip, high):
    old = tip.getVacuumLevelPartOnHigh()
    tip.setVacuumLevelPartOnHigh(float(high))
    return old


def apply_part_off(tip, probing_ms, low):
    from org.openpnp.machine.reference import ReferenceNozzleTip
    old = (str(tip.getMethodPartOff()), tip.getPartOffProbingMilliseconds(), tip.getVacuumLevelPartOffLow(),
           tip.getVacuumLevelPartOffHigh(), tip.isPartOffCheckAfterPlace())
    tip.setMethodPartOff(ReferenceNozzleTip.VacuumMeasurementMethod.Absolute)
    tip.setPartOffProbingMilliseconds(int(probing_ms))
    tip.setPartOffDwellMilliseconds(0)
    tip.setVacuumLevelPartOffLow(float(low))
    tip.setVacuumLevelPartOffHigh(max(float(tip.getVacuumLevelPartOffHigh()), 255.0))
    tip.setPartOffCheckAfterPlace(True)
    return old
