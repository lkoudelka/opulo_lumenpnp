# -*- coding: utf-8 -*-
# Feeder Assistant with the real OpenPnP classes on COPIES of the user's configuration, the test job and its
# board file (no machine).  Some parts of the board are renamed as another project would name them; the
# assistant must propose the set-up feeders on top, change nothing before Apply, then apply both ways.
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
ROOT = os.path.join(HERE, "..")
sandbox, jobfile, outdir, boards = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
os.makedirs(os.path.join(sandbox, "lumen", "logs"))
os.symlink(os.path.join(ROOT, "lib"), os.path.join(sandbox, "lumen", "lib"))
sys.path.insert(0, os.path.join(ROOT, "lib"))
from java.awt.image import BufferedImage
from java.io import File
from java.lang import System as S
from javax.imageio import ImageIO
from org.openpnp.model import Configuration, Part
from org.openpnp.model import Package as PPackage
Configuration.initialize(File(sandbox))
Configuration.get().load()
cfg = Configuration.get()
machine = cfg.getMachine()
job = cfg.loadJob(File(jobfile))
from lumen import uihelp
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    S.out.println("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


REAL_BOARD = os.path.expanduser("~/claude/opulo/pnp/WBA_panel_small.board.xml")
real_md5 = md5(REAL_BOARD) if os.path.exists(REAL_BOARD) else None
board_copy = [os.path.join(boards, f) for f in os.listdir(boards)][0]

# -- another project's names for parts that are set up on feeders -------------------------------------
board = job.getBoardLocations()[0].getBoard()
qfn = PPackage("QFN-48-1EP_7x7mm")
cfg.addPackage(qfn)
RENAME = {"C_0402_1005Metric-100n": ("CAP_0402-0.1uF_X7R_16V", None), "R_0402_1005Metric-100k": ("RES0402-100K_1%", None),
          "UFQFPN-48_STM-STM32WBA65CIx": ("QFN48-STM32WBA65CI", qfn), "C_0402_1005Metric-6p": ("C_0402-6.8p", None),
          "C_0402_1005Metric-1u": (u"C0402-1\u00b5F", None)}
newparts = {}
for old, (nid, pk) in RENAME.items():
    op = cfg.getPart(old)
    p = Part(nid)
    p.setPackage(pk or op.getPackage())
    p.setHeight(op.getHeight())
    cfg.addPart(p)
    newparts[old] = p
    for pl in board.getPlacements():
        if pl.getPart() == op:
            pl.setPart(p)
feeder_of = {}
for f in machine.getFeeders():
    if f.getPart() is not None and str(f.getPart().getId()) in RENAME:
        feeder_of[str(f.getPart().getId())] = str(f.getId())
check("the original parts are set up on feeders in the real configuration", len(feeder_of) >= 3, sorted(feeder_of))


class Frame(object):
    instances = []

    def __init__(self, t=""):
        self.content = None
        Frame.instances.append(self)

    def setContentPane(self, c):
        self.content = c

    def __getattr__(self, n):
        return lambda *a, **k: None


class Pane(object):
    OK_OPTION = YES_OPTION = 0
    NO_OPTION = 1
    OK_CANCEL_OPTION = YES_NO_OPTION = 2
    answer = 0
    shown = []

    @classmethod
    def showMessageDialog(cls, *a):
        cls.shown.append(a[1])

    @classmethod
    def showConfirmDialog(cls, *a):
        cls.shown.append(a[1])
        return cls.answer


class Scr(object):
    def getScriptsDirectory(self):
        return File(os.path.join(sandbox, "scripts"))


class Tab(object):
    def getJob(self):
        return job


class G(object):
    def getJobTab(self):
        return Tab()


def open_tool():
    src = open(os.path.join(ROOT, "scripts", "Lumen", "Feeder_Assistant.py")).read().rstrip().split("\n")
    g = {"__name__": "__main__", "scripting": Scr(), "machine": machine, "gui": G()}
    code = compile("\n".join(src[:-1]) + "\n", "Feeder_Assistant.py", "exec")
    exec(code, g)
    g["JFrame"] = Frame
    g["JOptionPane"] = Pane
    g["oppnp"].JOptionPane = Pane
    Frame.instances = []
    return g["FeederAssistant"](), Frame.instances[0].content


def render(panel, name):
    d = panel.getPreferredSize()
    panel.setSize(d)

    def lay(c):
        c.doLayout()
        for k in c.getComponents():
            lay(k)
    lay(panel)
    img = BufferedImage(d.width, d.height, BufferedImage.TYPE_INT_RGB)
    g2 = img.createGraphics()
    panel.paint(g2)
    from java.awt import Graphics2D
    Graphics2D.dispose(g2)
    ImageIO.write(img, "png", File(os.path.join(outdir, name)))


S.out.println("proposals")
fa, content = open_tool()
check("every option / button / column described", not uihelp.missing(content, "feeder_assist"), uihelp.missing(content, "feeder_assist")[:5])
rows = dict((x["id"], x) for x in fa.pmodel.rows)
check("the renamed parts are listed (no feeder holds them)", all(p[0] in rows for p in RENAME.values()), sorted(rows))
check("parts that have an enabled feeder are hidden", "C_0402_1005Metric-1u" not in rows or not any(
    machine.getFeeder(k).isEnabled() for k in [str(f.getId()) for f in machine.getFeeders() if f.getPart() is not None
                                               and str(f.getPart().getId()) == "C_0402_1005Metric-1u"]))
for old, (nid, _) in RENAME.items():
    x = rows[nid]
    best = x["cands"][0] if x["cands"] else None
    if old == "C_0402_1005Metric-6p":
        check("C_0402-6.8p: no feeder with 6.8p -> no proposal (6p is another value)",
              not any(machine.getFeeder(c[1]).getPart().getId() == old for c in x["cands"]), x["cands"][:2])
        continue
    check("%-26s -> top proposal is the feeder with %s" % (nid, old), best is not None and best[1] == feeder_of.get(old),
          best[:3] if best else x["cands"])
# the lower list for the 100n part: matches first, then a separator, then ALL other feeders
i = [k for k, x in enumerate(fa.pmodel.rows) if x["id"] == "CAP_0402-0.1uF_X7R_16V"][0]
fa.ptable.setRowSelectionInterval(fa.ptable.convertRowIndexToView(i), fa.ptable.convertRowIndexToView(i))
fr = fa.fmodel.rows
sep = [k for k, r in enumerate(fr) if r.get("sep")]
nfeed = len([f for f in machine.getFeeders() if f.getPart() is not None])
check("feeder list: matching feeders on top, then a separator, then every other feeder",
      sep and all(r.get("score") is not None for r in fr[:sep[0]]) and all(r.get("score") is None for r in fr[sep[0] + 1:])
      and len(fr) - 1 == nfeed, (sep, len(fr), nfeed))
check("the 100n proposal warns that 16V is needed and the feeder part does not say", any("16V" in w for w in fr[0]["warn"]), fr[0]["warn"])
render(content, "feeder-assistant.png")
# nothing changed yet
check("nothing changed before Apply (placements still use the new part, board file untouched)",
      any(pl.getPart().getId() == "CAP_0402-0.1uF_X7R_16V" for pl in board.getPlacements()) and md5(board_copy) == md5(board_copy))
before = md5(board_copy)

S.out.println("choose + apply: the job uses the feeder's part")
fa.preselect()
ch = dict((x["id"], x.get("choice")) for x in fa.pmodel.rows)
check("pre-select: only strong, warning-free proposals (100K resistor; not the 100n with its voltage warning, not the "
      "STM32WBA65 with another package name, not 6.8p)", ch.get("RES0402-100K_1%") == feeder_of["R_0402_1005Metric-100k"]
      and not ch.get("QFN48-STM32WBA65CI") and not ch.get("CAP_0402-0.1uF_X7R_16V") and not ch.get("C_0402-6.8p"),
      dict((k, v) for k, v in ch.items() if v))
fa.ftable.setRowSelectionInterval(0, 0)
fa.choose()                                                         # the 100n part is selected above: choose its top feeder
ch = dict((x["id"], x.get("choice")) for x in fa.pmodel.rows)
check("choose: the selected feeder becomes the part's choice", ch.get("CAP_0402-0.1uF_X7R_16V") == feeder_of["C_0402_1005Metric-100n"])
Pane.answer = 1                                                     # Cancel in the confirmation
Pane.shown = []
fa.apply()
check("Apply, Cancel in the confirmation: nothing changed", md5(board_copy) == before
      and any(pl.getPart().getId() == "CAP_0402-0.1uF_X7R_16V" for pl in board.getPlacements()))
conf = [m for m in Pane.shown if u"Apply" in unicode(m)]
check("the confirmation lists each change and the board file that will be saved",
      conf and "CAP_0402-0.1uF_X7R_16V" in conf[0] and "RES0402-100K_1%" in conf[0] and os.path.basename(board_copy) in conf[0]
      and "16V" in conf[0], unicode(conf[0])[:300] if conf else Pane.shown)
Pane.answer = 0
fa.apply()
ids = [str(pl.getPart().getId()) for pl in board.getPlacements()]
check("Apply OK: the placements use the feeders' parts", ids.count("C_0402_1005Metric-100n") == 36 and ids.count("R_0402_1005Metric-100k") == 6
      and "CAP_0402-0.1uF_X7R_16V" not in ids, (ids.count("C_0402_1005Metric-100n"), ids.count("R_0402_1005Metric-100k")))
txt = open(board_copy).read()
check("the board file COPY was saved with the feeders' parts", md5(board_copy) != before and "CAP_0402-0.1uF" not in txt
      and txt.count('part-id="C_0402_1005Metric-100n"') == 36)
check("the user's real board file is untouched", real_md5 is None or md5(REAL_BOARD) == real_md5)
st = json.load(open(os.path.join(sandbox, "lumen", "partmatch.json")))
check("non-ASCII name (C0402-1\u00b5F): applied, logged, remembered", st["aliases"].get(u"C0402-1\u00b5F") == "C_0402_1005Metric-1u"
      and "C_0402_1005Metric-1u" in [unicode(pl.getPart().getId()) for pl in board.getPlacements()], st["aliases"].get(u"C0402-1\u00b5F"))
check("the choices are remembered as aliases", st["aliases"].get("CAP_0402-0.1uF_X7R_16V") == "C_0402_1005Metric-100n"
      and st["aliases"].get("RES0402-100K_1%") == "R_0402_1005Metric-100k", st)
rows = dict((x["id"], x) for x in fa.pmodel.rows)
check("after Apply the assigned parts leave the list", "CAP_0402-0.1uF_X7R_16V" not in rows and "RES0402-100K_1%" not in rows)
S.out.println("a later project with the same name: proposed first as 'confirmed by you before'")
p2 = cfg.getPart("CAP_0402-0.1uF_X7R_16V")
pl1 = [pl for pl in board.getPlacements() if str(pl.getPart().getId()) == "C_0402_1005Metric-100n"][0]
pl1.setPart(p2)
# and an IC under another package name, for the second mode
ld = cfg.getPart("DFN4-1x1_STM-LD39020ADTPU33R")
dfn = PPackage("DFN-4-1EP_1x1mm")
cfg.addPackage(dfn)
ld2 = Part("DFN-4_1x1-LD39020ADTPU33R")
ld2.setPackage(dfn)
ld2.setHeight(ld.getHeight())
cfg.addPart(ld2)
for pl in board.getPlacements():
    if pl.getPart() == ld:
        pl.setPart(ld2)
fa2, _ = open_tool()
x = [r for r in fa2.pmodel.rows if r["id"] == "CAP_0402-0.1uF_X7R_16V"]
check("alias: 99, 'confirmed by you before'", x and x[0]["cands"][0][0] == 99 and "confirmed" in x[0]["cands"][0][2], x[0]["cands"][:1] if x else None)

S.out.println("apply: the feeder gets the job's part")
x = [r for r in fa2.pmodel.rows if r["id"] == "DFN-4_1x1-LD39020ADTPU33R"][0]
x["choice"] = x["cands"][0][1]
plan = fa2.plan()
w = [ww for r, f, ws in plan if r["id"] == "DFN-4_1x1-LD39020ADTPU33R" for ww in ws]
check("IC with another package name: warning 'check the orientation (Orientation Setup)'", any("orientation" in s for s in w), w)
fa2.mode.setSelectedIndex(1)
f = machine.getFeeder(x["choice"])
Pane.answer = 0
fa2.apply()
check("the feeder now holds the job's part (machine configuration, sandbox)", str(f.getPart().getId()) == "DFN-4_1x1-LD39020ADTPU33R",
      f.getPart().getId())
check("the board was not changed by this mode", "DFN-4_1x1-LD39020ADTPU33R" in [str(pl.getPart().getId()) for pl in board.getPlacements()])
S.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
S.exit(0 if all(results) else 1)
