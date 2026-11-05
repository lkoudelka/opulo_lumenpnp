# -*- coding: utf-8 -*-
"""Part orientation for setup: pin-1 / polarity mark position and the rotation in the feeder.

Pure Python (CPython 3 and Jython 2.7).

A "dot" is where pin 1 is on the part body, seen from above, as one of the 4 corners
TL TR BR BL - one per possible rotation (0 / 90 / 180 / 270).  For 2-terminal polarized
parts pin 1 is at an END; the convention is the corner at the pin-1 end on its clockwise
side (pin 1 left -> TL, top -> TR, right -> BR, bottom -> BL), which rotates consistently.

- CAD dot: pin 1 in the footprint's own 0 deg orientation, detected from a KiCad
  .kicad_pcb (pad "1" position) or from KiCad copper Gerbers with X2 attributes (%TO.P%).
- Feeder dot: pin 1 as the part sits in the feeder, seen from above in machine
  coordinates (X to the right, Y up, as in OpenPnP's camera view).
- Rotation in feeder = angle(feeder dot) - angle(CAD dot): the value OpenPnP needs as the
  feeder's pick rotation.

KiCad conventions (validated against KiCad's own paste Gerber of a real board): pad
positions are footprint-local with Y pointing down; footprint rotation is CCW in the
Y-up view, the same as OpenPnP's placement rotation.
"""
from __future__ import absolute_import, division, print_function

import json
import math
import os
import re
import time

DOTS = {"TR": 45, "TL": 135, "BL": -135, "BR": -45}
CORNERS = ("TL", "TR", "BR", "BL")
EDGE_TO_CORNER = {"L": "TL", "T": "TR", "R": "BR", "B": "BL"}      # clockwise side of the pin-1 end


def norm(a):
    a = (a + 180.0) % 360.0 - 180.0
    return 180.0 if a == -180.0 else a


def dot_from_vector(vx, vy):
    """Corner for a pin-1 vector (Y up).  A vector pointing at an edge (2-terminal parts)
    gives the corner on the clockwise side of that end."""
    if abs(vx) < 1e-9 and abs(vy) < 1e-9:
        return None
    m = max(abs(vx), abs(vy))
    if abs(vx) < 0.35 * m:
        return EDGE_TO_CORNER["T" if vy > 0 else "B"]
    if abs(vy) < 0.35 * m:
        return EDGE_TO_CORNER["R" if vx > 0 else "L"]
    return ("T" if vy > 0 else "B") + ("R" if vx > 0 else "L")


def rotate_dot(dot, deg):
    """The dot after rotating the part by deg (multiple of 90) CCW."""
    a = math.radians(DOTS[dot] + deg)
    return dot_from_vector(math.cos(a), math.sin(a))


def rotation_needed(feeder_dot, cad_dot):
    """Rotation in feeder (0, 90, 180 or -90 deg) or None if a mark is missing."""
    if feeder_dot not in DOTS or cad_dot not in DOTS:
        return None
    return norm(DOTS[feeder_dot] - DOTS[cad_dot])


def rotate_points(pads, deg):
    """[(n, x, y)] rotated CCW by deg (for drawing the predicted part in the feeder)."""
    a = math.radians(deg)
    c, s_ = math.cos(a), math.sin(a)
    return [(n, x * c - y * s_, x * s_ + y * c) for n, x, y in pads]


POLARIZED_2PIN = re.compile(r"(^|[:_])(D|LED|CP|C_?Elec|CP_Elec|Tantalum|Diode|SOD|SMA|SMB|SMC|MELF|Polarized)",
                            re.I)
NONPOLAR_REF = re.compile(r"^(R|C|L|FB|F|RN|JP|TP|FID|H|MH|SW|NT)\d", re.I)


def orientation_matters(ref, footprint, n_pins):
    """True / False (best guess, the user can override)."""
    if n_pins >= 3:
        return True
    if n_pins <= 1:
        return False
    if re.match(r"^(D|LED|CR|VD)\d", ref or "", re.I):
        return True
    if NONPOLAR_REF.match(ref or "") and not re.search(r"Elec|Tantal|CP_|Polar", footprint or "", re.I):
        return False
    return bool(POLARIZED_2PIN.search(footprint or ""))


def pin1_hint(footprint, ref):
    """What pin 1 looks like on the real part (KiCad pad 1 conventions)."""
    fp = (footprint or "").lower()
    r = (ref or "").upper()
    end = " Use the corner clockwise of that end (left end -> top-left)"
    if "elec" in fp or "cp_" in fp or r.startswith("CP"):
        return "electrolytic: pin 1 = PLUS terminal (the stripe / dark sector marks MINUS, the other end)." + end
    if "tantal" in fp:
        return "tantalum: pin 1 = PLUS terminal = the end with the bar." + end
    if "led" in fp or r.startswith("LED"):
        return "LED: pin 1 = cathode (green mark / T on the bottom, notch)." + end
    if fp.split(":")[-1].startswith(("d_", "diode")) or r.startswith("D"):
        return "diode: pin 1 = cathode = the end with the bar." + end
    return "pin 1 = dot / notch / chamfered corner on the body."


# ---------------------------------------------------------------------------------------
# KiCad .kicad_pcb (KiCad 6 .. 9 s-expression format)
# ---------------------------------------------------------------------------------------
_TOK = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+')


def _sexpr(text):
    toks = _TOK.findall(text)
    stack, cur = [], []
    for t in toks:
        if t == "(":
            stack.append(cur)
            cur = []
        elif t == ")":
            done, cur = cur, stack.pop()
            cur.append(done)
        else:
            cur.append(t[1:-1].replace('\\"', '"') if t.startswith('"') else t)
    return cur[0]


def _kids(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def _ref(fp):
    for p in _kids(fp, "property"):                     # KiCad 8/9
        if len(p) > 2 and p[1] == "Reference":
            return p[2]
    for t in _kids(fp, "fp_text"):                      # KiCad 6/7
        if len(t) > 2 and t[1] == "reference":
            return t[2]
    return None


def cad_info(footprint, ref, pads_local):
    """pads_local: [(number, x, y)] in the footprint 0 deg frame, Y up."""
    numbered = [(n, x, y) for n, x, y in pads_local if n not in ("", None)]
    pins = sorted(set(n for n, _, _ in numbered))
    info = {"ref": ref, "footprint": footprint, "pins": len(pins), "pads": [[n, round(x, 4), round(y, 4)] for n, x, y in numbered],
            "dot": None, "matters": orientation_matters(ref, footprint, len(pins))}
    if numbered:
        cx = sum(x for _, x, _ in numbered) / len(numbered)
        cy = sum(y for _, _, y in numbered) / len(numbered)
        p1 = [(x, y) for n, x, y in numbered if n == "1"]
        if p1 and len(pins) >= 2:
            x1 = sum(x for x, _ in p1) / len(p1)
            y1 = sum(y for _, y in p1) / len(p1)
            info["dot"] = dot_from_vector(x1 - cx, y1 - cy)
            info["pin1"] = [round(x1 - cx, 4), round(y1 - cy, 4)]
    return info


def parse_kicad_pcb(path):
    """{ref: info} for top-side footprints; info['side'] marks bottom ones."""
    f = open(path)
    try:
        root = _sexpr(f.read())
    finally:
        f.close()
    out = {}
    for fp in _kids(root, "footprint") + _kids(root, "module"):
        ref = _ref(fp)
        if not ref:
            continue
        layer = (_kids(fp, "layer") or [[None, "F.Cu"]])[0][1]
        at = (_kids(fp, "at") or [["at", "0", "0"]])[0]
        pads = []
        for p in _kids(fp, "pad"):
            if len(p) < 3 or p[2] in ("np_thru_hole",):
                continue
            pat = (_kids(p, "at") or [["at", "0", "0"]])[0]
            pads.append((p[1], float(pat[1]), -float(pat[2])))     # KiCad Y down -> Y up
        info = cad_info(fp[1], ref, pads)
        info["side"] = "bottom" if layer.startswith("B.") else "top"
        info["at"] = [float(at[1]), -float(at[2]), float(at[3]) if len(at) > 3 else 0.0]
        info["source"] = "kicad:" + os.path.basename(path)
        out[ref] = info
    return out


# ---------------------------------------------------------------------------------------
# Gerber X2 (copper layers exported by KiCad with netlist attributes: %TO.P,<ref>,<pin>*%)
# ---------------------------------------------------------------------------------------
def parse_gerber_pins(path):
    """{ref: {pin: [(x, y)...]}} in board coordinates (mm, Y up) from %TO.P% attributes."""
    f = open(path)
    try:
        text = f.read()
    finally:
        f.close()
    m = re.search(r"%FSLAX(\d)(\d)Y(\d)(\d)\*%", text)
    dec = int(m.group(2)) if m else 6
    scale = 25.4 if "%MOIN*%" in text else 1.0
    pins = {}
    cur = None
    x = y = 0.0
    region = None
    for blk in re.findall(r"%[^%]*%|[^%*]+\*", text):
        b = blk.strip()
        if b.startswith("%TO.P,"):
            parts = b[6:-2].split(",")
            cur = (parts[0], parts[1]) if len(parts) >= 2 else None
            continue
        if b.startswith("%TD"):
            if b in ("%TD*%", "%TD.P*%"):
                cur = None
            continue
        if b.startswith("%"):
            continue
        if b.startswith("G36"):
            region = []
            continue
        if b.startswith("G37"):
            if cur and region:
                rx = sum(p[0] for p in region) / len(region)
                ry = sum(p[1] for p in region) / len(region)
                pins.setdefault(cur[0], {}).setdefault(cur[1], []).append((rx, ry))
            region = None
            continue
        mx = re.search(r"X(-?\d+)", b)
        my = re.search(r"Y(-?\d+)", b)
        if mx:
            x = int(mx.group(1)) / 10.0 ** dec * scale
        if my:
            y = int(my.group(1)) / 10.0 ** dec * scale
        if region is not None and (mx or my):
            region.append((x, y))
        if "D03" in b and cur:
            pins.setdefault(cur[0], {}).setdefault(cur[1], []).append((x, y))
    return pins


def gerber_cad_info(pins_by_ref, placements):
    """CAD info from Gerber pins + OpenPnP placements {ref: (rotation_deg, footprint_name)}:
    the pin-1 vector is taken relative to the centre of all pads of the part and rotated
    back by the placement rotation into the footprint 0 deg frame."""
    out = {}
    for ref, pins in pins_by_ref.items():
        rot, fpname = placements.get(ref, (None, ""))
        if rot is None:
            continue
        a = math.radians(-rot)
        local = []
        for n, pts in pins.items():
            for (x, y) in pts:
                local.append((n, x, y))
        if not local:
            continue
        cx = sum(x for _, x, _ in local) / len(local)
        cy = sum(y for _, _, y in local) / len(local)
        rl = [(n, (x - cx) * math.cos(a) - (y - cy) * math.sin(a), (x - cx) * math.sin(a) + (y - cy) * math.cos(a))
              for n, x, y in local]
        info = cad_info(fpname, ref, rl)
        info["side"] = "top"
        info["source"] = "gerber"
        out[ref] = info
    return out


# ---------------------------------------------------------------------------------------
# Confirmation store  (~/.openpnp2/lumen/orientation.json)
# ---------------------------------------------------------------------------------------
class Store(object):
    def __init__(self, path):
        self.path = path
        try:
            f = open(path)
            self.data = json.load(f)
            f.close()
        except (IOError, OSError, ValueError):
            self.data = {}
        self.data.setdefault("parts", {})
        self.data.setdefault("sources", [])

    def part(self, pid):
        return self.data["parts"].setdefault(pid, {"cad": {}, "feeders": {}, "matters": None})

    def set_cad(self, pid, dot, source, confirmed):
        self.part(pid)["cad"] = {"dot": dot, "source": source, "confirmed": bool(confirmed),
                                 "t": time.strftime("%Y-%m-%dT%H:%M:%S")}

    def set_feeder(self, pid, feeder_id, dot, confirmed, rotation_applied=None):
        rec = {"dot": dot, "confirmed": bool(confirmed), "t": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if rotation_applied is not None:
            rec["applied"] = rotation_applied
        self.part(pid)["feeders"][feeder_id] = rec

    def save(self):
        d = os.path.dirname(self.path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        tmp = self.path + ".tmp"
        f = open(tmp, "w")
        json.dump(self.data, f, indent=1, sort_keys=True)
        f.close()
        os.rename(tmp, self.path)


def status(matters, cad_dot, cad_ok, feeder_dot, feeder_ok, current_rot):
    """(rotation_needed, text) for the setup list."""
    if matters is False:
        return None, "orientation not relevant"
    if not cad_dot:
        return None, "CAD pin 1 unknown: import KiCad / Gerber or set it in Check"
    if not feeder_dot:
        return None, "feeder mark not set: Check"
    need = rotation_needed(feeder_dot, cad_dot)
    if not (cad_ok and feeder_ok):
        return need, "needs %+.0f deg - not confirmed yet" % need
    if current_rot is None:
        return need, "confirmed, needs %+.0f deg (feeder rotation unknown)" % need
    if abs(norm(current_rot - need)) < 1.0:
        return need, "CORRECT (confirmed)"
    return need, "MISMATCH: feeder has %+.0f deg, needs %+.0f deg" % (norm(current_rot), need)
