"""Synthetic OpenPnP log lines of picks, shared by test_picksafety.py and openpnp_picksafety_sim.py."""


def pick(t, n, vac, reads, after, part, w, h):
    """Log lines of one pick as OpenPnP writes them (t: seconds as 'SS.mmm' within 10:00)."""
    ts = lambda s: "2026-11-26 10:%02d:%06.3f" % (int(s // 60), s % 60)
    out = ["%s ReferenceNozzle DEBUG: %s.pick()\n" % (ts(t), n), "%s ReferenceActuator DEBUG: %s.actuate(true)\n" % (ts(t), vac)]
    out += ["%s ReferenceActuator DEBUG: %s.read(): %d\n" % (ts(t + dt / 1000.0), vac, v) for dt, v in reads]
    out += ["%s Scripting TRACE: Scripting.on Nozzle.AfterPick\n" % ts(t + 0.25),
            "%s ReferenceActuator DEBUG: %s.read(): %d\n" % (ts(t + 1.1), vac, after),
            "%s ReferenceBottomVision DEBUG: Bottom vision part %s result rect { {958.5, 543.0} %dx%d * 90.0 }\n" % (ts(t + 2), part, w, h),
            "%s ReferencePnpJobProcessor$Align DEBUG: Align id %s, name null, heightUnits Millimeters, height 0.45, packageId (X) with %s %s, offsets\n"
            % (ts(t + 2), part, n, n),
            "%s ReferenceActuator DEBUG: %s.actuate(false)\n" % (ts(t + 4), vac)]
    return out


ramp = [(20, 0), (100, 252), (150, 246), (200, 241)]
LINES = []
for i in range(4):
    LINES += pick(10 * i, "N1", "VAC1", ramp, 224 + i % 2, "RES_0603-10k", 38, 21)
LINES += pick(50, "N1", "VAC1", ramp, 232, "RES_0603-10k", 1, 0)                     # foil: empty, accepted
LINES += pick(60, "N2", "VAC2", ramp, 225, "CAP 2220 1kV", 139, 122)                 # part id with spaces
LINES += ["2026-11-26 10:01:30.000 ReferenceNozzle DEBUG: N2.unloadNozzleTip(): Start\n"]
LINES += pick(100, "N2", "VAC2", ramp, 226, "CAP 2220 1kV", 140, 122)
lines = LINES
