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
# positions + rotations exactly as KiCad's .pos would give them (board origin), so the import verifies
from lumen import orientation as _ori
_at = dict((i["ref"], i["at"]) for i in _ori.parse_kicad_pcb_list(kicad) if i["ref"])
spec = [("U1", "STM32F031C6", _at["U1"][2]), ("D6", "D-SOD123", _at["D6"][2]), ("C12", "CP-6.3x7.7", _at["C12"][2]),
        ("R1", "R0805", _at["R1"][2])]
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
    pl.setLocation(Location(mm, _at[ref][0] - 100.0, _at[ref][1] + 50.0, 0, rot))   # any common origin offset
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
      and st["parts"]["STM32F031C6"]["feeders"][str(f.getId())]["applied"] == -90.0 and st["board_sources"] == {"name:feeder-mobo": ["kicad:" + kicad]} and st["sources"] == [])
# top copper Gerber (KiCad X2 style) written from the same board's pads: verified import in the GUI
import math as _mth
gl = ["%TF.GenerationSoftware,KiCad,Pcbnew,9.0.0*%", "%TF.FileFunction,Copper,L1,Top*%", "%FSLAX46Y46*%", "%MOMM*%",
      "%ADD10C,0.3*%", "D10*"]
for i in _ori.parse_kicad_pcb_list(kicad):
    if i["side"] != "top" or not i["ref"]:
        continue
    a_ = _mth.radians(i["at"][2])
    for n_, px, py in i["pads"]:
        gx = i["at"][0] - 100.0 + px * _mth.cos(a_) - py * _mth.sin(a_)
        gy = i["at"][1] + 50.0 + px * _mth.sin(a_) + py * _mth.cos(a_)
        gl += ["%%TO.P,%s,%s*%%" % (i["ref"], n_), "X%dY%dD03*" % (round(gx * 1e6), round(gy * 1e6)), "%TD*%"]
gpath = os.path.join(outdir, "mobo-F_Cu.gbr")
fh = open(gpath, "w")
fh.write("\n".join(gl + ["M02*"]))
fh.close()
ui.add_source("gerber", gpath)
_Sys.out.println(ui.last_import)
check("GUI: top copper Gerber import verified 4 of 4", "4 of 4 placements verified" in ui.last_import, ui.last_import)
ui2 = load("Orientation_Setup.py")[0][cls]()
check("reopen: sources reloaded, status kept", dict((r["part_id"], r) for r in ui2.model.rows)["STM32F031C6"]["status"].startswith("CORRECT"))

# --- second board imported from a KiCad .pos only (no .kicad_pcb, no Gerber) -----------------
import java.lang
from java.io import File as _File
from org.openpnp.gui.importer import KicadPosImporter
from org.openpnp.model import Footprint, Package
pos = os.path.join(outdir, "sensor-top.pos")
fh = open(pos, "w")                           # Jython: close explicitly (no refcount flush)
fh.write("""### Printed by KiCad version 9.0.0
## Unit = mm, Angle = deg.
# Ref     Val                   Package                                       PosX       PosY       Rot  Side
C31       100n                  C_0402_1005Metric                          10.0950    94.2500  180.0000  top
U31       STM32F031C6           LQFP-48_7x7mm_P0.5mm                       18.7500    95.6300   90.0000  top
U32       MAX                   QFN-32-No-Paste                            30.0000    95.0000  -90.0000  top
U33       STM32WBA65CIx         UFQFPN-48_STM                              18.7500    81.5800   90.0000  top
U1        LDO                   DFN4-1x1_STM                                9.6900    92.8950  180.0000  top
D31       SK6805_SIDE           LED-TEST                                    7.1550    90.7600    0.0000  top
## End
""")
fh.close()
pk = Package("LED-TEST")                      # a package with an imported footprint (pads named)
fpr = Footprint()
for n, x in (("1", -0.8), ("2", -0.3), ("3", 0.3), ("4", 0.8)):
    pad = Footprint.Pad()
    pad.setName(n)
    pad.setX(x)
    pad.setY(0.4 if n == "1" else 0.0)
    pad.setWidth(0.3)
    pad.setHeight(0.5)
    fpr.addPad(pad)
pk.setFootprint(fpr)
Configuration.get().addPackage(pk)
m = KicadPosImporter.getDeclaredMethod("parseFile", [_File, Abstract2DLocatable.Side, java.lang.Boolean.TYPE,
                                                    java.lang.Boolean.TYPE, java.lang.Boolean.TYPE])
m.setAccessible(True)
pls = m.invoke(None, [_File(pos), Abstract2DLocatable.Side.Top, True, True, False])
board2 = Board()
board2.setName("sensor-pos-only")
for pl in pls:
    board2.addPlacement(pl)
bl2 = BoardLocation(board2)
bl2.setGlobalSide(Abstract2DLocatable.Side.Top)
job2 = Job()
job2.addBoardOrPanelLocation(bl2)
gui = Gui(job2)
check("OpenPnP .pos import: package id = footprint name", sorted(str(p.getPart().getPackage().getId()) for p in pls)[0]
      == "C_0402_1005Metric", [str(p.getPart().getId()) for p in pls])
g3, _ = load("Orientation_Setup.py")
ui3 = g3[cls]()
ui3.only.setSelected(False)
ui3.add_library_dir(os.path.expanduser(os.environ.get("FEEDER_LIB", "~/claude/opulo/opulo_feeder/lib/kicad")))
rows = dict((r["refs"], r) for r in ui3.model.rows)
_Sys.out.println("\n".join("  %-4s %-26s %-6s %-5s %s" % (k, r["footprint"], r["matters"], r["cad_dot"], r["status"])
                           for k, r in sorted(rows.items())))
check("pos only: footprint confirmed on the first board -> confirmed here (from the table)", rows["U31"]["cad_dot"] == "TL"
      and rows["U31"]["cad_ok"] and rows["U31"]["cad_source"].startswith("table:"), (rows["U31"]["cad_source"], rows["U31"]["status"]))
check("pos only: footprint from the library -> auto, needs confirmation", rows["U32"]["cad_dot"] == "TL" and not rows["U32"]["cad_ok"]
      and rows["U32"]["cad_source"] == "lib:QFN-32-No-Paste.kicad_mod", rows["U32"].get("cad_source"))
check("pos only: footprint from the OpenPnP package (pads named) -> TL", rows["D31"]["cad_dot"] == "TL"
      and rows["D31"]["cad_source"] == "openpnp-package")
check("pos only: unknown footprint -> matters (U), CAD unknown", rows["U33"]["matters"] is True and rows["U33"]["cad_dot"] is None
      and "unknown" in rows["U33"]["status"])
check("pos only: U1 of this board does NOT take pin 1 of U1 of the other (mobo) board", rows["U1"]["cad_dot"] is None
      and rows["U1"]["footprint"] == "DFN4-1x1_STM", rows["U1"])
check("pos only: capacitor not relevant", rows["C31"]["matters"] is False)
idx = [i for i, r in enumerate(ui3.model.rows) if r["refs"] == "U33"][0]
ui3.table.setRowSelectionInterval(idx, idx)
dlg = ui3.check()
dlg.right.dot = "TL"
dlg.confirm(False)
st = json.load(open(os.path.join(sandbox, "lumen", "orientation.json")))
check("manual confirmation stored per footprint (reused on every later board)", st["footprints"]["UFQFPN-48_STM"] ==
      dict(st["footprints"]["UFQFPN-48_STM"], dot="TL", confirmed=True, source="manual"), st["footprints"].get("UFQFPN-48_STM"))
check("footprint table learned from the mobo .kicad_pcb (confirmed: STM32 + diode; auto: electrolytic)",
      st["footprints"]["LQFP-48_7x7mm_P0.5mm"]["confirmed"] and st["footprints"]["D_SOD-123"]["confirmed"]
      and st["footprints"]["C_Elec_6.3x7.7"]["dot"] == "TL" and not st["footprints"]["C_Elec_6.3x7.7"]["confirmed"],
      sorted(st["footprints"])[:6])
p5 = render(ui3.frame.content, "orientation-list-pos-only.png")

# --- real KiCad 9 data (optional): ~/claude/opulo/_testdata/wba65-panel -------------------------
REAL = os.path.expanduser(os.environ.get("ORIENTATION_REAL_DATA", "~/claude/opulo/_testdata/wba65-panel"))
if os.path.exists(os.path.join(REAL, "Panel.kicad_pcb")):
    import math as _m

    def pos_job(name, rows):
        path = os.path.join(outdir, name + ".pos")
        fh = open(path, "w")
        fh.write("### Printed by KiCad version 9.0.0\n## Unit = mm, Angle = deg.\n# Ref Val Package PosX PosY Rot Side\n")
        for r in rows:
            fh.write("%-8s %-12s %-40s %10.4f %10.4f %9.4f  top\n" % (r["ref"], "v", r["footprint"], r["x"], r["y"], r["rot"]))
        fh.write("## End\n")
        fh.close()
        pls = m.invoke(None, [_File(path), Abstract2DLocatable.Side.Top, True, True, False])
        b = Board()
        b.setName(name)
        for pl in pls:
            b.addPlacement(pl)
        bl_ = BoardLocation(b)
        bl_.setGlobalSide(Abstract2DLocatable.Side.Top)
        j = Job()
        j.addBoardOrPanelLocation(bl_)
        return j

    pcbp = os.path.join(REAL, "Panel.kicad_pcb")
    fps = _ori.parse_kicad_pcb_list(pcbp)
    rows = [{"ref": i["ref"], "x": i["at"][0] - 83.5, "y": i["at"][1] + 138.0, "rot": i["at"][2],
             "footprint": _ori.footprint_key(i["footprint"])} for i in fps
            if i["side"] == "top" and i["ref"] and "*" not in i["ref"] and i["pins"] >= 1]
    gui = Gui(pos_job("wba65-from-pcb", rows))
    g4, _ = load("Orientation_Setup.py")
    ui4 = g4[cls]()
    ui4.add_source("kicad", pcbp)
    check("real KiCad 9 panel: every placement verified from the .kicad_pcb", "%d of %d placements verified" % (len(rows), len(rows))
          in ui4.last_import, ui4.last_import)
    rr = dict((_ori.footprint_key(r["footprint"]), r) for r in ui4.model.rows)
    check("real panel: UFQFPN-48_STM pin 1 TL, ZDO_1610 TL, crystal 2016 BL (verified, from the board)",
          rr["UFQFPN-48_STM"]["cad_dot"] == "TL" and rr["ZDO_1610_STM"]["cad_dot"] == "TL"
          and rr["Crystal_SMD_2016-4Pin_2.0x1.6mm_abracon"]["cad_dot"] == "BL"
          and rr["UFQFPN-48_STM"]["cad_source"] == "kicad:Panel.kicad_pcb", [(k, r["cad_dot"]) for k, r in sorted(rr.items())][:6])
    # the real 7-up .pos of another revision against this board file: refused, nothing used
    gui = Gui(pos_job("wba65-7up", [dict(r, rot=r["rot"]) for r in _ori.parse_kicad_pos(os.path.join(REAL, "Panel-top.pos"))
                                     if "*" not in r["ref"]]))
    g5, _ = load("Orientation_Setup.py")
    ui5 = g5[cls]()
    ui5.add_source("kicad", pcbp)
    k5 = ui5.last_import
    ui5.add_source("gerber", os.path.join(REAL, "Panel-top_copper.gbr"))
    check("real .pos of another revision: board file and Gerber both REFUSED (NOT USED)", "NOT USED" in k5
          and "NOT USED" in ui5.last_import and "other design or revision" in ui5.last_import, (k5, ui5.last_import))
    rr5 = dict((_ori.footprint_key(r["footprint"]), r) for r in ui5.model.rows)
    check("... but pin 1 by footprint NAME from the board file's footprints: auto, to confirm",
          rr5["ZDO_1610_STM"]["cad_dot"] == "TL" and not rr5["ZDO_1610_STM"]["cad_ok"]
          and rr5["ZDO_1610_STM"]["cad_source"] == "table:kicad:Panel.kicad_pcb", rr5["ZDO_1610_STM"].get("cad_source"))
    st5 = json.load(open(os.path.join(sandbox, "lumen", "orientation.json")))
    check("refused files are not bound to the board", "name:wba65-7up" not in st5["board_sources"], st5["board_sources"].keys())
    ui5.add_source("gerber", os.path.join(REAL, "Panel-F_Silkscreen.gbr"))
    check("silkscreen Gerber refused: no pin data", "not a copper layer" in ui5.last_import, ui5.last_import)
    _Sys.out.println(ui4.last_import)
else:
    _Sys.out.println("(real data not found in %s: skipped)" % REAL)
import shutil
if os.environ.get("PNG_KEEP"):
    shutil.copy(p5, os.environ["PNG_KEEP"])
_Sys.out.println("PNG: %s %s %s %s %s" % (p1, p2, p3, p4, p5))
_Sys.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
_Sys.exit(0 if all(results) else 1)
