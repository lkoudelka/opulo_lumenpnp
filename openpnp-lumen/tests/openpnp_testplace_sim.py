# Test placement (Orientation Setup) on OpenPnP's SIMULATED machine (stock config: NullDriver, ImageCamera,
# SimulatedUpCamera), real OpenPnP classes, headless.  tests/run_testplace_sim.sh
# Feed -> pick -> place -> photo -> marks -> pick up again -> take back into the feeder, for a Photon feeder
# (SkipNext) and a tray feeder (feed count - 1).  No real machine is involved.
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "lib"))
sandbox, outdir = sys.argv[1], sys.argv[2]
if not os.path.exists(os.path.join(sandbox, "lumen", "lib")):
    os.makedirs(os.path.join(sandbox, "lumen"))
    os.symlink(os.path.join(ROOT, "lib"), os.path.join(sandbox, "lumen", "lib"))

from java.awt.image import BufferedImage
from java.io import File
from java.lang import System as _Sys
from javax.imageio import ImageIO
from org.openpnp.model import (Configuration, Board, BoardLocation, Footprint, Job, Length, LengthUnit, Location, Part,
                               Placement, Abstract2DLocatable, Package)
from org.openpnp.machine.photon import PhotonFeeder
from org.openpnp.machine.reference import ReferenceFeeder
from org.openpnp.machine.reference.feeder import ReferenceTrayFeeder
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
    NO_OPTION = 1
    CANCEL_OPTION = 2
    OK_CANCEL_OPTION = 2
    YES_NO_OPTION = 0
    YES_NO_CANCEL_OPTION = 1
    PLAIN_MESSAGE = -1
    answers, messages = [], []

    @classmethod
    def showMessageDialog(cls, p, m, *a):
        cls.messages.append(str(m))

    @classmethod
    def showConfirmDialog(cls, p, m, *a):
        cls.messages.append(str(m))
        return cls.answers.pop(0) if cls.answers else 0


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


head = machine.getDefaultHead()
n1 = head.getNozzles()[0]
tip = n1.getNozzleTip()
_Sys.out.println("simulated machine: nozzle %s tip %s, camera %s" % (n1.getName(), tip.getName(), head.getDefaultCamera().getName()))


def package(pid, w, h, pads):
    pk = Package(pid)
    fp = Footprint()
    fp.setBodyWidth(w)
    fp.setBodyHeight(h)
    for n, x, y in pads:
        p = Footprint.Pad()
        p.setName(n)
        p.setX(x)
        p.setY(y)
        p.setWidth(0.4)
        p.setHeight(0.4)
        fp.addPad(p)
    pk.setFootprint(fp)
    pk.addCompatibleNozzleTip(tip)
    Configuration.get().addPackage(pk)
    return pk


soic = package("SOIC-8-TEST", 4.0, 5.0, [("1", -1.9, 1.9), ("4", -1.9, -1.9), ("5", 1.9, -1.9), ("8", 1.9, 1.9)])
sod = package("SOD-123-TEST", 2.7, 1.6, [("1", -1.6, 0.0), ("2", 1.6, 0.0)])
parts = {}
for pid, pk in (("U-TEST", soic), ("D-TEST", sod)):
    p = Part(pid)
    p.setHeight(Length(1.0, mm))
    p.setPackage(pk)
    Configuration.get().addPart(p)
    parts[pid] = p

board = Board()
board.setName("test-board")
for ref, pid, x, y, rot in (("U1", "U-TEST", 10.0, 10.0, 90.0), ("U2", "U-TEST", 20.0, 10.0, 0.0), ("D1", "D-TEST", 10.0, 20.0, 0.0)):
    pl = Placement(ref)
    pl.setPart(parts[pid])
    pl.setLocation(Location(mm, x, y, 0, rot))
    pl.setSide(Abstract2DLocatable.Side.Top)
    board.addPlacement(pl)
bl = BoardLocation(board)
bl.setGlobalSide(Abstract2DLocatable.Side.Top)
bl.setLocation(Location(mm, 50.0, 50.0, -10.0, 0.0))
job = Job()
job.addBoardOrPanelLocation(bl)
gui = Gui(job)

ph = PhotonFeeder()                                   # Photon: no bus in the simulation -> start with SkipNext set,
ph.setSlotAddress(5)                                  # so feed() only resets it (as after a returned part)
ph.setHardwareId("05" * 12)
ph.setPart(parts["U-TEST"])
ph.setOffset(Location(mm, 0, 0, 0, 0.0))
ph.setEnabled(True)
ph.setFeedOptions(ReferenceFeeder.FeedOptions.SkipNext)
machine.addFeeder(ph)
ph.getSlot().setLocation(Location(mm, 150, 200, -20, 0))
tray = ReferenceTrayFeeder()
tray.setName("TRAY-D")
tray.setPart(parts["D-TEST"])
tray.setLocation(Location(mm, 100, 150, -20, 0))
tray.setOffsets(Location(mm, 4, 4, 0, 0))
tray.setTrayCountX(5)
tray.setTrayCountY(1)
tray.setFeedCount(0)
tray.setEnabled(True)
machine.addFeeder(tray)

machine.setEnabled(True)
from lumen import oppnp as _op
_op.run_machine_task(machine, lambda: machine.home())
check("simulated machine homed", machine.isHomed())


def _exec(code, g):
    exec code in g


def load(name):
    src = open(os.path.join(ROOT, "scripts", "Lumen", name)).read().rstrip().split("\n")
    g = {"__name__": "__main__", "scripting": FakeScripting(), "machine": machine, "gui": gui}
    _exec(compile("\n".join(src[:-1]) + "\n", name, "exec"), g)
    g["JFrame"] = FakeFrame
    g["JOptionPane"] = FakeOptionPane
    o = g["oppnp"]
    o.JOptionPane = FakeOptionPane
    o.job_state = lambda gu: "Stopped"
    o.in_background = lambda fn: fn()                 # run the machine work synchronously in the test
    o.on_ui = lambda fn: fn()
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
ui.only.setSelected(False)
ui.refresh()


def row_index(pid):
    return [i for i, r in enumerate(ui.model.rows) if r["part_id"] == pid][0]


_Sys.out.println("refusals (no motion)")
ui.table.clearSelection()
check("no row selected -> asks for rows with a feeder", ui.test() is None and "Select the row" in FakeOptionPane.messages[-1])
i = row_index("U-TEST")
ui.model.rows[i]["matters"] = False                 # as if marked 'orientation not relevant'
ui.table.setRowSelectionInterval(i, i)
check("row marked 'not relevant' -> skipped with a note, no window", ui.test() is None
      and "not relevant" in FakeOptionPane.messages[-1] and "U-TEST" in FakeOptionPane.messages[-1], FakeOptionPane.messages[-1])
ui.model.rows[i]["matters"] = True
ui.table.setRowSelectionInterval(i, i)
dlg = ui.test()
check("dialog: placement U1 preselected (first not placed), nozzle with compatible tip offered",
      str(dlg.where.getSelectedItem()).startswith("U1 on test-board") and dlg.nozzles == [n1], (dlg.where.getSelectedItem(), dlg.nozzles))
check("help: every control of the test window has a tooltip", not g["lumen"].uihelp.missing(dlg.frame.content, "orientation_test"),
      g["lumen"].uihelp.missing(dlg.frame.content, "orientation_test"))
check("start refused without 'NO solder paste'", dlg.start() is False and "NO solder paste" in FakeOptionPane.messages[-1])
dlg.nopaste.setSelected(True)
FakeOptionPane.answers = [2]                         # cancel at the motion confirmation
check("start cancelled at the confirmation -> nothing moves, Photon feed option untouched",
      dlg.start() is False and dlg.state is None and ph.getFeedOptions().name() == "SkipNext"
      and "feed one U-TEST from" in FakeOptionPane.messages[-1], FakeOptionPane.messages[-1].split("\n")[:3])
p0 = render(dlg.frame.content, "testplace-before.png")

_Sys.out.println("Photon feeder: test placement of U1 (rotation 90), the part sits turned 180 in the feeder")
dlg.align.setSelected(False)                         # simulated bottom camera: alignment tried separately below
FakeOptionPane.answers = [0]
ok = dlg.start()
st = dlg.state
check("test ran: placed on the board, nozzle empty, photo taken", ok and st is not None and st["on_board"] and n1.getPart() is None
      and dlg.res is not None and dlg.res.get("crop") is not None, (st and {k: v for k, v in st.items() if not k.startswith("_")},
                                                                     FakeOptionPane.messages[-1:]))
check("Photon feed consumed the SkipNext (no tape move) -> Normal", ph.getFeedOptions().name() == "Normal", ph.getFeedOptions())
at = st["_at"].convertToUnits(mm)
check("nozzle placed at the board placement (board 50/50 + U1 10/10, rotation 90)", abs(at.getX() - 60) < 1e-6
      and abs(at.getY() - 60) < 1e-6 and abs(at.getRotation() - 90) < 1e-6, at)
check("photo saved in lumen/testplace", dlg.res.get("image") and os.path.exists(dlg.res["image"]), dlg.res.get("image"))
check("Retake / Finish enabled, Start disabled while the part is on the board", dlg.finish_btn.isEnabled() and dlg.retake_btn.isEnabled()
      and not dlg.start_btn.isEnabled())
check("CAD pin 1 from the OpenPnP package (pad 1 top-left) -> board mark preset BL at 90 deg, part mark still to click",
      dlg.square.ring == "BL" and dlg.square.dot is None and "Mark pin 1 of the placed part" in str(dlg.result.getText()),
      (dlg.square.ring, dlg.result.getText()))
pad1 = [p for p in dlg.square.pads if p[0] == "1"]
check("CAD pads at true scale in the photo, turned 90: pad 1 bottom-left", dlg.square.pad_mm > 1 and pad1
      and pad1[0][1] < 0 and pad1[0][2] < 0, (dlg.square.pad_mm, pad1))
dlg.mark_board.setSelected(True)
dlg.click_mode()
content = dlg.frame.content
content.setSize(content.getPreferredSize())
layout(content)
mx, my = dlg.square.mark_xy("BL")                     # board pin 1 at 90 deg: CAD TL turned +90 = BL
dlg.square.click(int(mx), int(my))
dlg.mark_part.setSelected(True)
dlg.click_mode()
mx, my = dlg.square.mark_xy("TR")                     # the part's pin 1 is on the opposite corner: turned 180
dlg.square.click(int(mx), int(my))
check("clicks: green ring BL (board), red dot TR (part)", dlg.square.ring == "BL" and dlg.square.dot == "TR",
      (dlg.square.ring, dlg.square.dot))
check("result: WRONG, turned 180, feeder must be +180 (now +0)", "WRONG" in str(dlg.result.getText()) and "180" in str(dlg.result.getText()),
      dlg.result.getText())
p1 = render(dlg.frame.content, "testplace-photo-marked.png")
FakeOptionPane.answers = [0]                          # yes: set the rotation after the part is back
dlg.finish()
check("finish: part picked up and returned to the Photon feeder, next feed skipped (SkipNext)", ph.getFeedOptions().name() == "SkipNext"
      and n1.getPart() is None and not dlg.state["on_board"], (ph.getFeedOptions(), FakeOptionPane.messages[-1]))
check("feeder rotation set to 180 AFTER the take-back", abs(abs(ph.getPickLocation().getRotation()) - 180) < 1e-6,
      ph.getPickLocation().getRotation())
check("window closed, message lists recycling + rotation", dlg.frame.disposed and "SkipNext" in FakeOptionPane.messages[-1]
      and "rotation set to" in FakeOptionPane.messages[-1], FakeOptionPane.messages[-1])
st_ = json.load(open(os.path.join(sandbox, "lumen", "orientation.json")))
rec = st_["parts"]["U-TEST"]
check("store: test record (wrong, turn 180, rotation applied) + CAD pin 1 TL from the board mark, feeder mark confirmed",
      rec["tests"][-1]["result"] == "wrong" and rec["tests"][-1]["turn"] == 180.0 and rec["cad"]["dot"] == "TL"
      and rec["cad"]["source"] == "openpnp-package" and rec["cad"]["confirmed"] and rec["feeders"][str(ph.getId())]["confirmed"],
      (rec["cad"], rec["tests"][-1]["result"]))
rows = dict((r["part_id"], r) for r in ui.model.rows)
check("Orientation Setup list: U-TEST now CORRECT (confirmed)", rows["U-TEST"]["status"].startswith("CORRECT"), rows["U-TEST"]["status"])
log = open(ui.log.path).read()
check("log: fed, placed, picked back, result", "fed" in log and "placed at" in log and "picked back" in log and "WRONG" in log)

_Sys.out.println("again on the same feeder: now CORRECT, golden sample saved")
i = row_index("U-TEST")
ui.table.setRowSelectionInterval(i, i)
dlg = ui.test()
dlg.nopaste.setSelected(True)
dlg.align.setSelected(False)
FakeOptionPane.answers = [0]
dlg.start()
check("SkipNext consumed again: the SAME part was picked (no tape move)", ph.getFeedOptions().name() == "Normal" and dlg.state["on_board"])
check("board mark preset from the now known CAD pin 1 (TL at 90 -> BL)", dlg.square.ring == "BL", dlg.square.ring)
dlg.square.dot = "BL"
dlg.update()
check("result CORRECT, golden checkbox enabled", "CORRECT" in str(dlg.result.getText()) and dlg.golden.isEnabled(), dlg.result.getText())
dlg.golden.setSelected(True)
dlg.finish()
check("returned (SkipNext), golden saved for the package", ph.getFeedOptions().name() == "SkipNext" and
      os.path.exists(os.path.join(sandbox, "lumen", "inspection", "golden", "SOIC-8-TEST.png")), FakeOptionPane.messages[-1])

_Sys.out.println("tray feeder: feed count - 1; several rows in a row; close with the part on the board")
ui.only.setSelected(False)
ui.refresh()
i = row_index("D-TEST")
ui.table.setRowSelectionInterval(i, i)
dlg = ui.test()
dlg.nopaste.setSelected(True)
dlg.align.setSelected(False)
FakeOptionPane.answers = [0]
dlg.start()
check("tray fed: feed count 0 -> 1, part on the board", tray.getFeedCount() == 1 and dlg.state["on_board"], tray.getFeedCount())
FakeOptionPane.answers = [0]                          # close -> yes: return it (no result)
dlg.close()
check("close with the part on the board -> returned, feed count back to 0, no result stored", tray.getFeedCount() == 0
      and dlg.frame.disposed and json.load(open(os.path.join(sandbox, "lumen", "orientation.json")))["parts"]["D-TEST"]["tests"][-1]["result"]
      == "no result", FakeOptionPane.messages[-1])
i = row_index("D-TEST")
ui.table.setRowSelectionInterval(i, i)
dlg = ui.test()
dlg.nopaste.setSelected(True)
dlg.align.setSelected(False)
dlg.after.setSelectedIndex(1)                        # discard
FakeOptionPane.answers = [0]
dlg.start()
dlg.square.ring, dlg.square.dot = "TL", "TL"
dlg.finish()
check("after = discard: part to the discard location, tray count stays 1 (part used)", tray.getFeedCount() == 1 and n1.getPart() is None
      and "DISCARDED" in FakeOptionPane.messages[-1], FakeOptionPane.messages[-1])

_Sys.out.println("bottom vision as in the job (simulated bottom camera)")
i = row_index("U-TEST")
ui.table.setRowSelectionInterval(i, i)
dlg = ui.test()
dlg.nopaste.setSelected(True)
FakeOptionPane.answers = [0]
dlg.start()
if dlg.state is not None and dlg.state.get("on_board"):
    check("with alignment: placed (alignment result recorded)", "alignment" in dlg.state, dlg.state.get("alignment"))
    FakeOptionPane.answers = [0]
    dlg.close()
    check("... and returned", ph.getFeedOptions().name() == "SkipNext" and n1.getPart() is None)
else:
    msg = FakeOptionPane.messages[-1]
    check("with alignment: failure reported with where the part is, nozzle empty, Photon not left fed",
          "stopped" in msg and "The part:" in msg and n1.getPart() is None, msg)
    _Sys.out.println("    (simulated bottom vision: %s)" % msg.replace("\n", " | "))

_Sys.out.println("%d of %d checks passed" % (sum(results), len(results)))
if os.environ.get("PNG_KEEP"):
    _Sys.out.println("PNG: %s" % outdir)
_Sys.exit(0 if all(results) else 1)
