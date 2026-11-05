# Headless functional test of the menu scripts' own code (tests/run_openpnp_ui_headless.sh):
# real OpenPnP 2.6 classes + Swing models, real machine tasks of the simulated machine,
# the feeder bus via the Marlin/PBL simulator; only the top-level window (JFrame) and the
# message boxes (JOptionPane) are replaced by recording fakes (no display available).
from __future__ import print_function
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "lib"))
sys.path.insert(0, HERE)
sandbox, work, port = sys.argv[1], sys.argv[2], sys.argv[3]

from java.io import File
from org.openpnp.model import (Configuration, Board, BoardLocation, Job, Length, LengthUnit, Location,
                               Part, Placement, Abstract2DLocatable)
from org.openpnp.machine.photon import PhotonFeeder
Configuration.initialize(File(sandbox))
Configuration.get().load()
machine = Configuration.get().getMachine()
mm = LengthUnit.Millimeters

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


# ---- fakes for what needs a display ---------------------------------------------------
class FakeFrame(object):
    def __init__(self, title=""):
        self.title, self.visible, self.disposed = title, False, False

    def __getattr__(self, name):          # setDefaultCloseOperation, pack, setContentPane, ...
        return lambda *a, **k: None

    def setVisible(self, v):
        self.visible = v

    def dispose(self):
        self.disposed = True


class FakeOptionPane(object):
    OK_OPTION = YES_OPTION = 0
    NO_OPTION = 1
    OK_CANCEL_OPTION = YES_NO_OPTION = 2
    PLAIN_MESSAGE = -1
    answer = 0
    messages = []

    @classmethod
    def showMessageDialog(cls, parent, msg, *a):
        cls.messages.append(str(msg))

    @classmethod
    def showConfirmDialog(cls, parent, msg, *a):
        cls.messages.append(str(msg))
        return cls.answer


class FakeScripting(object):
    def getScriptsDirectory(self):
        return File(os.path.join(sandbox, "scripts"))


class FakePanel(object):
    def refresh(self):
        pass

    def updateActivePlacements(self):
        pass


class FakeJobTab(object):
    def __init__(self, job):
        self.job = job

    def getJob(self):
        return self.job

    def getJobPlacementsPanel(self):
        return FakePanel()


class FakeGui(object):
    def __init__(self, job):
        self.tab = FakeJobTab(job)

    def getJobTab(self):
        return self.tab


# ---- machine content: 3 Photon feeders on slots 1..3, a job using slots 2 and 3 --------
parts = {}
for pid in ("R0402", "C0402"):
    p = Part(pid)
    p.setHeight(Length(0.4, mm))
    Configuration.get().addPart(p)
    parts[pid] = p
for slot, pid in ((1, None), (2, "R0402"), (3, "C0402")):
    f = PhotonFeeder()
    f.setSlotAddress(slot)
    f.setHardwareId("%02x" % (0xA0 + slot) * 12)
    f.setOffset(Location(mm, 0, 0, 0, 0))
    if pid:
        f.setPart(parts[pid])
    f.setEnabled(True)
    machine.addFeeder(f)
    f.getSlot().setLocation(Location(mm, 20 * slot, 300, 10, 0))
board = Board()
board.setName("B")
for i, pid in enumerate(("R0402", "R0402", "C0402")):
    pl = Placement("P%d" % (i + 1))
    pl.setPart(parts[pid])
    pl.setLocation(Location(mm, 5 + i, 5, 0, 0))
    pl.setSide(Abstract2DLocatable.Side.Top)
    board.addPlacement(pl)
bl = BoardLocation(board)
bl.setLocation(Location(mm, 100, 100, 0, 0))
bl.setGlobalSide(Abstract2DLocatable.Side.Top)
job = Job()
job.addBoardOrPanelLocation(bl)
job.setFile(File(os.path.join(sandbox, "t.job.xml")))
gui = FakeGui(job)

import jython_smoke_transport as jst            # PtyTransport to the simulator
from lumen import oppnp, photon
transport = jst.PtyTransport(port)


def _exec(code, g):
    exec code in g


def load_script(name):
    """Execute a menu script like OpenPnP does, with fakes for windows/message boxes."""
    src = open(os.path.join(ROOT, "scripts", "Lumen", name)).read()
    lines = src.rstrip().split("\n")
    call = lines[-1]                       # e.g. UpdateDialog()
    src = "\n".join(lines[:-1]) + "\n"
    g = {"__name__": "__main__", "scripting": FakeScripting(), "machine": machine, "gui": gui}
    _exec(compile(src, name, "exec"), g)
    g["JFrame"] = FakeFrame
    g["JOptionPane"] = FakeOptionPane
    # the script reloaded the library: patch the fresh modules
    oppnp_mod = g["oppnp"]
    oppnp_mod.JOptionPane = FakeOptionPane
    oppnp_mod.ActuatorTransport = lambda m: transport
    oppnp_mod.job_state = lambda gu: "Stopped"
    return g, call.replace("()", "")


def wait_idle(obj, t=300):
    end = time.time() + t
    time.sleep(0.3)
    while getattr(obj, "busy", False) and time.time() < end:
        time.sleep(0.2)
    time.sleep(0.5)


print("Feeder Firmware Update dialog")
g, cls = load_script("Feeder_Firmware_Update.py")
d = g[cls]()
check("dialog constructed", d.frame.visible and d.model.getColumnCount() == 7)
d.set_image(os.path.join(work, "new.bin"))
check("binary chosen and described", d.image is not None and d.image.version == "v1.1.9"
      and "v1.1.9" in str(d.image_label.getText()))
machine.setEnabled(False)
FakeOptionPane.messages = []
d.scan()
check("scan refused while machine disabled", any("not enabled" in m for m in FakeOptionPane.messages),
      FakeOptionPane.messages)
machine.setEnabled(True)
d.last_addr.setValue(4)
d.scan()
wait_idle(d)
rows = d.model.rows
check("scan lists 3 feeders", [r["info"].addr for r in rows] == [1, 2, 3], [r["info"].addr for r in rows])
check("old firmware row not tickable", not d.model.isCellEditable(0, 0) and d.model.isCellEditable(1, 0))
check("names from OpenPnP config", "Slot: 2" in rows[1]["name"], rows[1]["name"])
d.model.set_all(lambda r: True)
check("select all ticks only updatable", [r["sel"] for r in rows] == [False, True, True])
d.model.set_all(lambda r: False)
d.model.setValueAt(True, 2, 0)                    # pick only address 3 in the checkbox list
check("checkbox pick of one feeder", [r["sel"] for r in rows] == [False, False, True])
FakeOptionPane.answer = 0
d.update()
wait_idle(d)
check("update result for addr 3", rows[2]["result"].startswith("OK -> v1.1.9"), rows[2]["result"])
check("addr 2 untouched", rows[1]["info"].version == "v1.1.8" and rows[1]["result"] == "")
d.select_outdated()
check("select outdated -> addr 2 only", [r["sel"] for r in rows] == [False, True, False])
FakeOptionPane.answer = 1                         # user says Cancel in the confirmation
d.update()
time.sleep(0.5)
check("cancelled confirmation does nothing", not d.busy and rows[1]["info"].version == "v1.1.8")
log = open(d.log.path).read()
check("log file records update", "addr 3: done" in log and "finished: 1 OK" in log, d.log.path)
d.close()
check("close disposes", d.frame.disposed)

print("Job Readiness dialog")
g, cls = load_script("Job_Readiness.py")
r = g[cls]()
ids = [x["part_id"] for x in r.model.rows]
check("only job parts listed", sorted(ids) == ["C0402", "R0402"], ids)
check("summary text", "3 placement(s)" in str(r.summary.getText()), r.summary.getText())
r.leds(True)
time.sleep(3)
llog = open(r.log.path).read()
check("LEDs set on job feeders", "(2, 'set')" in llog and "(3, 'set')" in llog, llog.strip()[-160:])

print("Last Placements dialog")
from lumen import journal
journal.record(FakeScripting(), str(job.getFile().getAbsolutePath()), parts["R0402"], None,
               board.getPlacements().get("P2"), bl, None)
job.storePlacedStatus(bl, "P2", True)
g, cls = load_script("Last_Placements.py")
lp = g[cls]()
check("journal row shown", len(lp.model.rows) == 1 and lp.model.getValueAt(0, 5) == "yes")
FakeOptionPane.answer = 0
lp.unplace(lp.model.rows[:1])
check("mark LAST not placed", not job.retrievePlacedStatus(bl, "P2") and lp.model.getValueAt(0, 5) == "no")

print("Preflight")
g, cls = load_script("Preflight.py")
pf = g[cls]()
pf.run()
end = time.time() + 120
while not pf.run_btn.isEnabled() and time.time() < end:
    time.sleep(0.2)
res = dict((row[0], row[1]) for row in pf.model.rows)
check("preflight ran all steps", len(res) == 8 and "..." not in res.values(), res)
check("home / job / readiness / bus pass", all(res.get(k) == "PASS" for k in
      ("machine_enabled", "job_open", "home", "job_readiness", "feeder_bus")), res)
machine.setEnabled(False)

print("\n%d/%d checks passed" % (sum(results), len(results)))
from java.lang import System
System.exit(0 if all(results) else 1)
