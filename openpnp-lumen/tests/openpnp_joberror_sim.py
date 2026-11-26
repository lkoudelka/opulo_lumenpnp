# Job errors explained (lib/lumen/joberror.py, jobinfo.tip_issue): a part whose package has no LOADED compatible
# nozzle tip -> named, with the fix, instead of only "Can't move y ... soft limit" (bench 2026-11-26, C11).
# Real OpenPnP configuration / job loading (stock simulated machine), headless.
#   tests/run_joberror_sim.sh
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


from lumen import jobinfo, joberror

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

check("loaded tip suits the package -> no issue", jobinfo.tip_issue(cfg.getPart("A"), machine) is None)
ib = jobinfo.tip_issue(cfg.getPart("B"), machine)
check("only a tip that is not loaded -> named, with the soft-limit symptom and the fix",
      ib and "needs nozzle tip N24" in ib and "N1 has %s" % nt1.getName() in ib and "soft limit" in ib
      and "Packages > PB > Nozzle Tips" in ib, ib)
ic = jobinfo.tip_issue(cfg.getPart("C"), machine)
check("package without any compatible tip -> said so", ic and "no compatible nozzle tip" in ic, ic)
probs = jobinfo.tip_problems(job, machine)
check("tip_problems lists the job's parts with their references",
      [(p, r) for p, r, _ in probs] == [("B", ["C11", "C12"]), ("C", ["U1"])], probs)
rows = dict((r["part_id"], r) for r in jobinfo.readiness(job, machine, lumen_profile=False))
check("Job Readiness / Preflight show it as an issue of part B", any("needs nozzle tip N24" in i for i in rows["B"]["issues"])
      and not any("nozzle tip" in i for i in rows["A"]["issues"]), rows["B"]["issues"])

soft = JobProcessor.JobProcessorException(nt1, JException("Can't move y to -110.698mm, lower than soft limit 0.000mm."))
lines = joberror.explain(job, machine, soft)
check("the job error names the parts / references / package", lines and "could not change the nozzle tip" in lines[0]
      and any("B (C11, C12)" in l and "N24" in l for l in lines), lines)
shown = []
_Sys.clearProperty(joberror.SEEN_KEY)
joberror.on_error(job, machine, soft, show=shown.append)
joberror.on_error(job, machine, soft, show=shown.append)
check("OpenPnP repeats the error on every retry: shown once", len(shown) == 1, len(shown))

# tips fixed (B and C can use the loaded tip): a soft limit error is then about a position
for pk in ("PB", "PC"):
    cfg.getPackage(pk).addCompatibleNozzleTip(nt1)
check("fixed packages -> no tip problems", jobinfo.tip_problems(job, machine) == [])
lines = joberror.explain(job, machine, soft)
check("other soft limit error -> points to board position / pick location", lines and "board position" in lines[0], lines)
check("an unrelated error -> nothing added", joberror.explain(job, machine, JException("Feeder F1 is not enabled")) == [])

_Sys.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
_Sys.exit(0 if all(results) else 1)
