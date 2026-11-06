# OpenPnP pick/place of the target (calibration Z from the config, no vacuum Z sensing): park -> visual home -> park
from lumen import nozzlecal
reload(nozzlecal)
head = machine.getDefaultHead()
from org.openpnp.model import LengthUnit
prim = head.getCalibrationPrimaryFiducialLocation().convertToUnits(LengthUnit.Millimeters)
dia = head.getCalibrationTestObjectDiameter().convertToUnits(LengthUnit.Millimeters).getValue()
n1 = head.getNozzles()[0]
HOME = (240.624, 189.420)
def run():
    c, _ = nozzlecal.look_disc(machine, HOME[0], HOME[1], prim.getZ(), dia)
    say("  target at park %.3f/%.3f" % c[:2])
    nozzlecal.carry(machine, n1, c[:2], (prim.getX(), prim.getY()), prim.getZ(), say)
    d, _ = nozzlecal.look_disc(machine, prim.getX(), prim.getY(), prim.getZ(), dia)
    say("  target on visual home at %.3f/%.3f (%.3f mm from the fiducial)" % (d[0], d[1], ((d[0] - prim.getX()) ** 2 + (d[1] - prim.getY()) ** 2) ** 0.5))
    nozzlecal.carry(machine, n1, d[:2], HOME, prim.getZ(), say)
    f, _ = nozzlecal.look_disc(machine, HOME[0], HOME[1], prim.getZ(), dia)
    say("  target back at %.3f/%.3f (%.3f mm from home)" % (f[0], f[1], ((f[0] - HOME[0]) ** 2 + (f[1] - HOME[1]) ** 2) ** 0.5))
    return d, f
try:
    d, f = oppnp.run_machine_task(machine, run)
    check("carry with OpenPnP pick/place, back home within 0.15 mm", ((f[0] - HOME[0]) ** 2 + (f[1] - HOME[1]) ** 2) ** 0.5 < 0.15, f)
except Exception as e:
    say("  STOPPED: %s" % e)
    check("carry", False, str(e))
