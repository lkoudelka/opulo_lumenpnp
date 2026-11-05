#!/usr/bin/env python3
"""lib/lumen/learning.py with synthetic bottom-vision records (CPython)."""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from lumen import learning  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def recs(fid, n, dx, dy, t0=0, noise=0.0, pick_rot=0.0, nozzle_rot=0.0, drot=0.0, seed=1):
    rnd = random.Random(seed)
    return [{"t": "2026-11-06T10:%02d:%02d" % ((t0 + i) // 60, (t0 + i) % 60), "feeder_id": fid, "feeder": fid,
             "part": "R0402", "dx": dx + rnd.gauss(0, noise), "dy": dy + rnd.gauss(0, noise), "drot": drot,
             "units": "Millimeters", "pick": [0, 0, 0, pick_rot], "nozzle_rot": nozzle_rot} for i in range(n)]


r = learning.analyse(recs("A", 10, 0.30, 0.0, noise=0.02) + recs("B", 10, 0.0, 0.0, noise=0.5, seed=2)
                     + recs("C", 3, 0.4, 0.0) + recs("D", 10, 0.0, 0.30, pick_rot=90, nozzle_rot=0)
                     + recs("E", 10, 2.0, 0.0) + recs("F", 10, 0.02, 0.0, drot=88), [])
check("systematic offset -> damped suggestion", r["A"]["suggest"] and abs(r["A"]["suggest"][0] - 0.15) < 0.02, r["A"]["status"])
check("large scatter -> no suggestion", r["B"]["suggest"] is None and "scatter" in r["B"]["status"], r["B"]["status"])
check("too few samples -> collecting", r["C"]["suggest"] is None and "collecting" in r["C"]["status"])
check("frame transform (pick rot 90): (0, 0.3) -> (-0.3, 0)", abs(r["D"]["mean_x"] + 0.3) < 1e-6 and abs(r["D"]["mean_y"]) < 1e-6,
      (round(r["D"]["mean_x"], 3), round(r["D"]["mean_y"], 3)))
check("step limited to max_step_mm", abs(r["E"]["suggest"][0] - 0.5) < 1e-9, r["E"]["suggest"])
check("orientation hint at ~90 deg", r["F"]["orientation_hint"] and "+88" in r["F"]["orientation_hint"], r["F"]["orientation_hint"])
check("small offset -> OK", r["F"]["status"].startswith("OK"))

corr = [{"t": "2026-11-06T10:00:30", "feeder_id": "A", "dx": 0.15, "dy": 0, "residual_before": 0.30}]
before = recs("A", 20, 0.30, 0.0, t0=0)
after_good = recs("A", 8, 0.12, 0.0, t0=40)
after_bad = recs("A", 8, 0.60, 0.0, t0=40)
g = learning.analyse(before + after_good, corr)["A"]
check("only samples after the correction count", g["n"] == 8 and abs(g["mean_x"] - 0.12) < 1e-6, g["n"])
b = learning.analyse(before + after_bad, corr)["A"]
check("worse after correction -> flagged for undo", b["worse"] and "WORSE" in b["status"], b["status"])
undo = corr + [{"t": "2026-11-06T10:01:00", "feeder_id": "A", "undo_of": "2026-11-06T10:00:30"}]
undo[0] = dict(undo[0], undone=True)
u = learning.analyse(before + after_bad + recs("A", 6, 0.3, 0.0, t0=70), undo)["A"]
check("after undo: new epoch, no WORSE flag", u["n"] == 6 and not u["worse"], (u["n"], u["status"]))
print("\n%d/%d checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
