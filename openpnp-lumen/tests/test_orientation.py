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
print("\n%d/%d checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
