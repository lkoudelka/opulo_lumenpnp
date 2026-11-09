# BENCH-TRIALS sections 0-3 without a job: camera only, bus LED, no feed, no pick, no nozzle down.
#   tests/run_bench_real_ui.sh exec tests/bench/trials_cam.py [RAW_DIR]
# Config changes (SkipNext, applied offsets) land in the sandbox copy only.
import json
from org.openpnp.model import LengthUnit

mm = LengthUnit.Millimeters
cam = machine.getDefaultHead().getDefaultCamera()
RAW = args[0] if args else None
RAW_SLOTS = (3, 4, 12, 15, 28, 38)          # 12 mm black, 12 mm + neighbour, paper off-pitch, empty, empty, paper

g, cls = load_script("Feeder_Part_Check.py")
d = g[cls]()
rows = d.model.rows
say("== Feeder Part Check: %d feeder rows" % len(rows))
# PhotonFeeder.isEnabled() is False until the slot address is known on the bus: filter on part + hardware id
idx = [i for i, x in enumerate(rows) if x["feeder"].getPart() is not None and getattr(x["feeder"], "getHardwareId", lambda: "x")()]
say("  with a part and a hardware id: %d" % len(idx))
from java.lang import Throwable
by_slot = {}
for i in idx:
    f = rows[i]["feeder"]
    try:
        if f.getSlotAddress() is None:
            oppnp.run_machine_task(machine, lambda f=f: f.findSlotAddress())
        by_slot[int(f.getSlotAddress())] = i
    except (Exception, Throwable):
        pass
say("  slots on the bus: %s" % sorted(by_slot))

if RAW:
    say("== raw images for the test data (camera only)")
    for s in RAW_SLOTS:
        if s in by_slot:
            p = rows[by_slot[s]]["feeder"].getPickLocation().convertToUnits(mm)
            look("slot%d-raw" % s, p.getX(), p.getY(), p.getZ(), RAW)

say("== Identify, Go to pick location")
d.tabs.setSelectedIndex(0)
first = by_slot.get(48, idx[0])
vi = d.table.convertRowIndexToView(first)
d.table.setRowSelectionInterval(vi, vi)
f0 = rows[first]["feeder"]
d.identify()
time.sleep(3)
check("Identify: feeder confirmed the blink command", "blinking" in str(d.info.getText()), d.info.getText())
d.go_to()
time.sleep(1)
end = time.time() + 60
while "camera at" not in str(d.info.getText()) and "failed" not in str(d.info.getText()) and time.time() < end:
    time.sleep(0.5)
pick = f0.getPickLocation().convertToUnits(mm)
loc = cam.getLocation().convertToUnits(mm)
check("Go to: camera over the pick location of %s" % f0.getName(),
      abs(loc.getX() - pick.getX()) < 0.05 and abs(loc.getY() - pick.getY()) < 0.05, d.info.getText())

say("== Check selected on every feeder with a part (camera only)")
for i, x in enumerate(rows):
    x["sel"] = i in idx
t0 = time.time()
d.check()
wait_idle(d, 1800)
say("  %d feeders in %.0f s" % (len(idx), time.time() - t0))
out = []
for i in idx:
    x = rows[i]
    r = x.get("res") or {}
    say("  | " + " | ".join(str(d.model.getValueAt(i, c)) for c in range(1, 8)))
    out.append({"feeder": x["feeder"].getName(), "slot": r.get("slot"), "part": str(x["feeder"].getPart().getId()),
                "status": x.get("status"), "method": r.get("method"), "part_at_pick": r.get("part_at_pick"),
                "dx": r.get("pocket_dx"), "dy": r.get("pocket_dy"), "error": r.get("error"), "image": r.get("image"),
                "feed_option_after": x["feeder"].getFeedOptions().name()})
json.dump(out, open(os.path.join(os.path.dirname(trace_path), "trials-partcheck-%s.json" % time.strftime("%H%M%S")), "w"), indent=1)
check("no Python error in any row", not [o for o in out if o["error"] and "'" in o["error"][:2]],
      [(o["slot"], o["error"]) for o in out if o["error"] and "'" in o["error"][:2]])
check("empty feeders (no tape) say so, no invented offset",
      all("no tape" in (o["error"] or "") for o in out if o["slot"] in (6, 10, 11, 13, 15, 17, 18, 28, 29, 37)),
      [(o["slot"], o["error"], o["dx"]) for o in out if o["slot"] in (6, 10, 11, 13, 15, 17, 18, 28, 29, 37)])
skipped = [o for o in out if o["part_at_pick"]]
check("part already at pick -> SkipNext set (sandbox)", all(o["feed_option_after"] == "SkipNext" for o in skipped),
      [o["slot"] for o in skipped])

say("== Apply offset (slots 3, 12, 38), then check again (sandbox config)")
k = [by_slot[s] for s in (3, 12, 38) if s in by_slot and (rows[by_slot[s]].get("res") or {}).get("pocket_dx") is not None]
for i, x in enumerate(rows):
    x["sel"] = i in k
want = dict((i, (rows[i]["res"]["pocket_dx"], rows[i]["res"]["pocket_dy"],
                 rows[i]["feeder"].getPickLocation().convertToUnits(mm))) for i in k)
d.apply()
for i in k:
    dx, dy, before = want[i]
    after = rows[i]["feeder"].getPickLocation().convertToUnits(mm)
    check("pick location moved by the shown offset (%s)" % rows[i]["feeder"].getName(),
          abs(after.getX() - before.getX() - dx) < 0.01 and abs(after.getY() - before.getY() - dy) < 0.01,
          "%+.2f / %+.2f" % (dx, dy))
d.check()
wait_idle(d, 600)
for i in k:
    r = rows[i].get("res") or {}
    check("check again after apply: offset < 0.1 mm (%s)" % rows[i]["feeder"].getName(),
          r.get("pocket_dx") is not None and max(abs(r["pocket_dx"]), abs(r["pocket_dy"])) < 0.1,
          "%s / %s %s" % (r.get("pocket_dx"), r.get("pocket_dy"), r.get("error") or ""))

say("== Preflight, no project loaded (empty job)")
from org.openpnp.model import Job
empty = Job()


class _Tab(object):
    def getJob(self):
        return empty


class _G(object):
    def getJobTab(self):
        return _Tab()


gp, clsp = load_script("Preflight.py")
gp["gui"] = _G()
p = gp[clsp]()
t0 = time.time()
p.run()
time.sleep(1)
end = time.time() + 300
while not p.run_btn.isEnabled() and time.time() < end:
    time.sleep(0.5)
for row in p.model.rows:
    say("  %-16s %-5s %s" % tuple(row))
say("  " + str(p.head.getText()))
res = dict((r[0], r[1]) for r in p.model.rows)
check("Preflight finished in %.1f s" % (time.time() - t0), p.run_btn.isEnabled())
check("home / lights / nozzle tips / vacuum sensors PASS",
      all(res.get(x) == "PASS" for x in ("home", "lights", "nozzle_tips", "vacuum_sensors")), res)
check("no project: job_open FAILs with a clear text, no step 'error:'",
      res.get("job_open") == "FAIL" and not [r for r in p.model.rows if "error:" in str(r[2])],
      [r for r in p.model.rows if r[1] != "PASS"])

say("== vacuum baseline in free air (nozzles at safe Z, no Z down)")
from lumen import zprobe
from org.openpnp.model import Location
from org.openpnp.util import MovableUtils
for n in machine.getDefaultHead().getNozzles():
    def task(n=n):
        MovableUtils.moveToLocationAtSafeZ(n, Location(mm, 300.0, 150.0, float("nan"), 0.0))
        return zprobe.read_level(n, 5), zprobe.baseline(n, 10)
    off, on = oppnp.run_machine_task(machine, task)
    say("  %s tip %s: vacuum OFF %.1f (sd %.2f)  ON (free, open tip) %.1f (sd %.2f)" % (
        n.getName(), n.getNozzleTip().getName() if n.getNozzleTip() else None, off[0], off[1], on[0], on[1]))
