# -*- coding: utf-8 -*-
"""Find the tape in a top-camera image of a Photon feeder: sprocket holes, pockets, the feeder
window edge, and whether each pocket holds a part.

Works on a grey image as a list of rows or numpy array (CPython + OpenCV for development and
tests); the OpenPnP script uses the same geometry through OpenPnP's OpenCV (Java).  All results
are in pixels of the image; the caller converts with the camera's mm per pixel.

EIA-481 8 mm tape: sprocket hole 1.5 mm, hole pitch 4 mm, pocket centre 3.5 mm from the hole
line; pocket pitch 2 or 4 mm.
"""
from __future__ import absolute_import, division, print_function

import math

HOLE_D_MM = 1.5
HOLE_PITCH_MM = 4.0
POCKET_TO_HOLES_MM = 3.5


def analyse(gray, mm_per_px, cv2, np):
    """gray: uint8 numpy image (OpenPnP camera image, +Y up = image up).  Returns a dict:
    holes [(x, y, d)], pockets [{x, y, w, h, part, score}], column_x, hole_x, pitch_mm,
    window_edge_y (lowest bright tape row), or {'error': ...}."""
    h, w = gray.shape[:2]
    px = 1.0 / mm_per_px
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    # tape: the bright band (paper / plastic lit by the ring light)
    # Otsu splits lit tape from the dark feeder body; the pocket threshold follows the paper level
    thr, _ = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bright = (blur > thr).astype(np.uint8)
    cols = bright.mean(axis=0)
    band = cols > 0.5
    if band.sum() < 4 * px:
        return {"error": "no tape band found"}
    # widest contiguous bright column run = the tape
    best, start = (0, 0, 0), None
    for x in range(w + 1):
        on = x < w and band[x]
        if on and start is None:
            start = x
        elif not on and start is not None:
            if x - start > best[0]:
                best = (x - start, start, x)
            start = None
    tape_l, tape_r = best[1], best[2]
    rows = bright[:, tape_l:tape_r].mean(axis=1)
    lit = [y for y in range(h) if rows[y] > 0.5]
    if not lit:
        return {"error": "tape band has no lit rows"}
    window_edge_y = max(lit)            # the window's lower edge (tape hidden below)
    window_top_y = min(lit)

    # dark blobs inside the tape band: darker than 72 % of the paper level
    paper = float(np.median(blur[window_top_y:window_edge_y, tape_l:tape_r]))
    inv = (blur < 0.72 * paper).astype(np.uint8) * 255
    mask = np.zeros_like(inv)
    mask[window_top_y:window_edge_y, tape_l:tape_r] = 255
    inv = cv2.bitwise_and(inv, mask)
    found = cv2.findContours(inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = found[0] if len(found) == 2 else found[1]
    holes, pockets = [], []
    hole_d = HOLE_D_MM * px
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        area = cv2.contourArea(c)
        if bw < 0.3 * px or bh < 0.3 * px:
            continue
        cx, cy = x + bw / 2.0, y + bh / 2.0
        if abs(bw - hole_d) < 0.35 * hole_d and abs(bh - hole_d) < 0.35 * hole_d and area > 0.6 * math.pi * (hole_d / 2) ** 2:
            holes.append((cx, cy, (bw + bh) / 2.0))
        elif bw < 3.5 * px and bh < 3.5 * px and area > 0.6 * bw * bh:
            if x <= tape_l + 2 or x + bw >= tape_r - 2 or y <= window_top_y + 1 or y + bh >= window_edge_y - 1:
                continue                # cut by the window / image border
            pockets.append({"x": cx, "y": cy, "w": bw, "h": bh})
    return _finish(holes, pockets, px, lambda x0, x1, y0, y1: [int(v) for v in blur[y0:y1, x0:x1].ravel()],
                   {"paper": paper, "window_edge_y": window_edge_y, "window_top_y": window_top_y,
                    "tape": (tape_l, tape_r), "size": (w, h)})


# ---------------------------------------------------------------------------------------
# Same analysis with OpenPnP's OpenCV (Java, Jython): image = java.awt.image.BufferedImage
# ---------------------------------------------------------------------------------------
def _ensure_opencv():
    from java.lang import Throwable
    from org.opencv.core import Mat
    try:
        Mat()
    except (Exception, Throwable):          # natives not loaded yet (outside the GUI): UnsatisfiedLinkError
        from nu.pattern import OpenCV
        OpenCV.loadLocally()


def analyse_java(image, mm_per_px):
    """Like analyse() for a BufferedImage from camera.settleAndCapture() (OpenPnP's OpenCV)."""
    _ensure_opencv()
    from org.opencv.core import Core, CvType, Mat, MatOfFloat, MatOfInt, Point, Scalar, Size
    from org.opencv.imgproc import Imgproc
    from org.openpnp.util import OpenCvUtils
    from java.util import ArrayList, Arrays
    import jarray
    mat = OpenCvUtils.toMat(image)
    gray = Mat()
    if mat.channels() > 1:
        Imgproc.cvtColor(mat, gray, Imgproc.COLOR_BGR2GRAY)
    else:
        gray = mat
    blur = Mat()
    Imgproc.GaussianBlur(gray, blur, Size(5, 5), 0)
    h, w = blur.rows(), blur.cols()
    px = 1.0 / mm_per_px

    def means(m, dim):                      # dim 0: per column, 1: per row (fraction of lit pixels)
        r = Mat()
        Core.reduce(m, r, dim, Core.REDUCE_AVG, CvType.CV_32F)
        a = jarray.zeros(r.rows() * r.cols(), "f")
        r.get(0, 0, a)
        return [v / 255.0 for v in a]
    bright = Mat()
    Imgproc.threshold(blur, bright, 0, 255, Imgproc.THRESH_BINARY + Imgproc.THRESH_OTSU)
    cols = means(bright, 0)
    best, start = (0, 0, 0), None
    for x in range(w + 1):
        on = x < w and cols[x] > 0.5
        if on and start is None:
            start = x
        elif not on and start is not None:
            if x - start > best[0]:
                best = (x - start, start, x)
            start = None
    if best[0] < 4 * px:
        return {"error": "no tape band found"}
    tape_l, tape_r = best[1], best[2]
    rows = means(bright.submat(0, h, tape_l, tape_r), 1)
    lit = [y for y in range(h) if rows[y] > 0.5]
    if not lit:
        return {"error": "tape band has no lit rows"}
    window_edge_y, window_top_y = max(lit), min(lit)
    band = blur.submat(window_top_y, window_edge_y, tape_l, tape_r)
    hist = Mat()
    Imgproc.calcHist(Arrays.asList([band]), MatOfInt([0]), Mat(), hist, MatOfInt([256]), MatOfFloat([0.0, 256.0]))
    hv = jarray.zeros(256, "f")
    hist.get(0, 0, hv)
    half, acc, paper = sum(hv) / 2.0, 0.0, 0.0
    for i in range(256):
        acc += hv[i]
        if acc >= half:
            paper = float(i)
            break
    inv = Mat()
    Imgproc.threshold(blur, inv, 0.72 * paper, 255, Imgproc.THRESH_BINARY_INV)
    mask = Mat.zeros(h, w, CvType.CV_8UC1)
    Imgproc.rectangle(mask, Point(tape_l, window_top_y), Point(tape_r - 1, window_edge_y - 1), Scalar(255.0), -1)
    Core.bitwise_and(inv, mask, inv)
    contours = ArrayList()
    Imgproc.findContours(inv, contours, Mat(), Imgproc.RETR_EXTERNAL, Imgproc.CHAIN_APPROX_SIMPLE)
    holes, pockets = [], []
    hole_d = HOLE_D_MM * px
    for c in contours:
        r = Imgproc.boundingRect(c)
        x, y, bw, bh = r.x, r.y, r.width, r.height
        area = Imgproc.contourArea(c)
        if bw < 0.3 * px or bh < 0.3 * px:
            continue
        cx, cy = x + bw / 2.0, y + bh / 2.0
        if abs(bw - hole_d) < 0.35 * hole_d and abs(bh - hole_d) < 0.35 * hole_d and area > 0.6 * math.pi * (hole_d / 2) ** 2:
            holes.append((cx, cy, (bw + bh) / 2.0))
        elif bw < 3.5 * px and bh < 3.5 * px and area > 0.6 * bw * bh:
            if x <= tape_l + 2 or x + bw >= tape_r - 2 or y <= window_top_y + 1 or y + bh >= window_edge_y - 1:
                continue
            pockets.append({"x": cx, "y": cy, "w": bw, "h": bh})

    def roi_values(x0, x1, y0, y1):
        if x1 <= x0 or y1 <= y0:
            return []
        a = jarray.zeros((x1 - x0) * (y1 - y0), "b")
        blur.submat(y0, y1, x0, x1).clone().get(0, 0, a)
        return [v & 0xFF for v in a]
    return _finish(holes, pockets, px, roi_values,
                   {"paper": paper, "window_edge_y": window_edge_y, "window_top_y": window_top_y,
                    "tape": (tape_l, tape_r), "size": (w, h)})


def _pct(values, q):
    v = sorted(values)
    return float(v[min(len(v) - 1, int(q / 100.0 * len(v)))]) if v else 0.0


def _finish(holes, pockets, px, roi_values, extra):
    """Shared geometry: hole line, pocket column 3.5 mm from it, pitch, part present per pocket."""
    if not holes:
        return dict(extra, error="no sprocket holes found", pockets=pockets)
    hole_x = sorted(hx for hx, _, _ in holes)[len(holes) // 2]
    want = POCKET_TO_HOLES_MM * px
    col = [p for p in pockets if abs(abs(p["x"] - hole_x) - want) < 0.5 * px]
    if not col:
        return dict(extra, error="no pockets 3.5 mm from the sprocket holes", holes=holes)
    column_x = sorted(p["x"] for p in col)[len(col) // 2]
    col.sort(key=lambda p: p["y"])
    pitch = None
    if len(col) >= 2:
        d = sorted(col[i + 1]["y"] - col[i]["y"] for i in range(len(col) - 1))
        pitch = d[len(d) // 2] / px
    for p in col:
        x0, x1 = int(p["x"] - p["w"] / 2) + 2, int(p["x"] + p["w"] / 2) - 2
        y0, y1 = int(p["y"] - p["h"] / 2) + 2, int(p["y"] + p["h"] / 2) - 2
        roi = roi_values(max(0, x0), x1, max(0, y0), y1)
        if not roi:
            p["part"], p["score"] = None, 0.0
            continue
        p["score"] = round(_pct(roi, 97) - _pct(roi, 50), 1)
        p["part"] = p["score"] > PART_SCORE
    return dict(extra, holes=holes, pockets=col, hole_x=hole_x, column_x=column_x, pitch_mm=pitch)


PART_SCORE = 40.0       # contrast (97th - 50th percentile) in the pocket: parts ~100, empty pockets 15-30


def pick_pocket(result, near_y=None):
    """The pocket nearest to the image centre row (the current pick location)."""
    pk = result.get("pockets") or []
    if not pk:
        return None
    cy = result["size"][1] / 2.0 if near_y is None else near_y
    return min(pk, key=lambda q: abs(q["y"] - cy))


# ---------------------------------------------------------------------------------------
# Tape geometry from the sprocket holes (works on paper, clear and black tape, any part):
# EIA-481: holes 1.5 mm every 4 mm; pocket centre F from the hole line (8 mm tape 3.5,
# 12 mm 5.5, 16 mm 7.5, 24 mm 11.5) and P2 = 2.0 mm along the tape from a hole.
# ---------------------------------------------------------------------------------------
F_STANDARD = (3.5, 5.5, 7.5, 11.5)


def hole_line(circles, upp):
    """circles [(x, y, r)] px -> the circles on one line (same x within 0.4 mm) whose spacings are
    multiples of 4 mm; None if no such pair."""
    best = None
    for h in circles:
        grp = [q for q in circles if abs(q[0] - h[0]) < 0.4 / upp]
        ys = sorted(q[1] for q in grp)
        good = 0
        for i in range(len(ys)):
            for j in range(i + 1, len(ys)):
                n = (ys[j] - ys[i]) * upp / HOLE_PITCH_MM
                if round(n) >= 1 and abs(n - round(n)) < 0.06:
                    good += 1
        if good and (best is None or good > best[0]):
            best = (good, grp)
    return best[1] if best else None


def eia_pocket(holes, size, upp, pitch_mm):
    """Pocket centre (px) nearest to the image centre, from the hole line and the part pitch.
    Returns {x, y, F, F_measured, holes, hole_x} or {'error'}."""
    if not holes or len(holes) < 2:
        return {"error": "sprocket holes not found"}
    w, h = size
    cx, cy = w / 2.0, h / 2.0
    xs = sorted(q[0] for q in holes)
    hx = xs[len(xs) // 2]
    y0 = holes[0][1]
    ph = y0 + sum(((y - y0) * upp + 2.0) % HOLE_PITCH_MM - 2.0 for _, y, _ in holes) / len(holes) / upp
    fe = abs(cx - hx) * upp
    F = min(F_STANDARD, key=lambda f: abs(f - fe))
    if abs(F - fe) > 1.0:
        return {"error": "pick location %.2f mm from the hole line: no standard tape (3.5/5.5/7.5/11.5)" % fe}
    side = 1.0 if cx > hx else -1.0
    # pocket centres are 2.0 mm from SOME hole: candidates every min(pitch, 4) mm (for 8/12 mm pitch
    # the hole parity is not known from the image -> the candidate nearest the current pick wins)
    grid = min(float(pitch_mm or 4.0), HOLE_PITCH_MM)
    k = round(((cy - ph) * upp - 2.0) / grid)
    return {"x": hx + side * F / upp, "y": ph + (2.0 + k * grid) / upp, "F": F, "F_measured": fe,
            "holes": len(holes), "hole_x": hx}


def holes_cv2(gray, upp, cv2):
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
    img = cv2.GaussianBlur(clahe, (9, 9), 2)
    for p2 in (40, 30, 25):
        c = cv2.HoughCircles(img, cv2.HOUGH_GRADIENT, 1.5, int(3.0 / upp), param1=50, param2=p2,
                             minRadius=int(0.6 / upp), maxRadius=int(0.9 / upp))
        found = hole_line([] if c is None else [tuple(float(v) for v in q) for q in c[0]], upp)
        if found:
            return found
    return None


def holes_java(image, upp):
    """Sprocket holes in a BufferedImage with OpenPnP's OpenCV (same parameters as holes_cv2)."""
    _ensure_opencv()
    from org.opencv.core import Mat, Size
    from org.opencv.imgproc import Imgproc
    from org.openpnp.util import OpenCvUtils
    import jarray
    mat = OpenCvUtils.toMat(image)
    g = Mat()
    Imgproc.cvtColor(mat, g, Imgproc.COLOR_BGR2GRAY)
    Imgproc.createCLAHE(3.0, Size(8, 8)).apply(g, g)
    Imgproc.GaussianBlur(g, g, Size(9, 9), 2)
    for p2 in (40, 30, 25):
        c = Mat()
        Imgproc.HoughCircles(g, c, Imgproc.HOUGH_GRADIENT, 1.5, int(3.0 / upp), 50, p2, int(0.6 / upp), int(0.9 / upp))
        circles = []
        if not c.empty():
            a = jarray.zeros(c.cols() * 3, "f")
            c.get(0, 0, a)
            circles = [(a[i], a[i + 1], a[i + 2]) for i in range(0, len(a), 3)]
        found = hole_line(circles, upp)
        if found:
            return found
    return None
