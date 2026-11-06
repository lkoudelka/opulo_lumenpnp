# Scripts > Lumen > Board Z Probe with the user's test job (read only; Apply in memory, not saved)
from java.io import File
from org.openpnp.model import Configuration
job = Configuration.get().loadJob(File(os.path.expanduser("~/claude/opulo/_test_session/WBA_panel_test.job.xml")))

class Tab(object):
    def getJob(self):
        return job

class G(object):
    def getJobTab(self):
        return Tab()
g, cls = load_script("Board_Z_Probe.py")
g["gui"] = G()
FakeOptionPane.answer = 0
d = g[cls]()
say("  fiducials: %s" % [(x["fid"], round(x["x"], 3), round(x["y"], 3)) for x in d.model.rows])
d.run()
wait_idle(d, 600)
for x in d.model.rows:
    say("  %s %s Z %s  %s" % (x["board"], x["fid"], x.get("z"), x.get("status")))
say("  " + str(d.info.getText()))
d.apply()
bl = job.getBoardLocations()[0]
check("board Z applied in memory: %.3f" % bl.getLocation().getZ(), 3.9 < bl.getLocation().getZ() < 4.7)
