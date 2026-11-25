# -*- coding: utf-8 -*-
# Every Lumen tool opened headless (real OpenPnP classes, copy of the user's configuration, the test
# job, NO machine): every button / checkbox / input / table column must have a description, the
# folding help panel must open; windows rendered to PNG for review.
import os
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
ROOT = os.path.join(HERE, "..")
sandbox, jobfile, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(os.path.join(sandbox, "lumen"))
os.symlink(os.path.join(ROOT, "lib"), os.path.join(sandbox, "lumen", "lib"))
sys.path.insert(0, os.path.join(ROOT, "lib"))
from java.awt.image import BufferedImage
from java.awt import Dimension
from java.io import File
from java.lang import System as S
from javax.imageio import ImageIO
from org.openpnp.model import Configuration
Configuration.initialize(File(sandbox))
Configuration.get().load()
machine = Configuration.get().getMachine()
job = Configuration.get().loadJob(File(jobfile))
from lumen import helptext, uihelp
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    S.out.println("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


class Frame(object):
    instances = []

    def __init__(self, t=""):
        self.title, self.content, self.visible = t, None, False
        Frame.instances.append(self)

    def setContentPane(self, c):
        self.content = c

    def getContentPane(self):
        return self.content

    def setVisible(self, v):
        self.visible = v

    def __getattr__(self, n):
        return lambda *a, **k: None


class Pane(object):
    OK_OPTION = YES_OPTION = 0
    NO_OPTION = 1
    OK_CANCEL_OPTION = YES_NO_OPTION = 2
    PLAIN_MESSAGE = -1

    @classmethod
    def showMessageDialog(cls, *a):
        pass

    @classmethod
    def showConfirmDialog(cls, *a):
        return 1


class Scr(object):
    def getScriptsDirectory(self):
        return File(os.path.join(sandbox, "scripts"))


class Tab(object):
    def getJob(self):
        return job

    def getJobPlacementsPanel(self):
        return None


class G(object):
    def getJobTab(self):
        return Tab()


def _exec(code, g):
    exec code in g


def layout(c):
    c.doLayout()
    for k in c.getComponents():
        layout(k)


def render(panel, name):
    d = panel.getPreferredSize()
    panel.setSize(d)
    layout(panel)
    img = BufferedImage(d.width, d.height, BufferedImage.TYPE_INT_RGB)
    g2 = img.createGraphics()
    panel.paint(g2)
    from java.awt import Graphics2D
    Graphics2D.dispose(g2)
    p = os.path.join(outdir, name)
    ImageIO.write(img, "png", File(p))
    return p


TOOLS = [("Feeder_Part_Check.py", "part_check"), ("Board_Z_Probe.py", "board_z"), ("Nozzle_Offset_Calibration.py", "nozzle_cal"),
         ("Placement_Inspection.py", "inspection"), ("Feeder_Firmware_Update.py", "firmware_update"),
         ("Job_Readiness.py", "job_readiness"), ("Last_Placements.py", "last_placements"), ("Orientation_Setup.py", "orientation"),
         ("Pick_Offset_Learning.py", "pick_learning"), ("Preflight.py", "preflight"),
         ("Feeder_Assistant.py", "feeder_assist"), ("Machine_Calibration.py", "machine_cal")]
OBJS = {}
for script, key in TOOLS:
    src = open(os.path.join(ROOT, "scripts", "Lumen", script)).read().rstrip().split("\n")
    g = {"__name__": "__main__", "scripting": Scr(), "machine": machine, "gui": G()}
    Frame.instances = []
    try:
        _exec(compile("\n".join(src[:-1]) + "\n", script, "exec"), g)
        g["JFrame"] = Frame
        g["JOptionPane"] = Pane
        g["oppnp"].JOptionPane = Pane
        obj = g[src[-1].replace("()", "").strip()]()
        OBJS[script] = (g, obj)
    except Exception as e:
        check("%s opens" % script, False, e)
        continue
    fr = Frame.instances[0]
    content = fr.content
    miss = uihelp.missing(content, key)
    check("%-30s every option / button / input / column described" % script, not miss, miss[:6])
    hp = [c for c in uihelp._walk(content) if hasattr(c, "getClientProperty") and c.getClientProperty("lumen.help.toggle")]
    ok = False
    if hp:
        btn = hp[0].getClientProperty("lumen.help.toggle")
        sp = hp[0].getClientProperty("lumen.help.text")
        btn.doClick()
        ok = sp.isVisible() and btn.getText().startswith(u"▾")
        if script in ("Feeder_Part_Check.py", "Board_Z_Probe.py"):
            render(content, "help-%s-open.png" % key)
        btn.doClick()
        ok = ok and not sp.isVisible()
    check("%-30s help panel opens and closes" % script, ok)
    if script == "Machine_Calibration.py":
        render(content, "machine_cal-steps.png")
        obj.show_question("Change the nozzle tip by hand",
                          "<p>OpenPnP moved N1 to the tip change position.</p><p><b>Please perform a manual nozzle tip N045 "
                          "unload from nozzle N1 and a manual nozzle tip N08 load on nozzle N1 now.</b></p><p>Pull the old "
                          "tip straight down, put it into its holder slot, push the new tip on until it sits straight. "
                          "Then press <i>Done</i>.</p>", ["cal-tip-swap.png"], ["Done", "Cancel"])
        btns = [c.getText() for c in uihelp._walk(obj.right) if c.getClass().getSimpleName() == "JButton"]
        pics = [c for c in uihelp._walk(obj.right) if c.getClass().getSimpleName() == "JLabel" and c.getIcon() is not None]
        check("calibration question shows its picture and buttons", btns == ["Done", "Cancel"] and len(pics) == 1, (btns, len(pics)))
        render(content, "machine_cal-ask.png")
        obj.show_step()
    if script == "Feeder_Part_Check.py":
        render(content, "help-%s-closed.png" % key)
        tips = [c.getToolTipText() for c in uihelp._walk(content) if hasattr(c, "getText") and unicode(c.getText()).startswith(u"return fails")]
        check("example tooltip (return fails option) is the concrete text", tips and "Off (default)" in tips[0], tips[:1])
        hdr = [c for c in uihelp._walk(content) if c.getClass().getSimpleName() == "JTable"][0].getTableHeader()
        check("table header visible in the scroll pane (column tips)", hdr.isShowing() or hdr.getParent() is not None, hdr.getParent())
    if script == "Feeder_Part_Check.py" and len(obj.opt_model.rows) >= 2:
        import json as _j
        from java.lang import Integer as _I
        sf = os.path.join(sandbox, "lumen", "settings.json")
        rows = obj.opt_model.rows
        obj.tabs.setSelectedIndex(1)
        obj.opt_table.setRowSelectionInterval(0, 1)
        r0 = obj.opt_table.convertRowIndexToModel(0)
        obj.opt_model.setValueAt(_I(2), r0, 4)
        obj.opt_model.setValueAt("discard + pick again", r0, 10)
        d = _j.load(open(sf))
        hw = [obj.opt_model.rows[obj.opt_table.convertRowIndexToModel(i)]["hwid"] for i in (0, 1)]
        own = [d.get("feeder_options", {}).get(h, {}) for h in hw]
        check("options tab: edit with 2 rows highlighted -> own value for both", all(o.get("every") == 2 and o.get("action") == "discard"
                                                                                   for o in own), own)
        others = [x["hwid"] for x in rows if x["hwid"] not in hw]
        check("other feeders unchanged (defaults)", all(h not in d.get("feeder_options", {}) for h in others), len(others))
        shown = [str(obj.opt_model.getValueAt(r0, c)) for c in (4, 10, 12)]
        check("table shows the own values", shown == ["2", "discard + pick again", "own: action, every"], shown)
        obj.opt_table.setRowSelectionInterval(0, 0)
        obj.opt_model.setValueAt(_I(0), r0, 4)
        check("invalid value (every 0) refused, old value kept", _j.load(open(sf))["feeder_options"][hw[0]]["every"] == 2)
        obj.opt_model.setValueAt(True, r0, 3)
        obj.opt_table.setRowSelectionInterval(0, 1)
        render(content, "help-part_check-options.png")
        obj.reset_highlighted()
        d = _j.load(open(sf))
        check("reset highlighted: back to defaults, 'While feeding' tick kept",
              d.get("feeder_options", {}).get(hw[0]) == {"watch": True} and hw[1] not in d.get("feeder_options", {}),
              d.get("feeder_options"))
        obj.every.setText("4")
        obj.save_defaults()
        d = _j.load(open(sf))
        check("Save defaults: feedwatch / pickvac defaults stored, own values kept", d["feedwatch"]["every"] == 4
              and d["feeder_options"].get(hw[0]) == {"watch": True} and str(obj.opt_model.getValueAt(r0, 4)) == "4",
              (d["feedwatch"], d["feeder_options"].get(hw[0]), str(obj.opt_model.getValueAt(r0, 4))))
    if script == "Orientation_Setup.py" and obj.model.rows:
        obj.table.setRowSelectionInterval(0, 0)
        Frame.instances = []
        dlg = obj.check()
        if Frame.instances:
            m2 = uihelp.missing(Frame.instances[0].content, "orientation_check")
            check("Orientation check dialog described", not m2, m2[:4])
# ---------------------------------------------------------------- zoom / pan (lumen.zoomview) and its users
from java.awt import Color as _C
from java.awt.image import BufferedImage as _BI
from javax.swing import JPanel as _JP
from lumen import zoomview
p = _JP()
p.setSize(400, 300)
zp = zoomview.ZoomPan(p)
before = zp.to_view(100, 80)
zp.wheel(100, 80, -3)                                    # zoom in 1.25^3 at (100, 80)
after = zp.to_view(100, 80)
check("zoom: wheel zooms in and keeps the point under the pointer", abs(zp.scale() - 1.953125) < 1e-6
      and abs(after[0] - before[0]) < 1e-6 and abs(after[1] - before[1]) < 1e-6, (zp.scale(), after))
x2 = zp.to_view(300, 200)
check("zoom: other points map back through the zoom", abs(x2[0] - (100 + 200 / 1.953125)) < 1e-6, x2)
zp.drag(-5000, -5000)
check("zoom: drag is kept inside the picture", zp.to_view(400, 300)[0] <= 400.0001 and zp.to_view(400, 300)[1] <= 300.0001,
      zp.to_view(400, 300))
zp.reset()
check("zoom: right click (reset) = fit", zp.scale() == 1.0 and zp.to_view(10, 20) == (10.0, 20.0))
img = _BI(200, 100, _BI.TYPE_INT_RGB)
v = zoomview.ImageView(img)
v.setSize(400, 218)                                      # 18 px status line
check("image view: centre of the panel = centre of the image", v.to_image(200, 100) == (100.0, 50.0), v.to_image(200, 100))
v.zp.wheel(300, 150, -2)
ip = v.to_image(300, 150)
check("image view: zoomed click -> the same image pixel as before zooming", abs(ip[0] - 150) < 1e-6 and abs(ip[1] - 75) < 1e-6, ip)

g_o, o_obj = OBJS["Orientation_Setup.py"]
sq = g_o["DotSquare"]("t", "s", None)
sq.setSize(320, 380)
mx, my = sq.mark_xy("TR") if "TR" in g_o["POS"] else sq.mark_xy(list(g_o["POS"])[0])
corner = "TR" if "TR" in g_o["POS"] else list(g_o["POS"])[0]
sq.zp.wheel(mx, my, -6)                                  # zoom in on that corner
sx, sy = mx, my                                          # the corner stays under the pointer
sq.click(*sq.zp.to_view(sx, sy))
check("test placement photo: zoomed in, a click on a corner sets that corner", sq.dot == corner, (sq.dot, corner))
render(sq, "zoom-dotsquare.png")

# test placement photo: whole camera frame behind the square; zoom OUT shows the rest of the frame
from java.awt import Graphics2D as _G2
fr = _BI(1280, 720, _BI.TYPE_INT_RGB)
gg = fr.createGraphics()
_G2.setColor(gg, _C(0, 0, 255)); _G2.fillRect(gg, 0, 0, 1280, 720)             # blue: outside the crop
_G2.setColor(gg, _C(0, 200, 0)); _G2.fillRect(gg, 640 - 150, 360 - 150, 300, 300)  # green: the 300 px crop
_G2.setColor(gg, _C(255, 0, 0)); _G2.fillRect(gg, 630, 350, 20, 20)              # red: the centre
_G2.dispose(gg)
sq2 = g_o["DotSquare"]("t", "s", None)
sq2.setSize(320, 380)
sq2.photo, sq2.photo_px = fr, 300


def _px(panel, x, y):
    im = _BI(320, 380, _BI.TYPE_INT_RGB)
    g2 = im.createGraphics()
    panel.paint(g2)
    _G2.dispose(g2)
    c = _C(im.getRGB(int(x), int(y)))
    return (c.getRed() > 150, c.getGreen() > 150, c.getBlue() > 150)


cx, cy, s = sq2.geometry()
check("photo: the crop fills the square (centre red, inside green)",
      _px(sq2, cx, cy) == (True, False, False) and _px(sq2, cx + s * 0.45, cy) == (False, True, False),
      (_px(sq2, cx, cy), _px(sq2, cx + s * 0.45, cy)))
for _ in range(20):
    sq2.zp.wheel(10, 10, 1)                                   # zoom out (pointer anywhere)
check("photo: zoom out goes below the fit, down to 0.1x", abs(sq2.zp.scale() - 0.1) < 1e-6, sq2.zp.scale())
check("photo: zoomed out around the square centre", max(abs(a - b) for a, b in zip(sq2.zp.to_view(cx, cy), (cx, cy))) < 1e-6)
# at 0.1x: crop half = 150 * s/300 * 0.1 (~12 px), frame half = 640 * s/300 * 0.1 (~53 px)
check("photo: zoomed out, the frame outside the crop is visible", _px(sq2, cx + s * 0.12, cy) == (False, False, True),
      _px(sq2, cx + s * 0.12, cy))
corner2 = list(g_o["POS"])[0]
m2x, m2y = sq2.mark_xy(corner2)
sx2, sy2 = cx + (m2x - cx) * 0.1, cy + (m2y - cy) * 0.1      # where that corner is drawn at 0.1x
sq2.click(*sq2.zp.to_view(sx2, sy2))
check("photo: zoomed out, a click on a corner still sets that corner", sq2.dot == corner2, (sq2.dot, corner2))
sq2.zp.wheel(cx, cy, -1)
check("photo: wheel zooms back in from below the fit", abs(sq2.zp.scale() - 0.125) < 1e-6, sq2.zp.scale())
render(sq2, "zoom-out-dotsquare.png")
sq2.zp.reset()

# Feeder Part Check: only the open job's feeders, offset set by hand in the photo
g_p, pc = OBJS["Feeder_Part_Check.py"]
jp = g_p["job_part_ids"](G())
pc.job_only.setSelected(True)
pc.apply_filter()
vis = pc.table.getRowCount()
want = len([x for x in pc.model.rows if x["feeder"].getPart() is not None and str(x["feeder"].getPart().getId()) in jp])
check("part check: 'only feeders of the open job' shows exactly the job's feeders", vis == want and 0 < vis < len(pc.model.rows),
      (vis, want, len(pc.model.rows)))
pc.select(lambda x: True)
check("part check: Select all with the filter ticks only the shown feeders", len(pc.selected()) == vis)
pc.job_only.setSelected(False)
pc.apply_filter()
check("part check: filter off shows all feeders again", pc.table.getRowCount() == len(pc.model.rows))
row = pc.model.rows[0]
f0 = row["feeder"]
f0.setSlotAddress(3)                                     # offline: no bus; slot 3 has a location in this config
shot = _BI(1000, 600, _BI.TYPE_INT_RGB)
from javax.imageio import ImageIO as _IO
from java.io import File as _F
ppath = os.path.join(outdir, "fake-check.png")
_IO.write(shot, "png", _F(ppath))
row["res"] = {"error": "no sprocket holes found", "image": ppath, "upp": (0.01, 0.01), "size": (1000, 600), "slot": 1}
row["status"] = g_p["verdict"](row["res"])
check("part check: NOT FOUND points to 'Set offset by hand'", "Set offset by hand" in row["status"], row["status"])
pc.tabs.setSelectedIndex(0)
pc.table.setRowSelectionInterval(pc.table.convertRowIndexToView(0), pc.table.convertRowIndexToView(0))
created = []
zoomview.JFrame = lambda t: (created.append(Frame(t)) or created[-1])
g_p["JOptionPane"].showConfirmDialog = classmethod(lambda cls, *a: 0)
before = f0.getPickLocation()
pc.hand_offset()
win = created[-1] if created else None
views = [c for c in uihelp._walk(win.content) if isinstance(c, zoomview.ImageView)] if win else []
if views:
    hv = views[0]
    hv.on_click(500 + 30, 300 - 50)                      # 0.30 mm right, 0.50 mm up of the pick location
    apply_btn = [c for c in uihelp._walk(win.content) if hasattr(c, "getText") and c.getText() == "Apply this offset"][0]
    apply_btn.doClick()
after = f0.getPickLocation()
d = (after.getX() - before.getX(), after.getY() - before.getY())
check("part check: click in the photo + Apply moves the pick location by the clicked offset",
      abs(d[0] - 0.30) < 1e-6 and abs(d[1] - 0.50) < 1e-6 and row["status"].startswith("offset set by hand"), (d, row.get("status")))

# Feeder Assistant: Look at this feeder (camera) - synthetic camera picture
g_a, fa = OBJS["Feeder_Assistant.py"]
fa.ptable.setRowSelectionInterval(0, 0)
fa.show_feeders()
fr_i = [i for i, r in enumerate(fa.fmodel.rows) if not r.get("sep")][0]
fa.ftable.setRowSelectionInterval(fr_i, fr_i)
cam = _BI(800, 500, _BI.TYPE_INT_RGB)
g_a["feedercheck"].look = lambda m, f: (cam, (0.0108, 0.0108), f.getPickLocation())
g_a["oppnp"].run_machine_task = lambda m, fn: fn()
g_a["oppnp"].confirm_ready = lambda *a: True
g_a["oppnp"].in_background = lambda fn: fn()
from javax.swing import SwingUtilities as _SU
from java.lang import Runnable as _R
class _Now(_R):
    def run(self):
        pass
created[:] = []
fa.look()
_SU.invokeAndWait(_Now())
_SU.invokeAndWait(_Now())
lw = [w for w in created if "intended component" in w.title]
check("feeder assistant: 'Look at this feeder' opens the zoomable camera picture with the job part", len(lw) == 1 and
      any(isinstance(c, zoomview.ImageView) for c in uihelp._walk(lw[0].content)), [w.title for w in created])
if lw:
    lw[0].content.setPreferredSize(Dimension(1000, 700))
    render(lw[0].content, "feeder-assist-look.png")

# The scripts' module level through OpenPnP's own script engine (JSR-223, like Scripts > Lumen > ...):
# there globals() is a Java scope object, not a dict (Preflight crashed on globals().items(), 2026-11-25).
from javax.script import ScriptEngineManager, SimpleBindings
eng = ScriptEngineManager().getEngineByExtension("py")
for script, key in TOOLS:
    src = open(os.path.join(ROOT, "scripts", "Lumen", script)).read().rstrip().split("\n")
    b = SimpleBindings()
    b.put("scripting", Scr())
    b.put("machine", machine)
    b.put("gui", G())
    try:
        eng.eval("\n".join(src[:-1]) + "\n", b)
        check("%-30s module level runs in OpenPnP's script engine" % script, True)
    except Exception as e:
        check("%-30s module level runs in OpenPnP's script engine" % script, False, str(e)[:200])
S.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
S.exit(0 if all(results) else 1)
