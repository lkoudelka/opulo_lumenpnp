# -*- coding: utf-8 -*-
"""Part orientation for setup: pin-1 / polarity mark position and the rotation in the feeder.

Pure Python (CPython 3 and Jython 2.7).

A "dot" is where pin 1 is on the part body, seen from above, as one of the 4 corners
TL TR BR BL - one per possible rotation (0 / 90 / 180 / 270).  For 2-terminal polarized
parts pin 1 is at an END; the convention is the corner at the pin-1 end on its clockwise
side (pin 1 left -> TL, top -> TR, right -> BR, bottom -> BL), which rotates consistently.

- CAD dot: pin 1 in the footprint's own 0 deg orientation, detected from a KiCad
  .kicad_pcb (pad "1" position) or from KiCad copper Gerbers with X2 attributes (%TO.P%).
  With only a position file (.pos), by footprint NAME: footprint library (.kicad_mod),
  OpenPnP package footprint, or the footprint table learned from earlier boards/confirmations.
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
    """True / False / None (best guess, the user can override).  n_pins None = no pad data
    (only a position file): the guess is made from the reference prefix alone."""
    if re.search(r"Fiducial|MountingHole|TestPoint", footprint or "", re.I):
        return False
    if n_pins is None:
        if NONPOLAR_REF.match(ref or "") and not POLARIZED_2PIN.search(footprint or ""):
            return False
        if re.match(r"^(U|IC|Q|D|LED|CR|VD|J|P|CN|X|T)\d", ref or "", re.I):
            return True
        return None
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


PIN1_NAMES = ("1", "A1")          # pad names taken as pin 1 (numbered parts, BGA)
SURE, ZERO = 0.6, 0.25            # pin-1 offset / half body size per axis: >= SURE = that side, <= ZERO = centre


def classify_pin1(pads):
    """pads [(name, x, y)] in the footprint 0 deg frame, Y up -> (corner or None, note).

    Pin 1 is located relative to the bounding box of the pads, normalised PER AXIS, so a long
    part (pin header, connector, SOIC) gives the corner a person sees.  Pin 1 in the middle of
    an edge (2-terminal parts, 1xN rows) gives the corner on the clockwise side of that edge.
    Anything between the bands is refused ("ambiguous"): no guessing."""
    named = [(n, x, y) for n, x, y in pads if n not in ("", None)]
    if len(set(n for n, _, _ in named)) < 2:
        return None, "fewer than 2 pins"
    p1 = []
    for name in PIN1_NAMES:
        p1 = [(x, y) for n, x, y in named if n == name]
        if p1:
            break
    if not p1:
        return None, "no pad named 1"
    xs = [x for _, x, _ in named]
    ys = [y for _, _, y in named]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    hw, hh = (max(xs) - min(xs)) / 2.0, (max(ys) - min(ys)) / 2.0
    vx = sum(x for x, _ in p1) / len(p1) - cx
    vy = sum(y for _, y in p1) / len(p1) - cy
    nx = vx / hw if hw > 1e-6 else 0.0
    ny = vy / hh if hh > 1e-6 else 0.0

    def band(n):
        return "side" if abs(n) >= SURE else "centre" if abs(n) <= ZERO else "?"
    bx, by = band(nx), band(ny)
    if "?" in (bx, by) or (bx, by) == ("centre", "centre"):
        return None, "ambiguous pin 1 position (%.2f / %.2f of the half body): set it in Check" % (nx, ny)
    if bx == "side" and by == "side":
        return ("T" if ny > 0 else "B") + ("R" if nx > 0 else "L"), ""
    if bx == "side":
        return EDGE_TO_CORNER["R" if nx > 0 else "L"], "pin 1 at the %s end" % ("right" if nx > 0 else "left")
    return EDGE_TO_CORNER["T" if ny > 0 else "B"], "pin 1 at the %s end" % ("top" if ny > 0 else "bottom")


def cad_info(footprint, ref, pads_local):
    """pads_local: [(number, x, y)] in the footprint 0 deg frame, Y up."""
    numbered = [(n, x, y) for n, x, y in pads_local if n not in ("", None)]
    pins = sorted(set(n for n, _, _ in numbered))
    info = {"ref": ref, "footprint": footprint, "pins": len(pins), "pads": [[n, round(x, 4), round(y, 4)] for n, x, y in numbered],
            "dot": None, "matters": orientation_matters(ref, footprint, len(pins))}
    if numbered:
        info["dot"], info["note"] = classify_pin1(numbered)
        p1 = [(x, y) for n, x, y in numbered if n in PIN1_NAMES]
        if p1:
            cx = sum(x for _, x, _ in numbered) / len(numbered)
            cy = sum(y for _, _, y in numbered) / len(numbered)
            info["pin1"] = [round(sum(x for x, _ in p1) / len(p1) - cx, 4), round(sum(y for _, y in p1) / len(p1) - cy, 4)]
    return info


def parse_kicad_pcb_list(path):
    """Every footprint of a .kicad_pcb (duplicate references kept, e.g. panels):
    [info] with info['at'] = [x, y, rot] in the position-file frame (Y up) and 'side'."""
    f = open(path)
    try:
        root = _sexpr(f.read())
    finally:
        f.close()
    out = []
    for fp in _kids(root, "footprint") + _kids(root, "module"):
        ref = _ref(fp)
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
        info["at"] = [float(at[1]), -float(at[2]), norm(float(at[3])) if len(at) > 3 else 0.0]
        info["source"] = "kicad:" + os.path.basename(path)
        out.append(info)
    return out


def parse_kicad_pcb(path):
    """{ref: info} (last one wins for duplicate references; use parse_kicad_pcb_list for panels)."""
    return dict((i["ref"], i) for i in parse_kicad_pcb_list(path) if i["ref"])


# ---------------------------------------------------------------------------------------
# Gerber X2 copper layer (KiCad: 'Use extended X2 format' + 'Include netlist attributes')
# Every pad flash / pad region carries %TO.P,<ref>,<pin>[,<name>]*%.
# ---------------------------------------------------------------------------------------
_UESC = re.compile(r"\\u([0-9A-Fa-f]{4})")


def _unescape(s):
    try:
        ch = unichr
    except NameError:
        ch = chr
    return _UESC.sub(lambda m: str(ch(int(m.group(1), 16))), s)


def parse_gerber(path):
    """{'software', 'function', 'pads': [(ref, pin, x, y)]} in mm, Y up, board coordinates.
    A pad region (G36/G37) counts once, at the centre of its bounding box."""
    f = open(path)
    try:
        text = f.read()
    finally:
        f.close()
    head = {}
    for k in ("GenerationSoftware", "FileFunction"):
        m = re.search(r"%TF\." + k + r",([^*%]*)\*%", text)
        head[k] = m.group(1) if m else ""
    m = re.search(r"%FSLAX(\d)(\d)Y(\d)(\d)\*%", text)
    dec = int(m.group(2)) if m else 6
    scale = 25.4 if "%MOIN*%" in text else 1.0
    pads = []
    cur = None
    x = y = 0.0
    region = None
    for blk in re.findall(r"%[^%]*%|[^%*]+\*", text):
        b = blk.strip()
        if b.startswith("%TO.P,"):
            parts = [_unescape(p) for p in b[6:-2].split(",")]
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
                xs = [p[0] for p in region]
                ys = [p[1] for p in region]
                pads.append((cur[0], cur[1], (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0))
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
        elif "D03" in b and cur:
            pads.append((cur[0], cur[1], x, y))
    return {"software": head["GenerationSoftware"], "function": head["FileFunction"], "pads": pads}


def gerber_check(g):
    """None if the file can be used, else why not."""
    if not g["function"].startswith("Copper"):
        return "not a copper layer (%s): use the top COPPER Gerber (F_Cu)" % (g["function"] or "no X2 file function")
    if ",Top" not in g["function"] and ",L1," not in g["function"]:
        return "not the TOP copper layer (%s)" % g["function"]
    if not [p for p in g["pads"] if p[1]]:
        return ("no pin attributes: export again with 'Use extended X2 format' and "
                "'Include netlist attributes' (KiCad Plot dialog)")
    return None


LINK_STEPS = (0.3, 0.5, 0.8, 1.2, 1.8, 2.5, 3.5, 5.0)   # mm, pad-to-pad link distances tried in order


def _clusters(pts, link):
    """Single-linkage clusters of [(pin, x, y)] sorted by x."""
    parent = list(range(len(pts)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(pts)):
        j = i + 1
        while j < len(pts) and pts[j][1] - pts[i][1] <= link:
            if math.hypot(pts[j][1] - pts[i][1], pts[j][2] - pts[i][2]) <= link:
                parent[root(i)] = root(j)
            j += 1
    cl = {}
    for i, q in enumerate(pts):
        cl.setdefault(root(i), []).append(q)
    return sorted(cl.values(), key=lambda g_: min(q[1:] for q in g_))


def _split_copies(lst, n, want):
    """n copies of one reference: the smallest link distance giving exactly n clusters that each
    hold exactly the expected pins (want = [(pin, pads per copy)]), AND the same clusters with the
    link doubled (a clear gap between copies).  Else None: refused, never guessed."""
    pts = sorted(lst, key=lambda q: (q[1], q[2]))
    for link in LINK_STEPS:
        cl = _clusters(pts, link)
        if len(cl) < n:
            return None
        if len(cl) == n:
            if not all(sorted((pin, len([1 for q in g_ if q[0] == pin])) for pin in set(q[0] for q in g_)) == want
                       for g_ in cl):
                return None
            if len(_clusters(pts, 2 * link)) != n:
                return None                 # copies closer than twice the pad spacing: not separable for sure
            return cl
    return None


def _gcd(vals):
    g_ = 0
    for c in vals:
        a, b = g_, c
        while b:
            a, b = b, a % b
        g_ = a
    return g_


def gerber_instances(pads):
    """Split the pads of every reference into its copies (a panel Gerber repeats references):
    ({ref: [{'pads': [(pin, x, y)], 'center': (x, y), 'half': (w, h)}]}, {ref: why not}, copies).
    The panel copy count is the one most references agree on; a reference that does not split
    into exactly that many clearly separated, complete copies is refused."""
    by = {}
    for ref, pin, x, y in pads:
        if pin:
            by.setdefault(ref, []).append((pin, x, y))
    cnts, gcds = {}, {}
    for ref, lst in by.items():
        cnt = {}
        for pin, _, _ in lst:
            cnt[pin] = cnt.get(pin, 0) + 1
        cnts[ref] = cnt
        gcds[ref] = _gcd(cnt.values())
    votes = {}
    for v in gcds.values():
        votes[v] = votes.get(v, 0) + 1
    copies = max(sorted(votes), key=lambda v: votes[v]) if votes else 1
    out, bad = {}, {}
    for ref, lst in by.items():
        if gcds[ref] % copies:
            bad[ref] = "%s has pads for %d copies, the panel has %d" % (ref, gcds[ref], copies)
            continue
        want = sorted((p, c // copies) for p, c in cnts[ref].items())
        groups = [lst] if copies == 1 else _split_copies(lst, copies, want)
        if groups is None:
            bad[ref] = "the %d copies of %s are too close to separate for sure" % (copies, ref)
            continue
        out[ref] = []
        for g_ in groups:
            xs = [x for _, x, _ in g_]
            ys = [y for _, _, y in g_]
            out[ref].append({"pads": g_, "center": ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0),
                             "half": ((max(xs) - min(xs)) / 2.0, (max(ys) - min(ys)) / 2.0)})
    return out, bad, copies


# ---------------------------------------------------------------------------------------
# Verified matching of a CAD file to the job's placements
#
# placements: [{'ref', 'x', 'y', 'rot', 'side', 'footprint'}] as in the job (position-file
# frame, mm).  Each placement gets {'ok': True, 'dot', 'pads', 'pins', 'source'} only if it is
# found unambiguously in the file at one common origin offset (KiCad board: same reference,
# footprint, side and rotation, position within 0.01 mm; Gerber: same reference, the pads of
# exactly one copy around the position).  Otherwise {'ok': False, 'reason'}.
# ---------------------------------------------------------------------------------------
PCB_TOL = 0.01
GERBER_TOL = 0.05


def _offset(pairs, step):
    """Most common translation (placement - file) of the candidate pairs, refined."""
    votes = {}
    for dx, dy in pairs:
        k = (round(dx / step), round(dy / step))
        votes[k] = votes.get(k, 0) + 1
    if not votes:
        return None
    k = max(sorted(votes), key=lambda q: votes[q])      # deterministic: identical panel copies tie
    near = [(dx, dy) for dx, dy in pairs if abs(dx - k[0] * step) <= step and abs(dy - k[1] * step) <= step]
    return (sum(d[0] for d in near) / len(near), sum(d[1] for d in near) / len(near))


def _summary(res, top, src, offset=None, refused=None):
    ok = len([r for r in res.values() if r["ok"]])
    return {"results": res, "verified": ok, "placements": top, "source": src, "offset": offset, "refused": refused}


def match_kicad_pcb(fps, placements, src="kicad"):
    top = [p for p in placements if p.get("side", "top") == "top"]
    by = {}
    for i in fps:
        if i["side"] == "top" and i["ref"]:
            by.setdefault(i["ref"], []).append(i)
    names = set(footprint_key(i["footprint"]) for i in fps)

    def same_fp(i, p):
        """Package name = KiCad footprint name after a .pos import.  A job whose packages have other
        names (made by hand, other importers) is matched by reference + position + rotation only."""
        jf = footprint_key(p.get("footprint"))
        return not jf or jf not in names or jf == footprint_key(i["footprint"])
    pairs = [(p["x"] - i["at"][0], p["y"] - i["at"][1]) for p in top for i in by.get(p["ref"], [])
             if same_fp(i, p) and abs(norm(i["at"][2] - p["rot"])) < 0.01]
    off = _offset(pairs, PCB_TOL)
    res = {}
    support = 0
    for p in top:
        cands = by.get(p["ref"], [])
        here = [i for i in cands if off and math.hypot(i["at"][0] + off[0] - p["x"], i["at"][1] + off[1] - p["y"]) <= PCB_TOL]
        if not cands:
            r = {"ok": False, "reason": "%s not in the board file" % p["ref"]}
        elif not here:
            r = {"ok": False, "reason": "position differs from the board file"}
        elif len(here) > 1:
            r = {"ok": False, "reason": "%d footprints %s at the same place" % (len(here), p["ref"])}
        else:
            i = here[0]
            support += 1
            if not same_fp(i, p):
                r = {"ok": False, "reason": "footprint differs: board %s, job %s" % (footprint_key(i["footprint"]), p["footprint"])}
            elif abs(norm(i["at"][2] - p["rot"])) >= 0.01:
                r = {"ok": False, "reason": "rotation differs: board %+.1f, job %+.1f" % (i["at"][2], p["rot"])}
            elif not i["dot"]:
                r = {"ok": False, "reason": i.get("note") or "pin 1 unknown", "pins": i["pins"]}
            else:
                r = {"ok": True, "dot": i["dot"], "note": i.get("note", ""), "pads": i["pads"], "pins": i["pins"],
                     "footprint": i["footprint"], "matters": i["matters"]}
        r["source"] = src
        res[p["ref"]] = r
    if top and support < max(1, len(top) // 2):
        return _summary(dict((p["ref"], {"ok": False, "source": src, "reason": "board file does not match the job"})
                             for p in top), len(top), src, off,
                        "only %d of %d placements found in the board file: other design or revision?" % (support, len(top)))
    return _summary(res, len(top), src, off)


def match_gerber(g, placements, src="gerber"):
    top = [p for p in placements if p.get("side", "top") == "top"]
    why = gerber_check(g)
    if why:
        return _summary(dict((p["ref"], {"ok": False, "source": src, "reason": why}) for p in top), len(top), src, None, why)
    inst, bad, copies = gerber_instances(g["pads"])
    # origin offset from parts whose pad centre is their origin (2-pad and symmetric parts: most of a board)
    pairs = [(p["x"] - c["center"][0], p["y"] - c["center"][1]) for p in top for c in inst.get(p["ref"], [])]
    off = _offset(pairs, GERBER_TOL)
    res = {}
    support = 0
    for p in top:
        cands = inst.get(p["ref"], [])
        if p["ref"] in bad:
            res[p["ref"]] = {"ok": False, "source": src, "reason": bad[p["ref"]]}
            continue
        if not cands:
            res[p["ref"]] = {"ok": False, "source": src, "reason": "%s has no pads with pin attributes in the Gerber" % p["ref"]}
            continue
        dist = sorted((math.hypot(c["center"][0] + off[0] - p["x"], c["center"][1] + off[1] - p["y"]), k)
                      for k, c in enumerate(cands)) if off else []
        c = cands[dist[0][1]] if dist else None
        tol = GERBER_TOL + (max(c["half"]) if c else 0.0)    # the origin may be off the pad centre, inside the part
        if not dist or dist[0][0] > tol:
            res[p["ref"]] = {"ok": False, "source": src, "reason": "no copy of %s at this position in the Gerber "
                             "(footprint origin outside its pads?)" % p["ref"]}
            continue
        if len(dist) > 1 and dist[1][0] <= 3 * tol:
            res[p["ref"]] = {"ok": False, "source": src, "reason": "two copies of %s near this position" % p["ref"]}
            continue
        support += 1
        a = math.radians(-p["rot"])                            # board frame -> footprint 0 deg frame
        cx, cy = c["center"]
        local = [(pin, (x - cx) * math.cos(a) - (y - cy) * math.sin(a), (x - cx) * math.sin(a) + (y - cy) * math.cos(a))
                 for pin, x, y in c["pads"]]
        info = cad_info(p["footprint"], p["ref"], local)
        if not info["dot"]:
            res[p["ref"]] = {"ok": False, "source": src, "reason": info.get("note") or "pin 1 unknown", "pins": info["pins"]}
            continue
        res[p["ref"]] = {"ok": True, "source": src, "dot": info["dot"], "note": info.get("note", ""), "pads": info["pads"],
                         "pins": info["pins"], "footprint": p["footprint"], "matters": info["matters"]}
    if top and support < max(1, len(top) // 2):
        return _summary(dict((p["ref"], {"ok": False, "source": src, "reason": "Gerber does not match the job"}) for p in top),
                        len(top), src, off, "only %d of %d placements found in the Gerber: other design or revision?"
                        % (support, len(top)))
    # the same footprint must show the same pad pattern on every part (else a rotation in the job is off)
    groups = {}                                            # footprint -> [[pads, [refs]]]
    for p in top:
        r = res[p["ref"]]
        if r["ok"] and footprint_key(p["footprint"]):       # only parts with a footprint (package) name
            lst = groups.setdefault(footprint_key(p["footprint"]), [])
            for grp in lst:
                if same_pattern(grp[0], r["pads"]):
                    grp[1].append(p["ref"])
                    break
            else:
                lst.append([r["pads"], [p["ref"]]])
    for k, lst in groups.items():
        if len(lst) > 1:
            main = max(lst, key=lambda grp: len(grp[1]))
            for grp in lst:
                if grp is not main:
                    for ref in grp[1]:
                        res[ref] = {"ok": False, "source": src, "reason": "pads differ from the other %s parts (%s): "
                                    "rotation in the job?" % (k, ", ".join(main[1][:3]))}
    return _summary(res, len(top), src, off)


def same_pattern(a, b, tol=0.03):
    """Two pad lists [(pin, x, y)] (footprint frame) are the same footprint: same pins, and every
    pad of a has its own pad of the same pin in b within tol mm."""
    if len(a) != len(b):
        return False
    left = list(b)
    for n, x, y in a:
        best = None
        for k, (m, u, v) in enumerate(left):
            if m == n and math.hypot(u - x, v - y) <= tol and (best is None or math.hypot(u - x, v - y) < best[0]):
                best = (math.hypot(u - x, v - y), k)
        if best is None:
            return False
        del left[best[1]]
    return True


def gerber_cad_info(pins_by_ref, placements):
    """Legacy API (single board, unique references): pins {ref: {pin: [(x, y)]}} + placements
    {ref: (rotation, footprint)} -> {ref: info}.  Use match_gerber for verified results."""
    out = {}
    for ref, pins in pins_by_ref.items():
        rot, fpname = placements.get(ref, (None, ""))
        if rot is None:
            continue
        pts = [(n, x, y) for n, lst in pins.items() for (x, y) in lst]
        if not pts:
            continue
        xs = [x for _, x, _ in pts]
        ys = [y for _, _, y in pts]
        cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
        a = math.radians(-rot)
        local = [(n, (x - cx) * math.cos(a) - (y - cy) * math.sin(a), (x - cx) * math.sin(a) + (y - cy) * math.cos(a))
                 for n, x, y in pts]
        info = cad_info(fpname, ref, local)
        info["side"] = "top"
        info["source"] = "gerber"
        out[ref] = info
    return out


def parse_gerber_pins(path):
    """Legacy API: {ref: {pin: [(x, y)...]}} from %TO.P% attributes."""
    pins = {}
    for ref, pin, x, y in parse_gerber(path)["pads"]:
        pins.setdefault(ref, {}).setdefault(pin, []).append((x, y))
    return pins


# ---------------------------------------------------------------------------------------
# Position files and footprints by NAME
#
# A position file (.pos / CPL) has no pad data, only the footprint name and the rotation.
# Pin 1 in the footprint 0 deg frame is a property of the footprint, the same on every
# board, so it is looked up by name: footprint library (.kicad_mod), the OpenPnP package
# footprint, or the footprint table learned from earlier imports and confirmations.
# ---------------------------------------------------------------------------------------
def footprint_key(name):
    """'Capacitor_SMD:C_0402_1005Metric' and 'C_0402_1005Metric' are the same footprint."""
    return (name or "").split(":")[-1].strip()


def parse_kicad_pos(path):
    """KiCad footprint position file, ASCII (.pos) or CSV: [{ref, value, footprint, x, y, rot, side}]."""
    f = open(path)
    try:
        lines = f.read().splitlines()
    finally:
        f.close()
    out = []
    csv_hdr = None
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if csv_hdr is None and s.startswith(("Ref,", '"Ref",')):
            csv_hdr = [c.strip('"') for c in s.split(",")]
            continue
        if csv_hdr:
            cols = [c.strip().strip('"') for c in s.split(",")]
            if len(cols) < len(csv_hdr):
                continue
            row = dict(zip(csv_hdr, cols))
            ref, val, fp = row.get("Ref"), row.get("Val"), row.get("Package")
            x, y, rot, side = row.get("PosX"), row.get("PosY"), row.get("Rot"), row.get("Side")
        else:
            cols = s.split()
            if len(cols) < 7:
                continue
            ref, val, fp, x, y, rot, side = cols[0], " ".join(cols[1:-5]), cols[-5], cols[-4], cols[-3], cols[-2], cols[-1]
        try:
            out.append({"ref": ref, "value": val, "footprint": fp, "x": float(x), "y": float(y),
                        "rot": norm(float(rot)), "side": (side or "top").lower()})
        except (TypeError, ValueError):
            continue
    return out


def parse_kicad_mod(path):
    """Footprint file -> cad info (pads Y up, pin 1 corner) in the footprint 0 deg frame."""
    f = open(path)
    try:
        root = _sexpr(f.read())
    finally:
        f.close()
    pads = []
    for p in _kids(root, "pad"):
        if len(p) < 3 or p[2] == "np_thru_hole":
            continue
        pat = (_kids(p, "at") or [["at", "0", "0"]])[0]
        pads.append((p[1], float(pat[1]), -float(pat[2])))           # KiCad Y down -> Y up
    info = cad_info(root[1] if len(root) > 1 else os.path.basename(path)[:-10], None, pads)
    info["source"] = "lib:" + os.path.basename(path)
    return info


DEFAULT_LIB_DIRS = ("/usr/share/kicad/footprints", "/usr/local/share/kicad/footprints")


def library_dirs(extra=()):
    """Configured dirs first, then the KiCad stock library if installed (env KICADn_FOOTPRINT_DIR)."""
    env = [os.environ[k] for k in sorted(os.environ) if re.match(r"KICAD\d*_FOOTPRINT_DIR$", k)]
    seen, out = set(), []
    for d in list(extra) + env + list(DEFAULT_LIB_DIRS):
        if d and d not in seen and os.path.isdir(d):
            seen.add(d)
            out.append(d)
    return out


def index_libraries(dirs):
    """{footprint name: path} of every *.kicad_mod below dirs (the first one found wins)."""
    idx = {}
    for d in dirs:
        for root, _, files in os.walk(d):
            for fn in sorted(files):
                if fn.endswith(".kicad_mod"):
                    idx.setdefault(fn[:-10], os.path.join(root, fn))
    return idx


def package_cad_info(name, pads):
    """OpenPnP package footprint [(pad name, x, y)] (already Y up, as KicadModImporter stores it)."""
    if not any(n == "1" for n, _, _ in pads):
        return None
    info = cad_info(name, None, pads)
    info["source"] = "openpnp-package"
    return info


def learn_footprints(infos):
    """From per-ref cad infos (KiCad board / Gerber): {footprint key: info} for footprints whose
    refs all agree on pin 1, and {key: [dots]} for those that disagree (a rotation problem)."""
    by = {}
    for i in infos:
        if i.get("dot") and i.get("side", "top") == "top":
            by.setdefault(footprint_key(i["footprint"]), []).append(i)
    good, bad = {}, {}
    for k, lst in by.items():
        dots = sorted(set(i["dot"] for i in lst))
        if len(dots) == 1:
            good[k] = lst[0]
        else:
            bad[k] = dots
    return good, bad


def resolve_footprint(key, table_rec=None, package_info=None, lib_info=None):
    """Pin 1 of a footprint from the sources by name.  Order: confirmed table entry, OpenPnP
    package footprint, footprint library, unconfirmed table entry (learned from a board or
    Gerber).  Returns {dot, source, confirmed, pins, pads, conflict} or None."""
    cands = []
    if table_rec and table_rec.get("dot") and table_rec.get("confirmed"):
        cands.append((table_rec["dot"], "table:" + (table_rec.get("source") or "?"), True, table_rec))
    for i in (package_info, lib_info):
        if i and i.get("dot"):
            cands.append((i["dot"], i.get("source"), False, i))
    if table_rec and table_rec.get("dot") and not table_rec.get("confirmed"):
        cands.append((table_rec["dot"], "table:" + (table_rec.get("source") or "?"), False, table_rec))
    if not cands:
        return None
    dot, src, ok, rec = cands[0]
    others = sorted(set(c[0] for c in cands if c[0] != dot))
    return {"dot": dot, "source": src, "confirmed": ok, "pins": rec.get("pins"), "pads": rec.get("pads") or [],
            "conflict": ["%s (%s)" % (c[0], c[1]) for c in cands if c[0] in others]}


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
        self.data.setdefault("footprints", {})      # pin 1 by footprint name, reused on every board
        self.data.setdefault("lib_dirs", [])
        self.data.setdefault("board_sources", {})  # OpenPnP board -> [kicad:/gerber: files imported for it]

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

    def set_footprint(self, key, info, source, confirmed):
        """Store pin 1 of a footprint.  A confirmed entry is never replaced by an automatic one
        with a different corner: that returns the conflicting corner instead (shown in the list)."""
        key = footprint_key(key)
        old = self.data["footprints"].get(key)
        dot = info.get("dot")
        if not dot:
            return None
        if old and old.get("confirmed") and not confirmed:
            return None if old.get("dot") == dot else dot
        self.data["footprints"][key] = {"dot": dot, "source": source, "confirmed": bool(confirmed),
                                        "pins": info.get("pins"), "pads": info.get("pads") or [],
                                        "t": time.strftime("%Y-%m-%dT%H:%M:%S")}
        return None

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
        return None, "CAD pin 1 unknown: import KiCad board / Gerber / footprint library, or set it in Check"
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
