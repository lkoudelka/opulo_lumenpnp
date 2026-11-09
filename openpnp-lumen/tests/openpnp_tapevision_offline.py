# lib/lumen/tapevision.py holes_java + eia_pocket with OpenPnP's OpenCV on raw bench images (2026-11-09):
# the same results as the CPython path (tests/test_tapevision.py) and as Feeder Part Check on the machine.
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from java.io import File
from java.lang import System as S
from javax.imageio import ImageIO
from lumen import tapevision as tv

D = sys.argv[1]
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    S.out.println("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def run(pat, pitch):
    f = sorted(glob.glob(os.path.join(D, pat)))[0]
    upp = json.load(open(f[:-4] + ".json"))["upp"][0]
    img = ImageIO.read(File(f))
    w, h = img.getWidth(), img.getHeight()
    e = tv.eia_pocket(tv.holes_java(img, upp), (w, h), upp, pitch)
    o = None if e.get("error") else ((e["x"] - w / 2.0) * upp, -(e["y"] - h / 2.0) * upp)
    return e, o


S.out.println("empty feeders: no tape")
for pat in ("look-slot15-raw*.png", "look-slot28-raw*.png"):
    e, o = run(pat, 4)
    check("%s -> 'no tape', no offset" % pat[5:11], "no tape" in e.get("error", ""), e)
S.out.println("own hole line (neighbouring tape in view), pocket as measured on the machine")
for pat, pitch, F, want in (("look-slot4-raw*.png", 8, 5.5, (0.13, 1.84)), ("look-slot3-raw*.png", 8, 5.5, (0.26, 0.38)),
                            ("look-slot12-raw*.png", 2, 3.5, (-0.04, -0.90)), ("look-slot38-raw*.png", 4, 3.5, (-0.06, 1.69))):
    e, o = run(pat, pitch)
    check("%s: F %.1f, pocket %+.2f/%+.2f" % (pat[5:11], F, want[0], want[1]),
          o and e["F"] == F and abs(o[0] - want[0]) < 0.1 and abs(o[1] - want[1]) < 0.1, (e.get("error"), e.get("F"), o))
S.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
S.exit(0 if all(results) else 1)
