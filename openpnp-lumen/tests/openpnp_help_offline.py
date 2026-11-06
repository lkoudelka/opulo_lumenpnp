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
         ("Pick_Offset_Learning.py", "pick_learning"), ("Preflight.py", "preflight")]
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
    if script == "Feeder_Part_Check.py":
        render(content, "help-%s-closed.png" % key)
        tips = [c.getToolTipText() for c in uihelp._walk(content) if hasattr(c, "getText") and unicode(c.getText()).startswith(u"return fails")]
        check("example tooltip (return fails option) is the concrete text", tips and "Off (default)" in tips[0], tips[:1])
        hdr = [c for c in uihelp._walk(content) if c.getClass().getSimpleName() == "JTable"][0].getTableHeader()
        check("table header visible in the scroll pane (column tips)", hdr.isShowing() or hdr.getParent() is not None, hdr.getParent())
    if script == "Orientation_Setup.py" and obj.model.rows:
        obj.table.setRowSelectionInterval(0, 0)
        Frame.instances = []
        dlg = obj.check()
        if Frame.instances:
            m2 = uihelp.missing(Frame.instances[0].content, "orientation_check")
            check("Orientation check dialog described", not m2, m2[:4])
S.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
S.exit(0 if all(results) else 1)
