# FOR LATER (moves the camera only): Placement Inspection on the open test job, real placements.
#   tests/run_bench_real_ui.sh exec tests/bench/inspect_placements.py
# Inspects the first 6 placements of the test job with the real camera; prints verdicts.
from java.io import File
from org.openpnp.model import Configuration
job = Configuration.get().loadJob(File(os.path.expanduser("~/claude/opulo/_test_session/WBA_panel_test.job.xml")))

class Tab(object):
    def getJob(self):
        return job

class G(object):
    def getJobTab(self):
        return Tab()
g, cls = load_script("Placement_Inspection.py")
g["gui"] = G()
d = g[cls]()
d.only_placed.setSelected(False)
d.filter()
for x in d.model.rows[:6]:
    x["sel"] = True
d.run()
wait_idle(d, 600)
for x in d.model.rows[:6]:
    say("  %s %s: %s  image %s" % (x["ref"], x["part"], (x.get("res") or {}).get("verdict"), (x.get("res") or {}).get("image")))
check("6 placements inspected", all(x.get("res") for x in d.model.rows[:6]))
