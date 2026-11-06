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

LIMITS = {"offset_mm": 0.15, "angle_deg": 8.0, "score_ok": 0.70, "score_fail": 0.45, "search_mm": 0.6,
          "size_tol": 0.45}


# ---------------------------------------------------------------------------------------
# expected body size
# ---------------------------------------------------------------------------------------
_METRIC = re.compile(r"(\d{2})(\d{2})Metric")
_IMPERIAL = {"0201": (0.6, 0.3), "0402": (1.0, 0.5), "0603": (1.6, 0.8), "0805": (2.0, 1.25), "1206": (3.2, 1.6),
             "1210": (3.2, 2.5), "2220": (5.7, 5.0)}


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
    return None, None, "body size unknown (set the package footprint body)"


# ---------------------------------------------------------------------------------------
# image analysis
# ---------------------------------------------------------------------------------------
def _cv():
    from lumen.tapevision import _ensure_opencv
    _ensure_opencv()


def _gray(image):
    from org.opencv.core import Mat
    from org.opencv.imgproc import Imgproc
    from org.openpnp.util import OpenCvUtils
    m = OpenCvUtils.toMat(image)
    g = Mat()
    if m.channels() > 1:
        Imgproc.cvtColor(m, g, Imgproc.COLOR_BGR2GRAY)
    else:
        g = m
    return g


def find_body(image, upp, length, width, expect_rot):
    """Body blob near the image centre.  expect_rot: machine-frame rotation of the body's long axis
    (deg, CCW).  Returns {found, dx, dy (mm, machine), angle_err (deg), size (l, w mm), score}."""
    _cv()
    from java.util import ArrayList
    from org.opencv.core import Mat, MatOfPoint2f, Rect, Size
    from org.opencv.imgproc import Imgproc
    g = _gray(image)
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
                best = (score, r.center.x, r.center.y, -ang, (l_, w_), name, serr)
    if best is None:
        return {"found": False, "why": "no blob of %.2f x %.2f mm near the location" % (length, width)}
    _, bx, by, mang, size, name, serr = best
    period = 90.0 if abs(length - width) < 0.15 * length else 180.0
    err = ((mang - expect_rot) + period / 2.0) % period - period / 2.0
    return {"found": True, "dx": (bx - cx) * upp, "dy": -(by - cy) * upp, "angle_err": err, "size": size,
            "size_err": serr, "method": "size (%s)" % name}


def rotate(mat, deg):
    from org.opencv.core import Mat, Point, Size
    from org.opencv.imgproc import Imgproc
    c = Point(mat.cols() / 2.0, mat.rows() / 2.0)
    m = Imgproc.getRotationMatrix2D(c, deg, 1.0)
    out = Mat()
    Imgproc.warpAffine(mat, out, m, Size(mat.cols(), mat.rows()), Imgproc.INTER_LINEAR, 1)   # BORDER_REPLICATE
    return out


def match_golden(image, upp, golden, expect_rot):
    """golden: {"mat": gray Mat, "rot": machine rotation it was taken at, "upp"}.  Returns
    {score, score180, dx, dy, polarity_suspect}."""
    _cv()
    from org.opencv.core import Core, Mat, Rect, Size
    from org.opencv.imgproc import Imgproc
    g = _gray(image)
    t = golden["mat"]
    if abs(golden.get("upp", upp) - upp) / upp > 0.03:
        t2 = Mat()
        f = golden["upp"] / upp
        Imgproc.resize(t, t2, Size(int(t.cols() * f), int(t.rows() * f)))
        t = t2
    h, w = g.rows(), g.cols()
    sm = int(LIMITS["search_mm"] / upp)
    W = t.cols() + 2 * sm
    H = t.rows() + 2 * sm
    x0, y0 = w // 2 - W // 2, h // 2 - H // 2
    roi = g.submat(Rect(x0, y0, W, H))

    def best(deg):
        tr = rotate(t, deg)
        res = Mat()
        Imgproc.matchTemplate(roi, tr, res, Imgproc.TM_CCOEFF_NORMED)
        mm = Core.minMaxLoc(res)
        return mm.maxVal, mm.maxLoc
    # image rotation is clockwise-positive in OpenCV's y-down frame = machine CCW positive
    d = expect_rot - golden["rot"]
    s, loc = best(d)
    s180, _ = best(d + 180.0)
    cxm = x0 + loc.x + t.cols() / 2.0
    cym = y0 + loc.y + t.rows() / 2.0
    return {"score": s, "score180": s180, "dx": (cxm - w / 2.0) * upp, "dy": -(cym - h / 2.0) * upp,
            "polarity_suspect": s180 > s + 0.10}


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
        if not b.get("found"):
            if not g or g["score"] < LIMITS["score_ok"]:
                fail = True
                notes.append("part body not found: missing?")
        else:
            off = math.hypot(b["dx"], b["dy"])
            if off > LIMITS["offset_mm"]:
                notes.append("offset %.2f mm (%+.2f / %+.2f)" % (off, b["dx"], b["dy"]))
            if abs(b["angle_err"]) > LIMITS["angle_deg"]:
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


def load_golden(root, package_id):
    p = golden_path(root, package_id)
    if not os.path.exists(p + ".png"):
        return None
    _cv()
    from org.opencv.imgcodecs import Imgcodecs
    f = open(p + ".json")
    try:
        meta = json.load(f)
    finally:
        f.close()
    meta["mat"] = Imgcodecs.imread(p + ".png", Imgcodecs.IMREAD_GRAYSCALE)
    return meta


def save_golden(root, package_id, image, upp, rot, length, width, source):
    """Crop around the image centre (part + margin) as the golden sample of the package."""
    _cv()
    from org.opencv.core import Rect
    from org.opencv.imgcodecs import Imgcodecs
    g = _gray(image)
    half = int((max(length, width) * 0.75 + 0.25) / upp)
    h, w = g.rows(), g.cols()
    crop = g.submat(Rect(w // 2 - half, h // 2 - half, 2 * half, 2 * half)).clone()
    p = golden_path(root, package_id)
    d = os.path.dirname(p)
    if not os.path.isdir(d):
        os.makedirs(d)
    Imgcodecs.imwrite(p + ".png", crop)
    f = open(p + ".json", "w")                            # Jython: close explicitly (no refcount flush)
    try:
        json.dump({"rot": rot, "upp": upp, "size": [length, width], "source": source,
                   "t": time.strftime("%Y-%m-%dT%H:%M:%S")}, f)
    finally:
        f.close()
    return p + ".png"


def analyse(image, upp, package_id, length, width, rot, root):
    """Both methods on one image -> result dict incl. verdict."""
    res = {}
    if length:
        res["body"] = find_body(image, upp, length, width, rot)
    g = load_golden(root, package_id) if root else None
    if g is not None:
        res["golden"] = match_golden(image, upp, g, rot)
    if not length and g is None:
        res["error"] = "no body size and no golden sample for %s" % package_id
    res["verdict"] = verdict(res)
    return res


# ---------------------------------------------------------------------------------------
# machine part (camera only)
# ---------------------------------------------------------------------------------------
def inspect_placement(machine, board_location, placement, out_dir, root):
    """Top camera over the placement (board Z + part height), capture, analyse, save the image."""
    from org.openpnp.model import Length, LengthUnit, Location
    from org.openpnp.util import MovableUtils, Utils2D
    from javax.imageio import ImageIO
    from java.io import File
    mm = LengthUnit.Millimeters
    part = placement.getPart()
    pkg = part.getPackage() if part is not None else None
    loc = Utils2D.calculateBoardPlacementLocation(board_location, placement.getLocation()).convertToUnits(mm)
    z = board_location.getLocation().convertToUnits(mm).getZ() + (part.getHeight().convertToUnits(mm).getValue() if part else 0.0)
    cam = machine.getDefaultHead().getDefaultCamera()
    MovableUtils.moveToLocationAtSafeZ(cam, Location(mm, loc.getX(), loc.getY(), z, 0.0))
    img = cam.settleAndCapture()
    upp = cam.getUnitsPerPixel(Length(z, mm)).convertToUnits(mm).getX()
    length, width, src = body_size(pkg)
    # the body's long axis: footprint X if body width >= height, else Y
    rot = loc.getRotation()
    if pkg is not None and pkg.getFootprint() is not None and pkg.getFootprint().getBodyHeight() > pkg.getFootprint().getBodyWidth():
        rot += 90.0
    res = analyse(img, upp, str(pkg.getId()) if pkg else "?", length, width, rot, root)
    res.update(location=[loc.getX(), loc.getY(), z, loc.getRotation()], upp=upp, size_source=src, axis_rot=rot)
    if out_dir:
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        p = os.path.join(out_dir, "%s.png" % _safe(str(placement.getId())))
        ImageIO.write(img, "png", File(p))
        res["image"] = p
    res["_image"] = img
    return res
