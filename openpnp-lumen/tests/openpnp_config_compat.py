# Compatibility with the REAL machine configuration (sandbox copy of ~/.openpnp2), see
# tests/run_config_compat.sh: the installed Lumen scripts must not change what OpenPnP loads,
# and the journal hook must run through OpenPnP's own scripting engine without ever raising.
from __future__ import print_function
import json
import os
import sys

sandbox = sys.argv[1]
from java.io import File
from java.util import HashMap
from org.openpnp.model import Configuration, Location, LengthUnit, Board, BoardLocation, Placement, Part
from org.openpnp.scripting import Scripting

results = []


from java.lang import System as _Sys


def check(name, cond, detail=""):
    # java System.out: OpenPnP's script engine redirects Python's sys.stdout in this JVM
    results.append(bool(cond))
    _Sys.out.println("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


Configuration.initialize(File(sandbox))
Configuration.get().load()
m = Configuration.get().getMachine()
names = sorted(str(a.getName()) for a in m.getActuators())
check("real config loads with Lumen installed", m is not None, names)
check("actuators as in machine.xml", all(n in names for n in ("LED", "PhotonFeederData")), names)
check("feeders / parts loaded", len(m.getFeeders()) == int(sys.argv[2]) and len(Configuration.get().getParts()) == int(sys.argv[3]),
      "%d feeders, %d parts" % (len(m.getFeeders()), len(Configuration.get().getParts())))

sc = Scripting(File(os.path.join(sandbox, "scripts")))
menu = sorted(os.listdir(os.path.join(sandbox, "scripts", "Lumen")))
check("menu scripts present", menu == ["Feeder_Firmware_Update.py", "Job_Readiness.py", "Last_Placements.py", "Orientation_Setup.py", "Pick_Offset_Learning.py", "Preflight.py"], menu)
part = Part("R1")
b = Board(); pl = Placement("C7"); pl.setPart(part); b.addPlacement(pl)
bl = BoardLocation(b)
params = HashMap()
for k, v in (("part", part), ("nozzle", m.getDefaultHead().getDefaultNozzle()), ("placement", pl),
             ("boardLocation", bl), ("placementLocation", Location(LengthUnit.Millimeters, 1, 2, 3, 4)),
             ("jobProcessor", None)):
    params.put(k, v)
params.put("scripting", sc)
try:
    sc.on("Job.Placement.Complete", params)
    ok = True
except Exception as e:
    ok = False
jp = os.path.join(sandbox, "lumen", "placement-journal.jsonl")
lines = open(jp).read().splitlines() if os.path.isfile(jp) else []
check("journal hook runs via OpenPnP Scripting.on()", ok and lines and json.loads(lines[-1])["placement"] == "C7",
      lines[-1:] or "(no journal; note: no GUI -> job file unknown is expected)")
bad = HashMap(); bad.put("scripting", sc)          # missing variables: hook must swallow the error
try:
    sc.on("Job.Placement.Complete", bad)
    check("journal hook never raises into the job", True)
except Exception as e:
    check("journal hook never raises into the job", False, e)
_Sys.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
from java.lang import System
System.exit(0 if all(results) else 1)
