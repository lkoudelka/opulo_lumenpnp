#!/usr/bin/env python3
"""lib/lumen/orientation.py on real Opulo KiCad boards (CPython)."""
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from lumen import orientation as o  # noqa: E402

REPOS = os.path.expanduser(os.environ.get("OPULO_REPOS", "~/claude/opulo"))
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


print("rotation arithmetic")
ok = all(o.rotation_needed(o.rotate_dot(c, t), c) == o.norm(t) for c in o.DOTS for t in (0, 90, 180, 270, -90))
check("rotate_dot / rotation_needed consistent for all 4 marks x 4 rotations", ok)
check("only 4 corner marks", sorted(o.DOTS) == ["BL", "BR", "TL", "TR"])
check("TL in CAD, TR in feeder -> -90", o.rotation_needed("TR", "TL") == -90)
check("TL in CAD, BR in feeder -> 180", o.rotation_needed("BR", "TL") == 180)
check("2-pin ends -> clockwise corner (L->TL, T->TR, R->BR, B->BL)", [o.dot_from_vector(*v) for v in
      ((-1, 0), (0, 1), (1, 0), (0, -1))] == ["TL", "TR", "BR", "BL"])
check("2-pin convention consistent under rotation", all(o.rotate_dot(o.dot_from_vector(-1, 0), t) ==
      o.dot_from_vector(math.cos(math.radians(180 + t)), math.sin(math.radians(180 + t))) for t in (90, 180, -90)))
pr = o.rotate_points([("1", -1.0, 0.0), ("2", 1.0, 0.0)], 90)
check("predicted pads rotate CCW (pin 1 left -> bottom at +90)", abs(pr[0][1]) < 1e-9 and abs(pr[0][2] + 1) < 1e-9, pr)
check("status CORRECT / MISMATCH", o.status(True, "TL", True, "TR", True, -90)[1].startswith("CORRECT")
      and o.status(True, "TL", True, "TR", True, 0)[1].startswith("MISMATCH"))
check("status not confirmed / not relevant", "not confirmed" in o.status(True, "TL", True, "TR", False, 0)[1]
      and o.status(False, None, False, None, False, None)[1] == "orientation not relevant")

print("KiCad: feeder mobo (STM32F031C6 LQFP-48, MAX3078E SOIC-8, ...)")
mobo = o.parse_kicad_pcb(os.path.join(REPOS, "opulo_feeder/pcb/mobo/mobo.kicad_pcb"))
u1 = mobo.get("U1", {})
check("U1 LQFP-48: 48 pins, pin 1 top-left, matters", u1.get("pins") == 48 and u1.get("dot") == "TL" and u1.get("matters"),
      (u1.get("footprint"), u1.get("dot")))
soic = [i for i in mobo.values() if "SOIC-8" in i["footprint"]]
check("SOIC-8: pin 1 top-left", soic and all(i["dot"] == "TL" for i in soic), [(i["ref"], i["dot"]) for i in soic])
res = [i for i in mobo.values() if i["footprint"].startswith("Resistor_SMD:")]
check("resistors: orientation not relevant", res and not any(i["matters"] for i in res), len(res))

print("KiCad: all Opulo boards")
seen = {}
for root, _, files in os.walk(REPOS):
    if "/_dev" in root or "node_modules" in root:
        continue
    for fn in files:
        if fn.endswith(".kicad_pcb"):
            for ref, i in o.parse_kicad_pcb(os.path.join(root, fn)).items():
                key = i["footprint"].split(":")[-1]
                seen.setdefault(key, set()).add((i["dot"], i["matters"]))
sot = {k: v for k, v in seen.items() if k.startswith("SOT-23")}
# KiCad's library draws SOT-23 rotated vs the datasheet: pins 1+2 on the left, pin 3 right -> pin 1 top-left
check("SOT-23 family: pin 1 top-left (KiCad library orientation)", sot and all(d == {("TL", True)} for d in sot.values()), sot)
diodes = {k: v for k, v in seen.items() if k.startswith(("D_SOD", "D_SMA", "D_SMB", "LED_0"))}
check("diodes / LEDs: cathode (pad 1) left -> TL, matters", diodes and all(d == {("TL", True)} for d in diodes.values()), diodes)
caps = {k: v for k, v in seen.items() if k.startswith("C_0")}
check("ceramic caps: not relevant", caps and all(not m for d in caps.values() for _, m in d), list(caps)[:4])
print("     footprint types analysed: %d" % len(seen))

print("Gerber X2 vs KiCad (copper pins generated from the validated pad positions of ftp.kicad_pcb)")
pcb = os.path.join(REPOS, "opulo_lumenpnp/src/PCB/ftp/ftp.kicad_pcb")
kic = o.parse_kicad_pcb(pcb)
lines = ["%FSLAX46Y46*%", "%MOMM*%", "%ADD10C,0.5*%", "D10*"]
placements = {}
for ref, i in kic.items():
    if i["side"] != "top":
        continue
    fx, fy, fr = i["at"]
    placements[ref] = (fr, i["footprint"])
    a = math.radians(fr)
    for n, x, y in i["pads"]:              # footprint 0 deg frame, Y up (relative to anchor)
        pass
f = open(pcb).read()
root = o._sexpr(f)
for fp in o._kids(root, "footprint"):
    ref = o._ref(fp)
    at = o._kids(fp, "at")[0]
    fx, fy, fr = float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0
    a = math.radians(fr)
    for p in o._kids(fp, "pad"):
        if p[1] in ("",):
            continue
        pa = o._kids(p, "at")[0]
        px, py = float(pa[1]), float(pa[2])
        ax, ay = fx + px * math.cos(a) + py * math.sin(a), fy - px * math.sin(a) + py * math.cos(a)   # KiCad Y down
        lines += ["%%TO.P,%s,%s*%%" % (ref, p[1]), "X%dY%dD03*" % (round(ax * 1e6), round(-ay * 1e6)), "%TD*%"]
g = tempfile.NamedTemporaryFile("w", suffix=".gbr", delete=False)
g.write("\n".join(lines + ["M02*"]))
g.close()
gi = o.gerber_cad_info(o.parse_gerber_pins(g.name), placements)
both = [r for r in gi if r in kic and kic[r]["dot"]]
same = [r for r in both if gi[r]["dot"] == kic[r]["dot"]]
check("Gerber-derived pin-1 mark == KiCad for every part", both and len(same) == len(both), "%d/%d" % (len(same), len(both)))
real = o.parse_gerber_pins(os.path.join(REPOS, "opulo_paste-utility/test/ftp-F_Paste.gbr"))
check("real KiCad paste Gerber (no pin attributes) parses to nothing, no crash", real == {})

print("store")
st = o.Store(os.path.join(tempfile.mkdtemp(), "orientation.json"))
st.set_cad("SOT23-X", "BL", "kicad:x", True)
st.set_feeder("SOT23-X", "F1", "BR", True, 90)
st.save()
st2 = o.Store(st.path)
check("store round trip", st2.part("SOT23-X")["feeders"]["F1"]["applied"] == 90 and st2.part("SOT23-X")["cad"]["dot"] == "BL")

print("position file only (.pos): pin 1 by footprint name")
tmp = tempfile.mkdtemp()
pos = os.path.join(tmp, "b-top.pos")
open(pos, "w").write("""### Footprint positions - created on 2026-11-06T10:50:11+0100 ###
### Printed by KiCad version 9.0.0
## Unit = mm, Angle = deg.
## Side : top
# Ref     Val                   Package                                       PosX       PosY       Rot  Side
C60       4.7_uF                C_0402_1005Metric                          13.0750    92.5900  -90.0000  top
U15       STM32WBA65CIx         UFQFPN-48_STM                              18.7500    95.6300   90.0000  top
REF**     Fiducial_1mm_Mask2mm  Fiducial_1mm_Mask2mm                       12.0000   104.5000    0.0000  top
## End
""")
rows = o.parse_kicad_pos(pos)
check("KiCad 9 ASCII .pos parsed (-90 kept as -90, values with _)", [(r["ref"], r["footprint"], r["rot"]) for r in rows] ==
      [("C60", "C_0402_1005Metric", -90.0), ("U15", "UFQFPN-48_STM", 90.0), ("REF**", "Fiducial_1mm_Mask2mm", 0.0)]
      and rows[0]["value"] == "4.7_uF", rows)
csvp = os.path.join(tmp, "b-top-pos.csv")
open(csvp, "w").write('Ref,Val,Package,PosX,PosY,Rot,Side\n"U15","STM32WBA65CIx","UFQFPN-48_STM",18.75,95.63,270,top\n')
check("KiCad CSV position file parsed (270 -> -90)", [(r["ref"], r["rot"]) for r in o.parse_kicad_pos(csvp)] == [("U15", -90.0)])
check("no pad data: R/C/L not relevant, U/D/CR matter, fiducial not, unknown ?", [o.orientation_matters(r, f, None) for r, f in
      (("C60", "C_0402_1005Metric"), ("U15", "UFQFPN-48_STM"), ("CR1", "ZDO_1610_STM"), ("D1", "LED-SK6805SIDE-G-003"),
       ("REF**", "Fiducial_1mm_Mask2mm"), ("Y1", "Crystal_SMD_2016-4Pin"))] == [False, True, True, True, False, None])
check("footprint key ignores the library nickname", o.footprint_key("Package_QFP:LQFP-48_7x7mm_P0.5mm") == "LQFP-48_7x7mm_P0.5mm")

libs = [os.path.join(REPOS, "opulo_feeder/lib/kicad"), os.path.join(REPOS, "opulo_lumenpnp/lib/kicad")]
idx = o.index_libraries(libs)
qfn = o.parse_kicad_mod(idx["QFN-32-No-Paste"])
check(".kicad_mod: QFN-32 pin 1 top-left, matters", qfn["dot"] == "TL" and qfn["matters"] and qfn["pins"] >= 32, qfn["source"])
agree, dis = 0, []
for root, _, files in os.walk(REPOS):
    if "/_dev" in root or "node_modules" in root:
        continue
    for fn in files:
        if fn.endswith(".kicad_pcb"):
            for ref, i in o.parse_kicad_pcb(os.path.join(root, fn)).items():
                k = o.footprint_key(i["footprint"])
                if k in idx and i["dot"]:
                    if o.parse_kicad_mod(idx[k])["dot"] == i["dot"]:
                        agree += 1
                    else:
                        dis.append((fn, ref, k))
check("library pin 1 == placed footprint on every Opulo board that uses it", agree > 50 and not dis, "%d agree %s" % (agree, dis[:3]))
good, bad = o.learn_footprints(mobo.values())
check("learn from a board: one entry per footprint, LQFP-48 TL, no disagreement", good["LQFP-48_7x7mm_P0.5mm"]["dot"] == "TL"
      and not bad and len(good) >= 10, len(good))
bad_in = [dict(mobo["U1"]), dict(mobo["U1"])]
bad_in[1]["dot"] = "TR"
check("learn: refs of one footprint disagreeing are reported, not learned", o.learn_footprints(bad_in) == ({}, {"LQFP-48_7x7mm_P0.5mm": ["TL", "TR"]}))

lib_i = {"dot": "TL", "source": "lib:x.kicad_mod", "pins": 48, "pads": []}
pkg_i = {"dot": "TL", "source": "openpnp-package", "pins": 48, "pads": []}
r = o.resolve_footprint("X", None, None, lib_i)
check("resolve: library only -> auto (not confirmed)", r["dot"] == "TL" and not r["confirmed"] and r["source"].startswith("lib:"))
r = o.resolve_footprint("X", {"dot": "TL", "source": "manual", "confirmed": True}, pkg_i, lib_i)
check("resolve: confirmed table entry first, agreeing sources -> no conflict", r["confirmed"] and r["source"] == "table:manual" and not r["conflict"])
r = o.resolve_footprint("X", {"dot": "BL", "source": "manual", "confirmed": True}, None, lib_i)
check("resolve: confirmed BL vs library TL -> conflict shown", r["dot"] == "BL" and r["conflict"] == ["TL (lib:x.kicad_mod)"], r)
check("resolve: nothing known -> None", o.resolve_footprint("X") is None)
pk = o.package_cad_info("SOT-23", [("1", -0.95, 1.1), ("2", 0.95, 1.1), ("3", 0.0, -1.1)])
check("OpenPnP package footprint (Y up): SOT-23 pin 1 top-left", pk["dot"] == "TL")
check("OpenPnP package footprint without pad names -> None", o.package_cad_info("X", [("", 0, 0), ("", 1, 0)]) is None)
st = o.Store(os.path.join(tmp, "o.json"))
st.set_footprint("Package_QFP:LQFP-48", {"dot": "TL", "pins": 48}, "manual", True)
c = st.set_footprint("LQFP-48", {"dot": "TR", "pins": 48}, "kicad:other.kicad_pcb", False)
check("store: confirmed footprint not overwritten by an automatic TR, conflict returned",
      c == "TR" and st.data["footprints"]["LQFP-48"]["dot"] == "TL" and st.data["footprints"]["LQFP-48"]["confirmed"])
st.save()
check("store: footprint table persists", o.Store(st.path).data["footprints"]["LQFP-48"]["source"] == "manual")

check("same_pattern: identical within 0.03 mm across a rounding boundary / different pins / moved pad",
      o.same_pattern([("1", 0.0249, 0), ("2", 1, 0)], [("1", 0.0251, 0), ("2", 1, 0)])
      and not o.same_pattern([("1", 0, 0), ("2", 1, 0)], [("2", 0, 0), ("1", 1, 0)])
      and not o.same_pattern([("1", 0, 0), ("2", 1, 0)], [("1", 0, 0), ("2", 1.1, 0)]))
print("pin-1 corner rule (per-axis, refuses ambiguous)")
hdr = [(str(i + 1), (i % 2) * 2.54, -(i // 2) * 2.54) for i in range(10)]          # 2x5 header, pin 1 top-left
check("2x5 pin header: TL (the corner a person sees)", o.classify_pin1(hdr)[0] == "TL", o.classify_pin1(hdr))
check("1x3 row: pin 1 at the left end -> TL", o.classify_pin1([("1", -2, 0), ("2", 0, 0), ("3", 2, 0)])[0] == "TL")
amb = [("1", -1.0, 1.0), ("2", 1.0, 1.0), ("MP", -3.0, -1.0), ("MP", 3.0, -1.0)]       # row inside wider mounting pads
check("connector with mounting pads wider than the row: refused (ambiguous)", o.classify_pin1(amb)[0] is None
      and "ambiguous" in o.classify_pin1(amb)[1], o.classify_pin1(amb))
check("no pad 1: refused", o.classify_pin1([("A", 0, 0), ("K", 1, 0)]) == (None, "no pad named 1"))
check("BGA: A1 is pin 1", o.classify_pin1([("A1", -1, 1), ("A2", 1, 1), ("B1", -1, -1), ("B2", 1, -1)])[0] == "TL")

REAL = os.path.expanduser(os.environ.get("ORIENTATION_REAL_DATA", "~/claude/opulo/_testdata/wba65-panel"))
if os.path.exists(os.path.join(REAL, "Panel.kicad_pcb")):
    print("real KiCad 9.0.0 files (%s)" % REAL)
    fps = o.parse_kicad_pcb_list(os.path.join(REAL, "Panel.kicad_pcb"))
    g = o.parse_gerber(os.path.join(REAL, "Panel-top_copper.gbr"))
    check("copper Gerber: KiCad X2, top copper, pin attributes", o.gerber_check(g) is None and g["software"].startswith("KiCad"),
          (g["software"], g["function"]))
    check("silkscreen Gerber refused (no pin data)", "not a copper layer" in o.gerber_check(o.parse_gerber(
        os.path.join(REAL, "Panel-F_Silkscreen.gbr"))))
    inst, bad, copies = o.gerber_instances(g["pads"])
    check("21-up panel Gerber: 21 copies of every reference, split safely", copies == 21 and all(len(v) == 21 for v in inst.values())
          and len(inst) >= 37, (copies, len(inst)))
    check("tall connector J1 (copies 2.3 mm apart, pads 2.5 mm): refused, not guessed", list(bad) == ["J1"], bad)
    # placements of ONE copy of the board, taken from the .kicad_pcb (= what its .pos says), matched onto Gerber copies
    def bp(i):
        a = math.radians(i["at"][2])
        return [(n, i["at"][0] + x * math.cos(a) - y * math.sin(a), i["at"][1] + x * math.sin(a) + y * math.cos(a)) for n, x, y in i["pads"]]
    def bbc(pts):
        xs = [q[1] for q in pts]
        ys = [q[2] for q in pts]
        return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    tops = [i for i in fps if i["side"] == "top" and i["pins"] >= 2]
    votes = {}
    for i in tops:
        ci = bbc(bp(i))
        for ref, lst in inst.items():
            for c in lst:
                if len(set(q[0] for q in c["pads"])) == i["pins"]:
                    k = (round(c["center"][0] - ci[0], 1), round(c["center"][1] - ci[1], 1))
                    votes[k] = votes.get(k, 0) + 1
    T = max(sorted(votes), key=lambda k: votes[k])
    pl, truth = [], {}
    for i in tops:
        ci = bbc(bp(i))
        want = sorted((n, len([1 for q in i["pads"] if q[0] == n])) for n in set(q[0] for q in i["pads"]))
        hit = [r for r, lst in inst.items() for c in lst if math.hypot(c["center"][0] - ci[0] - T[0], c["center"][1] - ci[1] - T[1]) < 0.15
               and sorted((n, len([1 for q in c["pads"] if q[0] == n])) for n in set(q[0] for q in c["pads"])) == want]
        if len(hit) == 1 and hit[0] not in truth:
            pl.append({"ref": hit[0], "x": i["at"][0] + T[0] + 5.0, "y": i["at"][1] + T[1] - 7.0, "rot": i["at"][2], "side": "top",
                       "footprint": o.footprint_key(i["footprint"])})
            truth[hit[0]] = i
    r = o.match_gerber(g, pl)
    okr = [ref for ref in truth if r["results"][ref]["ok"]]
    same = [ref for ref in okr if r["results"][ref]["dot"] == truth[ref]["dot"]]
    check("Gerber pin 1 == .kicad_pcb pin 1 for every verified part (one board copy)", len(okr) >= 30 and same == okr,
          "%d/%d verified, %d agree" % (len(okr), len(pl), len(same)))
    custom = sorted(set(o.footprint_key(truth[ref]["footprint"]) for ref in same if "_STM" in truth[ref]["footprint"]))
    check("... including the custom ST footprints", len(custom) >= 4, custom)
    t2 = [dict(p) for p in pl]
    c0402 = [p for p in t2 if p["footprint"] == "C_0402_1005Metric"]
    c0402[0]["rot"] = o.norm(c0402[0]["rot"] + 90)
    r2 = o.match_gerber(g, t2)
    check("Gerber: one capacitor with a wrong rotation in the job is flagged (pads differ)", not r2["results"][c0402[0]["ref"]]["ok"]
          and "pads differ" in r2["results"][c0402[0]["ref"]]["reason"], r2["results"][c0402[0]["ref"]])
    plp = [{"ref": i["ref"], "x": i["at"][0] - 83.5, "y": i["at"][1] + 138.0, "rot": i["at"][2], "side": "top",
            "footprint": o.footprint_key(i["footprint"])} for i in fps if i["side"] == "top" and i["ref"] and "*" not in i["ref"]]
    r3 = o.match_kicad_pcb(fps, plp)
    check(".kicad_pcb: all 108 placements verified at one origin offset", r3["verified"] == len(plp) == 108, (r3["verified"], len(plp)))
    t3 = [dict(p) for p in plp]
    t3[0]["rot"] = o.norm(t3[0]["rot"] + 180)
    t3[1]["x"] += 0.02
    r4 = o.match_kicad_pcb(fps, t3)
    check(".kicad_pcb: rotation off by 180 / position off by 0.02 mm -> that placement refused", not r4["results"][t3[0]["ref"]]["ok"]
          and not r4["results"][t3[1]["ref"]]["ok"] and r4["verified"] == 106, (r4["results"][t3[0]["ref"]], r4["results"][t3[1]["ref"]]))
    pos = o.parse_kicad_pos(os.path.join(REAL, "Panel-top.pos"))
    check("real 7-up .pos (other revision): .kicad_pcb and Gerber refused as a whole", o.match_kicad_pcb(fps, pos)["refused"]
          and o.match_gerber(g, pos)["refused"])

    print("inputs: which file is usable, and the reason when not (Load CAD data / tools/orientation_check.py)")
    import shutil
    import subprocess
    import tempfile
    import zipfile
    W = tempfile.mkdtemp(prefix="ori-in-")
    cu = open(os.path.join(REAL, "Panel-top_copper.gbr")).read()

    def write(name, text):
        p = os.path.join(W, name)
        if not os.path.isdir(os.path.dirname(p)):
            os.makedirs(os.path.dirname(p))
        f = open(p, "w")
        f.write(text)
        f.close()
        return p
    x1 = "\n".join(ln for ln in cu.split("\n") if not ln.startswith(("%TF", "%TO", "%TA", "%TD")))
    why = o.gerber_check(o.parse_gerber(write("old/board-F_Cu.gbr", x1)))
    check("old Gerber without X2 (RS-274X / X1): refused, says how to export X2", why and "without X2" in why and "netlist" in why, why)
    nonet = "\n".join(ln for ln in cu.split("\n") if not ln.startswith(("%TO", "%TD")))
    why = o.gerber_check(o.parse_gerber(write("nonet/b-F_Cu.gbr", nonet)))
    check("X2 copper without netlist attributes: refused, says 'Include netlist attributes'",
          why and "Include netlist attributes" in why, why)
    bot = cu.replace("%TF.FileFunction,Copper,L1,Top*%", "%TF.FileFunction,Copper,L2,Bot*%")
    why = o.gerber_check(o.parse_gerber(write("bot/b-B_Cu.gbr", bot)))
    check("bottom copper: refused (use F.Cu)", why and "not the TOP" in why, why)
    gdir = os.path.join(W, "gerbers")
    os.makedirs(gdir)
    shutil.copy(os.path.join(REAL, "Panel-top_copper.gbr"), os.path.join(gdir, "Panel-F_Cu.gbr"))
    shutil.copy(os.path.join(REAL, "Panel-F_Silkscreen.gbr"), os.path.join(gdir, "Panel-F_Silkscreen.gbr"))
    write("gerbers/Panel-PTH.drl", "M48\nMETRIC\nT1C0.3\n%\nM30\n")
    r = o.classify_input(gdir)
    check("folder with all Gerbers: the top copper X2 is picked", r["kind"] == "gerber" and r["path"].endswith("Panel-F_Cu.gbr"), r)
    zp = os.path.join(W, "fab.zip")
    z = zipfile.ZipFile(zp, "w")
    for fn in os.listdir(gdir):
        z.write(os.path.join(gdir, fn), "fab/" + fn)
    z.close()
    r = o.classify_input(zp, os.path.join(W, "unz"))
    check(".zip from the fab export: unpacked, top copper picked", r["kind"] == "gerber" and r["path"].endswith("Panel-F_Cu.gbr")
          and os.path.isfile(r["path"]), r)
    r = o.classify_input(os.path.join(W, "old"))
    check("folder with only an old (non-X2) top copper: refused, says how to export", r["kind"] is None and "no X2" in r["error"], r)
    shutil.copy(os.path.join(REAL, "Panel-top_copper.gbr"), os.path.join(gdir, "Other-F_Cu.gbr"))
    r = o.classify_input(gdir)
    check("two top copper Gerbers in a folder: refused, asks to choose", r["kind"] is None and "choose" in r["error"], r)
    r = o.classify_input(os.path.join(gdir, "Panel-PTH.drl"))
    check("drill file: refused", r["kind"] is None and "drill" in r["error"], r)
    r = o.classify_input(os.path.join(REAL, "Panel-top.pos"))
    check(".pos: refused ('that is the job itself')", r["kind"] is None and "job itself" in r["error"], r)
    r = o.classify_input(os.path.join(REAL, "Panel-F_Silkscreen.gbr"))
    check("silkscreen Gerber is read as a Gerber and then refused on load (not copper)", r["kind"] == "gerber")
    # a footprint library as KiCad's 'Export footprints to new library' would make it (.pretty from the board)
    lib = os.path.join(W, "board.pretty")
    os.makedirs(lib)
    for i in fps:
        k = o.footprint_key(i["footprint"])
        if i["side"] == "top" and k and not os.path.exists(os.path.join(lib, k + ".kicad_mod")):
            write("board.pretty/%s.kicad_mod" % k, '(footprint "%s"\n%s)\n' % (k, "\n".join(
                '  (pad "%s" smd rect (at %.4f %.4f) (size 0.5 0.5) (layers "F.Cu"))' % (n, x, -y) for n, x, y in i["pads"])))
    r = o.classify_input(lib)
    check(".pretty folder: library", r["kind"] == "library" and "footprints" in r["note"], r)
    TOOL = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "orientation_check.py"),
            os.path.join(REAL, "Panel-top.pos")]

    def tool(*args):
        pr = subprocess.run(TOOL + list(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        return pr.returncode, pr.stdout
    rc, out = tool()
    check("checker, nothing given: exit 2 'no usable input'", rc == 2 and "NO USABLE INPUT" in out, rc)
    rc, out = tool("--cad", os.path.join(REAL, "Panel.kicad_pcb"))
    check("checker, board file of another revision: refused for positions, all 42 relevant parts by footprint name (exit 3)",
          rc == 3 and "REFUSED" in out and "OK, 42 placement(s) only by footprint name" in out, out.strip().split("\n")[-1])
    rc, out = tool("--cad", os.path.join(REAL, "Panel-top_copper.gbr"))
    check("checker, Gerber of another revision: NOT DETECTED with the reason per part (exit 1)",
          rc == 1 and "NOT DETECTED: Gerber does not match" in out and "NOT COMPLETE" in out, rc)
    rc, out = tool("--cad", os.path.join(REAL, "Panel-F_Silkscreen.gbr"))
    check("checker, silkscreen: every part says 'not a copper layer'", rc == 1 and "NOT DETECTED: not a copper layer" in out, rc)
    rc, out = tool("--cad", lib)
    check("checker, only a footprint library (.pretty): pin 1 by name for all relevant parts (exit 3)",
          rc == 3 and "OK, 42 placement(s)" in out and "name:lib:" in out, out.strip().split("\n")[-1])
    one = [i for i in fps if i["side"] == "top" and i["ref"] and "*" not in i["ref"]]
    write("one.pos", "# Ref Val Package PosX PosY Rot Side\n" + "\n".join("%s v %s %.4f %.4f %.4f top" % (
        i["ref"], o.footprint_key(i["footprint"]), i["at"][0], i["at"][1], i["at"][2]) for i in one) + "\n")
    pr = subprocess.run(TOOL[:2] + [os.path.join(W, "one.pos"), "--cad", os.path.join(REAL, "Panel.kicad_pcb")],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    check("checker, .pos and board of the same revision: verified from the board file (exit 0)",
          pr.returncode == 0 and "108 of 108" in pr.stdout, pr.stdout.strip().split("\n")[-1])
    shutil.rmtree(W)
else:
    print("(real KiCad data not in %s: skipped)" % REAL)
print("\n%d/%d checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
