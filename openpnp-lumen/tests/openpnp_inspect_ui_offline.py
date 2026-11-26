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

    def setContentPane(self, c):
        self.content = c


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
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    res.update(upp=truth["upp"], size_source=src_, axis_rot=0.0, _image=img,     # never the test data: Set as OK
               image=os.path.join(out_dir, "%s.png" % pl.getId()))               # rewrites the image
    ins.save_annotated(res, str(pl.getId()))
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
fail = caps[2]
vi = d.table.convertRowIndexToView(d.model.rows.index(fail))
d.table.setRowSelectionInterval(vi, vi)
iv = g["inspectview"]
iv.JFrame = Frame
iv.JOptionPane = Pane
v = d.show_image()
check("Show image: one window with the result drawn in, << Previous / Next >>, Camera to part / Set as OK / NOT OK / "
      "Draw where the part is", v is not None and v.x is fail and v.view.image is not None
      and v.view.image is not fail["res"]["_image"] and sorted(v.buttons) == sorted(iv.BUTTONS), v and sorted(v.buttons))
order = [x["ref"] for x in v.rows()]
seen = [v.x["ref"]]
v.step(-1)
while v.x["ref"] != seen[-1]:
    seen.append(v.x["ref"])
    v.step(-1)
first = v.x
for _ in range(len(order) + 1):
    v.step(1)
check("Previous / Next walk the inspected rows in the table's order and stop at the ends",
      first["ref"] == order[0] and v.x["ref"] == order[-1] and len(order) == 3, (order, first["ref"], v.x["ref"]))
v.only_bad.setSelected(True)
check("'only not OK': Next / Previous skip the OK rows", all(not x["res"]["verdict"].startswith("OK") or x is v.x
                                                           for x in v.rows()), [x["ref"] for x in v.rows()])
v.only_bad.setSelected(False)
if os.environ.get("INSPECT_PNG"):                       # look at the window: render it headless
    from java.awt.image import BufferedImage
    from java.awt import Graphics2D

    def _lay(c):
        c.doLayout()
        for k in c.getComponents():
            _lay(k)
    pnl = v.frame.content
    pnl.setSize(pnl.getPreferredSize())
    _lay(pnl)
    _bi = BufferedImage(pnl.getWidth(), pnl.getHeight(), BufferedImage.TYPE_INT_RGB)
    _g = _bi.createGraphics()
    pnl.paint(_g)
    Graphics2D.dispose(_g)
    ImageIO.write(_bi, "png", File(os.environ["INSPECT_PNG"]))
# the offset row: detection says CHECK; the operator draws the part where it really is (here: around the image centre)
off_row = caps[1]
v.show(off_row)
im = off_row["res"]["_image"]
cx, cy, hw, hh = im.getWidth() / 2.0, im.getHeight() / 2.0, 0.5 / truth["upp"], 0.25 / truth["upp"]
v.draw()
check("Draw where the part is: the picture switches to rectangle mode", v.view.on_rect is not None)
v.drawn(cx - hw, cy - hh, cx + hw, cy + hh)
r = off_row["res"]
lp = os.path.join(d.root, "learning", d.run_name(off_row), "meta.json")
lm = json.load(open(lp))["parts"].get(off_row["ref"], {}) if os.path.isfile(lp) else {}
check("drawn at the placement location: verdict OK from the drawn position, magenta box kept, back to pan mode",
      r["verdict"].startswith("OK (part drawn by hand at +0.00 / +0.00") and r.get("hand_box") and v.view.on_rect is None,
      r["verdict"])
check("saved for learning: raw picture + meta (package, mm/px, rotation, the drawn box, truth ok, what was detected)",
      lm.get("truth") == "ok" and lm.get("hand_box") and lm.get("upp") == truth["upp"] and lm["detected"]["found"]
      and os.path.isfile(os.path.join(os.path.dirname(lp), off_row["ref"] + "-raw.png")), lm)
gs = ins.load_golden(d.root, "C_0402_1005Metric")
check("package with golden samples: one more sample, centred where the part was drawn",
      gs and len(gs["samples"]) == 2 and "drawn by hand" in gs["samples"][1]["source"], gs and [x.get("source") for x in gs["samples"]])
v.show(off_row)
v.draw()
v.drawn(cx - hw, cy - hh + 0.4 / truth["upp"], cx + hw, cy + hh + 0.4 / truth["upp"])
check("drawn 0.4 mm off the location: CHECK offset (0402 allows 0.15) and truth 'shifted' for learning",
      off_row["res"]["verdict"].startswith("CHECK: offset, part drawn by hand at +0.00 / -0.40")
      and json.load(open(lp))["parts"][off_row["ref"]]["truth"] == "shifted", off_row["res"]["verdict"])
was = fail["res"]["verdict"]
vi = d.table.convertRowIndexToView(d.model.rows.index(fail))
d.table.setRowSelectionInterval(vi, vi)
d.set_ok()
check("Set as OK (selected FAIL row, after the confirmation) -> 'OK (set by hand; was FAIL ...)'",
      fail["res"]["verdict"].startswith("OK (set by hand; was FAIL") and fail["res"].get("manual_ok"), fail["res"]["verdict"])
gs = ins.load_golden(d.root, "C_0402_1005Metric")
check("Set as OK learns: the confirmed placement is one more golden sample of its package",
      gs and len(gs["samples"]) == 4 and "set as OK" in gs["samples"][-1]["source"], gs and [x.get("source") for x in gs["samples"]])
d.select(lambda x: bool(x.get("res")) and not x["res"].get("verdict", "").startswith("OK"))
check("Select not OK no longer ticks it", not fail["sel"])
moved = []
ins.go_to_placement = lambda m, bl, pl: (moved.append(str(pl.getId())) or (bl.getLocation(), 1.0))
oppnp.in_background = lambda fn: fn()
oppnp.on_ui = lambda fn: fn()
_h = machine.isHomed()
machine.setHomed(True)
d.camera_to_part()
check("Camera to part: top camera over the selected placement", moved == [fail["ref"]] and "camera over" in d.info.getText(),
      (moved, d.info.getText(), Pane.msgs[-1:], machine.isHomed()))
machine.setHomed(_h)
ok_row = caps[0]
job.storePlacedStatus(ok_row["bl"], ok_row["pl"].getId(), True)
vi = d.table.convertRowIndexToView(d.model.rows.index(ok_row))
d.table.setRowSelectionInterval(vi, vi)
d.set_not_ok()                                            # dialog answered OK with the default reason
check("Set as NOT OK (default 'not assembled'): FAIL with the reason, NOT placed in the job (placed again next run)",
      ok_row["res"]["verdict"].startswith("FAIL: not assembled (part missing) (set by hand; was OK")
      and not job.retrievePlacedStatus(ok_row["bl"], ok_row["pl"].getId()), ok_row["res"]["verdict"])
d.export()
csvp = os.path.join(d.out_dir, "inspection.csv")
rows = open(csvp).read().strip().split("\n")
check("CSV report written with %d rows" % (len(rows) - 1), len(rows) == 4 and rows[0].startswith("board,ref,part"), csvp)
check("CSV: the accepted placement says 'set by hand'", any("set by hand" in r and fail["ref"] in r for r in rows[1:]))
S.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
S.exit(0 if all(results) else 1)
