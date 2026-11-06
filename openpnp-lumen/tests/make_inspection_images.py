#!/usr/bin/env python3
"""Semi-synthetic test images for lib/lumen/inspect.py (CPython + OpenCV): a REAL 0402 capacitor
cut from a top-camera image of a feeder tape, pasted on REAL board background (soldermask) at known
offset / rotation; plus the bare background (missing part) and an asymmetric part (polarity).
Writes PNG + truth.json into the output dir (default ~/claude/opulo/_testdata/inspection)."""
import json
import os
import sys

import cv2
import numpy as np

T = os.path.expanduser("~/claude/opulo/_testdata")
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(T, "inspection")
os.makedirs(out, exist_ok=True)
UPP = 0.0111
bg = cv2.imread(sorted(__import__("glob").glob(os.path.join(T, "assembled", "look-board-REF_1-*.png")))[0])
g = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY).astype(np.float32)
# flattest 300 x 300 px patch (bare soldermask) -> rolled to the image centre
best = None
for y in range(0, g.shape[0] - 300, 50):
    for x in range(0, g.shape[1] - 300, 50):
        s = g[y:y + 300, x:x + 300].std()
        if best is None or s < best[0]:
            best = (s, x + 150, y + 150)
h, w = bg.shape[:2]
bg = np.roll(np.roll(bg, h // 2 - best[2], axis=0), w // 2 - best[1], axis=1)
src = cv2.imread(sorted(__import__("glob").glob(os.path.join(T, "feeder-images", "look-slot48-*.png")))[0])
part = src[362 - 27:362 + 27, 972 - 52:972 + 52].copy()          # one 0402 in its pocket (paper tape)


def paste(img, p, dx_mm, dy_mm, rot_deg):
    m = cv2.getRotationMatrix2D((p.shape[1] / 2, p.shape[0] / 2), rot_deg, 1.0)
    c, s_ = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(p.shape[0] * s_ + p.shape[1] * c) + 2, int(p.shape[0] * c + p.shape[1] * s_) + 2
    m[0, 2] += nw / 2 - p.shape[1] / 2
    m[1, 2] += nh / 2 - p.shape[0] / 2
    r = cv2.warpAffine(p, m, (nw, nh), borderValue=(0, 0, 0))
    mask = cv2.warpAffine(np.full(p.shape[:2], 255, np.uint8), m, (nw, nh))
    o = img.copy()
    cx, cy = int(round(w / 2 + dx_mm / UPP)), int(round(h / 2 - dy_mm / UPP))
    x0, y0 = cx - nw // 2, cy - nh // 2
    roi = o[y0:y0 + nh, x0:x0 + nw]
    roi[mask > 0] = r[mask > 0]
    return o


asym = part.copy()
cv2.circle(asym, (12, 27), 6, (255, 255, 255), -1)                # pin-1 mark at the left end
cases = {
    "ok": (part, 0.0, 0.0, 0.0), "offset": (part, 0.20, -0.10, 0.0), "rot90": (part, 0.0, 0.0, 90.0),
    "rot5": (part, 0.05, 0.0, 5.0), "missing": (None, 0, 0, 0), "asym_ok": (asym, 0.0, 0.0, 0.0),
    "asym_180": (asym, 0.0, 0.0, 180.0),
}
truth = {}
for name, (p, dx, dy, rot) in cases.items():
    img = bg if p is None else paste(bg, p, dx, dy, rot)
    cv2.imwrite(os.path.join(out, name + ".png"), img)
    truth[name] = {"dx": dx, "dy": dy, "rot": rot, "present": p is not None}
json.dump({"upp": UPP, "body": [1.0, 0.5], "cases": truth}, open(os.path.join(out, "truth.json"), "w"), indent=1)
print("written", sorted(truth), "to", out)
