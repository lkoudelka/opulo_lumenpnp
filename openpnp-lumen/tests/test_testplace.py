#!/usr/bin/env python3
"""lib/lumen/testplace.py: mark / rotation arithmetic of the test placement (CPython)."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from lumen import orientation as o  # noqa: E402
from lumen import testplace as tp  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


print("marks and rotations")
check("board mark: CAD TL placed at 0 -> TL, at 90 -> BL, at 180 -> BR, at -90 -> TR",
      [tp.board_mark("TL", r) for r in (0, 90, 180, -90)] == ["TL", "BL", "BR", "TR"])
check("board mark with a near-90 rotation (89.6) rounds to 90", tp.board_mark("TL", 89.6) == "BL" and tp.off90(89.6) < 1)
check("cad_from_board is the inverse of board_mark", all(tp.cad_from_board(tp.board_mark(c, r), r) == c
                                                          for c in o.DOTS for r in (0, 90, 180, -90, 270)))
check("no CAD pin 1 -> no board mark", tp.board_mark(None, 0) is None)
check("turn: TL expected, BL seen -> +90; BR -> 180; TR -> -90",
      (tp.turn("BL", "TL"), tp.turn("BR", "TL"), tp.turn("TR", "TL")) == (90.0, 180.0, -90.0))

e = tp.evaluate("TL", "TL", 90.0)
check("evaluate: same corner -> CORRECT, rotation kept", e["ok"] and e["turn"] == 0 and e["new_rotation"] == 90.0, e["text"])
e = tp.evaluate("BR", "TL", 90.0)
check("evaluate: turned 180 -> WRONG, new feeder rotation -90", e["ok"] is False and e["new_rotation"] == -90.0, e["text"])
e = tp.evaluate("TL", None, 0.0)
check("evaluate: board mark missing -> asks for both marks", e["turn"] is None and "board" in e["text"], e["text"])
e = tp.evaluate("BL", "TL", None)
check("evaluate: feeder rotation unknown -> turn only", e["turn"] == 90.0 and e["new_rotation"] is None, e["text"])

print("round trip: a part sits in the feeder differently than the feeder rotation says")
ok = True
for cad in o.DOTS:
    for true_rot in (0, 90, 180, -90):
        for set_rot in (0, 90, 180, -90):
            for place_rot in (0, 90, 180, -90, 270):
                # what the camera sees: the part turned by place_rot + (true - set) (the job turns by place - set)
                seen = o.rotate_dot(cad, o.norm(place_rot + true_rot - set_rot))
                b = tp.board_mark(cad, place_rot)
                r = tp.evaluate(seen, b, float(set_rot))
                fd = tp.feeder_dot_for(cad, r["new_rotation"])
                if not (r["new_rotation"] == o.norm(true_rot) and o.rotation_needed(fd, cad) == o.norm(true_rot)
                        and (r["ok"] == (o.norm(true_rot - set_rot) == 0))):
                    ok = False
                    print("    mismatch", cad, true_rot, set_rot, place_rot, r)
check("every CAD mark x true rotation x feeder rotation x placement rotation: corrected rotation = the true one, "
      "and the stored feeder mark gives it back in Orientation Setup", ok)

print("camera proposal (golden-sample scores per turn)")
check("clear winner -> proposed", tp.propose_turn({0.0: 0.92, 90.0: 0.31, 180.0: 0.55, -90.0: 0.30})[0] == 0.0)
check("turned part -> its turn", tp.propose_turn({0.0: 0.50, 90.0: 0.31, 180.0: 0.88, -90.0: 0.30})[0] == 180.0)
check("no clear winner (symmetric body) -> none", tp.propose_turn({0.0: 0.90, 180.0: 0.86, 90.0: 0.2, -90.0: 0.2})[0] is None)
check("weak everywhere -> none", tp.propose_turn({0.0: 0.30, 180.0: 0.10})[0] is None)
check("no golden sample -> none, says how to make one", tp.propose_turn(None)[0] is None and "Placement Inspection"
      in tp.propose_turn(None)[1])

print("pick back from the board")
dx, dy, da, why = tp.pickback_correction({"found": True, "dx": 0.12, "dy": -0.05, "angle_err": 3.0})
check("body found close -> corrected by its offset and turn", (dx, dy, da) == (0.12, -0.05, 3.0), why)
check("body far away -> nominal", tp.pickback_correction({"found": True, "dx": 0.9, "dy": 0, "angle_err": 0})[:3] == (0, 0, 0))
check("body turned a lot -> offset only", tp.pickback_correction({"found": True, "dx": 0.1, "dy": 0, "angle_err": 40})[2] == 0)
check("no body -> nominal", tp.pickback_correction({"found": False})[:3] == (0, 0, 0)
      and tp.pickback_correction(None)[:3] == (0, 0, 0))
x, y, r = tp.pickback_location((10.3, 20.0, 90.0), (10.0, 20.0), 0.1, 0.0, 90.0)
check("pick-back orbits the part centre: nozzle 0.3 mm right of the part, part turned +90 -> nozzle 0.3 mm above",
      abs(x - 10.1) < 1e-9 and abs(y - 20.3) < 1e-9 and r == 180.0, (x, y, r))
x, y, r = tp.pickback_location((10.3, 20.0, 0.0), (10.0, 20.0), 0.0, 0.0, 0.0)
check("no correction -> same nozzle location", (round(x, 9), round(y, 9), r) == (10.3, 20.0, 0.0))

print("feeders and choices")
check("Photon: recycled with SkipNext", "SkipNext" in tp.recycle_text("PhotonFeeder"))
check("strip / tray: feed count - 1", "feed count - 1" in tp.recycle_text("ReferenceStripFeeder")
      and "feed count - 1" in tp.recycle_text("ReferenceTrayFeeder"))
check("unknown feeder type -> would be DISCARDED", "DISCARDED" in tp.recycle_text("SomeOtherFeeder"))
check("default placement: first one not placed yet", tp.placement_choices([("R1", True), ("R2", False), ("R3", False)]) == 1
      and tp.placement_choices([("R1", True)]) == 0)

print("%d of %d checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
