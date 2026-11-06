# dry: nozzles in free air at safe Z (NO Z down): vacuum off level, vacuum-on baseline and noise
from lumen import zprobe
reload(zprobe)
from org.openpnp.model import LengthUnit, Location
from org.openpnp.util import MovableUtils
head = machine.getDefaultHead()
for n in head.getNozzles():
    def task(n=n):
        MovableUtils.moveToLocationAtSafeZ(n, Location(LengthUnit.Millimeters, 300.0, 150.0, float("nan"), 0.0))
        off = zprobe.read_level(n, 5)
        on = zprobe.baseline(n, 10)
        return off, on
    off, on = oppnp.run_machine_task(machine, task)
    say("  %s tip %s: vacuum OFF %.1f (sd %.2f)  ON %.1f (sd %.2f)  values %s" % (n.getName(), n.getNozzleTip().getName() if n.getNozzleTip() else None,
        off[0], off[1], on[0], on[1], [int(v) for v in on[2]]))
