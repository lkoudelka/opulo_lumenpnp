#!/usr/bin/env python3
"""lib/lumen/tapevision.py on real top-camera images of Photon feeders (CPython + OpenCV).
Images: ~/claude/opulo/_testdata/feeder-images (outside the repo); skipped if missing."""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from lumen import tapevision as tv  # noqa: E402

D = os.path.expanduser(os.environ.get("FEEDER_IMAGES", "~/claude/opulo/_testdata/feeder-images"))
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


try:
    import cv2
    import numpy as np
except ImportError:
    print("(no OpenCV in this python: skipped)")
    sys.exit(0)
if not os.path.isdir(D):
    print("(no images in %s: skipped)" % D)
    sys.exit(0)


def load(pat):
    f = sorted(glob.glob(os.path.join(D, pat)))[0]
    j = f[:-4] + ".json"
    upp = json.load(open(j))["upp"][0] if os.path.exists(j) else 0.0110
    return cv2.cvtColor(cv2.imread(f), cv2.COLOR_BGR2GRAY), upp


def eia(g, upp, pitch):
    return tv.eia_pocket(tv.holes_cv2(g, upp, cv2), (g.shape[1], g.shape[0]), upp, pitch)


def off(e, g, upp):
    return ((e["x"] - g.shape[1] / 2.0) * upp, -(e["y"] - g.shape[0] / 2.0) * upp)


print("white paper tape: hole geometry == directly detected pocket (5 calibrated feeders)")
worst = 0.0
for pat, pitch in (("look-slot44*.png", 2), ("look-slot46*.png", 2), ("look-slot47*.png", 4), ("look-slot48*.png", 2), ("look-slot50*.png", 2)):
    g, upp = load(pat)
    e = eia(g, upp, pitch)
    p = tv.pick_pocket(tv.analyse(g, upp, cv2, np))
    worst = max(worst, abs(e["x"] - p["x"]) * upp, abs(e["y"] - p["y"]) * upp)
check("hole-geometry pocket within 0.1 mm of the detected pocket", worst < 0.1, "worst %.3f mm" % worst)
g, upp = load("look-slot45*.png")
check("slot 45 (pocket detection fails): hole geometry still finds the pocket", not eia(g, upp, 2).get("error"))

print("clear and black 12 mm tape (no paper band)")
for pat, pitch, want in (("slot27-*.png", 8, (-0.2, -1.73)), ("slot26-*.png", 8, (-0.2, -0.86)), ("slot3-*.png", 8, (0.27, 0.35))):
    g, upp = load(pat)
    e = eia(g, upp, pitch)
    o = off(e, g, upp) if not e.get("error") else None
    check("%s: 12 mm tape (F 5.5), pocket %+.2f/%+.2f" % (pat[:6], want[0], want[1]), o and e["F"] == 5.5
          and abs(o[0] - want[0]) < 0.15 and abs(o[1] - want[1]) < 0.15, (e.get("error"), o))
    check("%s: paper analysis reports no tape band / pockets (presence stays '?')" % pat[:6], "error" in tv.analyse(g, upp, cv2, np))
g, upp = load("slot27-*.png")
e8 = eia(g, upp, 8.0)
e4 = eia(g, upp, 4.0)
check("8 mm pitch: candidate grid 4 mm (hole parity unknown) -> same pocket as with 4 mm", abs(e8["y"] - e4["y"]) < 1, (e8["y"], e4["y"]))
check("no standard tape: pick far from any F -> error", "error" in tv.eia_pocket([(100, 100, 70), (100, 464, 70)], (1931, 1099), 0.011, 2))
print("\n%d/%d checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
