# Orientation Setup with real OpenPnP classes + the real feeder mainboard (KiCad), headless.
# Renders the dialogs to PNG (argv[3]) for visual review.  tests/run_orientation_headless.sh
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "lib"))
sandbox, kicad, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
if not os.path.exists(os.path.join(sandbox, "lumen", "lib")):
    os.makedirs(os.path.join(sandbox, "lumen"))
    os.symlink(os.path.join(ROOT, "lib"), os.path.join(sandbox, "lumen", "lib"))

from java.awt.image import BufferedImage
from java.io import File
from java.lang import System as _Sys
from javax.imageio import ImageIO
from org.openpnp.model import (Configuration, Board, BoardLocation, Job, Length, LengthUnit, Location, Part,
                               Placement, Abstract2DLocatable, Package)
from org.openpnp.machine.photon import PhotonFeeder
Configuration.initialize(File(sandbox))
Configuration.get().load()
machine = Configuration.get().getMachine()
mm = LengthUnit.Millimeters
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    _Sys.out.println("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


class FakeFrame(object):
    def __init__(self, title=""):
        self.title, self.content, self.disposed = title, None, False

    def __getattr__(self, n):
        return lambda *a, **k: None

    def setContentPane(self, c):
        self.content = c

    def dispose(self):
        self.disposed = True


class FakeOptionPane(object):
    OK_OPTION = YES_OPTION = 0
    OK_CANCEL_OPTION = YES_NO_OPTION = 2
    answer, messages = 0, []

    @classmethod
    def showMessageDialog(cls, p, m, *a):
        cls.messages.append(str(m))

    @classmethod
    def showConfirmDialog(cls, p, m, *a):
        cls.messages.append(str(m))
        return cls.answer


class FakeScripting(object):
    def getScriptsDirectory(self):
        return File(os.path.join(sandbox, "scripts"))


class Tab(object):
    def __init__(self, j):
        self.j = j

    def getJob(self):
        return self.j


class Gui(object):
    def __init__(self, j):
        self.t = Tab(j)

    def getJobTab(self):
        return self.t


# parts named like the board's footprints, placements = refs of the real board
spec = [("U1", "STM32F031C6", 90.0), ("D6", "D-SOD123", 0.0), ("C12", "CP-6.3x7.7", -90.0), ("R1", "R0805", 0.0)]
parts, feeders = {}, {}
board = Board()
board.setName("feeder-mobo")
for slot, (ref, pid, rot) in enumerate(spec, start=2):
    p = Part(pid)
    p.setHeight(Length(1.0, mm))
    Configuration.get().addPart(p)
    parts[pid] = p
    pl = Placement(ref)
    pl.setPart(p)
    pl.setLocation(Location(mm, 10, 10, 0, rot))
    pl.setSide(Abstract2DLocatable.Side.Top)
    board.addPlacement(pl)
    f = PhotonFeeder()
    f.setSlotAddress(slot)
    f.setHardwareId("%02x" % slot * 12)
    f.setPart(p)
    f.setOffset(Location(mm, 0, 0, 0, 90.0 if ref == "D6" else 0.0))
    f.setEnabled(True)
    machine.addFeeder(f)
    f.getSlot().setLocation(Location(mm, 20 * slot, 300, 10, 0))
    feeders[ref] = f
bl = BoardLocation(board)
bl.setGlobalSide(Abstract2DLocatable.Side.Top)
job = Job()
job.addBoardOrPanelLocation(bl)
gui = Gui(job)


def _exec(code, g):
    exec code in g


def load(name):
    src = open(os.path.join(ROOT, "scripts", "Lumen", name)).read().rstrip().split("\n")
    g = {"__name__": "__main__", "scripting": FakeScripting(), "machine": machine, "gui": gui}
    _exec(compile("\n".join(src[:-1]) + "\n", name, "exec"), g)
    g["JFrame"] = FakeFrame
    g["JOptionPane"] = FakeOptionPane
    g["oppnp"].JOptionPane = FakeOptionPane
    g["oppnp"].job_state = lambda gu: "Stopped"
    return g, src[-1].replace("()", "")


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


g, cls = load("Orientation_Setup.py")
ui = g[cls]()
rows0 = list(ui.model.rows)
check("without CAD: rows for job parts, CAD unknown", rows0 and all("CAD pin 1 unknown" in r["status"] or r["matters"] is False
                                                                for r in rows0), [r["status"] for r in rows0][:2])
ui.add_source("kicad", kicad)
rows = dict((r["part_id"], r) for r in ui.model.rows)
check("KiCad import: STM32 pin 1 TL (auto)", rows["STM32F031C6"]["cad_dot"] == "TL" and not rows["STM32F031C6"]["cad_ok"])
check("diode / electrolytic: pin-1 end left -> TL, matters", rows["D-SOD123"]["cad_dot"] == "TL" and rows["CP-6.3x7.7"]["cad_dot"] == "TL"
      and rows["CP-6.3x7.7"]["matters"])
check("resistor hidden (orientation not relevant)", "R0805" not in rows)
ui.only.setSelected(False)
ui.refresh()
check("resistor listed when the filter is off", "R0805" in dict((r["part_id"], r) for r in ui.model.rows))
ui.only.setSelected(True)
ui.refresh()
rows = dict((r["part_id"], r) for r in ui.model.rows)
p1 = render(ui.frame.content, "orientation-list-before.png")

# STM32: the part sits in the feeder with pin 1 top-RIGHT (seen from above) -> needs -90
idx = [i for i, r in enumerate(ui.model.rows) if r["part_id"] == "STM32F031C6"][0]
ui.table.setRowSelectionInterval(idx, idx)
dlg = ui.check()
check("left square preset from the feeder rotation (0 deg -> TL)", dlg.left.dot == "TL")
content = dlg.frame.content
content.setSize(content.getPreferredSize())
layout(content)
mx, my = dlg.left.mark_xy("TR")
dlg.left.click(int(mx), int(my))
check("click on the top-right corner selects TR", dlg.left.dot == "TR")
check("rotation shown: -90 deg, change needed", "-90" in str(dlg.result.getText()) and "CHANGE" in str(dlg.result.getText()),
      dlg.result.getText())
p2 = render(content, "orientation-check-stm32.png")
FakeOptionPane.answer = 0
dlg.confirm(True)
f = feeders["U1"]
check("applied: Photon pick rotation now -90", abs(f.getPickLocation().getRotation() + 90) < 1e-6, f.getPickLocation())
rows = dict((r["part_id"], r) for r in ui.model.rows)
check("list: STM32 CORRECT (confirmed)", rows["STM32F031C6"]["status"].startswith("CORRECT"), rows["STM32F031C6"]["status"])

# diode: feeder at 90 deg, mark seen where the preset says -> confirm without change
idx = [i for i, r in enumerate(ui.model.rows) if r["part_id"] == "D-SOD123"][0]
ui.table.setRowSelectionInterval(idx, idx)
dlg = ui.check()
check("diode preset from 90 deg feeder: TL -> BL", dlg.left.dot == "BL", dlg.left.dot)
check("feeder square shows the predicted pads (pin 1 at the bottom)", dlg.left.pads and
      [p for p in dlg.left.pads if p[0] == "1"][0][2] < 0, dlg.left.pads)
content = dlg.frame.content
content.setSize(content.getPreferredSize())
layout(content)
p3 = render(content, "orientation-check-diode.png")
dlg.confirm(False)
rows = dict((r["part_id"], r) for r in ui.model.rows)
check("diode CORRECT without change", rows["D-SOD123"]["status"].startswith("CORRECT") and
      abs(feeders["D6"].getPickLocation().getRotation() - 90) < 1e-6, rows["D-SOD123"]["status"])
check("electrolytic still to check", "confirmed" not in rows["CP-6.3x7.7"]["status"].lower() or "not" in rows["CP-6.3x7.7"]["status"])
check("summary counts", "2 correct" in str(ui.summary.getText()), ui.summary.getText())
p4 = render(ui.frame.content, "orientation-list-after.png")
st = json.load(open(os.path.join(sandbox, "lumen", "orientation.json")))
check("store: confirmations + applied rotation + source", st["parts"]["STM32F031C6"]["cad"]["confirmed"]
      and st["parts"]["STM32F031C6"]["feeders"][str(f.getId())]["applied"] == -90.0 and st["sources"] == ["kicad:" + kicad])
ui2 = load("Orientation_Setup.py")[0][cls]()
check("reopen: sources reloaded, status kept", dict((r["part_id"], r) for r in ui2.model.rows)["STM32F031C6"]["status"].startswith("CORRECT"))
_Sys.out.println("PNG: %s %s %s %s" % (p1, p2, p3, p4))
_Sys.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
_Sys.exit(0 if all(results) else 1)
