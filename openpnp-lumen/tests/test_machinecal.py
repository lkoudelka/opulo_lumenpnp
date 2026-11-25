# Machine Calibration: pure helpers (CPython).   python3 tests/test_machinecal.py
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from lumen import machinecal as mc  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


# order and coverage of the Opulo V4.1 guide
keys = [s.key for s in mc.STEPS]
opulo = ["primary_fid", "secondary_fid", "n1_primary", "n1_secondary", "n2_primary", "bottom_cam", "precise",
         "settle_top", "settle_bottom", "backlash_x", "backlash_y", "homing_prep"]
check("every Opulo V4.1 step is there, in the guide's order", [k for k in keys if k in opulo] == opulo, keys)
check("safety/backup first, verification last", keys[0] == "prepare" and keys[-1] == "verify")
check("tips go back before the target is carried (precise)", keys.index("tips_back") < keys.index("precise"))
check("10 fundamental Opulo pages (precise N1 + N2 = one step: the target is carried once) + 2 optional",
      [s.kind for s in mc.STEPS].count("fundamental") == 9 and "N1 and N2" in mc.BY_KEY["precise"].title
      and [s.kind for s in mc.STEPS].count("optional") == 2)
check("every step links an Opulo V4.1 page", all(s.doc.startswith("https://docs.opulo.io/openpnp/v4-1/") for s in mc.STEPS))
check("every step has an engine method", all(hasattr(mc.Calibrator, "step_" + k) for k in keys))

# detection check
ok, why = mc.check_detection(96.0, 97.0, 3.0, 1080)
check("detection matching the known size is accepted", ok, why)
ok, why = mc.check_detection(160.0, 97.0, 3.0, 1080)
check("much bigger circle (another ring / the target) is refused", not ok and "+65 %" in why, why)
ok, why = mc.check_detection(97.0, 97.0, 400.0, 1080)
check("circle far from the centre is refused", not ok and "centre" in why, why)
check("nothing detected is refused", not mc.check_detection(None, 97.0, 0, 1080)[0])
check("unknown expected size -> by eye", not mc.check_detection(50.0, 0, 0, 1080)[0])

# contact probe window
check("probe from stored Z + 1.5, 2.5 mm travel", mc.probe_window(5.16, 26.5) == (6.66, 6.66 - 2.5),
      mc.probe_window(5.16, 26.5))
check("no stored Z -> person brings the nozzle close", mc.probe_window(0.0, 26.5) is None
      and mc.probe_window(float("nan"), 26.5) is None and mc.probe_window(None, 26.5) is None)
w = mc.probe_window(26.4, 26.5)
check("start never at / above safe Z", w is None or w[0] < 26.5, w)
check("Z change limit", mc.z_change_ok(5.16, 5.30) and not mc.z_change_ok(5.16, 6.5) and mc.z_change_ok(0.0, 9.0))

# issue titles = OpenPnP 2.x strings (checked against the installed jar's constant pool)
check("titles", mc.issue_title("n2_primary", nozzle="N2") == "Nozzle N2 offsets for the primary fiducial."
      and mc.issue_title("bottom_cam", camera="Bottom") == "Determine the up-looking camera Bottom position and initial calibration."
      and mc.issue_title("precise", nozzle="N1") == u"Calibrate precise camera ↔ nozzle N1 offsets."
      and mc.issue_title("backlash", axis="x") == "Calibrate backlash compensation for axis x.")


class JEx(Exception):
    def __init__(self, cls, msg, cause=None):
        Exception.__init__(self, msg)
        self.cls, self.msg, self.cause = cls, msg, cause

    def getClass(self):
        c = self.cls

        class K(object):
            def getName(self):
                return c
        return K()

    def getMessage(self):
        return self.msg

    def getCause(self):
        return self.cause


inner = JEx("org.openpnp.util.UiUtils$ExceptionWithContinuation",
            "Task interrupted: Please perform\na manual nozzle tip N045 unload from nozzle N1 and\n"
            "a manual nozzle tip N08 load on nozzle N1 now.")
e = JEx("org.openpnp.machine.reference.ReferenceNozzle$ManualLoadException", "x", inner)
t = mc.manual_change_text(e)
check("manual tip change: OpenPnP's instructions are shown", t is not None and t.startswith("Please perform")
      and "N08 load on nozzle N1" in t, repr(t))
check("other errors are not taken for a tip change", mc.manual_change_text(JEx("java.lang.Exception", "boom")) is None)
check("diff rows", mc.diff_rows({"a": "1", "b": "2"}, {"a": "1", "b": "3", "c": "4"}) == [("b", "2", "3"), ("c", None, "4")])

print("%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
