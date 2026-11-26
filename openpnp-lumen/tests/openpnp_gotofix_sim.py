# Job Readiness > Go to problem / Next problem >> (lib/lumen/gotofix.py, jobinfo.readiness fixes): every problem
# points to where it is fixed - OpenPnP Feeders / Packages / Parts tab with the row selected, or Lumen Feeders >
# Assign feeders with the part.  Real OpenPnP configuration / job (stock simulated machine), headless; the GUI
# panels are recorded.
#   tests/run_gotofix_sim.sh
import os
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sandbox = sys.argv[1]

from java.io import File
from java.lang import Exception as JException, System as _Sys
from org.openpnp.machine.reference import ReferenceNozzleTip
from org.openpnp.model import Configuration, Package, Part
from org.openpnp.spi import JobProcessor

Configuration.initialize(File(sandbox))
Configuration.get().load()
cfg = Configuration.get()
machine = cfg.getMachine()
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    _Sys.out.println("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


from lumen import jobinfo, gotofix
from org.openpnp.machine.reference.feeder import ReferenceTrayFeeder

n1 = machine.getDefaultHead().getNozzles()[0]
nt1 = n1.getNozzleTip()
nt2 = ReferenceNozzleTip()
nt2.setName("N24")
machine.addNozzleTip(nt2)
for pid, tips in (("PA", [nt1]), ("PB", [nt2]), ("PC", [])):
    pk = Package(pid)
    for t in tips:
        pk.addCompatibleNozzleTip(t)
    cfg.addPackage(pk)
for part_id, pk in (("A", "PA"), ("B", "PB"), ("C", "PC")):
    p = Part(part_id)
    p.setPackage(cfg.getPackage(pk))
    cfg.addPart(p)

d = os.path.join(sandbox, "project")
os.makedirs(d)
board = os.path.join(d, "t.board.xml")
pl = "\n".join('''      <placement version="1.4" side="Top" id="%s" part-id="%s" type="Placement" enabled="true" rank="0">
         <location units="Millimeters" x="%d.0" y="6.0" z="0.0" rotation="0.0"/>
      </placement>''' % (ref, part, i) for i, (ref, part) in enumerate((("R1", "A"), ("C11", "B"), ("C12", "B"), ("U1", "C"))))
with open(board, "w") as f:
    f.write('''<openpnp-board version="1.1" name="t.board.xml">
   <dimensions units="Millimeters" x="0.0" y="0.0" z="0.0" rotation="0.0"/>
   <placements>
%s
   </placements>
</openpnp-board>''' % pl)
jobfile = os.path.join(d, "t.board.job.xml")
with open(jobfile, "w") as f:
    f.write('''<openpnp-job version="2.0">
   <root-panel version="2.0">
      <dimensions units="Millimeters" x="0.0" y="0.0" z="0.0" rotation="0.0"/>
      <placements/>
      <children>
         <object class="org.openpnp.model.BoardLocation" side="Top" id="Brd1" file-name="%s" check-fiducials="false" locally-enabled="true">
            <location units="Millimeters" x="100.0" y="100.0" z="0.0" rotation="0.0"/>
         </object>
      </children>
      <pseudo-placement-ids/>
   </root-panel>
</openpnp-job>''' % board)
job = cfg.loadJob(File(jobfile))


# A: tip OK, but its only feeder is switched off; B: tip N24 not loaded, feeder OK; C: no feeder, no tip
ta = ReferenceTrayFeeder()
ta.setName("tray-A")
ta.setPart(cfg.getPart("A"))
ta.setEnabled(False)
machine.addFeeder(ta)
tb = ReferenceTrayFeeder()
tb.setName("tray-B")
tb.setPart(cfg.getPart("B"))
tb.setEnabled(True)
machine.addFeeder(tb)
rows = jobinfo.readiness(job, machine, lumen_profile=True)
by = dict((r["part_id"], r) for r in rows)
kinds = lambda pid: [(f["kind"], f["target"]) for f in by[pid]["fixes"]]
check("A: switched-off feeder -> fix 'feeder' with that feeder", kinds("A")[:1] == [("feeder", ta)], kinds("A"))
check("B: tip not loaded -> fix 'package' with package PB", ("package", cfg.getPackage("PB")) in kinds("B"), kinds("B"))
check("C: no feeder -> fix 'assign' with the part id first", kinds("C")[:1] == [("assign", "C")], kinds("C"))
check("every line with an issue has at least one fix (no dead end)",
      all(r["fixes"] for r in rows if r["issues"]), [(r["part_id"], r["issues"]) for r in rows if r["issues"] and not r["fixes"]])
check("body size missing (lumen) -> fix 'package'", any(f["kind"] == "package" and "body size" in f["text"]
                                                         for f in by["A"]["fixes"]), by["A"]["fixes"])

walk, at = [], None
for _ in range(sum(len(r["fixes"]) for r in rows) + 1):
    at = gotofix.next_problem(rows, at)
    walk.append(at)
n = sum(len(r["fixes"]) for r in rows)
check("Next problem walks every fix once, in table order, then starts again", len(set(walk[:n])) == n
      and walk[:n] == sorted(walk[:n]) and walk[n] == walk[0], walk)
check("Next problem on a job without problems: None", gotofix.next_problem([{"fixes": []}], None) is None)


class Panel(object):
    def __init__(self, log, name):
        self.log, self.name = log, name

    def __getattr__(self, m):
        if m == "getClass":                          # search clearing (reflection): checked on the real panels below
            raise AttributeError(m)
        return lambda *a: self.log.append((self.name, m) + a)


class Gui(object):
    def __init__(self):
        self.log = []

    def showTab(self, t):
        self.log.append(("tab", t))

    def getFeedersTab(self):
        return Panel(self.log, "Feeders")

    def getPackagesTab(self):
        return Panel(self.log, "Packages")

    def getPartsTab(self):
        return Panel(self.log, "Parts")


g = Gui()
t = gotofix.show(g, by["A"]["fixes"][0])
check("feeder fix: Feeders tab shown, the feeder selected in its table", g.log == [("tab", "Feeders"),
      ("Feeders", "selectFeederInTable", ta)] and "tray-A" in t, (g.log, t))
g = Gui()
gotofix.show(g, [f for f in by["B"]["fixes"] if f["kind"] == "package"][0])
check("package fix: Packages tab, PB selected", g.log == [("tab", "Packages"), ("Packages", "selectPackageInTable",
                                                                                cfg.getPackage("PB"))], g.log)
g = Gui()
gotofix.show(g, gotofix.fix("part", "height", cfg.getPart("C")))
check("part fix: Parts tab, part selected", g.log == [("tab", "Parts"), ("Parts", "selectPartInTable", cfg.getPart("C"))], g.log)


class Scr(object):
    def __init__(self):
        self.ran = []

    def getScriptsDirectory(self):
        return File(os.path.join(sandbox, "scripts"))

    def execute(self, f, g):
        self.ran.append((str(f.getPath()), dict(g)))


s = Scr()
gotofix.open_assign(s, "C")
check("assign fix: Scripts/Lumen/Feeders.py run with lumen_focus = Assign tab + part",
      len(s.ran) == 1 and s.ran[0][0].endswith(os.path.join("Lumen", "Feeders.py"))
      and s.ran[0][1]["lumen_focus"] == {"tab": "assign", "part": "C"}, s.ran)

# OpenPnP's real panels: the private search field is cleared before selecting (a leftover search would hide the row)
from javax.swing import JPanel
from org.openpnp.gui import FeedersPanel, PackagesPanel, PartsPanel
ok = []
for c in (FeedersPanel, PackagesPanel, PartsPanel):
    try:
        ok.append(str(c.getDeclaredField("searchTextField").getType().getSimpleName()) == "JTextField"
                  and c.getDeclaredMethod("search") is not None)
    except:
        ok.append(False)
check("OpenPnP's Feeders / Packages / Parts panels have the private searchTextField + search() that get cleared", all(ok), ok)
check("search clearing never raises on a panel without a search field", gotofix._clear_search(JPanel()) is None)
_Sys.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
_Sys.exit(0 if all(results) else 1)
