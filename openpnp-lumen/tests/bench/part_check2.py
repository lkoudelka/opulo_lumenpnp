# Feeder Part Check (hole geometry) on white / clear / black tapes + sorting + BeforeFeed hook via OpenPnP Scripting
import json
from java.util import HashMap
from org.openpnp.model import Configuration
HW = {"001980104648570520333535": 48, "000F001C4648570420333535": 26, "0018800B4648570520333535": 27, "000980084648570620333535": 3}
g, cls = load_script("Feeder_Part_Check.py")
d = g[cls]()
for x in d.model.rows:
    x["sel"] = x["hwid"] in HW
d.check()
wait_idle(d, 600)
res = {}
for i, x in enumerate(d.model.rows):
    if x["sel"]:
        res[HW[x["hwid"]]] = x.get("res") or {}
        say("  | " + " | ".join(str(d.model.getValueAt(i, c)) for c in range(2, 9)))
check("hole geometry found on all 4 feeders (white, clear, black)", all(not r.get("error") for r in res.values()),
      dict((k, r.get("error")) for k, r in res.items()))
check("12 mm tape recognised on 26/27/3", all("12 mm" in (res[k].get("method") or "") for k in (26, 27, 3)), [res[k].get("method") for k in (26, 27, 3)])
d.table.getRowSorter().toggleSortOrder(3)
order = [d.model.rows[d.table.convertRowIndexToModel(i)]["feeder"].getSlotAddress() for i in range(d.table.getRowCount())]
order = [o for o in order if o is not None]
check("table sorts by slot (numeric)", order == sorted(order), order[:12])
f48 = [x["feeder"] for x in d.model.rows if x["hwid"] == "001980104648570520333535"][0]
from org.openpnp.machine.reference import ReferenceFeeder
f48.setFeedOptions(ReferenceFeeder.FeedOptions.Normal)
# BeforeFeed hook through OpenPnP's scripting (as the job processor calls it)
cfg = str(Configuration.get().getConfigurationDirectory())
ev = os.path.join(cfg, "scripts", "Events")
if not os.path.isdir(ev):
    os.makedirs(ev)
src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(trace_path))), "_dev/lumenpnp/openpnp-lumen/openpnp-lumen/events/Feeder.BeforeFeed.py")
src = os.path.expanduser("~/claude/opulo/_dev/lumenpnp/openpnp-lumen/openpnp-lumen/events/Feeder.BeforeFeed.py")
if not os.path.exists(os.path.join(ev, "Feeder.BeforeFeed.py")):
    os.symlink(src, os.path.join(ev, "Feeder.BeforeFeed.py"))
sp = os.path.join(cfg, "lumen", "settings.json")
st = json.load(open(sp)) if os.path.exists(sp) else {}
st["feedwatch"] = {"feeders": ["001980104648570520333535"], "every": 1, "confirm": False, "skip_if_part": True, "min_mm": 0.05, "max_mm": 0.5}
json.dump(st, open(sp, "w"))
before = f48.getPickLocation()
m = HashMap()
m.put("feeder", f48); m.put("nozzle", machine.getDefaultHead().getNozzles()[0]); m.put("part", f48.getPart())
oppnp.run_machine_task(machine, lambda: Configuration.get().getScripting().on("Feeder.BeforeFeed", m))
logs = sorted(f for f in os.listdir(os.path.join(cfg, "lumen", "logs")) if f.startswith("feedwatch"))
txt = open(os.path.join(cfg, "lumen", "logs", logs[-1])).read() if logs else ""
say("  feedwatch log: " + txt.strip().replace("\n", " | "))
check("hook: part at pick on feeder 48 -> SkipNext", f48.getFeedOptions().name() == "SkipNext", f48.getFeedOptions())
check("hook logged the check", "48" in txt or "001980104648570520333535" in txt, txt[:200])
say("  pick before %s after %s" % (before, f48.getPickLocation()))
