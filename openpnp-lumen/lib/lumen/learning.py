# -*- coding: utf-8 -*-
"""Pick-offset learning from bottom-vision offsets (study §3 layer A) + orientation hints (§2).

Pure Python (CPython 3 and Jython 2.7): records come from the lumen-profile hook
Vision.PartAlignment.After (pick-offsets.jsonl), corrections are logged in
offset-corrections.jsonl.

Model: the bottom vision reports the part offset relative to the nozzle (dx, dy) at the
nozzle rotation used for alignment.  Rotated into the frame at pick time, the mean of that
vector is the systematic pick error of the feeder; moving the feeder's pick location by
+gain * mean centres the pick.  The sign/frame assumption is checked automatically after
every correction: if the following samples get worse, the correction is flagged for undo.
"""
from __future__ import absolute_import, division, print_function

import json
import math
import os

DEFAULTS = {
    "min_samples": 5,         # samples since the last correction before suggesting
    "min_mean_mm": 0.15,      # systematic error worth correcting
    "max_std_mm": 0.25,       # only if the scatter is small (systematic, not noise)
    "gain": 0.5,              # damped correction
    "max_step_mm": 0.5,       # never move a feeder more than this in one step
    "worse_factor": 1.3,      # residual after a correction this much larger -> flag
    "orientation_deg": 30.0,  # mean rotation correction beyond this -> orientation hint
}


def load_jsonl(path):
    out = []
    if not os.path.isfile(path):
        return out
    f = open(path)
    try:
        for line in f:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    finally:
        f.close()
    return out


def append_jsonl(path, rec):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    f = open(path, "a")
    f.write(json.dumps(rec) + "\n")
    f.close()


def to_pick_frame(rec):
    """(ex, ey) in mm: the part offset rotated from the alignment rotation to the pick rotation."""
    dx, dy = rec.get("dx") or 0.0, rec.get("dy") or 0.0
    if (rec.get("units") or "Millimeters") != "Millimeters":
        f = 25.4 if rec.get("units") == "Inches" else 1.0
        dx, dy = dx * f, dy * f
    pick = rec.get("pick") or [0, 0, 0, 0]
    a = math.radians((pick[3] if len(pick) > 3 else 0.0) - (rec.get("nozzle_rot") or 0.0))
    return dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)


def _mean_std(vals):
    n = len(vals)
    if not n:
        return 0.0, 0.0
    m = sum(vals) / n
    return m, math.sqrt(sum((v - m) ** 2 for v in vals) / n)


def _norm_angle(a):
    a = (a + 180.0) % 360.0 - 180.0
    return a


def analyse(records, corrections, cfg=None):
    """Per feeder: {feeder_id: {...}} using only samples after the feeder's last correction."""
    c = dict(DEFAULTS)
    c.update(cfg or {})
    epoch, last_corr = {}, {}              # newest correction/undo event per feeder
    for k in corrections:
        fid = k["feeder_id"]
        if k["t"] >= epoch.get(fid, ""):
            epoch[fid] = k["t"]
            last_corr[fid] = None if (k.get("undone") or k.get("undo_of")) else k
    groups = {}
    for r in records:
        fid = r.get("feeder_id")
        if not fid:
            continue
        g = groups.setdefault(fid, {"feeder_id": fid, "feeder": r.get("feeder"), "slot": r.get("slot"),
                                    "parts": set(), "before": [], "after": []})
        (g["after"] if fid not in epoch or r["t"] > epoch[fid] else g["before"]).append(r)
        if r.get("part"):
            g["parts"].add(r["part"])
    out = {}
    for fid, g in groups.items():
        cur = g["after"]
        ex = [to_pick_frame(r)[0] for r in cur]
        ey = [to_pick_frame(r)[1] for r in cur]
        mx, sx = _mean_std(ex)
        my, sy = _mean_std(ey)
        rots = [_norm_angle(r.get("drot") or 0.0) for r in cur]
        mr, sr = _mean_std(rots)
        mag, std = math.hypot(mx, my), math.hypot(sx, sy)
        res = {"feeder_id": fid, "feeder": g["feeder"], "slot": g["slot"], "parts": sorted(g["parts"]),
               "n": len(cur), "mean_x": mx, "mean_y": my, "mean": mag, "std": std, "mean_rot": mr,
               "suggest": None, "status": "", "orientation_hint": None, "worse": False}
        lc = last_corr.get(fid)
        if lc is not None and len(cur) >= c["min_samples"] and lc.get("residual_before") is not None:
            if mag > c["worse_factor"] * lc["residual_before"] and mag > c["min_mean_mm"]:
                res["worse"] = True
        if abs(mr) > c["orientation_deg"] and len(cur) >= c["min_samples"]:
            res["orientation_hint"] = "vision corrects about %+.0f deg on average: check the feeder rotation" % mr
        if res["worse"]:
            res["status"] = "last correction made it WORSE (%.2f -> %.2f mm): undo" % (lc["residual_before"], mag)
        elif len(cur) < c["min_samples"]:
            res["status"] = "collecting (%d/%d samples)" % (len(cur), c["min_samples"])
        elif std > c["max_std_mm"]:
            res["status"] = "scatter %.2f mm too large: tape/feeder issue, not a fixed offset" % std
        elif mag < c["min_mean_mm"]:
            res["status"] = "OK (%.2f mm)" % mag
        else:
            k = c["gain"]
            sx_, sy_ = k * mx, k * my
            step = math.hypot(sx_, sy_)
            if step > c["max_step_mm"]:
                sx_, sy_ = sx_ * c["max_step_mm"] / step, sy_ * c["max_step_mm"] / step
            res["suggest"] = (sx_, sy_)
            res["status"] = "suggest move %+.3f / %+.3f mm" % (sx_, sy_)
        out[fid] = res
    return out
