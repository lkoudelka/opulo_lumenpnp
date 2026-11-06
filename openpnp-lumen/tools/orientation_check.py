#!/usr/bin/env python3
"""Check BEFORE the job: is pin 1 of every part of a KiCad .pos verified by the .kicad_pcb and/or
the top copper Gerber?  Same code as Scripts > Lumen > Orientation Setup (lib/lumen/orientation.py).

  orientation_check.py BOARD-top.pos [--pcb BOARD.kicad_pcb] [--gerber BOARD-F_Cu.gbr] [--all]

Exit 0 = every placement where orientation matters is verified (and the files agree);
1 = something is not verified (listed with the reason); 2 = a file is refused as a whole."""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from lumen import orientation as o  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pos")
    ap.add_argument("--pcb")
    ap.add_argument("--gerber")
    ap.add_argument("--all", action="store_true", help="list also parts where orientation does not matter")
    a = ap.parse_args()
    if not (a.pcb or a.gerber):
        ap.error("give --pcb and/or --gerber")
    pl = [p for p in o.parse_kicad_pos(a.pos) if p["side"] == "top"]
    runs = []
    if a.pcb:
        runs.append(("pcb", o.match_kicad_pcb(o.parse_kicad_pcb_list(a.pcb), pl, "kicad:" + os.path.basename(a.pcb))))
    if a.gerber:
        runs.append(("gerber", o.match_gerber(o.parse_gerber(a.gerber), pl, "gerber:" + os.path.basename(a.gerber))))
    rc = 0
    for name, r in runs:
        print("%-6s %s: %d of %d top placements verified%s" % (name, r["source"], r["verified"], r["placements"],
                                                                "" if not r["offset"] else "  (origin offset %+.3f / %+.3f mm)" % r["offset"]))
        if r["refused"]:
            print("       REFUSED: %s" % r["refused"])
            rc = 2
    print()
    print("%-8s %-42s %-8s %s" % ("ref", "footprint", "pin 1", "  ".join(n for n, _ in runs)))
    by_fp = {}
    for p in pl:
        res = [r["results"].get(p["ref"], {"ok": False, "reason": "-"}) for _, r in runs]
        dots = set(x["dot"] for x in res if x["ok"])
        matters = next((x["matters"] for x in res if x["ok"]), None)
        if matters is None:
            matters = o.orientation_matters(p["ref"], p["footprint"], None)
        if len(dots) > 1:
            verdict = "FILES DISAGREE"
        elif dots:
            verdict = dots.pop()
        else:
            verdict = "-"
        bad = matters is not False and verdict in ("-", "FILES DISAGREE")
        if bad and rc == 0:
            rc = 1
        by_fp.setdefault(p["footprint"], []).append(p["ref"])
        if a.all or matters is not False:
            cols = ["ok %s%s" % (x["dot"], " (" + x["note"] + ")" if x.get("note") else "") if x["ok"] else "NO: " + x["reason"]
                    for x in res]
            print("%-8s %-42s %-8s %s%s" % (p["ref"], p["footprint"][:42], verdict, "  |  ".join(cols),
                                            "" if matters is not False else "   (orientation not relevant)"))
    print()
    print({0: "OK: every part where orientation matters is verified",
           1: "NOT COMPLETE: confirm the listed parts by hand (Orientation Setup > Check)",
           2: "A FILE WAS REFUSED: it does not belong to this .pos (other design / revision?)"}[rc])
    return rc


if __name__ == "__main__":
    sys.exit(main())
