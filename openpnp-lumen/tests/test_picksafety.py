#!/usr/bin/env python3
"""lib/lumen/picksafety.py: learn body sizes and vacuum limits from OpenPnP's log (CPython, no OpenPnP).
Real excerpt: ~/claude/opulo/_testdata/picksafety/OpenPnP-20261126-keys.log (bench 26 Nov; skipped if missing)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lumen import picksafety as ps  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


from test_picksafety_lines import LINES as lines  # noqa: E402
r = ps.parse_log(lines, {"N1": "VAC1", "N2": "VAC2"})
n1 = r["picks"]["N1"]
check("picks per nozzle; a tip change drops the older picks of that nozzle", len(n1) == 5 and len(r["picks"]["N2"]) == 1,
      (len(n1), len(r["picks"]["N2"])))
check("part-on level = first reading after Nozzle.AfterPick; zero readings ignored",
      [p["level"] for p in n1] == [224, 225, 224, 225, 232] and all(v > 0 for p in n1 for _, v in p["curve"]))
check("bottom-vision rect assigned to the pick (via 'Align ... with N1'): empty rect -> not ok",
      [p["ok"] for p in n1] == [True, True, True, True, False])
check("good levels leave out the empty pick", sorted(ps.good_levels(n1)) == [224, 224, 225, 225])
sizes = ps.learn_sizes(r["rects"], 0.0381, lambda p: {"RES_0603-10k": "RES_0603", "CAP 2220 1kV": "CAPC_2220"}.get(p))
s = sizes["RES_0603"]
check("RES_0603 learned 1.45 x 0.80 mm from 4 good picks, 1 empty pick counted", s["ok"] and abs(s["w"] - 1.45) < 0.01
      and abs(s["h"] - 0.80) < 0.01 and s["n"] == 4 and s["empties"] == 1, s)
check("too few picks -> no proposal, says why", not sizes["CAPC_2220"]["ok"] and "only 2" in sizes["CAPC_2220"]["why"])
mixed = [{"part": "U", "w": 154, "h": 112}, {"part": "U", "w": 112, "h": 154}] * 3
check("orientation varies -> not proposed", not ps.learn_sizes(mixed, 0.04, lambda p: "PK")["PK"]["ok"])
check("part-on: high halfway between good picks and free air", ps.propose_part_on([223, 224, 228], 233.5, 215, 232)[0] == 230.0)
check("part-on: too close to free air -> none, says why", ps.propose_part_on([223, 232], 233.5, 215, 232)[0] is None)
check("part-on: free air not measured -> none", ps.propose_part_on([223], None, 215, 232)[0] is None)
part = [[(100, 252), (150, 246), (200, 241), (1100, 224)]] * 3
free_slow = [(t, 254 - 0.02 * t) for t in range(50, 1500, 25)]                    # empty nozzle stays high longer
probe, low, why = ps.propose_part_off(part, free_slow)
check("part-off: earliest probing time with >= 5 counts apart, limit halfway", probe is not None and probe <= 700 and low is not None,
      why)
same = [(t, 252 - 28 * min(1.0, t / 1100.0)) for t in range(50, 1500, 25)]
check("part-off: curves not apart -> none, says why", ps.propose_part_off([[(100, 252), (1100, 224)]] * 3, same)[0] is None)
check("free air = median after 1 s", ps.steady([(100, 250), (900, 240), (1100, 233), (1300, 234), (1400, 233)]) == 233)

print("real log excerpt (bench 26 Nov)")
X = os.path.expanduser("~/claude/opulo/_testdata/picksafety/OpenPnP-20261126-keys.log")
if os.path.isfile(X):
    rr = ps.parse_log(open(X).readlines(), {"N1": "VAC1", "N2": "VAC2"})
    g1 = ps.good_levels(rr["picks"]["N1"])
    empt = [p["level"] for p in rr["picks"]["N1"] if p["ok"] is False]
    check("N1: good picks 223..228, the empty foil picks read 231..232", g1 and min(g1) >= 223 and max(g1) <= 228
          and empt and min(empt) >= 231, (min(g1), max(g1), empt))
    hi = ps.propose_part_on(g1, 233.5, 215, 232)
    check("N1 part-on high proposal 230 (would have rejected the 232 empty picks)", hi[0] == 230.0, hi[1])
    pk = lambda p: "RES_0603" if p.startswith("RES_0603") else None
    rs = ps.learn_sizes(rr["rects"], 0.0381, pk)["RES_0603"]
    check("RES_0603 from the real log: 1.45 x 0.80, empties seen", rs["ok"] and abs(rs["w"] - 1.45) < 0.03 and abs(rs["h"] - 0.80) < 0.03
          and rs["empties"] >= 1, rs)
else:
    print("  (no %s: skipped)" % X)
print("\n%d/%d checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
