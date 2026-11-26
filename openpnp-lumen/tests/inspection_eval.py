# Placement inspection over a test set (tests/inspection_dataset.py output; Jython, OpenPnP's OpenCV, no machine):
# every placement analysed as Placement Inspection does, compared with the truth.  Prints one line per CHECK / FAIL
# and a summary per package.
#   tests/run_inspection_eval.sh <dataset dir> [golden root] [-v] [--learn]
# --learn: the golden root is copied to a temp directory and, run by run in time order, a present part that is CHECK
# only for a weak golden match is added as a golden sample (what Set as OK by hand does) - the later runs show the
# effect.
# Exit 0 when no present part FAILs and every missing part FAILs (CHECKs on present parts are counted, not failed:
# the summary is the measure).
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
data = sys.argv[1]
root = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else None
verbose = "-v" in sys.argv
learn = "--learn" in sys.argv
min_ok = float(sys.argv[sys.argv.index("--min-ok") + 1]) if "--min-ok" in sys.argv else 0.0
learned = []
if learn and root:
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp()
    shutil.copytree(os.path.join(root, "golden"), os.path.join(tmp, "golden"))
    root = tmp

from java.io import File
from java.lang import System as S
from javax.imageio import ImageIO
from lumen import inspect as ins

stats, bad = {}, []
for run in sorted(os.listdir(data)):
    mp = os.path.join(data, run, "meta.json")
    if not os.path.isfile(mp) or run.startswith("golden"):
        continue
    meta = json.load(open(mp))["parts"]
    for ref in sorted(meta):
        m = meta[ref]
        img = ImageIO.read(File(os.path.join(data, run, ref + "-raw.png")))
        res = ins.analyse(img, m["upp"], m["package"], m["length"], m["width"], m["axis_rot"], root)
        v = res["verdict"]
        if learn and m["truth"] == "ok" and v.startswith("CHECK") and "weak match with the golden" in v:
            ins.add_golden_sample(root, m["package"], img, m["upp"], m["axis_rot"], m["length"] or 2.0,
                                  m["width"] or 2.0, "eval %s %s" % (run[-6:], ref))
            learned.append("%s %s" % (run[-6:], ref))
        st = stats.setdefault(m["package"], {"ok": 0, "check": 0, "fail": 0, "missing_caught": 0, "missing": 0})
        b = res.get("body") or {}
        off = ((b.get("dx") ** 2 + b.get("dy") ** 2) ** 0.5) if b.get("found") else None
        line = "t%s %-4s %-20s %-8s %s%s" % (run[-6:], ref, m["package"], m["truth"], v,
                                               "" if off is None else "  [%.2f mm, %+.0f deg, %s]" % (off, b.get("angle_err", 0), b.get("method")))
        if m["truth"] == "shifted":
            st["shifted"] = st.get("shifted", 0) + 1
            if v.startswith("OK"):
                bad.append("SHIFT NOT SEEN " + line)
            else:
                st["shifted_caught"] = st.get("shifted_caught", 0) + 1
            S.out.println(line)
            continue
        if m["truth"] == "missing":
            st["missing"] += 1
            if v.startswith("FAIL"):
                st["missing_caught"] += 1
            else:
                bad.append("MISSED " + line)
        else:
            k = "ok" if v.startswith("OK") else ("fail" if v.startswith("FAIL") or v.startswith("ERROR") else "check")
            st[k] += 1
            if k == "fail" and m["truth"] == "ok":
                bad.append("FALSE FAIL " + line)
            if k != "ok" or verbose:
                S.out.println(line)
S.out.println("\n%-22s %5s %5s %5s %s" % ("package", "OK", "CHECK", "FAIL", "missing caught"))
tot = {"ok": 0, "check": 0, "fail": 0, "missing_caught": 0, "missing": 0}
for p in sorted(stats):
    s = stats[p]
    for k in tot:
        tot[k] += s[k]
    S.out.println("%-22s %5d %5d %5d %s" % (p, s["ok"], s["check"], s["fail"],
                                           "%d/%d" % (s["missing_caught"], s["missing"]) if s["missing"] else ""))
S.out.println("%-22s %5d %5d %5d %d/%d" % ("TOTAL", tot["ok"], tot["check"], tot["fail"], tot["missing_caught"], tot["missing"]))
for x in bad:
    S.out.println(x)
if learn:
    S.out.println("learned golden samples (operator confirmations simulated): %s" % ", ".join(learned))
sh = sum(s.get("shifted", 0) for s in stats.values())
S.out.println("shifted parts flagged: %d of %d" % (sum(s.get("shifted_caught", 0) for s in stats.values()), sh))
S.out.println("present parts OK: %d of %d (%.0f %%)" % (tot["ok"], tot["ok"] + tot["check"] + tot["fail"],
                                                        100.0 * tot["ok"] / max(1, tot["ok"] + tot["check"] + tot["fail"])))
pct = 100.0 * tot["ok"] / max(1, tot["ok"] + tot["check"] + tot["fail"])
if pct < min_ok:
    bad.append("present parts OK %.0f %% below --min-ok %.0f %%" % (pct, min_ok))
    S.out.println(bad[-1])
S.exit(0 if not bad else 1)
