# -*- coding: utf-8 -*-
"""Inspection of placed parts with the top camera (Jython, OpenPnP's OpenCV).

Per placement the top camera looks at the placement location (board location + placement, view
plane = board Z + part height).  Two methods:
- size: the part body is searched near the image centre as a blob of the expected body size
  (package footprint body, else footprint pads, else the KiCad name e.g. C_0402_1005Metric);
  result: found / not found, offset, angle error (mod 180, mod 90 for square bodies);
- golden: if a golden sample image exists for the package (made from a good placement), it is
  rotated to the expected rotation and matched (normalised correlation) in a search window;
  result: score, offset, and whether the part matches better turned by 180 deg (polarity).
Verdicts are an aid for the operator, not a sign-off: every result has its image saved.
"""
from __future__ import absolute_import, division, print_function

import json
import math
import os
import re
import time

# Offset limits relative to the body (offset_limits): across the part offset_frac x width (IPC-A-610 class 2 accepts a
# side overhang of 50 % of the termination width), along it (towards one pad: the other end loses its pad) only
# offset_along x length; never below offset_mm; and both together not more than the larger of the two.
# 0603 (1.6 x 0.8): 0.24 along / 0.24 across; 0805: 0.30 / 0.38; 0402: 0.15 / 0.15.
LIMITS = {"offset_mm": 0.15, "offset_frac": 0.3, "offset_along": 0.15, "angle_deg": 8.0, "angle_square_deg": 15.0,
          "score_ok": 0.70, "score_fail": 0.45, "search_mm": 0.6, "size_tol": 0.45}
DEFAULT_LIMITS = dict(LIMITS)
# what the operator sets (Placement Inspection > Limits...): key -> (label, unit, min, max, step); fractions shown in %
USER_LIMITS = (("offset_along", "Offset along the part (towards one pad)", "% of length", 0.05, 0.6, 0.01),
               ("offset_frac", "Offset across the part", "% of width", 0.05, 0.8, 0.01),
               ("offset_mm", "Offset limit never below", "mm", 0.05, 1.0, 0.01),
               ("angle_deg", "Rotation", "deg", 1.0, 45.0, 0.5),
               ("angle_square_deg", "Rotation, nearly square parts", "deg", 1.0, 45.0, 0.5))
LIMIT_EXAMPLES = (("0402", 1.0, 0.5), ("0603", 1.6, 0.8), ("0805", 2.0, 1.25), ("1206", 3.2, 1.6),
                  ("SOD-123", 2.7, 1.6), ("SOT-223", 6.5, 3.5))


def limits_path(root):
    return os.path.join(root, "limits.json")


def check_limits(values):
    """{key: float} -> the same, only USER_LIMITS keys, each within its range (ValueError otherwise)."""
    out = {}
    for k, label, unit, lo, hi, step in USER_LIMITS:
        if k in values:
            v = float(values[k])
            if not lo - 1e-9 <= v <= hi + 1e-9:
                raise ValueError("%s: %s outside %s .. %s" % (label, v, lo, hi))
            out[k] = v
    return out


def load_limits(root):
    """Operator limits from <root>/limits.json over the defaults (LIMITS updated); returns the values set there.
    A missing or broken file: defaults."""
    LIMITS.update(DEFAULT_LIMITS)
    try:
        f = open(limits_path(root))
        try:
            got = check_limits(json.load(f))
        finally:
            f.close()
    except (IOError, OSError, ValueError, TypeError, AttributeError):
        return {}
    LIMITS.update(got)
    return got


def save_limits(root, values):
    """Store the operator limits (only the ones differing from the defaults) and use them (LIMITS)."""
    v = check_limits(values)
    keep = dict((k, x) for k, x in v.items() if abs(x - DEFAULT_LIMITS[k]) > 1e-9)
    if not os.path.isdir(root):
        os.makedirs(root)
    f = open(limits_path(root), "w")
    try:
        json.dump(keep, f, indent=1, sort_keys=True)
    finally:
        f.close()
    LIMITS.update(DEFAULT_LIMITS)
    LIMITS.update(v)
    return keep


def limits_text(limits=None):
    """One line per example size: the allowed offsets (mm) along / across and the rotation."""
    lim = limits or LIMITS
    lo = lim["offset_mm"]
    out = []
    for name, l, w in LIMIT_EXAMPLES:
        a = lim["angle_deg"] if l > 1.3 * w else lim["angle_square_deg"]
        out.append("%s (%.1f x %.2f mm): along %.2f, across %.2f mm, rotation %g deg" % (
            name, l, w, max(lo, lim["offset_along"] * l), max(lo, lim["offset_frac"] * w), a))
    return out


def reverdict(res):
    """The verdict again with the current LIMITS.  A part drawn by hand is judged again from where it was drawn; a
    decision by hand (Set as OK / NOT OK) is kept.  Returns (old, new) or None when kept / nothing to judge."""
    v = res.get("verdict") or ""
    if res.get("error") or "(set by hand" in v:
        return None
    if res.get("hand_box"):
        if res.get("_image") is None:
            return None
        dx, dy, hv, truth = hand_position(res, *res["hand_box"])
        new = "%s (was %s)" % (hv, res.get("detected_verdict", ""))
        res.update(verdict=new, manual_ok=truth == "ok")
        return v, new
    if res.get("manual_ok") is not None:
        return None
    new = verdict(res)
    res["verdict"] = new
    return v, new


# ---------------------------------------------------------------------------------------
# expected body size
# ---------------------------------------------------------------------------------------
_METRIC = re.compile(r"(\d{2})(\d{2})Metric")
_IMPERIAL = {"0201": (0.6, 0.3), "0402": (1.0, 0.5), "0603": (1.6, 0.8), "0805": (2.0, 1.25), "1206": (3.2, 1.6),
             "1210": (3.2, 2.5), "1812": (4.5, 3.2), "2010": (5.0, 2.5), "2220": (5.7, 5.0), "2512": (6.3, 3.2)}


# typical plastic body (without leads) of small packages, for the dark-body search when the footprint has no body size
_BODY_BY_NAME = [("SOD-523", (1.2, 0.8)), ("SOD-323", (1.7, 1.25)), ("SOD-123", (2.7, 1.6))]


def body_size(package):
    """(length, width) mm of the body, length >= width, and where it came from; (None, None, why)."""
    if package is None:
        return None, None, "no package"
    fp = package.getFootprint()
    if fp is not None:
        f = 1.0 if str(fp.getUnits()) in ("Millimeters", "mm") else 25.4
        w, h = fp.getBodyWidth() * f, fp.getBodyHeight() * f
        if w > 0 and h > 0:
            return max(w, h), min(w, h), "package body"
        pads = list(fp.getPads())
        if pads:
            xs = [p.getX() * f for p in pads]
            ys = [p.getY() * f for p in pads]
            w = max(xs) - min(xs) + max(p.getWidth() * f for p in pads)
            h = max(ys) - min(ys) + max(p.getHeight() * f for p in pads)
            if w > 0 and h > 0:
                return max(w, h), min(w, h), "package pads"
    name = str(package.getId())
    m = _METRIC.search(name)
    if m:
        a, b = int(m.group(1)) / 10.0, int(m.group(2)) / 10.0
        return max(a, b), min(a, b), "name %s" % m.group(0)
    for code, (a, b) in _IMPERIAL.items():
        if re.search(r"(^|[_\-A-Za-z])%s($|[_\-])" % code, name):
            return a, b, "name %s" % code
    for code, (a, b) in _BODY_BY_NAME:
        if re.search(r"(^|[_\-])%s($|[_\-])" % re.escape(code), name, re.I):
            return a, b, "name %s (typical body)" % code
    return None, None, "body size unknown (set the package footprint body)"


# ---------------------------------------------------------------------------------------
# image analysis
# ---------------------------------------------------------------------------------------
def _cv():
    from lumen.tapevision import _ensure_opencv
    _ensure_opencv()


# Detection channels (bench 2026-11-26, blue solder mask, white LED ring; levels after the top camera colour change,
# WB 6500 K, gamma 130):  blue channel: mask 99, dark body 69, tin ~250 -> dark bodies (find_body);  red channel:
# mask 32, resistor body 40, ceramic body 130, tin 208 -> metal terminations / leads (chip_check).  Grey mixes both
# (body vs mask 8 levels).  Golden samples keep the channel they were made with (older ones: grey).
CHANNELS = {"blue": 0, "green": 1, "red": 2}


def _gray(image, channel="gray"):
    """One channel of a colour picture as the detection image: 'blue' / 'green' / 'red', or 'gray' (luminance)."""
    from org.opencv.core import Core, Mat
    from org.opencv.imgproc import Imgproc
    from org.openpnp.util import OpenCvUtils
    m = OpenCvUtils.toMat(image)
    if m.channels() == 1:
        return m
    g = Mat()
    if channel in CHANNELS:
        Core.extractChannel(m, g, CHANNELS[channel])         # OpenCV order B, G, R
    else:
        Imgproc.cvtColor(m, g, Imgproc.COLOR_BGR2GRAY)
    return g


def find_body(image, upp, length, width, expect_rot, channel="blue", polarity=None):
    """Body blob near the image centre.  expect_rot: machine-frame rotation of the body's long axis
    (deg, CCW).  channel: detection image (_gray); polarity 'bright' / 'dark' / None (both).
    Returns {found, dx, dy (mm, machine), angle_err (deg), size (l, w mm), score}."""
    _cv()
    from java.util import ArrayList
    from org.opencv.core import Mat, MatOfPoint2f, Rect, Size
    from org.opencv.imgproc import Imgproc
    g = _gray(image, channel)
    h, w = g.rows(), g.cols()
    half = int((max(length, width) * 1.3 + 0.4) / upp)
    x0, y0 = max(0, w // 2 - half), max(0, h // 2 - half)
    roi = g.submat(Rect(x0, y0, min(w - x0, 2 * half), min(h - y0, 2 * half))).clone()
    Imgproc.GaussianBlur(roi, roi, Size(5, 5), 0)
    cx, cy = w / 2.0 - x0, h / 2.0 - y0
    blk = max(3, int(max(length, width) / upp)) | 1
    best = None
    variants = [(Imgproc.THRESH_BINARY + Imgproc.THRESH_OTSU, "otsu bright"),
                (Imgproc.THRESH_BINARY_INV + Imgproc.THRESH_OTSU, "otsu dark")]
    masks = []
    for flag, name in variants:
        b = Mat()
        Imgproc.threshold(roi, b, 0, 255, flag)
        masks.append((b, name))
    for flag, name in ((Imgproc.THRESH_BINARY, "adaptive bright"), (Imgproc.THRESH_BINARY_INV, "adaptive dark")):
        b = Mat()
        Imgproc.adaptiveThreshold(roi, b, 255, Imgproc.ADAPTIVE_THRESH_MEAN_C, flag, blk, -5 if "bright" in name else 5)
        masks.append((b, name))
    k = Imgproc.getStructuringElement(Imgproc.MORPH_ELLIPSE, Size(max(3, int(0.08 / upp)) | 1, max(3, int(0.08 / upp)) | 1))
    for b, name in masks:
        if polarity is not None and polarity not in name:
            continue
        Imgproc.morphologyEx(b, b, Imgproc.MORPH_CLOSE, k)
        cs = ArrayList()
        Imgproc.findContours(b, cs, Mat(), Imgproc.RETR_LIST, Imgproc.CHAIN_APPROX_SIMPLE)
        for c in cs:
            r = Imgproc.minAreaRect(MatOfPoint2f(c.toArray()))
            a, bb = r.size.width * upp, r.size.height * upp
            l_, w_ = max(a, bb), min(a, bb)
            if l_ <= 0 or w_ <= 0:
                continue
            serr = abs(l_ - length) / length + abs(w_ - width) / width
            d = math.hypot(r.center.x - cx, r.center.y - cy) * upp
            if serr > 2 * LIMITS["size_tol"] or d > 0.6 * length:
                continue
            score = serr + d / length
            if best is None or score < best[0]:
                ang = r.angle if a >= bb else r.angle + 90.0       # image angle of the long axis (deg, y down)
                best = (score, r.center.x, r.center.y, -ang, (l_, w_), name, serr, r)
    if best is None:
        return {"found": False, "why": "no blob of %.2f x %.2f mm near the location" % (length, width)}
    _, bx, by, mang, size, name, serr, rect = best
    period = 90.0 if abs(length - width) < 0.15 * length else 180.0
    err = ((mang - expect_rot) + period / 2.0) % period - period / 2.0
    from org.opencv.core import Point
    import jarray
    pts = jarray.array([Point() for _ in range(4)], Point)
    rect.points(pts)
    return {"found": True, "dx": (bx - cx) * upp, "dy": -(by - cy) * upp, "angle_err": err, "size": size,
            "size_err": serr, "method": "size (%s)" % name,
            "box_px": [(p.x + x0, p.y + y0) for p in pts]}              # the body found, whole-image pixels


# ---------------------------------------------------------------------------------------
# chip parts (R / C / L 0201 .. 2512): the two metal terminations
# ---------------------------------------------------------------------------------------
# Bench 2026-11-26 (0603 on a dark mask): the body-blob search took ONE bare pad (~1 x 0.9 mm) of a missing part
# as the 1.6 x 0.8 body ("CHECK offset 0.7 mm" instead of missing), and boxed pads / half parts of good ones.
# Chip parts have a clearer signature: two bright terminations L - t apart; when the part is missing, the middle
# is solder mask (as dark as the mask around) and the pads are matte grey.
_CHIP = re.compile(r"^(R|C|L|D|RES|CAP|CAPC|IND|FB|LED)_?(0201|0402|0603|0805|1206|1210|1812|2010|2220|2512)(_|$)", re.I)
CHIP_LIMITS = {"mid_missing": 15, "term_frac": 0.2, "max_dev_deg": 12.0, "light_ratio": 0.62, "body_darker": 12}


def is_chip(package_id):
    return bool(_CHIP.search(str(package_id or "")))


# DO-214 diodes (SMA / SMB / SMC): two bent lead tabs at the ends of a black body - checked like a chip part with the
# leads as the ends: (lead-to-lead span, lead width) mm, typical datasheet values.  A body size learned by the bottom
# camera (Pick safety) is exactly that (SMA 4.73 x 1.49) and is used when set.
_LEADED = re.compile(r"(DO-?214A[ABC]|(^|[_\-])SM[ABC]($|[_\-]))", re.I)
_LEADED_SIZE = {"A": (5.0, 1.4), "C": (5.0, 1.4), "B": (5.3, 2.0), "AA": (5.3, 2.0), "AB": (7.9, 3.0), "SMC": (7.9, 3.0)}


def leaded_size(package_id):
    """(span, lead width) of a DO-214 / SMA / SMB / SMC package, or (None, None) when not one."""
    name = str(package_id or "")
    m = _LEADED.search(name)
    if not m:
        return None, None
    t = m.group(0).upper()
    if "SMB" in t or t.endswith("AA"):
        return _LEADED_SIZE["B"]
    if "SMC" in t or t.endswith("AB"):
        return _LEADED_SIZE["SMC"]
    return _LEADED_SIZE["A"]


def chip_size(package_id):
    """(length, width) mm of a chip package from its EIA size code (RES_0603 -> 1.6 x 0.8), or (None, None)."""
    m = _CHIP.search(str(package_id or ""))
    return _IMPERIAL.get(m.group(2), (None, None)) if m else (None, None)


def _percentile_hist(mat, q):
    import jarray
    from org.opencv.core import Mat, MatOfFloat, MatOfInt
    from org.opencv.imgproc import Imgproc
    from java.util import ArrayList
    hist, mats = Mat(), ArrayList()
    mats.add(mat)
    Imgproc.calcHist(mats, MatOfInt(jarray.array([0], "i")), Mat(), hist, MatOfInt(jarray.array([256], "i")),
                     MatOfFloat(jarray.array([0.0, 256.0], "f")))
    total, acc = float(mat.rows() * mat.cols()), 0.0
    for i in range(256):
        acc += hist.get(i, 0)[0]
        if acc >= q / 100.0 * total:
            return float(i)
    return 255.0


def _sample(g, cx, cy, a, upp, u, v, hu, hv, n=9):
    """grey values in a window centred (u, v) mm along / across the axis a (rad, machine CCW), half sizes hu, hv."""
    out = []
    for i in range(n):
        for j in range(n):
            x = u + hu * (2.0 * i / (n - 1) - 1)
            y = v + hv * (2.0 * j / (n - 1) - 1)
            px = int(cx + (x * math.cos(a) - y * math.sin(a)) / upp)
            py = int(cy - (x * math.sin(a) + y * math.cos(a)) / upp)
            if 0 <= px < g.cols() and 0 <= py < g.rows():
                out.append(g.get(py, px)[0])
    return out


def light_ratio(image, upp, length, width, expect_rot):
    """(middle - mask) / (bright - mask) in the RED channel around the expected part: ~1 = the body is as bright as the
    ends (light ceramic caps), < 0.6 = dark body (resistors; their white marking lifts it to ~0.55).  Red: the blue
    mask is dark there under either camera colour (bench 26 Nov test set: resistors <= 0.56, light caps 0.7..0.98)."""
    r = _gray(image, "red")
    cx, cy, a = r.cols() / 2.0, r.rows() / 2.0, math.radians(expect_rot)
    box = sorted(_sample(r, cx, cy, a, upp, 0.0, 0.0, 0.45 * length, 0.4 * width, 7))
    mid = sorted(_sample(r, cx, cy, a, upp, 0.0, 0.0, 0.12 * length, 0.25 * width, 7))
    ring = sorted(_sample(r, cx, cy, a, upp, 0.0, 0.5 * width + 0.5, 0.4 * length, 0.08, 7) +
                  _sample(r, cx, cy, a, upp, 0.0, -(0.5 * width + 0.5), 0.4 * length, 0.08, 7))
    if not box or not mid or not ring:
        return 0.0
    mask, top, m = ring[len(ring) // 4], box[int(len(box) * 0.95)], mid[len(mid) // 2]
    return (m - mask) / max(1.0, top - mask)


def chip_check(image, upp, length, width, expect_rot, leads=False):
    """Chip part at the image centre (the placement location).  Returns like find_body {found, dx, dy (mm, machine),
    angle_err, size, method, box_px} plus missing (True: the middle is solder mask = bare pads) and the levels."""
    _cv()
    from java.util import ArrayList
    from org.opencv.core import Mat, MatOfPoint2f, Rect, Size
    from org.opencv.imgproc import Imgproc
    g = _gray(image)
    Imgproc.GaussianBlur(g, g, Size(3, 3), 0)
    h, w = g.rows(), g.cols()
    cx, cy = w / 2.0, h / 2.0
    a = math.radians(expect_rot)
    half = int((length * 1.3 + 0.4) / upp)
    x0, y0 = max(0, int(cx) - half), max(0, int(cy) - half)
    roi = g.submat(Rect(x0, y0, min(w - x0, 2 * half), min(h - y0, 2 * half)))
    mask = _percentile_hist(roi, 15)                    # the solder mask: the darkest common level around
    top = _percentile_hist(roi, 99.5)
    t = 0.2 * length                                    # termination length along the part
    mid = _sample(g, cx, cy, a, upp, 0.0, 0.0, 0.2 * length, 0.3 * width)
    mid_level = sorted(mid)[len(mid) // 2] if mid else 0.0
    levels = {"mask": mask, "middle": mid_level, "bright": top,
              "light_ratio": light_ratio(image, upp, length, width, expect_rot)}
    if not leads and levels["light_ratio"] >= CHIP_LIMITS["light_ratio"]:
        # light ceramic body (bench 26 Nov, neutral white balance: 0805 / 0603 caps as bright as their tin): the ends
        # do not stand out (an end pairs with exposed solder on a pad) -> the whole part as one bright L x W blob
        r = _whole_part(image, upp, length, width, expect_rot, levels)
        if r is not None:
            return r
    # terminations: bright blobs about t x width, L - t apart, around the centre
    b = Mat()
    Imgproc.threshold(roi, b, mask + 0.55 * (top - mask), 255, Imgproc.THRESH_BINARY)
    # only a corridor along the expected axis counts: a neighbour's end or a via ring merged with an end moved its
    # centre off the part (bench R7 next to a via)
    _keep_corridor(b, int(cx) - x0, int(cy) - y0, a, 0.8 * length / upp, (0.8 * width + 0.25) / upp)
    cs = ArrayList()
    Imgproc.findContours(b, cs, Mat(), Imgproc.RETR_EXTERNAL, Imgproc.CHAIN_APPROX_SIMPLE)
    area0 = t * width / upp / upp
    blobs = []
    for c in cs:
        ar = Imgproc.contourArea(c)
        if CHIP_LIMITS["term_frac"] * area0 <= ar <= 3.0 * area0:
            r = Imgproc.minAreaRect(MatOfPoint2f(c.toArray()))
            blobs.append((r.center.x + x0, r.center.y + y0, ar))
    want = length - t
    best = None
    for i in range(len(blobs)):
        for j in range(i + 1, len(blobs)):
            (ax, ay, aa), (bx, by, ba) = blobs[i], blobs[j]
            d = math.hypot(bx - ax, by - ay) * upp
            if not (0.65 * want <= d <= 1.3 * want) or max(aa, ba) > 3.0 * min(aa, ba):
                continue
            mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
            off = math.hypot(mx - cx, my - cy) * upp
            if off > 0.5 * length:
                continue
            ang = math.degrees(math.atan2(-(by - ay), bx - ax))
            dev = abs(((ang - expect_rot) + 90.0) % 180.0 - 90.0)
            if dev > CHIP_LIMITS["max_dev_deg"]:         # an end paired with the marking text / a pad (bench R7)
                continue
            score = abs(d - want) / want + off / length + dev / 30.0
            if best is None or score < best[0]:
                best = (score, mx, my, ang, d)
    if best is None and leads:
        return {"found": False, "missing": False, "levels": levels, "method": "leads",
                "why": "leads not found (part shifted, tilted or missing?)"}
    if best is None:
        missing = mid_level - mask < CHIP_LIMITS["mid_missing"]
        if not missing:
            # no pair of ends: light ceramic body (bench 26 Nov, neutral white balance: 0805 / 0603 caps whose body is
            # as bright as the tin; 2220 grey body, ends barely brighter) -> the whole part as one bright L x W blob
            # on the dark mask, along the expected axis
            r = _whole_part(image, upp, length, width, expect_rot, levels)
            if r is not None:
                return r
        return {"found": False, "missing": missing, "levels": levels, "method": "terminations",
                "why": ("part missing: bare pads (the middle is as dark as the solder mask)" if missing else
                        "terminations not found (part shifted, tilted or not a chip part?)")}
    _, mx, my, ang, d = best
    # bare pads look like two ends at the right distance: between them lies solder mask, not a body
    if leads:
        # black epoxy body: in grey as dark as the blue mask, in the blue channel clearly darker (bench D3: 69 vs 99)
        bl = _gray(image, "blue")
        between = _sample(bl, mx, my, math.radians(ang), upp, 0.0, 0.0, 0.15 * length, 0.25 * width)
        ring = sorted(_sample(bl, mx, my, math.radians(ang), upp, 0.0, 0.5 * width + 0.9, 0.35 * length, 0.08, 7) +
                      _sample(bl, mx, my, math.radians(ang), upp, 0.0, -(0.5 * width + 0.9), 0.35 * length, 0.08, 7))
        between = sorted(between)[len(between) // 2] if between else 255.0
        mask_b = ring[len(ring) // 4] if ring else 0.0
        levels.update(between_blue=between, mask_blue=mask_b)
        if mask_b - between < CHIP_LIMITS["body_darker"]:
            return {"found": False, "missing": False, "levels": levels, "method": "leads",
                    "why": "leads / pads found, but no dark body between them: part missing?"}
    else:
        between = _sample(g, mx, my, math.radians(ang), upp, 0.0, 0.0, 0.15 * length, 0.25 * width)
        between = sorted(between)[len(between) // 2] if between else 255.0
        levels["between"] = between
        if between - mask < CHIP_LIMITS["mid_missing"]:
            return {"found": False, "missing": True, "levels": levels, "method": "terminations",
                    "why": "part missing: bare pads (between them the solder mask)"}
    err = ((ang - expect_rot) + 90.0) % 180.0 - 90.0
    hl, hw = (d + t) / 2.0 / upp, width / 2.0 / upp
    ar = math.radians(ang)
    box = [(mx + x * math.cos(ar) - y * math.sin(ar), my - (x * math.sin(ar) + y * math.cos(ar)))
           for x, y in ((-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw))]
    return {"found": True, "missing": False, "dx": (mx - cx) * upp, "dy": -(my - cy) * upp, "angle_err": err,
            "size": (d + t, width), "size_err": abs(d - want) / want, "method": "leads" if leads else "terminations",
            "box_px": box,
            "levels": levels}


def _keep_corridor(binary, cx, cy, a, half_len, half_wid):
    """Zero a binary Mat outside the rectangle centred (cx, cy) px, axis a (rad, machine CCW; image y down)."""
    import jarray
    from org.opencv.core import Core, Mat, MatOfPoint, Point, Scalar
    from org.opencv.imgproc import Imgproc
    pts = [Point(cx + x * math.cos(a) - y * math.sin(a), cy - (x * math.sin(a) + y * math.cos(a)))
           for x, y in ((-half_len, -half_wid), (half_len, -half_wid), (half_len, half_wid), (-half_len, half_wid))]
    m = Mat.zeros(binary.rows(), binary.cols(), binary.type())
    Imgproc.fillConvexPoly(m, MatOfPoint(jarray.array(pts, Point)), Scalar(255.0))
    Core.bitwise_and(binary, m, binary)


def _whole_part(image, upp, length, width, expect_rot, levels):
    """The chip part as one bright L x W blob along the expected axis (grey), or None."""
    r = find_body(image, upp, length, width, expect_rot, channel="gray", polarity="bright")
    if r.get("found") and abs(r["angle_err"]) <= CHIP_LIMITS["max_dev_deg"]:
        r["method"] = "whole part (light body)"
        r["missing"] = False
        r["levels"] = levels
        return r
    return None


def rotate(mat, deg):
    from org.opencv.core import Mat, Point, Size
    from org.opencv.imgproc import Imgproc
    c = Point(mat.cols() / 2.0, mat.rows() / 2.0)
    m = Imgproc.getRotationMatrix2D(c, deg, 1.0)
    out = Mat()
    Imgproc.warpAffine(mat, out, m, Size(mat.cols(), mat.rows()), Imgproc.INTER_LINEAR, 1)   # BORDER_REPLICATE
    return out


def _template(sample, upp):
    """A golden sample's grey Mat at the camera's mm/px."""
    from org.opencv.core import Mat, Size
    from org.opencv.imgproc import Imgproc
    t = sample["mat"]
    if abs(sample.get("upp", upp) - upp) / upp > 0.03:
        t2 = Mat()
        f = sample["upp"] / upp
        Imgproc.resize(t, t2, Size(int(t.cols() * f), int(t.rows() * f)))
        t = t2
    return t


def _samples(golden):
    return golden.get("samples") or [golden]


def match_golden(image, upp, golden, expect_rot):
    """golden: load_golden() (one or more samples {"mat": gray Mat, "rot": machine rotation it was taken at, "upp"}).
    Every sample is matched, the best counts.  Returns {score, score180, dx, dy, polarity_suspect, samples, sample}."""
    _cv()
    from org.opencv.core import Core, Mat, Rect
    from org.opencv.imgproc import Imgproc
    g = _gray(image)
    h, w = g.rows(), g.cols()
    sm = int(LIMITS["search_mm"] / upp)
    out = None
    for k, smp in enumerate(_samples(golden)):
        t = _template(smp, upp)
        W, H = min(w, t.cols() + 2 * sm), min(h, t.rows() + 2 * sm)
        x0, y0 = w // 2 - W // 2, h // 2 - H // 2
        roi = g.submat(Rect(x0, y0, W, H))

        def best(deg):
            res = Mat()
            Imgproc.matchTemplate(roi, rotate(t, deg), res, Imgproc.TM_CCOEFF_NORMED)
            mm = Core.minMaxLoc(res)
            return mm.maxVal, mm.maxLoc
        # image rotation is clockwise-positive in OpenCV's y-down frame = machine CCW positive
        d = expect_rot - smp["rot"]
        s, loc = best(d)
        if out is not None and s <= out["score"]:
            continue
        s180, _ = best(d + 180.0)
        cxm = x0 + loc.x + t.cols() / 2.0
        cym = y0 + loc.y + t.rows() / 2.0
        out = {"score": s, "score180": s180, "dx": (cxm - w / 2.0) * upp, "dy": -(cym - h / 2.0) * upp,
               "polarity_suspect": s180 > s + 0.10, "sample": smp.get("source") or "sample %d" % (k + 1)}
    out["samples"] = len(_samples(golden))
    return out


def match_golden_turns(image, upp, golden, expect_rot, turns=(0.0, 90.0, 180.0, -90.0)):
    """Golden-sample score with the part turned by each of `turns` (deg CCW, machine frame) against the
    expected rotation: {turn: score} (best sample per turn).  The best turn says how the placed part really sits
    (test placement, lumen.testplace.propose_turn)."""
    _cv()
    from org.opencv.core import Core, Mat, Rect
    from org.opencv.imgproc import Imgproc
    g = _gray(image)
    h, w = g.rows(), g.cols()
    sm = int(LIMITS["search_mm"] / upp)
    out = {}
    for smp in _samples(golden):
        t = _template(smp, upp)
        W, H = min(w, t.cols() + 2 * sm), min(h, t.rows() + 2 * sm)
        roi = g.submat(Rect(w // 2 - W // 2, h // 2 - H // 2, W, H))
        for turn in turns:
            res = Mat()
            Imgproc.matchTemplate(roi, rotate(t, expect_rot - smp["rot"] + turn), res, Imgproc.TM_CCOEFF_NORMED)
            out[float(turn)] = max(out.get(float(turn), -1.0), Core.minMaxLoc(res).maxVal)
    return out


def offset_limits(length, width):
    """(along, across) allowed offsets (mm) for a body length x width (None: the fixed minimum).  Along the part
    (towards one pad) offset_along x length, across offset_frac x width, never below offset_mm."""
    lo = LIMITS["offset_mm"]
    return (max(lo, LIMITS["offset_along"] * length) if length else lo,
            max(lo, LIMITS["offset_frac"] * width) if width else lo)


def verdict(res):
    """'OK' / 'CHECK: ...' / 'FAIL: ...' from a result dict."""
    if res.get("error"):
        return "ERROR: " + res["error"]
    notes, fail = [], False
    g = res.get("golden")
    if g:
        if g["score"] < LIMITS["score_fail"]:
            fail = True
            notes.append("does not match the golden sample (%.2f): missing / wrong part?" % g["score"])
        elif g["score"] < LIMITS["score_ok"]:
            notes.append("weak match with the golden sample (%.2f)" % g["score"])
        if g["polarity_suspect"]:
            fail = True
            notes.append("matches better turned by 180 deg (%.2f vs %.2f): polarity?" % (g["score180"], g["score"]))
    b = res.get("body")
    if b is not None:
        if b.get("missing"):
            fail = True
            notes.append(b.get("why") or "part missing")
        elif not b.get("found"):
            if not g or g["score"] < LIMITS["score_ok"]:
                if b.get("method") in ("terminations", "leads"):
                    notes.append(b.get("why"))
                elif g and g["score"] >= LIMITS["score_fail"]:
                    # a leaded IC's configured size includes its leads: the dark body alone does not match it;
                    # the golden sample still sees the part (bench U3 VIPer, 0.64)
                    notes.append("part body not found (golden sample %.2f): check by eye" % g["score"])
                else:
                    fail = True
                    notes.append("part body not found: missing?")
        else:
            off = math.hypot(b["dx"], b["dy"])
            size = res.get("expect_size") or b.get("size") or (None, None)
            a = math.radians(res.get("axis_rot") or 0.0)
            along = b["dx"] * math.cos(a) + b["dy"] * math.sin(a)
            across = -b["dx"] * math.sin(a) + b["dy"] * math.cos(a)
            lim_l, lim_w = offset_limits(size[0], size[1])
            golden_here = g and g["score"] >= LIMITS["score_ok"] and math.hypot(g["dx"], g["dy"]) <= max(lim_l, lim_w)
            if golden_here and off > 2 * max(lim_l, lim_w):
                # the golden sample sees the part where it belongs; the body search took something else (bench U3:
                # a dark blob 3.35 mm away) -> the body result is not used
                b["ignored"] = "the golden sample matches %.2f at the location" % g["score"]
            else:
                if abs(along) > lim_l or abs(across) > lim_w or off > max(lim_l, lim_w):
                    notes.append("offset %.2f mm (%+.2f / %+.2f; along the part %.2f of %.2f allowed, across %.2f of "
                                 "%.2f)" % (off, b["dx"], b["dy"], abs(along), lim_l, abs(across), lim_w))
                # nearly square parts: the axis from two wide ends is uncertain (bench C11 2220: +-9 deg)
                lim_a = LIMITS["angle_deg"] if not size[0] or size[0] > 1.3 * size[1] else LIMITS["angle_square_deg"]
                if abs(b["angle_err"]) > lim_a:
                    notes.append("rotated %+.0f deg" % b["angle_err"])
    if not notes:
        return "OK"
    return ("FAIL: " if fail else "CHECK: ") + "; ".join(notes)


# ---------------------------------------------------------------------------------------
# golden samples:  <lumen>/inspection/golden/<package>.png + .json
# ---------------------------------------------------------------------------------------
def _safe(name):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


def golden_path(root, package_id):
    return os.path.join(root, "golden", _safe(package_id))


MAX_GOLDEN = 6      # samples per package: <package>.png (the first, "Make golden") + <package>.2.png ... .6.png


def _sample_paths(root, package_id):
    p = golden_path(root, package_id)
    return [p] + ["%s.%d" % (p, i) for i in range(2, MAX_GOLDEN + 1)]


def _read_sample(p):
    from org.opencv.imgcodecs import Imgcodecs
    f = open(p + ".json")
    try:
        meta = json.load(f)
    finally:
        f.close()
    meta["mat"] = Imgcodecs.imread(p + ".png", Imgcodecs.IMREAD_GRAYSCALE)
    meta["path"] = p + ".png"
    return meta


def load_golden(root, package_id):
    """The golden samples of a package, or None: the first sample's fields (mat, rot, upp, ...) plus "samples" [all].
    Extra samples come from parts the operator confirmed (add_golden_sample): the best match counts, so the
    package's look under the current light and boards is learned."""
    paths = [p for p in _sample_paths(root, package_id) if os.path.exists(p + ".png") and os.path.exists(p + ".json")]
    if not paths:
        return None
    _cv()
    samples = [_read_sample(p) for p in paths]
    out = dict(samples[0])
    out["samples"] = samples
    return out


def _write_sample(p, image, upp, rot, length, width, source, centre_px=None):
    from org.opencv.core import Rect
    from org.opencv.imgcodecs import Imgcodecs
    g = _gray(image)
    half = int((max(length, width) * 0.75 + 0.25) / upp)
    h, w = g.rows(), g.cols()
    cx, cy = (int(round(centre_px[0])), int(round(centre_px[1]))) if centre_px else (w // 2, h // 2)
    cx, cy = min(max(cx, half), w - half), min(max(cy, half), h - half)
    crop = g.submat(Rect(cx - half, cy - half, 2 * half, 2 * half)).clone()
    d = os.path.dirname(p)
    if not os.path.isdir(d):
        os.makedirs(d)
    Imgcodecs.imwrite(p + ".png", crop)
    f = open(p + ".json", "w")                            # Jython: close explicitly (no refcount flush)
    try:
        json.dump({"rot": rot, "upp": upp, "size": [length, width], "source": source, "channel": "gray",
                   "t": time.strftime("%Y-%m-%dT%H:%M:%S")}, f)
    finally:
        f.close()
    return p + ".png"


def save_golden(root, package_id, image, upp, rot, length, width, source, centre_px=None):
    """Crop around the image centre (or centre_px: where the part really is) as THE golden sample of the package:
    the first sample; the learned extra samples are removed (a fresh start)."""
    _cv()
    paths = _sample_paths(root, package_id)
    for p in paths[1:]:
        for ext in (".png", ".json"):
            if os.path.exists(p + ext):
                os.remove(p + ext)
    return _write_sample(paths[0], image, upp, rot, length, width, source, centre_px)


def add_golden_sample(root, package_id, image, upp, rot, length, width, source, centre_px=None):
    """One more golden sample (a placement the operator confirmed).  The first sample is kept; when all MAX_GOLDEN
    are used, the oldest extra one is replaced.  Returns the file written."""
    _cv()
    paths = _sample_paths(root, package_id)
    if not os.path.exists(paths[0] + ".png"):
        return _write_sample(paths[0], image, upp, rot, length, width, source, centre_px)
    free = [p for p in paths[1:] if not os.path.exists(p + ".png")]
    if free:
        target = free[0]
    else:
        target = min(paths[1:], key=lambda p: _read_meta_t(p))
    return _write_sample(target, image, upp, rot, length, width, source, centre_px)


def _read_meta_t(p):
    try:
        f = open(p + ".json")
        try:
            return json.load(f).get("t", "")
        finally:
            f.close()
    except (IOError, ValueError):
        return ""


def analyse(image, upp, package_id, length, width, rot, root, fixed=False):
    """Both methods on one image -> result dict incl. verdict.  fixed: length x width is the operator's drawn size
    (inspection_size): used as it is, not replaced by the EIA code or the lead span."""
    res = {}
    if is_chip(package_id) and not fixed:
        # chip parts: the EIA size code is the top-view outline (a body size learned by the bottom camera, e.g.
        # 0603 1.45 x 0.80, is shorter: bench R6 ends 1.5 mm apart rejected)
        nl, nw = chip_size(package_id)
        if nl:
            length, width = nl, nw
    span, lead_w = leaded_size(package_id)
    if span and not is_chip(package_id):
        if not fixed and (not length or length < 0.8 * span):           # a learned lead span (Pick safety) is kept when set
            length, width = span, lead_w
        res["body"] = chip_check(image, upp, length, width, rot, leads=True)
    elif length and is_chip(package_id):
        res["body"] = chip_check(image, upp, length, width, rot)
    elif length:
        res["body"] = find_body(image, upp, length, width, rot)
    g = load_golden(root, package_id) if root else None
    if g is not None:
        res["golden"] = match_golden(image, upp, g, rot)
    if not length and g is None:
        res["error"] = "no body size and no golden sample for %s" % package_id
    res["expect_size"] = [length, width] if length else None
    res["axis_rot"] = rot
    res["verdict"] = verdict(res)
    return res


# ---------------------------------------------------------------------------------------
# the result drawn into the image
# ---------------------------------------------------------------------------------------
def verdict_colour(v):
    from java.awt import Color
    if v.startswith("OK"):
        return Color(0, 200, 0)
    if v.startswith("FAIL") or v.startswith("ERROR"):
        return Color(235, 0, 0)
    return Color(255, 150, 0)


def annotate(image, res, title):
    """Copy of the camera image with the inspection drawn in: where the part should be (cyan, dashed: body size at
    the placement rotation; cross = placement location), the body found (green OK / orange CHECK / red FAIL)
    and the verdict."""
    import jarray
    from java.awt import BasicStroke, Color, Font, FontMetrics, Polygon, RenderingHints
    from lumen import zoomview
    out = zoomview.copy_image(image)
    w, h = out.getWidth(), out.getHeight()
    g = zoomview._G(out.createGraphics())
    g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
    v = res.get("verdict", "")
    col = verdict_colour(v)
    lw = max(2.0, w / 700.0)
    cx, cy = w / 2.0, h / 2.0

    def poly(points):
        return Polygon(jarray.array([int(round(x)) for x, _ in points], "i"),
                       jarray.array([int(round(y)) for _, y in points], "i"), len(points))
    upp, size = res.get("upp"), res.get("expect_size")
    g.setColor(Color(0, 220, 255))
    if upp and size and size[0] and size[1]:
        a = math.radians(res.get("axis_rot", 0.0))
        hl, hw = size[0] / 2.0 / upp, size[1] / 2.0 / upp
        pts = [(cx + x * math.cos(a) - y * math.sin(a), cy - (x * math.sin(a) + y * math.cos(a)))
               for x, y in ((-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw))]      # machine CCW, image y down
        g.setStroke(BasicStroke(lw, BasicStroke.CAP_BUTT, BasicStroke.JOIN_MITER, 10.0,
                                jarray.array([4 * lw, 3 * lw], "f"), 0.0))
        g.draw(poly(pts))
    g.setStroke(BasicStroke(lw))
    r = 6 * lw
    g.drawLine(int(cx - r), int(cy), int(cx + r), int(cy))
    g.drawLine(int(cx), int(cy - r), int(cx), int(cy + r))
    box = (res.get("body") or {}).get("box_px")
    if box and not res.get("hand_box"):
        g.setColor(col)
        g.setStroke(BasicStroke(1.5 * lw))
        g.draw(poly(box))
    hb = res.get("hand_box")
    if hb:                                               # where the operator drew the part (magenta)
        g.setColor(Color(255, 0, 255))
        g.setStroke(BasicStroke(1.5 * lw))
        g.draw(poly([(hb[0], hb[1]), (hb[2], hb[1]), (hb[2], hb[3]), (hb[0], hb[3])]))
    fs = max(16, int(w / 55))
    g.setFont(Font("SansSerif", Font.BOLD, fs))
    text = "%s   %s" % (title, v)
    tw = FontMetrics.stringWidth(g.getFontMetrics(), text)          # (public class: Java 17 module access)
    g.setColor(Color(0, 0, 0, 170))
    g.fillRect(0, 0, min(w, tw + fs), int(fs * 1.6))
    g.setColor(col)
    g.drawString(text, int(fs / 2), int(fs * 1.15))
    g.dispose()
    return out


def save_annotated(res, title):
    """(Re)write res['image'] from the raw picture (res['_image']) and the result, e.g. after Set as OK."""
    from javax.imageio import ImageIO
    from java.io import File
    if res.get("_image") is not None and res.get("image"):
        ImageIO.write(annotate(res["_image"], res, title), "png", File(res["image"]))


# ---------------------------------------------------------------------------------------
# what the inspection used, and the operator's corrections (learning)
# ---------------------------------------------------------------------------------------
def meta_of(res, package_id, part_id, truth=None):
    """The inputs and result of one inspection as plain data (the test set format of tests/inspection_dataset.py)."""
    size = res.get("expect_size") or [None, None]
    b = res.get("body") or {}
    g = res.get("golden") or {}
    m = {"package": package_id, "part": part_id, "length": size[0], "width": size[1], "axis_rot": res.get("axis_rot"),
         "upp": res.get("upp"), "size_source": res.get("size_source"), "verdict": res.get("verdict"),
         "detected": {"found": b.get("found"), "method": b.get("method"), "dx": b.get("dx"), "dy": b.get("dy"),
                      "angle_err": b.get("angle_err"), "box_px": b.get("box_px"), "golden": g.get("score")}}
    if res.get("location"):
        m["location"] = res["location"]
    if res.get("hand_box"):
        m["hand_box"], m["hand_dx"], m["hand_dy"] = res["hand_box"], res.get("hand_dx"), res.get("hand_dy")
    if truth:
        m["truth"] = truth
    return m


def _write_json(path, data):
    f = open(path, "w")                                   # Jython: close explicitly
    try:
        json.dump(data, f, indent=1, sort_keys=True)
    finally:
        f.close()


# ---------------------------------------------------------------------------------------
# operator's top-view sizes: <root>/sizes.json {package: {x, y (mm, footprint X / Y), source, t}}
# ---------------------------------------------------------------------------------------
def sizes_path(root):
    return os.path.join(root, "sizes.json")


def load_sizes(root):
    try:
        f = open(sizes_path(root))
        try:
            d = json.load(f)
        finally:
            f.close()
        return dict((k, v) for k, v in d.items() if v.get("x", 0) > 0 and v.get("y", 0) > 0)
    except (IOError, OSError, ValueError, TypeError, AttributeError):
        return {}


def inspection_size(root, package_id):
    """The size the operator drew for this package ({x, y, source, t}) or None."""
    return load_sizes(root).get(package_id) if root else None


def save_inspection_size(root, package_id, x, y, source):
    d = load_sizes(root)
    d[package_id] = {"x": round(float(x), 2), "y": round(float(y), 2), "source": source,
                     "t": time.strftime("%Y-%m-%d %H:%M")}
    if not os.path.isdir(root):
        os.makedirs(root)
    _write_json(sizes_path(root), d)
    return d[package_id]


def forget_inspection_size(root, package_id):
    d = load_sizes(root)
    if d.pop(package_id, None) is None:
        return False
    _write_json(sizes_path(root), d)
    return True


def drawn_size(res, x0, y0, x1, y1):
    """The drawn rectangle as the part's size in footprint X / Y (mm): (x, y), or None when the placement is not
    turned by about a multiple of 90 deg (an upright rectangle around a slanted part is not its size)."""
    upp = res.get("upp")
    loc = res.get("location")
    if not upp or not loc:
        return None
    r = loc[3] % 180.0
    w, h = abs(x1 - x0) * upp, abs(y1 - y0) * upp
    if min(r, 180.0 - r) <= 10.0:
        return round(w, 2), round(h, 2)
    if abs(r - 90.0) <= 10.0:
        return round(h, 2), round(w, 2)
    return None


def hand_position(res, x0, y0, x1, y1):
    """The part where the operator drew it (image px rectangle) -> (dx, dy) mm from the placement location,
    verdict text, truth ('ok' / 'shifted').  The rotation is taken as expected (the rectangle has none)."""
    w, h = res["_image"].getWidth(), res["_image"].getHeight()
    upp = res["upp"]
    dx, dy = ((x0 + x1) / 2.0 - w / 2.0) * upp, -((y0 + y1) / 2.0 - h / 2.0) * upp
    dx, dy = round(dx, 3) + 0.0, round(dy, 3) + 0.0                # no "-0.00"
    size = res.get("expect_size") or [abs(x1 - x0) * upp, abs(y1 - y0) * upp]
    a = math.radians(res.get("axis_rot") or 0.0)
    along, across = dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a)
    lim_l, lim_w = offset_limits(size[0], size[1])
    off = math.hypot(dx, dy)
    within = abs(along) <= lim_l and abs(across) <= lim_w and off <= max(lim_l, lim_w)
    text = "part drawn by hand at %+.2f / %+.2f mm (%.2f mm; along %.2f of %.2f, across %.2f of %.2f allowed)" % (
        dx, dy, off, abs(along), lim_l, abs(across), lim_w)
    return dx, dy, ("OK (%s)" % text) if within else ("CHECK: offset, %s" % text), "ok" if within else "shifted"


def save_learning(root, run_name, ref, res, package_id, part_id, truth):
    """The picture and the operator's correction into <root>/learning/<run>/ (<ref>-raw.png + meta.json, the test
    set format: tests/run_inspection_eval.sh evaluates it).  Returns the directory."""
    from javax.imageio import ImageIO
    from java.io import File
    d = os.path.join(root, "learning", _safe(run_name))
    if not os.path.isdir(d):
        os.makedirs(d)
    ImageIO.write(res["_image"], "png", File(os.path.join(d, _safe(ref) + "-raw.png")))
    mp = os.path.join(d, "meta.json")
    data = {"source": run_name, "parts": {}}
    if os.path.isfile(mp):
        f = open(mp)
        try:
            data = json.load(f)
        finally:
            f.close()
    m = meta_of(res, package_id, part_id, truth)
    m["t"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    data["parts"][ref] = m
    _write_json(mp, data)
    return d


# ---------------------------------------------------------------------------------------
# machine part (camera only)
# ---------------------------------------------------------------------------------------
def go_to_placement(machine, board_location, placement):
    """Top camera over the placement at safe Z, focused on the part top (board Z + part height).
    Returns (location mm, z).  Call inside a machine task."""
    from org.openpnp.model import LengthUnit, Location
    from org.openpnp.util import MovableUtils, Utils2D
    mm = LengthUnit.Millimeters
    part = placement.getPart()
    loc = Utils2D.calculateBoardPlacementLocation(board_location, placement.getLocation()).convertToUnits(mm)
    z = board_location.getLocation().convertToUnits(mm).getZ() + (part.getHeight().convertToUnits(mm).getValue() if part else 0.0)
    cam = machine.getDefaultHead().getDefaultCamera()
    MovableUtils.moveToLocationAtSafeZ(cam, Location(mm, loc.getX(), loc.getY(), z, 0.0))
    return loc, z


def inspect_placement(machine, board_location, placement, out_dir, root):
    """Top camera over the placement (board Z + part height), capture, analyse, save the picture with the result
    drawn in (<ref>.png) and as taken (<ref>-raw.png)."""
    from org.openpnp.model import Length, LengthUnit
    from javax.imageio import ImageIO
    from java.io import File
    mm = LengthUnit.Millimeters
    part = placement.getPart()
    pkg = part.getPackage() if part is not None else None
    loc, z = go_to_placement(machine, board_location, placement)
    cam = machine.getDefaultHead().getDefaultCamera()
    img = cam.settleAndCapture()
    upp = cam.getUnitsPerPixel(Length(z, mm)).convertToUnits(mm).getX()
    own = inspection_size(root, str(pkg.getId())) if pkg is not None and root else None
    rot = loc.getRotation()
    if own is not None:
        # the operator's drawn top-view size (footprint X / Y), not the footprint body (bottom vision: for diodes
        # only the contacts, bench 2026-11-27)
        length, width, src = max(own["x"], own["y"]), min(own["x"], own["y"]), "drawn by hand (%s)" % own.get("source", "")
        if own["y"] > own["x"]:
            rot += 90.0
    else:
        length, width, src = body_size(pkg)
        # the body's long axis: footprint X if body width >= height, else Y
        if pkg is not None and pkg.getFootprint() is not None and pkg.getFootprint().getBodyHeight() > pkg.getFootprint().getBodyWidth():
            rot += 90.0
    res = analyse(img, upp, str(pkg.getId()) if pkg else "?", length, width, rot, root, fixed=own is not None)
    res.update(location=[loc.getX(), loc.getY(), z, loc.getRotation()], upp=upp, size_source=src, axis_rot=rot)
    if own is None and is_chip(str(pkg.getId()) if pkg else "") and chip_size(str(pkg.getId()))[0]:
        res["size_source"] = "EIA size code (chip)"           # analyse() used it, expect_size says so
    res["_image"] = img
    if out_dir:
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        base = os.path.join(out_dir, _safe(str(placement.getId())))
        ImageIO.write(img, "png", File(base + "-raw.png"))
        res["raw_image"], res["image"] = base + "-raw.png", base + ".png"
        save_annotated(res, "%s  %s" % (placement.getId(), part.getId() if part else "-"))
        _write_json(base + ".json", meta_of(res, str(pkg.getId()) if pkg else None,
                                            str(part.getId()) if part else None))
    return res
