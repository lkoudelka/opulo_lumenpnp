#!/usr/bin/env python3
"""Check BEFORE the job: can pin 1 of every part of a KiCad .pos be detected, and from what?
Same code as Scripts > Lumen > Orientation Setup (lib/lumen/orientation.py).

  orientation_check.py BOARD-top.pos [--cad FILE_OR_FOLDER_OR_ZIP ...] [--pcb B.kicad_pcb] [--gerber B-F_Cu.gbr]
                       [--lib FOOTPRINTS_DIR ...] [--all]

--cad takes anything (board, Gerber, folder / zip of Gerbers, KiCad project folder, .pretty folder) and says what
it found.  One input is enough.  Pin 1 comes from, in this order:
  1. a board file / top copper Gerber X2 verified against the .pos (reference, footprint, rotation, position);
  2. by footprint NAME: footprints of every loaded board file (also another revision), verified Gerber
     parts, footprint libraries (--lib, KiCad's standard library if installed).

Exit 0 = every part where orientation matters is detected from verified files; 3 = all detected, some only by
footprint name (confirm those once in Orientation Setup); 1 = some NOT detected or the files disagree (listed
with the reason); 2 = no usable input at all."""
import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from lumen import orientation as o  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pos")
    ap.add_argument("--cad", action="append", default=[], help="board / Gerber / folder / zip / library: detected automatically")
    ap.add_argument("--pcb", action="append", default=[])
    ap.add_argument("--gerber", action="append", default=[])
    ap.add_argument("--lib", action="append", default=[], help="folder with KiCad footprints (.pretty)")
    ap.add_argument("--all", action="store_true", help="list also parts where orientation does not matter")
    a = ap.parse_args(argv)
    pl = [p for p in o.parse_kicad_pos(a.pos) if p["side"] == "top"]
    inputs = [("kicad", p) for p in a.pcb] + [("gerber", p) for p in a.gerber]
    libs = list(a.lib)
    tmp = tempfile.mkdtemp(prefix="orientation-")
    for c in a.cad:
        r = o.classify_input(os.path.abspath(c), tmp)
        if not r.get("kind"):
            print("NOT LOADED %s: %s" % (c, r["error"]))
            continue
        print("loaded     %s: %s (%s)" % (c, r["kind"], r.get("note", "")))
        if r["kind"] == "library":
            libs.append(r["path"])
        else:
            inputs.append((r["kind"], r["path"]))
    runs, learned = [], []
    for kind, path in inputs:
        src = "%s:%s" % (kind, os.path.basename(path))
        try:
            if kind == "kicad":
                fps = o.parse_kicad_pcb_list(path)
                res = o.match_kicad_pcb(fps, pl, src)
                learned += [i for i in fps if i["side"] == "top"]           # footprint-local pads: right in any revision
            else:
                res = o.match_gerber(o.parse_gerber(path), pl, src)
                learned += [dict(r, ref=ref, side="top", footprint=r.get("footprint", ""), source=src)
                            for ref, r in res["results"].items() if r["ok"]]
        except Exception as e:                                             # unreadable file
            res = {"results": {}, "verified": 0, "placements": len(pl), "source": src, "offset": None,
                   "refused": "cannot read: %s" % e}
        runs.append(res)
        print("%-30s %d of %d top placements verified%s" % (res["source"], res["verified"], res["placements"],
                                                           "" if not res["offset"] else "  (origin offset %+.3f / %+.3f mm)" % res["offset"]))
        if res["refused"]:
            print("%-30s REFUSED for the positions: %s" % ("", res["refused"]))
    table, disagree = o.learn_footprints(learned)
    lib_dirs = o.library_dirs(libs)
    idx = o.index_libraries(lib_dirs)
    for d in lib_dirs:
        print("%-30s footprint library" % d)
    if table:
        print("%-30s pin 1 by footprint name known for %d footprint(s) from the loaded files" % ("", len(table)))
    if not runs and not idx:
        print("\nNO USABLE INPUT: give --cad (board, top copper Gerber X2, folder / zip) or --lib")
        return 2
    print()
    print("%-8s %-40s %-6s %s" % ("ref", "footprint", "pin 1", "from"))
    lib_cache = {}
    n_name = n_miss = 0
    for p in pl:
        key = o.footprint_key(p["footprint"])
        res = [r["results"].get(p["ref"]) for r in runs if r["results"].get(p["ref"])]
        good = [(x["dot"], x["source"]) for x in res if x["ok"]]
        dots = set(d for d, _ in good)
        info, how = None, ""
        if len(dots) == 1:
            verdict, how = dots.pop(), ", ".join(s for _, s in good)
            info = next(x for x in res if x["ok"])
        elif len(dots) > 1:
            verdict, how = "DISAGREE", "; ".join("%s says %s" % (s, d) for d, s in good)
        else:
            li = None
            if key in idx:
                if idx[key] not in lib_cache:
                    try:
                        lib_cache[idx[key]] = o.parse_kicad_mod(idx[key])
                    except Exception:
                        lib_cache[idx[key]] = None
                li = lib_cache[idx[key]]
            cands = [(t["dot"], "name:" + t["source"]) for t in [table.get(key)] if t and t.get("dot")]
            cands += [(li["dot"], "name:" + li["source"]) for _ in [0] if li and li.get("dot")]
            cdots = set(d for d, _ in cands)
            if len(cdots) == 1:
                verdict, how = cdots.pop(), ", ".join(s for _, s in cands) + "  (by footprint name: confirm once)"
                info = table.get(key) or li
            elif len(cdots) > 1:
                verdict, how = "DISAGREE", "; ".join("%s says %s" % (s, d) for d, s in cands)
            else:
                verdict = "-"
                why = [x["reason"] for x in res if not x["ok"]] + [r["refused"] for r in runs if r["refused"]][:1]
                if key in disagree:
                    why.append("the loaded board has %s with different pin 1 (%s)" % (key, ", ".join(disagree[key])))
                if li is not None and not li.get("dot"):
                    why.append("library footprint: %s" % (li.get("note") or "pin 1 unknown"))
                if not why or all("does not match" in w for w in why):
                    why.append("footprint %s not in the loaded files / libraries" % key)
                how = "NOT DETECTED: " + "; ".join(dict.fromkeys(why))
        matters = info.get("matters") if info and "by footprint name" not in how else None   # by name: decide with THIS ref
        if matters is None:
            matters = o.orientation_matters(p["ref"], key, info.get("pins") if info else None)
        if matters is not False:
            if verdict in ("-", "DISAGREE"):
                n_miss += 1
            elif "by footprint name" in how:
                n_name += 1
        if a.all or matters is not False:
            print("%-8s %-40s %-6s %s%s" % (p["ref"], key[:40], verdict, how, "" if matters is not False else "   (orientation not relevant)"))
    print()
    if n_miss:
        print("NOT COMPLETE: pin 1 not detected for %d placement(s) where orientation matters - load what the reason says, "
              "or set pin 1 by hand (Orientation Setup > Check)" % n_miss)
        return 1
    if n_name:
        print("OK, %d placement(s) only by footprint name: confirm those once in Orientation Setup > Check" % n_name)
        return 3
    print("OK: every part where orientation matters is detected from verified files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
