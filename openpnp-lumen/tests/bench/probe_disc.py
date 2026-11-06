# gentle probes (start 9.0, max 4 mm travel, 0.05 mm steps, 5 % speed): bare plate next to the rings, then the disc centre
from lumen import zprobe
reload(zprobe)
n1 = machine.getDefaultHead().getNozzles()[0]
out = {}
for name, x, y in (("plate", 230.0, 186.0), ("disc", 240.624, 189.420)):
    try:
        r = oppnp.run_machine_task(machine, lambda x=x, y=y: zprobe.probe(n1, x, y, 9.0, 5.0, max_travel=4.0, log=say))
        out[name] = r["z"]
        say("  %s Z %.3f  tail %s" % (name, r["z"], r["readings"][-4:]))
    except Exception as e:
        say("  %s STOPPED: %s" % (name, e))
if len(out) == 2:
    say("  disc top is %.2f mm above the plate" % (out["disc"] - out["plate"]))
check("plate + disc probed", len(out) == 2, out)
