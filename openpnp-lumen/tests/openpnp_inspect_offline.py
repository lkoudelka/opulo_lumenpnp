# lib/lumen/inspect.py with OpenPnP's OpenCV (Jython), offline on semi-synthetic images:
# real 0402 part on real soldermask at known offset / rotation (tests/make_inspection_images.py)
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from java.io import File
from java.lang import System as S
from javax.imageio import ImageIO
from lumen import inspect as ins

D = sys.argv[1]
truth = json.load(open(os.path.join(D, "truth.json")))
upp = truth["upp"]
L, W = truth["body"]
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    S.out.println("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def img(n):
    return ImageIO.read(File(os.path.join(D, n + ".png")))


def fmt(b):
    return "found" if not b.get("found") else "dx %+.3f dy %+.3f ang %+.1f size %.2fx%.2f %s" % (
        b["dx"], b["dy"], b["angle_err"], b["size"][0], b["size"][1], b["method"])


S.out.println("size method (body 1.0 x 0.5 mm)")
# the real part sits ~0.06 mm off-centre in the cut-out pocket: offsets are compared to the "ok" image
r0 = ins.find_body(img("ok"), upp, L, W, 0.0)
check("ok: found, size 1.0 x 0.5, angle ~0, near the centre", r0["found"] and abs(r0["angle_err"]) < 3 and
      abs(r0["size"][0] - 1.0) < 0.1 and abs(r0["size"][1] - 0.5) < 0.1 and abs(r0["dx"]) < 0.1 and abs(r0["dy"]) < 0.1, fmt(r0))
r = ins.find_body(img("offset"), upp, L, W, 0.0)
check("offset: +0.20 / -0.10 mm relative to ok, within 0.02", r["found"] and abs(r["dx"] - r0["dx"] - 0.20) < 0.02
      and abs(r["dy"] - r0["dy"] + 0.10) < 0.02, "%s (relative %+.3f / %+.3f)" % (fmt(r), r["dx"] - r0["dx"], r["dy"] - r0["dy"]))
r = ins.find_body(img("rot90"), upp, L, W, 0.0)
check("rot90: angle error 90", r["found"] and abs(abs(r["angle_err"]) - 90) < 5, fmt(r))
r = ins.find_body(img("rot90"), upp, L, W, 90.0)
check("rot90 expected at 90: angle error ~0", r["found"] and abs(r["angle_err"]) < 5, fmt(r))
r = ins.find_body(img("rot5"), upp, L, W, 0.0)
check("rot5: angle error +5 (CCW) within 2", r["found"] and abs(r["angle_err"] - 5) < 2, fmt(r))
r = ins.find_body(img("missing"), upp, L, W, 0.0)
check("missing: not found", not r["found"], r)
check("verdicts: ok OK / offset CHECK / rot90 CHECK / missing FAIL",
      ins.verdict({"body": ins.find_body(img("ok"), upp, L, W, 0.0)}) == "OK"
      and ins.verdict({"body": ins.find_body(img("offset"), upp, L, W, 0.0)}).startswith("CHECK")
      and "rotated" in ins.verdict({"body": ins.find_body(img("rot90"), upp, L, W, 0.0)})
      and ins.verdict({"body": ins.find_body(img("missing"), upp, L, W, 0.0)}).startswith("FAIL"))

S.out.println("result drawn into the saved image")
r = ins.find_body(img("offset"), upp, L, W, 0.0)
bx = [p[0] for p in r["box_px"]]
by = [p[1] for p in r["box_px"]]
w0, h0 = img("offset").getWidth(), img("offset").getHeight()
cxb, cyb = sum(bx) / 4.0, sum(by) / 4.0
check("found body: box corners in whole-image pixels around the found centre",
      len(r["box_px"]) == 4 and abs((cxb - w0 / 2.0) * upp - r["dx"]) < 0.01 and abs(-(cyb - h0 / 2.0) * upp - r["dy"]) < 0.01
      and abs((max(bx) - min(bx)) * upp - 1.0) < 0.15, (r["box_px"], r["dx"], r["dy"]))
res = {"body": r, "verdict": ins.verdict({"body": r}), "upp": upp, "expect_size": [L, W], "axis_rot": 0.0}
a = ins.annotate(img("offset"), res, "C7  C_0402")
raw = img("offset")
orange = ins.verdict_colour(res["verdict"]).getRGB() & 0xFFFFFF
px = lambda im, x, y: im.getRGB(int(x), int(y)) & 0xFFFFFF
mx, my = (r["box_px"][0][0] + r["box_px"][1][0]) / 2.0, (r["box_px"][0][1] + r["box_px"][1][1]) / 2.0
on_box = [px(a, mx + i, my + j) for i in range(-2, 3) for j in range(-2, 3)]      # (anti-aliased line)
check("annotated: the found box in the verdict colour (CHECK = orange), the raw image unchanged",
      orange in on_box and px(raw, cxb, cyb) == px(img("offset"), cxb, cyb) and a is not raw, (hex(on_box[0]), hex(orange)))
check("annotated: placement cross (cyan) at the image centre", 0x00DCFF in [px(a, w0 / 2.0 + i, h0 / 2.0 + j) for i in (-1, 0, 1)
                                                                          for j in (-1, 0, 1)])
out = os.path.join(tempfile.mkdtemp(), "C7.png")
res.update(_image=raw, image=out)
ins.save_annotated(res, "C7  C_0402")
check("save_annotated writes <ref>.png", os.path.isfile(out) and ImageIO.read(File(out)).getWidth() == w0)
S.out.println("chip parts: terminations (real 0603 bench images, 2026-11-26)")
C = os.path.expanduser(os.environ.get("CHIP_IMAGES", "~/claude/opulo/_testdata/inspection-0603"))
if os.path.isfile(os.path.join(C, "truth.json")):
    ct = json.load(open(os.path.join(C, "truth.json")))
    got = {}
    for ref, p in sorted(ct["parts"].items()):
        cr = ins.chip_check(ImageIO.read(File(os.path.join(C, ref + ".png"))), ct["upp"], ct["body"][0], ct["body"][1], p["rot"])
        got[ref] = (ins.verdict({"body": cr}), cr)
    bad = [r for r, p in ct["parts"].items() if p["present"] != (not got[r][0].startswith("FAIL"))]
    check("missing parts (bare pads) FAIL, placed ones not: %d images" % len(got), not bad, [(r, got[r][0]) for r in bad])
    present = [r for r, p in ct["parts"].items() if p["present"]]
    check("placed parts: OK, offset < 0.15 mm, angle < 4 deg (were CHECK with pads / half parts boxed)",
          all(got[r][0] == "OK" and abs(got[r][1]["dx"]) < 0.15 and abs(got[r][1]["dy"]) < 0.15
              and abs(got[r][1]["angle_err"]) < 4 for r in present), [(r, got[r][0]) for r in present])
    check("missing: says 'bare pads'", all("bare pads" in got[r][0] for r, p in ct["parts"].items() if not p["present"]))
else:
    S.out.println("  (no %s: skipped)" % C)
check("chip packages recognised by name", ins.is_chip("RES_0603") and ins.is_chip("CAPC_1206") and ins.is_chip("C_0402_1005Metric")
      and ins.is_chip("R_0805_2012Metric") and not ins.is_chip("SOT-223_LM1117") and not ins.is_chip("DIODE_SOD-323"))
S.out.println("golden sample method")
root = tempfile.mkdtemp()
ins.save_golden(root, "C_0402_1005Metric", img("ok"), upp, 0.0, L, W, "test ok.png")
g = ins.load_golden(root, "C_0402_1005Metric")
m = ins.match_golden(img("offset"), upp, g, 0.0)
check("offset: score > 0.9, offset +0.20 / -0.10 within 0.03 (golden made from ok)", m["score"] > 0.9 and abs(m["dx"] - 0.20) < 0.03 and abs(m["dy"] + 0.10) < 0.03,
      "score %.2f dx %+.3f dy %+.3f" % (m["score"], m["dx"], m["dy"]))
m = ins.match_golden(img("rot90"), upp, g, 90.0)
check("rot90 expected at 90: golden rotated -> score > 0.8", m["score"] > 0.8, "score %.2f" % m["score"])
m = ins.match_golden(img("rot90"), upp, g, 0.0)
check("rot90 expected at 0: low score", m["score"] < ins.LIMITS["score_ok"], "score %.2f" % m["score"])
m = ins.match_golden(img("missing"), upp, g, 0.0)
check("missing: score below the fail limit", m["score"] < ins.LIMITS["score_fail"], "score %.2f" % m["score"])
ins.save_golden(root, "LED-ASYM", img("asym_ok"), upp, 0.0, L, W, "test asym_ok.png")
ga = ins.load_golden(root, "LED-ASYM")
m1 = ins.match_golden(img("asym_ok"), upp, ga, 0.0)
m2 = ins.match_golden(img("asym_180"), upp, ga, 0.0)
check("asymmetric part correct: no polarity suspicion", not m1["polarity_suspect"], "%.2f / 180: %.2f" % (m1["score"], m1["score180"]))
check("asymmetric part turned 180: polarity suspected", m2["polarity_suspect"], "%.2f / 180: %.2f" % (m2["score"], m2["score180"]))
from lumen import testplace as tp
t1 = ins.match_golden_turns(img("asym_ok"), upp, ga, 0.0)
t2 = ins.match_golden_turns(img("asym_180"), upp, ga, 0.0)
check("test placement: golden turns, correct part -> proposal 0", tp.propose_turn(t1)[0] == 0.0, tp.propose_turn(t1)[1])
check("test placement: golden turns, part turned 180 -> proposal 180", tp.propose_turn(t2)[0] == 180.0, tp.propose_turn(t2)[1])
t3 = ins.match_golden_turns(img("rot90"), upp, g, 90.0)
check("test placement: golden turns at the expected 90 deg -> best turn 0 or 180 (2-pin body)",
      max(t3, key=t3.get) in (0.0, 180.0), t3)
check("verdict for the turned part: FAIL ... polarity", "polarity" in ins.verdict({"golden": m2, "body": ins.find_body(img("asym_180"), upp, L, W, 0.0)}),
      ins.verdict({"golden": m2}))
res = ins.analyse(img("offset"), upp, "C_0402_1005Metric", L, W, 0.0, root)
check("analyse(): both methods, verdict CHECK offset", "body" in res and "golden" in res and "offset" in res["verdict"], res["verdict"])
S.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
S.exit(0 if all(results) else 1)
