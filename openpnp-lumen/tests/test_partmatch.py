#!/usr/bin/env python3
"""lib/lumen/partmatch.py (CPython): job part names of another project -> the set-up feeder parts.
Feeder part names below are taken from the real ~/.openpnp2 configuration (2026-11-06)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from lumen import partmatch as pm  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


FEEDERS = [  # (part id, package id) as in the real configuration
    ("C_0402_1005Metric-100n", "C_0402_1005Metric"), ("CAPC_0805-100n", "CAPC_0805"), ("CAPC_2220-100n 1kV", "CAPC_2220"),
    ("C_0402_1005Metric-1u", "C_0402_1005Metric"), ("C_0402_1005Metric-4.7_uF", "C_0402_1005Metric"),
    ("CAPC_0603_4u7_16V", "CAPC_0603"), ("CAPC_0402-CAPC_47n_0402_X7R_25V_10%", "CAPC_0402"),
    ("CAPC_0402-CAPC_10p_0402_NP0_25V_5%", "CAPC_0402"), ("CAPC_1206-10u25V", "CAPC_1206"), ("CAPC_1210_10u_100V", "CAPC_1206"),
    ("RES_0402-7k5", "RES_0402"), ("RES_0402-100R", "RES_0402"), ("RES_0603-0R1", "RES_0603"), ("RES_0603-10k", "RES_0603"),
    ("RES_2818_Sense-10m", "RES_2818"), ("R_0402_1005Metric-100k", "R_0402_1005Metric"), ("R_0603_1608Metric-R_Small", "R_0603"),
    ("FB_0603_600R_0A5", "FB_0603"), ("RES_0603-100R@100MHz, 0,5A", "RES_0603"), ("L_0805_2012Metric-2.2_uH", "L_0805_2012Metric"),
    ("LED_0603_RED", "LED_0603"), ("LED_0603_BLUE", "LED_0603"), ("LED_0603_G-0603 Green", "LED_0603"),
    ("LED-SK6805SIDE-G-003-SK6805_SIDE", "LED-SK6805SIDE-G-003"), ("UFQFPN-48_STM-STM32WBA65CIx", "UFQFPN-48_STM"),
    ("ZDO_1610_STM-ESDA7P60-1U1M", "ZDO_1610_STM"), ("SOT-223_LM1117-LM1117", "SOT-223"), ("DIODE_SOD-323-BAT46", "SOD-323"),
    ("STM32_-_LQFP48-STM32G431CBT6", "LQFP48"), ("Crystal_SMD_2016-4Pin_2.0x1.6mm_abracon-Crystal_GND24", "Crystal_SMD_2016"),
]
FD = [(pid, pm.describe(pid, "", pkg)) for pid, pkg in FEEDERS]


def best(pid, pkg="", refs=(), aliases=None):
    return pm.rank(pm.describe(pid, "", pkg, refs), FD, aliases)


def top(pid, pkg="", refs=()):
    r = best(pid, pkg, refs)
    return r[0][1] if r else None


print("parsing")
for pid, want in [("C_0402_1005Metric-100n", "C 100nF 0402"), ("CAPC_0402-CAPC_47n_0402_X7R_25V_10%", "C 47nF 0402 25V X7R 10%"),
                  ("CAPC_1206-10u25V", "C 10uF 1206 25V"), ("RES_0603-0R1", "R 0.1R 0603"), ("RES_2818_Sense-10m", "R 0.01R 2818"),
                  ("RES_0402-7k5", "R 7.5k 0402"), ("FB_0603_600R_0A5", "FB 600R 0603"), ("RES_0603-100R@100MHz, 0,5A", "FB 100R 0603"),
                  ("L_0805_2012Metric-2.2_uH", "L 2.2uH 0805"), ("C0402-0.1uF", "C 100nF 0402"), ("C_0603_1608Metric-4.7uF/16V", "C 4.7uF 0603 16V"),
                  ("R0603 4K7 1%", "R 4.7k 0603 1%")]:
    s = pm.summary(pm.describe(pid))
    check("%-38s -> %s" % (pid, want), s == want, s)
check("micro sign and ohm sign in names: C0402-1\u00b5F, R_0402-10\u03a9", pm.summary(pm.describe(u"C0402-1\u00b5F")) == "C 1uF 0402"
      and pm.summary(pm.describe(u"R_0402-10\u03a9")) == "R 10R 0402", (pm.summary(pm.describe(u"C0402-1\u00b5F")),))
check("QFN6L_ECMF2 / L7983 / SOT23-5L_L are not inductors", all(pm.describe(x)["kind"] != "L" for x in
                                                                ("QFN6L_ECMF2_STM-ECMF2-40A100N6", "L7983", "SOT23-5L_L-ST715MR")))
check("named 1210 with a 1206 package: size unknown (contradiction kept as a warning)",
      pm.describe("CAPC_1210_10u_100V", "", "CAPC_1206")["size"] is None and pm.describe("CAPC_1210_10u_100V", "", "CAPC_1206")["size_conflict"])

print("matching other projects' names onto the feeders")
check("C0402-0.1uF -> C_0402_1005Metric-100n (100n = 0.1u)", top("C0402-0.1uF") == "C_0402_1005Metric-100n", best("C0402-0.1uF")[:2])
r = best("CAPC_0402_100nF_X7R_16V")
check("100nF 0402 X7R 16V -> only the 0402 100n (0805 and 2220 100n not proposed: other size)",
      [x[1] for x in r] == ["C_0402_1005Metric-100n"] and any("voltage" in w for w in r[0][3]), r)
check("R_0402_1005Metric-7.5k -> RES_0402-7k5 (4k7-style notation)", top("R_0402_1005Metric-7.5k") == "RES_0402-7k5")
check("RES_0603_0.1R -> RES_0603-0R1", top("RES_0603_0.1R") == "RES_0603-0R1")
r = best("R_0603-4k7")
check("R_0603-4k7: no feeder has 4.7k -> no value match; only the 0603 resistor whose value is unreadable, weak (20, check by hand)",
      [x[:2] for x in r] == [(20, "R_0603_1608Metric-R_Small")] and "check by hand" in r[0][2], r)
check("C_0402-10n: no 10n -> nothing (10p, 1u, 47n are not proposed)", best("C_0402_1005Metric-10n") == [])
r = best("C_0603_1608Metric-4.7uF_25V")
check("4.7uF 0603 needing 25V -> CAPC_0603_4u7_16V proposed with a LOWER VOLTAGE warning, low score",
      r and r[0][1] == "CAPC_0603_4u7_16V" and r[0][0] < 70 and any("16V < 25V" in w for w in r[0][3]), r[:1])
r = best("C_0402-10p_C0G")
check("10p C0G -> the NP0 10p (C0G = NP0)", r and r[0][1] == "CAPC_0402-CAPC_10p_0402_NP0_25V_5%" and not r[0][3], r[:1])
r = best("C_0402-10p_X7R")
check("10p X7R -> the NP0 10p only with a dielectric warning", r and any("dielectric" in w for w in r[0][3]), r[:1])
check("RES_2818_Sense-10m is not proposed for a 0603 10 milliohm", "RES_2818_Sense-10m" not in [x[1] for x in best("R_0603_10m")])
check("FB_0603-600R -> FB_0603_600R_0A5 (ferrite, not the 600 ohm resistor rule)", top("FB_0603-600R") == "FB_0603_600R_0A5")
check("Ferrite 0603 100R@100MHz -> the RES_0603-100R@100MHz feeder", top("BEAD_0603-100R_100MHz") == "RES_0603-100R@100MHz, 0,5A")
check("L_0805-2u2 -> L_0805_2012Metric-2.2_uH", top("L_0805-2u2") == "L_0805_2012Metric-2.2_uH")
check("LED_0603_1608Metric-RED -> LED_0603_RED, not BLUE / Green", [x[1] for x in best("LED_0603_1608Metric-RED")] == ["LED_0603_RED"])
check("LED green from 'Green' in the name", top("LED_0603-GREEN") == "LED_0603_G-0603 Green")
check("SK6805 side LED by part number", top("LED_SK6805-SIDE-RGB", "", ("D1",)) == "LED-SK6805SIDE-G-003-SK6805_SIDE")
check("STM32WBA65CI (no 'x') -> UFQFPN-48_STM-STM32WBA65CIx (order-code suffix)", top("U_QFN48-STM32WBA65CI") == "UFQFPN-48_STM-STM32WBA65CIx")
check("ESDA7P60 -> ZDO_1610_STM-ESDA7P60-1U1M", top("ESDA7P60-1U1M_ZDO") == "ZDO_1610_STM-ESDA7P60-1U1M")
check("LM1117 in another package name -> SOT-223_LM1117 (part number)", top("LM1117-3.3_SOT223") == "SOT-223_LM1117-LM1117")
check("STM32G431 other order code -> nothing guessed beyond the common prefix rule",
      top("STM32G474RET6") != "STM32_-_LQFP48-STM32G431CBT6")
check("same part id -> 100", best("RES_0603-10k")[0][:2] == (100, "RES_0603-10k"))
check("C kind from the reference (C12) when the name says nothing", pm.describe("100n_0402", "", "", ("C12", "C13"))["kind"] == "C"
      and top("100n_0402", "", ("C12",)) == "C_0402_1005Metric-100n")
r = best("MyLib_Cap-0402-100n", aliases={"MyLib_Cap-0402-100n": "CAPC_0805-100n"})
check("a confirmed alias (earlier decision) comes first with 99", r[0][:2] == (99, "CAPC_0805-100n"), r[:2])
check("value unreadable (R_Small) -> only a weak 'check by hand' candidate", all(x[0] <= 20 for x in best("R_0603_1608Metric-R_Small_x")
                                                                                if x[1] == "R_0603_1608Metric-R_Small"))
print("\n%d/%d checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
