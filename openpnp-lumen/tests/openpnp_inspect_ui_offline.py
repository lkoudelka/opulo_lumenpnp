# Scripts > Lumen > Placement Inspection, headless, NO machine: the user's job (read only), the camera
# replaced by the semi-synthetic test images (ok / offset / missing)
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
ROOT = os.path.join(HERE, "..")
sandbox, images, jobfile = sys.argv[1], sys.argv[2], sys.argv[3]
if not os.path.exists(os.path.join(sandbox, "lumen", "lib")):
    os.makedirs(os.path.join(sandbox, "lumen"))
    os.symlink(os.path.join(ROOT, "lib"), os.path.join(sandbox, "lumen", "lib"))
sys.path.insert(0, os.path.join(ROOT, "lib"))
from java.io import File
from java.lang import System as S
from javax.imageio import ImageIO
from org.openpnp.model import Configuration
Configuration.initialize(File(sandbox))
Configuration.get().load()
machine = Configuration.get().getMachine()
job = Configuration.get().loadJob(File(jobfile))
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    S.out.println("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


class Frame(object):
    def __init__(self, t=""):
        self.visible = False

    def __getattr__(self, n):
        return lambda *a, **k: None

    def setVisible(self, v):
        self.visible = v


class Pane(object):
    OK_OPTION = 0
    OK_CANCEL_OPTION = 2
    msgs = []

    @classmethod
    def showMessageDialog(cls, p, m, *a):
        cls.msgs.append(str(m))

    @classmethod
    def showConfirmDialog(cls, p, m, *a):
        return 0


class Scr(object):
    def getScriptsDirectory(self):
        return File(os.path.join(sandbox, "scripts"))


class Tab(object):
    def getJob(self):
        return job


class G(object):
    def getJobTab(self):
        return Tab()


def _exec(code, g):
    exec code in g


src = open(os.path.join(ROOT, "scripts", "Lumen", "Placement_Inspection.py")).read().rstrip().split("\n")
g = {"__name__": "__main__", "scripting": Scr(), "machine": machine, "gui": G()}
_exec(compile("\n".join(src[:-1]) + "\n", "Placement_Inspection.py", "exec"), g)
g["JFrame"] = Frame
g["JOptionPane"] = Pane
oppnp, ins = g["oppnp"], g["ins"]
oppnp.confirm_ready = lambda *a: True
oppnp.run_machine_task = lambda m, fn: fn()
truth = json.load(open(os.path.join(images, "truth.json")))
cycle = ["ok", "offset", "missing"]
calls = []


def fake_inspect(machine_, bl, pl, out_dir, root):
    """camera replaced: the n-th inspected placement gets the n-th test image (0402 body)"""
    name = cycle[len(calls) % len(cycle)]
    calls.append((str(pl.getId()), name))
    img = ImageIO.read(File(os.path.join(images, name + ".png")))
    pkg = pl.getPart().getPackage()
    length, width, src_ = ins.body_size(pkg)
    res = ins.analyse(img, truth["upp"], str(pkg.getId()), length, width, 0.0, root)
    res.update(upp=truth["upp"], size_source=src_, axis_rot=0.0, image=os.path.join(images, name + ".png"), _image=img)
    return res
ins.inspect_placement = fake_inspect
d = g["Inspection"]()
n_all = len(d.all_rows)
check("job placements listed (%d), filter 'only placed' shows %d" % (n_all, len(d.model.rows)), n_all > 0)
d.only_placed.setSelected(False)
d.filter()
check("filter off: all placements", len(d.model.rows) == n_all)
caps = [x for x in d.model.rows if x["package"] == "C_0402_1005Metric"][:3]
for x in caps:
    x["sel"] = True
d.run()
end = time.time() + 60
while d.busy and time.time() < end:
    time.sleep(0.2)
time.sleep(0.5)
v = [x["res"]["verdict"] for x in caps]
S.out.println("  verdicts: %s" % list(zip([c[0] for c in calls], [c[1] for c in calls], v)))
check("0402 body size known (package footprint body, else the KiCad name)", caps[0]["res"].get("size_source") in ("package body", "name 1005Metric"), caps[0]["res"].get("size_source"))
check("ok -> OK, offset -> CHECK offset, missing -> FAIL", v[0] == "OK" and v[1].startswith("CHECK") and "offset" in v[1]
      and v[2].startswith("FAIL"), v)
d.table.getRowSorter().toggleSortOrder(6)
check("table sorts by result", d.table.getRowCount() == len(d.model.rows))
i = d.model.rows.index(caps[0])
vi = d.table.convertRowIndexToView(i)
d.table.setRowSelectionInterval(vi, vi)
d.make_golden()
gp = ins.golden_path(d.root, "C_0402_1005Metric") + ".png"
check("golden sample saved for C_0402_1005Metric", os.path.exists(gp), gp)
calls[:] = []
d.run()
end = time.time() + 60
while d.busy and time.time() < end:
    time.sleep(0.2)
time.sleep(0.5)
g2 = [x["res"].get("golden") for x in caps]
check("second run uses the golden: ok ~1.0, missing < fail limit", g2[0] and g2[0]["score"] > 0.9 and g2[2]["score"] < ins.LIMITS["score_fail"],
      [round(x["score"], 2) for x in g2 if x])
d.export()
csvp = os.path.join(d.out_dir, "inspection.csv")
rows = open(csvp).read().strip().split("\n")
check("CSV report written with %d rows" % (len(rows) - 1), len(rows) == 4 and rows[0].startswith("board,ref,part"), csvp)
S.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
S.exit(0 if all(results) else 1)
