# Board positions live in the job: start-up offer to reopen the last job, boards at X 0 / Y 0 flagged
# (lib/lumen/lastjob.py).  Real OpenPnP job loading (stock config), headless; the main window is a stand-in.
#   tests/run_lastjob_sim.sh
import os
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sandbox = sys.argv[1]

from java.io import File
from java.lang import System as _Sys
from org.openpnp.model import BoardLocation, Configuration, Job

Configuration.initialize(File(sandbox))
Configuration.get().load()
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    _Sys.out.println("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


from lumen import lastjob

d = os.path.join(sandbox, "project")
os.makedirs(d)
board = os.path.join(d, "test.board.xml")


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


write(board, '''<openpnp-board version="1.1" name="test.board.xml">
   <dimensions units="Millimeters" x="0.0" y="0.0" z="0.0" rotation="0.0"/>
   <placements>
      <placement version="1.4" side="Top" id="R1" type="Placement" enabled="true" rank="0">
         <location units="Millimeters" x="5.0" y="6.0" z="0.0" rotation="90.0"/>
      </placement>
   </placements>
</openpnp-board>''')
jobfile = os.path.join(d, "test.board.job.xml")
write(jobfile, '''<openpnp-job version="2.0">
   <root-panel version="2.0">
      <dimensions units="Millimeters" x="0.0" y="0.0" z="0.0" rotation="0.0"/>
      <placements/>
      <children>
         <object class="org.openpnp.model.BoardLocation" side="Top" id="Brd1" file-name="%s" check-fiducials="false" locally-enabled="true">
            <location units="Millimeters" x="318.66" y="145.14" z="4.5" rotation="-1.89"/>
         </object>
      </children>
      <pseudo-placement-ids/>
   </root-panel>
</openpnp-job>''' % board)


class Prefs(object):
    def __init__(self, v):
        self.v = v

    def get(self, k, default):
        return self.v if k == lastjob.RECENT_KEY else default


class Tab(object):
    def __init__(self, job):
        self.job, self.set_calls = job, 0

    def getJob(self):
        return self.job

    def setJob(self, j):
        self.job, self.set_calls = j, self.set_calls + 1


class Feeders(object):
    updated = 0

    def updateView(self):
        Feeders.updated += 1


class Gui(object):
    def __init__(self, job):
        self.tab = Tab(job)

    def getJobTab(self):
        return self.tab

    def getFeedersTab(self):
        return Feeders()


# start-up: empty job, last job exists -> asked; Yes -> OpenPnP's loader, positions kept
g = Gui(Job())
asked = []
r = lastjob.offer(g, ask=lambda t: asked.append(t) or True, prefs=Prefs(jobfile))
bl = list(g.tab.job.getBoardLocations())
check("empty job at start + last job exists -> the person is asked", len(asked) == 1 and "test.board.job.xml" in asked[0])
check("Yes: the last job is open with its saved board position (318.66 / 145.14, Z 4.5, -1.89 deg)",
      r == jobfile and len(bl) == 1 and abs(lastjob.board_xy(bl[0])[0] - 318.66) < 1e-6
      and abs(bl[0].getLocation().getRotation() + 1.89) < 1e-6 and Feeders.updated == 1,
      bl and bl[0].getLocation())
check("the reopened job has no board at 0 / 0", lastjob.unplaced_boards(g.tab.job) == [])

g2 = Gui(Job())
r2 = lastjob.offer(g2, ask=lambda t: False, prefs=Prefs(jobfile))
check("No: nothing is opened", r2 is None and g2.tab.set_calls == 0)
asked[:] = []
check("a job already open (not empty) -> not asked", lastjob.offer(g, ask=lambda t: asked.append(t) or True,
                                                                   prefs=Prefs(jobfile)) is None and not asked)
check("no recent job / file missing -> not asked",
      lastjob.offer(Gui(Job()), ask=lambda t: asked.append(t) or True, prefs=Prefs(None)) is None
      and lastjob.offer(Gui(Job()), ask=lambda t: asked.append(t) or True, prefs=Prefs(jobfile + ".gone")) is None
      and not asked)

# the bench case: the board file added again to a new job (Add Board) -> X 0 / Y 0, flagged
j3 = Job()
b3 = Configuration.get().getBoard(File(board))
j3.addBoardOrPanelLocation(BoardLocation(b3))
z = lastjob.unplaced_boards(j3)
check("board added again (Add Board) sits at X 0 / Y 0 and is flagged", len(z) == 1, z)

ok = sum(results)
_Sys.out.println("%d/%d checks passed" % (ok, len(results)))
_Sys.exit(0 if ok == len(results) else 1)
