# -*- coding: utf-8 -*-
"""Which already set-up feeder holds the part a new board needs?  (pure Python: CPython tests, Jython)

Different projects name the same component differently ("C_0402_1005Metric-100n",
"CAPC_0402-CAPC_100n_0402_X7R_25V_10%", "C0402-0.1uF"), so the part id is read as a description:
kind (C / R / L / FB / LED / D / Y / other), size code (0402 ... 2512, also from "1005Metric"), value
(100n = 100nF = 0.1uF; 4k7 = 4.7k; 0R1 = 0.1 ohm; 10m = 10 milliohm for R), rating (V, %,
dielectric), LED colour, and the remaining keywords (MPN-like tokens for ICs).

score(job, feeder) -> (0..100, why, warnings).  Passives must agree on kind, value and size (a
different value or size is never proposed); ratings only add or warn (a feeder part with a lower
voltage or a different dielectric is shown with a warning).  Other parts are matched on keywords
(identical MPN-like tokens first).  Nothing is assigned here: the operator confirms.
"""
from __future__ import absolute_import, division, print_function

import re

PASSIVE = ("C", "R", "L", "FB")
METRIC = {"0402": "01005", "0603": "0201", "1005": "0402", "1608": "0603", "2012": "0805", "3216": "1206",
          "3225": "1210", "4532": "1812", "5025": "2010", "5750": "2220", "6332": "2512", "7142": "2818"}
IMPERIAL = ("01005", "0201", "0402", "0603", "0805", "1206", "1210", "1806", "1812", "2010", "2220", "2512", "2818")
MICRO, OHM = u"\u00b5", u"\u03a9"        # escapes: the same in CPython 3 and Jython 2
MULT = {"p": 1e-12, "n": 1e-9, "u": 1e-6, MICRO: 1e-6, "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "": 1.0, "R": 1.0}
UNIT_KIND = {"F": "C", "H": "L", "R": "R", "OHM": "R", OHM: "R"}
COLOURS = ("RED", "GREEN", "BLUE", "AMBER", "YELLOW", "WHITE", "ORANGE", "RGB", "PINK", "PURPLE", "UV", "IR", "WARM", "COLD")
DIELECTRIC = ("X7R", "X5R", "C0G", "NP0", "COG", "NPO", "Y5V", "X6S", "X7S", "X8R", "Z5U")
GENERIC = set("""SMD SMT SMALL METRIC CAPC CAP CAPE RES RESC IND COIL LED DIODE CRYSTAL CONN CON HEADER FP IPC PAD
PADS HANDSOLDERING HAND SOLDERING THT TH PTH VIA PIN PINS DEFAULT GENERIC PART THE AND FOR WITH POLARIZED""".split())
_SZ = "(?:%s)(?!\\d)" % "|".join(IMPERIAL)
_B = r"(^|[_\-\s/:])"                        # a name part starts here (not inside a word or number)
KIND_WORDS = [  # (regex on the upper-case text, kind); first match wins
    (_B + r"(FB|FERRITE|BEAD)", "FB"),
    (_B + r"(CAPE|CP_|C_ELEC|CP_ELEC|ELEC|TANTAL)", "C"),
    (_B + r"(CAPC|CAP|C)[_\-]?" + _SZ, "C"), (_B + r"C_", "C"), (_B + r"CAPACITOR", "C"),
    (_B + r"(RES|RESC|R)[_\-]?" + _SZ, "R"), (_B + r"R_", "R"), (_B + r"RESISTOR", "R"),
    (_B + r"(IND|L)[_\-]?" + _SZ, "L"), (_B + r"L_\d", "L"), (_B + r"(COIL|INDUCTOR)", "L"),
    (_B + r"LED", "LED"), (_B + r"(DIODE|SOD|SMA|SMB|SMC|MELF|D_)", "D"), (_B + r"(CRYSTAL|XTAL)", "Y"),
    (_B + r"FIDUCIAL", "FID"),
]
# package / body names: never a part number, never enough for a match on their own
PKG_TOK = re.compile(r"^(U?V?W?T?S?L?QFN|DFN|SON|SOT|SOD|SOIC|SO|SOP|SSOP|TSSOP|MSOP|LQFP|TQFP|QFP|BGA|WLCSP|LGA|DO|SMA|SMB|SMC|"
                     r"TO|DPAK|D2PAK|POWERFLAT|UMT|HEADER|PINHEADER|DIP|SIP|UFQFPN|VFQFPN|QFN\d|P\d|\d+L|\d+PIN|\d+X\d)",
                     re.I)
REF_KIND = [(r"^(C|CP|CE)\d", "C"), (r"^(R|RN)\d", "R"), (r"^(FB)\d", "FB"), (r"^L\d", "L"), (r"^(LED)\d", "LED"),
            (r"^(D|CR|VD)\d", "D"), (r"^(Y|X|XTAL)\d", "Y"), (r"^(U|IC)\d", "U"), (r"^Q\d", "Q"), (r"^(J|P|CN)\d", "J"),
            (r"^SW\d", "SW"), (r"^F\d", "F")]


def _num(s):
    return float(s.replace(",", "."))


def parse_value(tok, kind=None):
    """'100n' / '100nF' / '4.7uF' / '4k7' / '0R1' / '10m' (R: milliohm) / '600R' -> (value SI, unit kind) or None."""
    t = tok.replace(MICRO, u"u").replace(OHM, u"R").replace(u"\u03bc", u"u")
    m = re.match(r"^(\d+)([pnumkKMGR])(\d+)(F|H)?$", t)              # RKM: 4n7, 7k5, 0R1, 1M65, 2u2
    if m:
        mult = m.group(2)
        unit = m.group(4) or ("R" if mult in "RkKMG" or kind in ("R", "FB") else None)
        if mult == "m" and kind not in ("R", "FB") and unit is None:
            return None
        return float("%s.%s" % (m.group(1), m.group(3))) * MULT[mult], UNIT_KIND.get(unit) if unit else kind
    m = re.match(r"^(\d+(?:[.,]\d+)?)([pnumkKMG]?)(F|H|R|OHM|OHMS)?$", t, re.I if t.upper().endswith(("OHM", "OHMS")) else 0)
    if not m:
        return None
    num, mult, unit = m.group(1), m.group(2), (m.group(3) or "").upper().rstrip("S")
    if mult == "M" and kind in ("C", "L") and not unit:
        mult = "u" if kind == "C" else mult                          # never seen, keep it simple
    if not mult and not unit:
        if kind in ("R", "FB"):                                         # '100' on a resistor = 100 ohm
            return _num(num), "R"
        return None                                                     # bare number: not a value
    if mult == "m" and not unit and kind not in ("R", "FB"):
        return None
    k = UNIT_KIND.get(unit) if unit else ("R" if mult in "kKMG" and kind in (None, "R", "FB") else kind)
    if kind == "FB" and k == "R":
        k = "FB"
    return _num(num) * MULT[mult], k


def fmt_value(v, kind):
    """ASCII on purpose (Jython 2 shows non-ASCII str badly): 100nF, 2.2uH, 4.7k, 600R, 0.1R."""
    if v is None:
        return "?"
    if kind in ("R", "FB"):
        if v < 1:
            return "%gR" % round(v, 4)
        for m, s in ((1e9, "G"), (1e6, "M"), (1e3, "k")):
            if v >= m * 0.999:
                return ("%g" % round(v / m, 3)) + s
        return "%gR" % round(v, 3)
    unit = {"C": "F", "L": "H"}.get(kind, "")
    for m, s in ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "u"), (1e-9, "n"), (1e-12, "p")):
        if abs(v) >= m * 0.999:
            return ("%g" % round(v / m, 3)) + s + unit
    return "%g%s" % (v, unit)


def tokens(text):
    t = text.replace(MICRO, u"u").replace(u"\u03bc", u"u").replace(OHM, u"R")
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)                              # 0,5A -> 0.5A
    t = re.sub(r"(\d)_([pnumkKM]?[FH])\b", r"\1\2", t)                  # 4.7_uF -> 4.7uF
    t = re.sub(r"([pnuFH])(\d+(?:\.\d+)?k?V)\b", r"\1 \2", t)           # 10u25V -> 10u 25V
    return [x for x in re.split(r"[\s_\-/,@();:+]+", t) if x]


def describe(part_id, name="", package="", refs=()):
    """Parsed description of a part (dict)."""
    text = " ".join(x for x in (part_id or "", name or "", package or "") if x)
    up = text.upper()
    d = {"id": part_id, "kind": None, "size": None, "value": None, "volt": None, "tol": None, "diel": None,
         "colour": None, "hz": None, "keys": set(), "pkg_keys": set(), "mpn": set(), "package": (package or "").strip()}
    kinds = []
    for r in refs or ():
        for pat, k in REF_KIND:
            if re.match(pat, r, re.I):
                kinds.append(k)
                break
    by_name = None
    for pat, k in KIND_WORDS:
        if re.search(pat, up):
            by_name = k
            break
    d["kind"] = max(set(kinds), key=kinds.count) if kinds else by_name
    if d["kind"] == "D" and by_name == "LED":                  # LEDs often have D references
        d["kind"] = "LED"
    if d["kind"] == "R" and by_name == "FB":                   # ferrite beads with R references
        d["kind"] = "FB"
    sizes = set()
    for m in re.finditer(r"(?<!\d)(\d{4})_?METRIC", up):
        if m.group(1) in METRIC:
            sizes.add(METRIC[m.group(1)])
    toks = tokens(text)
    metric_raw = set(m.group(1) for m in re.finditer(r"(?<!\d)(\d{4})_?METRIC", up))
    for t in toks:
        tt = re.sub(r"^(CAPC|CAP|RES|RESC|IND|LED|FB|C|R|L)(?=\d{4,5}$)", "", t.upper())
        if tt in IMPERIAL and tt not in metric_raw and not (sizes and tt in METRIC and METRIC[tt] in sizes):
            sizes.add(tt)
    d["size_conflict"] = None
    if len(sizes) == 1:
        d["size"] = sizes.pop()
    elif sizes:
        d["size_conflict"] = "/".join(sorted(sizes))            # e.g. named 1210, package 1206: unknown + warning
    vals = []
    for t in toks:
        u = t.upper()
        if re.match(r"^\d+(\.\d+)?K?V(AC|DC)?$", u):
            v = _num(re.match(r"^(\d+(?:\.\d+)?)", u).group(1)) * (1000 if "KV" in u else 1)
            d["volt"] = max(d["volt"] or 0, v)
            continue
        if re.match(r"^\d+(\.\d+)?%$", u):
            d["tol"] = _num(u[:-1])
            continue
        if re.match(r"^\d+(\.\d+)?[KMG]?HZ$", u):
            m = re.match(r"^(\d+(?:\.\d+)?)([KMG]?)HZ$", u)
            d["hz"] = _num(m.group(1)) * {"": 1, "K": 1e3, "M": 1e6, "G": 1e9}[m.group(2)]
            continue
        if re.match(r"^(\d+(\.\d+)?M?A|\d+A\d+)$", u):                   # current rating
            continue
        if u in DIELECTRIC:
            d["diel"] = {"COG": "C0G", "NPO": "C0G", "NP0": "C0G"}.get(u, u)
            continue
        if u in COLOURS:
            d["colour"] = u
            continue
        if u in IMPERIAL or u in metric_raw or u.endswith("METRIC"):
            continue
        pv = parse_value(t, d["kind"] if d["kind"] in PASSIVE else None)
        if pv:
            vals.append(pv)
            continue
        if len(u) >= 2 and not u.isdigit() and u not in GENERIC:
            if PKG_TOK.match(u):
                d["pkg_keys"].add(u)
                continue
            d["keys"].add(u)
            if re.search(r"[A-Z]", u) and re.search(r"\d", u) and len(u) >= 5:
                d["mpn"].add(u)
    if d["kind"] == "R" and d["hz"]:                                    # '100R@100MHz' = ferrite bead
        d["kind"] = "FB"
    if d["kind"] is None and vals:
        ks = set(k for _, k in vals if k)
        if len(ks) == 1:
            d["kind"] = ks.pop()
    if d["kind"] in PASSIVE:
        want = "R" if d["kind"] == "FB" else d["kind"]
        good = [v for v, k in vals if k in (want, d["kind"], None)]
        if len(set(round(v, 15) for v in good)) == 1:
            d["value"] = good[0]
        elif good:
            d["value"] = "ambiguous"
    return d


def summary(d):
    """Short text: 'C 100nF 0402 25V X7R'."""
    if d["kind"] in PASSIVE:
        v = fmt_value(d["value"], d["kind"]) if isinstance(d["value"], float) else (d["value"] or "?")
        s = "%s %s %s" % (d["kind"], v, d["size"] or ("size %s?" % d["size_conflict"] if d.get("size_conflict") else "size?"))
        if d["volt"]:
            s += " %gV" % d["volt"]
        if d["diel"]:
            s += " " + d["diel"]
        if d["tol"]:
            s += " %g%%" % d["tol"]
        return s
    if d["kind"] == "LED":
        return "LED %s %s" % (d["colour"] or "colour?", d["size"] or "")
    return "%s %s" % (d["kind"] or "?", " ".join(sorted(d["mpn"]) or sorted(d["keys"])[:3]))


def _same(a, b):
    return abs(a - b) <= 1e-6 * max(abs(a), abs(b), 1e-15)


def mpn_common(a, b):
    """Part numbers shared by two descriptions: equal, or one a prefix of the other with >= 7 characters in
    common (order-code suffixes: STM32WBA65CI ~ STM32WBA65CIX, ESDA7P60 ~ ESDA7P60-1U1M)."""
    out = set(a & b)
    for x in a:
        for y in b:
            s, l = (x, y) if len(x) <= len(y) else (y, x)
            if len(s) >= 7 and l.startswith(s):
                out.add(s)
    return out


def score(job, fd):
    """(score 0..100, why, [warnings]); 0 = not a candidate."""
    if job["id"] == fd["id"]:
        return 100, "same part", []
    if "FID" in (job["kind"], fd["kind"]):
        return 0, "", []                                       # fiducials are not fed
    warn = []
    if job["kind"] in PASSIVE or fd["kind"] in PASSIVE:
        if job["kind"] != fd["kind"]:
            return 0, "", []
        jv, fv = job["value"], fd["value"]
        if not isinstance(jv, float) or not isinstance(fv, float):
            if job["size"] and job["size"] == fd["size"]:
                return 20, "same kind and size, value not readable (%s / %s): check by hand" % (summary(job), summary(fd)), \
                    ["value not readable"]
            return 0, "", []
        if not _same(jv, fv):
            return 0, "", []
        js, fs = job["size"], fd["size"]
        if js and fs and js != fs:
            return 0, "", []
        sc = 85 if js and fs else 50
        why = "%s %s, %s" % (job["kind"], fmt_value(jv, job["kind"]), "size %s" % js if js and fs else "size unknown")
        if not (js and fs):
            conf = [x["size_conflict"] for x in (job, fd) if x.get("size_conflict")]
            warn.append("size %s: check the package" % ("contradicts itself (%s)" % conf[0] if conf else "not in both names"))
        if job["volt"] and fd["volt"]:
            if fd["volt"] >= job["volt"]:
                sc += 5
                why += ", %gV >= %gV" % (fd["volt"], job["volt"])
            else:
                sc -= 30
                warn.append("feeder part %gV < %gV needed" % (fd["volt"], job["volt"]))
        elif job["volt"]:
            sc -= 10
            warn.append("voltage %gV needed, feeder part does not say" % job["volt"])
        if job["diel"] and fd["diel"]:
            if job["diel"] == fd["diel"]:
                sc += 4
                why += ", " + fd["diel"]
            else:
                sc -= 15
                warn.append("dielectric %s, needed %s" % (fd["diel"], job["diel"]))
        if job["tol"] and fd["tol"]:
            if fd["tol"] <= job["tol"]:
                sc += 3
            else:
                sc -= 15
                warn.append("tolerance %g%%, needed %g%%" % (fd["tol"], job["tol"]))
        return max(5, min(99, sc)), why, warn
    if job["kind"] == "LED" or fd["kind"] == "LED":
        if job["kind"] != fd["kind"]:
            return 0, "", []
        common = mpn_common(job["mpn"], fd["mpn"])
        if common:
            return 97, "LED %s" % ", ".join(sorted(common)), []
        if job["colour"] != fd["colour"]:                       # different, or only one of them says a colour
            return 0, "", []
        if job["size"] and fd["size"] and job["size"] != fd["size"]:
            return 0, "", []
        if job["colour"]:
            sc, why = 85, "LED %s" % job["colour"]
        else:
            sc, why = 40, "LED, no colour in the names"
            warn.append("check the colour")
        if job["size"] and job["size"] == fd["size"]:
            sc += 8
            why += " %s" % job["size"]
        return min(99, sc), why, warn
    common = mpn_common(job["mpn"], fd["mpn"])
    if common:
        return 95, "same part number %s" % ", ".join(sorted(common)), []
    if not job["keys"] or not fd["keys"]:
        return 0, "", []
    inter = job["keys"] & fd["keys"]
    if not inter:
        return 0, "", []
    pk = (" + package %s" % ", ".join(sorted(job["pkg_keys"] & fd["pkg_keys"]))) if job["pkg_keys"] & fd["pkg_keys"] else ""
    jac = len(inter) / float(len(job["keys"] | fd["keys"]))
    sc = int(round(30 + 50 * jac))
    if job["kind"] and fd["kind"] and job["kind"] != fd["kind"] and job["kind"] in ("D", "Y") and fd["kind"] in ("D", "Y"):
        return 0, "", []
    if sc < 40:
        return 0, "", []
    return min(90, sc + (5 if pk else 0)), "keywords %s%s" % (", ".join(sorted(inter)[:4]), pk), \
        ["matched on keywords only: check the part number"]


def rank(job, feeders, aliases=None):
    """feeders: [(key, description)] -> [(score, key, why, warnings)] best first (score > 0 only).
    aliases: {job part id: feeder part id} confirmed earlier -> 99."""
    out = []
    for key, fd in feeders:
        if aliases and aliases.get(job["id"]) == fd["id"] and fd["id"] != job["id"]:
            out.append((99, key, "confirmed by you before (%s)" % fd["id"], []))
            continue
        s, why, warn = score(job, fd)
        if s > 0:
            out.append((s, key, why, warn))
    out.sort(key=lambda x: -x[0])
    return out
