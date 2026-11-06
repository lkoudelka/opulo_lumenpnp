# Pick vacuum check + feed hook + identify packet + Feeder Part Check options, with the real OpenPnP
# classes on a COPY of the user's configuration, WITHOUT a machine (no motion, no serial port).
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
ROOT = os.path.join(HERE, "..")
sandbox = sys.argv[1]
os.makedirs(os.path.join(sandbox, "lumen"))
os.symlink(os.path.join(ROOT, "lib"), os.path.join(sandbox, "lumen", "lib"))
ev = os.path.join(sandbox, "scripts", "Events")
os.makedirs(ev)
for n in ("Feeder.BeforeFeed.py", "Nozzle.AfterPick.py"):
    os.symlink(os.path.join(ROOT, "events", n), os.path.join(ev, n))
sys.path.insert(0, os.path.join(ROOT, "lib"))
from java.io import File
from java.lang import System as S
from java.lang import Throwable
from java.util import HashMap
from org.openpnp.model import Configuration
Configuration.initialize(File(sandbox))
Configuration.get().load()
machine = Configuration.get().getMachine()
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    S.out.println("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def settings(d):
    f = open(os.path.join(sandbox, "lumen", "settings.json"), "w")
    json.dump(d, f)
    f.close()


f48 = [f for f in machine.getFeeders() if str(getattr(f, "getHardwareId", lambda: "")() or "").upper() == "001980104648570520333535"][0]
n1 = machine.getDefaultHead().getNozzles()[0]


class FakeNozzle(object):
    """the real N1 for ids/tip, a scripted vacuum level instead of the sensor"""
    level = 224.0

    def getId(self):
        return n1.getId()

    def getName(self):
        return n1.getName()

    def getNozzleTip(self):
        return n1.getNozzleTip()

    def readVacuumLevel(self):
        return FakeNozzle.level


fake = FakeNozzle()
scr = Configuration.get().getScripting()


def fire(event, **kw):
    m = HashMap()
    for k, v in kw.items():
        m.put(k, v)
    scr.on(event, m)


settings({"pickvac": {"enabled": True, "threshold": {"N045": 3, "N08": 7, "*": 3}}})
logs = os.path.join(sandbox, "lumen", "logs")
S.out.println("pick vacuum check through OpenPnP's Scripting.on (no machine)")
for lv in (224, 224, 223, 225):
    FakeNozzle.level = lv
    fire("Feeder.BeforeFeed", feeder=f48, nozzle=fake, part=f48.getPart())     # remembers the feeder (no motion)
    fire("Nozzle.AfterPick", nozzle=fake, part=f48.getPart())
hist = json.loads(S.getProperty("lumen.pickvac.history.001980104648570520333535." + n1.getNozzleTip().getName(), "[]"))
check("good picks learned per feeder and tip", hist == [224.0, 224.0, 223.0, 225.0], hist)
check("no re-centring requested after good picks", S.getProperty("lumen.feedwatch.force.001980104648570520333535") is None)
FakeNozzle.level = 229
fire("Feeder.BeforeFeed", feeder=f48, nozzle=fake, part=f48.getPart())
fire("Nozzle.AfterPick", nozzle=fake, part=f48.getPart())
check("edge pick (229 vs typical 224, threshold 3 for N045) -> re-centring requested",
      S.getProperty("lumen.feedwatch.force.001980104648570520333535") == "1")
txt = "".join(open(os.path.join(logs, f)).read() for f in sorted(os.listdir(logs))) if os.path.isdir(logs) else ""
check("logged in feedwatch log", "PICKVAC" in txt and "edge pick" in txt, txt.strip().split("\n")[-1:])
# the next feed: before_feed sees the request; check_feeder replaced (it would move the camera)
from lumen import feedwatch, feedercheck
calls = []
_real_check = feedercheck.check_feeder
feedercheck.check_feeder = lambda m, f, save=None: calls.append(f.getName()) or {"error": "camera replaced in this test"}
feedwatch.before_feed(machine, f48, fake)
check("next feed: the forced camera check runs once (feeder not ticked 'While feeding')", len(calls) == 1, calls)
check("request cleared after the check", S.getProperty("lumen.feedwatch.force.001980104648570520333535") is None)
feedwatch.before_feed(machine, f48, fake)
check("following feed: no check (not ticked, no request)", len(calls) == 1)
settings({"pickvac": {"enabled": False}})
FakeNozzle.level = 240
fire("Nozzle.AfterPick", nozzle=fake, part=f48.getPart())
check("disabled: nothing happens", S.getProperty("lumen.feedwatch.force.001980104648570520333535") is None)
S.setProperty("lumen.lastfeed." + str(n1.getId()), json.dumps({"feeder": "X", "name": "x", "part": "other", "t": 0}))
settings({"pickvac": {"enabled": True}})
from lumen import pickvac
check("manual pick (no recent feed on this nozzle): not judged", pickvac.after_pick(machine, fake, f48.getPart()) is None)

S.out.println("action 'recycle, synchronise and pick again' (repick)")
S.clearProperty("lumen.feedwatch.force.001980104648570520333535")
part = f48.getPart()
old_retry = part.getPickRetryCount()
settings({"pickvac": {"enabled": True, "threshold": {"N045": 3, "*": 3}, "action": "repick"}})
part.setPickRetryCount(0)
FakeNozzle.level = 230
fire("Feeder.BeforeFeed", feeder=f48, nozzle=fake, part=part)
raised = None
try:
    fire("Nozzle.AfterPick", nozzle=fake, part=part)
except (Exception, Throwable) as e:
    raised = e
check("part pick retry count 0: no exception (job not stopped), only re-centring requested",
      raised is None and S.getProperty("lumen.feedwatch.force.001980104648570520333535") == "1", raised)
S.clearProperty("lumen.feedwatch.force.001980104648570520333535")
part.setPickRetryCount(2)
fire("Feeder.BeforeFeed", feeder=f48, nozzle=fake, part=part)
raised = None
try:
    fire("Nozzle.AfterPick", nozzle=fake, part=part)
except (Exception, Throwable) as e:
    raised = e
check("pick retry count 2: the hook makes the pick FAIL (OpenPnP then discards and picks again)",
      raised is not None and "RECYCLE" in str(raised), str(raised)[:160])
check("... and the re-feed will re-centre (synchronise)", S.getProperty("lumen.feedwatch.force.001980104648570520333535") == "1")
FakeNozzle.level = 224
raised = None
try:
    fire("Feeder.BeforeFeed", feeder=f48, nozzle=fake, part=part)
    fire("Nozzle.AfterPick", nozzle=fake, part=part)
except (Exception, Throwable) as e:
    raised = e
check("good pick with action repick: no exception", raised is None, raised)
part.setPickRetryCount(old_retry)
S.clearProperty("lumen.feedwatch.force.001980104648570520333535")

S.out.println("identify packet (fake transport)")
sent = []


class T(object):
    def transact_hex(self, h):
        sent.append(h)
        b = [int(h[i:i + 2], 16) for i in range(0, len(h), 2)]
        from lumen import photon
        rep = [0x00, b[0], b[2], 1]
        return photon.to_hex(rep + [photon.crc8(rep + [0])] + [0])
f48.setSlotAddress(48)
addr = feedercheck.identify(machine, f48, T())
pkt = [int(sent[0][i:i + 2], 16) for i in range(0, len(sent[0]), 2)]
check("IDENTIFY_FEEDER to address 48: cmd 0xC1 + the feeder's UUID", addr == 48 and pkt[0] == 48 and pkt[5] == 0xC1
      and "".join("%02X" % v for v in pkt[6:18]) == "001980104648570520333535", sent[0])
S.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
S.exit(0 if all(results) else 1)
