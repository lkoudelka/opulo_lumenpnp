# homed on the secondary calibration fiducial (main homing fiducial covered by the target):
# 1. frame check on board fiducial REF_1, 2. find target on the visual home, 3. OpenPnP carry back to park
from lumen import nozzlecal
reload(nozzlecal)
from org.openpnp.model import LengthUnit
head = machine.getDefaultHead()
prim = head.getCalibrationPrimaryFiducialLocation().convertToUnits(LengthUnit.Millimeters)
dia = head.getCalibrationTestObjectDiameter().convertToUnits(LengthUnit.Millimeters).getValue()
n1 = head.getNozzles()[0]
HOME = (240.624, 189.420)
p, meta = look("frame-REF_1", 293.932, 99.179, 4.3)
def run():
    d, _ = nozzlecal.look_disc(machine, prim.getX(), prim.getY(), prim.getZ(), dia)
    if not d:
        raise RuntimeError("target not found on the visual home")
    say("  target on visual home at %.3f/%.3f (%.3f mm from the fiducial)" % (d[0], d[1], ((d[0] - prim.getX()) ** 2 + (d[1] - prim.getY()) ** 2) ** 0.5))
    nozzlecal.carry(machine, n1, d[:2], HOME, prim.getZ(), say)
    f, _ = nozzlecal.look_disc(machine, HOME[0], HOME[1], prim.getZ(), dia)
    if f:
        say("  target back at %.3f/%.3f (%.3f mm from its park spot)" % (f[0], f[1], ((f[0] - HOME[0]) ** 2 + (f[1] - HOME[1]) ** 2) ** 0.5))
    return d, f
try:
    d, f = oppnp.run_machine_task(machine, run)
    check("target back at park", f is not None, f)
except Exception as e:
    say("  STOPPED: %s" % e)
    check("return", False, str(e))
