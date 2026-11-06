# board Z: N1 probes the 4 board fiducials (start 6.0, floor 4.0, 0.05 mm steps, 5 % speed)
import math
from lumen import zprobe
reload(zprobe)
n1 = machine.getDefaultHead().getNozzles()[0]
bx, by, br = 281.87061927526315, 95.5251955507456, -0.9332188672243589
a = math.radians(br)
pts = []
for name, x, y in (("REF_1", 12.0, 3.85), ("REF_2", 88.9202, 3.85), ("REF_3", 88.9202, 104.5), ("REF_4", 12.0, 104.5)):
    mx, my = bx + x * math.cos(a) - y * math.sin(a), by + x * math.sin(a) + y * math.cos(a)
    try:
        r = oppnp.run_machine_task(machine, lambda mx=mx, my=my: zprobe.probe(n1, mx, my, 6.0, 4.0, log=say))
        pts.append((mx, my, r["z"]))
        say("  %s Z %.3f  tail %s" % (name, r["z"], r["readings"][-5:]))
    except Exception as e:
        say("  %s STOPPED: %s" % (name, e))
if len(pts) >= 3:
    mz, tilt, sx, sy = zprobe.plane_tilt(pts)
    say("  board Z mean %.3f, spread %.3f mm, slope %+.3f mm/100mm in X, %+.3f mm/100mm in Y" % (mz, tilt, sx, sy))
check("4 fiducials probed", len(pts) == 4, pts)
