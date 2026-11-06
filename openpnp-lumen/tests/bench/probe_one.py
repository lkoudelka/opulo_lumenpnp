# ONE contact probe (safe version): N1 on board fiducial REF_1, start Z 6.0 (floor 4.0), 0.05 mm steps at 5 % speed,
# max 2 mm travel (never below 2.0); free-air level read at safe Z
from lumen import zprobe
reload(zprobe)
n1 = machine.getDefaultHead().getNozzles()[0]
try:
    res = oppnp.run_machine_task(machine, lambda: zprobe.probe(n1, 293.932, 99.179, 6.0, 4.0, log=say))
    say("  readings (z, level): %s" % res["readings"])
    check("REF_1 surface Z = %.3f" % res["z"], True, "")
except Exception as e:
    say("  PROBE STOPPED: %s" % e)
    check("probe", False, str(e))
