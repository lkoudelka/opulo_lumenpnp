# Jython helper for test_profiles.py: load a config dir with the real OpenPnP 2.6 classes,
# optionally edit + save it like the GUI would, and print nozzle / bottom-vision state as JSON.
#   dump CFG            -> JSON
#   tune CFG            -> lumen-only tuning + a common edit, then Configuration.save()
import json
import sys
from java.io import File
from java.lang import System
from org.openpnp.model import Configuration, Length, LengthUnit, Location
mode, cfg = sys.argv[1], sys.argv[2]
Configuration.initialize(File(cfg))
Configuration.get().load()
m = Configuration.get().getMachine()
mm = LengthUnit.Millimeters
if mode == "tune":
    for n in m.getDefaultHead().getNozzles():
        if n.getClass().getSimpleName() == "ContactProbeNozzle":
            n.setContactProbeDepthZ(Length(3.3, mm))              # lumen-only tuning
    n1 = m.getDefaultHead().getNozzle("N1")
    n1.setHeadOffsets(Location(mm, -23.5, -64.888, 0, 0))         # common calibration edit
    bvs = Configuration.get().getVisionSettings("BVS_Default")
    try:
        bvs.setCheckSizeTolerancePercent(30)                      # lumen-only tuning
    except Exception:
        pass
    Configuration.get().save()
out = {"nozzles": {}, "bvs": {}}
for n in m.getDefaultHead().getNozzles():
    d = {"class": n.getClass().getSimpleName(), "head_offsets": str(n.getHeadOffsets()),
         "vac": str(n.getVacuumActuator().getName()), "vac_sense": str(n.getVacuumSenseActuator().getName()),
         "rotation_mode": str(n.getRotationMode()), "tips": sorted(str(t.getId()) for t in n.getCompatibleNozzleTips())}
    if d["class"] == "ContactProbeNozzle":
        d.update({"method": str(n.getContactProbeMethod()), "feeder_probing": str(n.getFeederHeightProbing()),
                  "part_probing": str(n.getPartHeightProbing()), "depth": n.getContactProbeDepthZ().getValue()})
    out["nozzles"][str(n.getName())] = d
b = Configuration.get().getVisionSettings("BVS_Default")
out["bvs"] = {"method": str(b.getCheckPartSizeMethod()), "tolerance": b.getCheckSizeTolerancePercent()}
System.out.println("JSON " + json.dumps(out, sort_keys=True))
System.exit(0)
