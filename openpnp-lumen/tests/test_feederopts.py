#!/usr/bin/env python3
"""lib/lumen/feederopts.py (CPython): options per feeder, defaults, legacy list, validation."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from lumen import feederopts as fo  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


A, B = "001980104648570520333535", "aabbccddeeff001122334455"
d = {}
e = fo.effective(d, A)
check("no settings: built-in defaults", e == {"watch": False, "every": 5, "confirm": True, "skip_if_part": True, "max_mm": 0.5,
                                              "pickvac": False, "threshold": None, "action": "recenter",
                                              "fallback_feed_next": False}, e)
d = {"feedwatch": {"every": 3, "confirm": False, "feeders": [A.lower()]}, "pickvac": {"enabled": True, "action": "return"}}
check("defaults from feedwatch / pickvac sections", fo.defaults(d)["every"] == 3 and fo.defaults(d)["pickvac"]
      and fo.defaults(d)["action"] == "return")
check("legacy 'feeders' list = while feeding on (any case)", fo.effective(d, A)["watch"] and not fo.effective(d, B)["watch"])
fo.set_own(d, B, "every", "1")
fo.set_own(d, B, "action", "discard")
fo.set_own(d, B, "threshold", "5")
eb, ea = fo.effective(d, B), fo.effective(d, A)
check("own values for feeder B only", eb["every"] == 1 and eb["action"] == "discard" and eb["threshold"] == 5.0
      and ea["every"] == 3 and ea["action"] == "return" and ea["threshold"] is None, (eb, ea))
check("other options of B still the defaults", eb["confirm"] is False and eb["pickvac"] is True)
check("stored under the upper-case hardware id", B.upper() in d["feeder_options"], list(d["feeder_options"]))
d["feedwatch"]["every"] = 7
check("changing a default changes feeders without own value only", fo.effective(d, A)["every"] == 7 and fo.effective(d, B)["every"] == 1)
fo.set_own(d, A, "watch", False)
check("own 'while feeding' off overrides the legacy list, list entry removed",
      not fo.effective(d, A)["watch"] and d["feedwatch"]["feeders"] == [])
fo.set_own(d, B, "threshold", "")
check("blank threshold = per tip (no own value)", fo.effective(d, B)["threshold"] is None and "threshold" not in fo.own(d, B))
fo.set_own(d, B, "watch", True)
fo.clear_own(d, B)
check("reset: own values gone, 'while feeding' tick kept", fo.own(d, B) == {"watch": True}, fo.own(d, B))
check("summary text", fo.summary(d, B) == "defaults" and "every" in fo.summary({"feeder_options": {A: {"every": 2}}}, A))
bad = []
for k, v in (("every", 0), ("every", "x"), ("max_mm", 0.01), ("max_mm", 5), ("threshold", -1), ("action", "boom"), ("nope", 1)):
    try:
        fo.validate(k, v)
    except ValueError:
        bad.append(k)
check("invalid values refused", len(bad) == 7, bad)
check("'repick' (older name) = discard", fo.validate("action", "repick") == "discard"
      and fo.effective({"pickvac": {"action": "repick"}}, A)["action"] == "discard")
fo.clear_own(d, B, keep=())
check("reset everything: feeder entry removed", B.upper() not in d.get("feeder_options", {}))
print("\n%d/%d checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
