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


print("hole lines (no OpenCV needed)")
U = 0.0108
mm = lambda v: v / U
own = [(mm(4.9), mm(y), 70) for y in (1.0, 5.0, 9.0)]          # 12 mm tape: line 5.5 mm left of the centre (10.43 mm)
nbr = [(mm(20.2), mm(y), 70) for y in (2.0, 6.0, 10.0)]        # neighbouring tape's holes 9.8 mm right
size = (1931, 1099)
lines = tv.hole_lines(own + nbr, U)
check("two tapes in view -> two hole lines", len(lines) == 2, [len(x) for x in lines])
check("the line fitting a standard tape (F 5.5) is chosen, not the neighbour's", tv.choose_line(lines, size, U) == sorted(own))
check("only the neighbour's line -> misfit > 1 mm (eia_pocket refuses)", tv.line_fit(sorted(nbr), size, U) > 1.0
      and "error" in tv.eia_pocket(sorted(nbr), size, U, 4))
dark = lambda x, y, r: ([20] * 50, [180] * 50)                 # paper: black hole in white tape
emb = lambda x, y, r: ([40] * 40 + [200] * 10, [75] * 50)       # embossed tape: dark hole with a bright reflection
rib = lambda x, y, r: ([60, 70, 80] * 20, [62, 72, 78] * 20)   # feeder ribbing, no tape loaded
check("real holes kept (paper, embossed), ribbing circles dropped",
      len(tv.real_holes(own, dark)) == 3 and len(tv.real_holes(own, emb)) == 3 and tv.real_holes(own, rib) == [])
check("no real holes -> 'no tape at the pick location?'", "no tape" in tv.eia_pocket(tv.real_holes(own, rib), size, U, 4)["error"])

print("feeder nose fiducial (no OpenCV needed)")
from lumen import feedercheck as fc  # noqa: E402
c = (size[0] / 2.0, size[1] / 2.0)
board = [(c[0] + mm(1.0), c[1], 46)]
sides = [(c[0] + mm(1.0 - 2.0), c[1] + 3, 23), (c[0] + mm(1.0 + 2.0), c[1] - 2, 23)]
hit = tv.fiducial_pattern(board, sides, size, U)
check("centre mark with a side mark at 2 mm left and right -> found", hit and hit["x"] == board[0][0]
      and all(abs(d - 2.0) < 0.01 for d in hit["side_mm"]), hit)
check("lone bright dot (a sprocket hole with a reflection) -> None", tv.fiducial_pattern(board, [], size, U) is None)
check("side marks only on one side -> None", tv.fiducial_pattern(board, [sides[0], (sides[0][0] - mm(0.1), c[1], 23)],
                                                                 size, U) is None)
check("unequal side distances (2.0 / 3.0 mm) -> None",
      tv.fiducial_pattern(board, [sides[0], (c[0] + mm(4.0), c[1], 23)], size, U) is None)
check("side marks along the tape (Y) do not count", tv.fiducial_pattern(
    board, [(board[0][0], c[1] - mm(2.0), 23), (board[0][0], c[1] + mm(2.0), 23)], size, U) is None)
two = tv.fiducial_pattern(board + [(c[0] - mm(6), c[1], 46)],
                          sides + [(c[0] - mm(8), c[1], 23), (c[0] - mm(4), c[1], 23)], size, U)
check("two full patterns -> the one nearest the photo centre", two and two["x"] == board[0][0], two)
front = {"holes": [(300, 100, 70), (300, 470, 70)], "pocket_px": (620, 540)}     # holes left of the pocket
rear = {"holes": [(1600, 100, 70), (1600, 470, 70)], "pocket_px": (1280, 540)}
rails = [53.9, 58.5, 413.5, 407.0]
check("nose direction from the holes: left of the pocket -> +Y (front rail), right -> -Y (rear)",
      fc.nose_sign(55.0, front, rails) == 1 and fc.nose_sign(410.0, rear, rails) == -1)
check("nose direction without holes: towards the middle of the slot locations",
      fc.nose_sign(55.0, {}, rails) == 1 and fc.nose_sign(410.0, None, rails) == -1 and fc.nose_sign(410.0, {}, [400, 410]) == 1)
n8 = fc.fiducial_nominal((296.9, 53.9), 1)
n12 = fc.fiducial_nominal((296.9, 410.0), -1, 5.5)
check("CAD position: 8 mm tape front rail +0.6 / +13.15, 12 mm rear rail +1.4 / -13.15 mm",
      abs(n8[0] - 297.5) < 1e-9 and abs(n8[1] - 67.05) < 1e-9 and abs(n12[0] - 298.3) < 1e-9
      and abs(n12[1] - 396.85) < 1e-9, (n8, n12))

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
print("bench 2026-11-09 (raw images): empty feeders, neighbouring tape in view")
for pat in ("look-slot15-raw*.png", "look-slot28-raw*.png"):
    g, upp = load(pat)
    check("%s: no tape loaded (ribbed feeder housing) -> 'no tape', no offset" % pat[5:11],
          "no tape" in eia(g, upp, 4).get("error", ""), eia(g, upp, 4))
for pat, pitch, want in (("look-slot4-raw*.png", 8, (0.13, 1.84)), ("look-slot3-raw*.png", 8, (0.26, 0.38)),
                         ("look-slot12-raw*.png", 2, (-0.04, -0.90)), ("look-slot38-raw*.png", 4, (-0.06, 1.69))):
    g, upp = load(pat)
    e = eia(g, upp, pitch)
    o = off(e, g, upp) if not e.get("error") else None
    check("%s: own hole line, pocket %+.2f/%+.2f (bench result)" % (pat[5:11], want[0], want[1]),
          o and abs(o[0] - want[0]) < 0.1 and abs(o[1] - want[1]) < 0.1, (e.get("error"), e.get("F"), o))
check("no standard tape: pick far from any F -> error", "error" in tv.eia_pocket([(100, 100, 70), (100, 464, 70)], (1931, 1099), 0.011, 2))
print("\n%d/%d checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
