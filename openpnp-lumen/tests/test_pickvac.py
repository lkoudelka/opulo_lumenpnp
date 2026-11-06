#!/usr/bin/env python3
"""lib/lumen/pickvac.py decision logic (CPython): edge pick = vacuum closer to free air than usual."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from lumen import pickvac as pv  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


# N045 on the bench: free air 233-234, covered 223-224
h = []
for lv in (224, 224, 223):
    f, t, why = pv.assess(h, lv, 3.0)
    h = pv.update_history(h, lv, f, 10)
check("first 3 picks: learning, never flagged, history built", not f and "learning" in why and len(h) == 3, why)
f, t, why = pv.assess([], 230, 3.0)
check("no history: learning (no flag even for a weak pick)", not f and "learning" in why, why)
f, t, why = pv.assess(h, 225, 3.0)
check("good pick (+1 count): not flagged", not f and t == 224, why)
f, t, why = pv.assess(h, 228, 3.0)
check("edge pick (+4 counts, threshold 3): flagged", f and "edge pick" in why, why)
h2 = pv.update_history(h, 228, True, 10)
check("flagged pick does not shift the typical level", h2 == h)
h3 = pv.update_history(list(range(200, 215)), 224, False, 10)
check("history window keeps the last 10", len(h3) == 10 and h3[-1] == 224)
st = {"threshold": {"N045": 3, "N08": 7, "*": 4}}
check("threshold per tip, '*' fallback", pv.threshold_for(st, "N045") == 3 and pv.threshold_for(st, "N08") == 7
      and pv.threshold_for(st, "N24") == 4)
check("defaults: N045 3, N08 7 (30 % of the bench span)", pv.threshold_for(pv.DEFAULTS, "N045") == 3.0
      and pv.threshold_for(pv.DEFAULTS, "N08") == 7.0 and not pv.DEFAULTS["enabled"])
big = [210, 211, 210]                     # a big part seals better: its own typical level
f, t, why = pv.assess(big, 214, 3.0)
check("each feeder compared with itself (big part +4 flagged against 210)", f and t == 210, why)
print("\n%d/%d checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
