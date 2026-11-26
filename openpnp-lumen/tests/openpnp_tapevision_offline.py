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
S.out.println("feeder nose fiducial (synthetic photo: black mask, FR4 openings, copper dots, noise)")
from java.awt import Color, Graphics2D as G2
from java.awt.image import BufferedImage
from java.util import Random


def fid_photo(marks, upp=0.0114, size=(1929, 1093)):
    """marks: [(x mm, y mm from the centre, +y up, copper diameter mm, mask opening mm)]."""
    w, h = size
    im = BufferedImage(w, h, BufferedImage.TYPE_3BYTE_BGR)
    g = im.createGraphics()                                    # (calls through Graphics2D: Java 17 modules)
    G2.setColor(g, Color(25, 35, 30))
    G2.fillRect(g, 0, 0, w, h)
    rnd = Random(7)
    for _ in range(4000):                                       # mask texture
        v = 20 + rnd.nextInt(30)
        G2.setColor(g, Color(v, v + 8, v + 4))
        G2.fillRect(g, rnd.nextInt(w), rnd.nextInt(h), 3, 3)
    for (x, y, d, o) in marks:
        cx, cy = w / 2.0 + x / upp, h / 2.0 - y / upp
        for dd, c in ((o, Color(95, 85, 60)), (d, Color(225, 205, 150))):
            r = dd / 2.0 / upp
            G2.setColor(g, c)
            G2.fillOval(g, int(cx - r), int(cy - r), int(2 * r), int(2 * r))
    G2.dispose(g)
    return im


U = 0.0114
board = [(1.2, -0.7, 1.0, 2.0), (1.2 - 2.0, -0.7, 0.5, 1.5), (1.2 + 2.0, -0.7, 0.5, 1.5)]
hit = tv.fiducial_java(fid_photo(board), U)
fx, fy = ((hit["x"] - 1929 / 2.0) * U, -(hit["y"] - 1093 / 2.0) * U) if hit else (None, None)
check("centre mark found with both side marks, within 0.05 mm", hit and hit["sides"] == 2
      and abs(fx - 1.2) < 0.05 and abs(fy + 0.7) < 0.05, (hit, fx, fy))
lone = tv.fiducial_java(fid_photo(board + [(0.2, 0.3, 1.0, 2.0)]), U)
check("a lone bright dot nearer the centre loses to the mark with side marks", lone and lone["sides"] == 2
      and abs((lone["x"] - 1929 / 2.0) * U - 1.2) < 0.05, lone)
check("no marks (plain mask) -> None", tv.fiducial_java(fid_photo([]), U) is None)
S.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
S.exit(0 if all(results) else 1)
