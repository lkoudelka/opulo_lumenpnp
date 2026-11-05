# Run with OpenPnP's own Jython:
#   java -jar /opt/openpnp/lib/jython-standalone-2.7.1.jar tests/jython_smoke.py WORKDIR SIMPORT
# WORKDIR contains new.bin and the simulator runs on SIMPORT (started by run_jython_smoke.sh).
# Checks that lib/lumen/photon.py works unchanged in Jython 2.7 (same interpreter as OpenPnP).
from __future__ import print_function
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "..", "lib"))
from lumen import photon
sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[0])))
from jython_smoke_transport import PtyTransport


work, port = sys.argv[1], sys.argv[2]
bus = photon.Bus(PtyTransport(port))
img = photon.Image.load(os.path.join(work, "new.bin"))
print("jython", sys.version.split()[0], "image:", img.describe(), img.problems)
found = photon.scan(bus, range(1, 4))
print("scan:", dict((a, (f.mode, f.version, f.update_status())) for a, f in found.items()))
after = photon.flash_one(bus, 2, img)
ok = after.version == img.version and sorted(found) == [1, 2, 3] and not img.problems
print("JYTHON SMOKE", "PASS" if ok else "FAIL", "-> addr 2 now", after.version, "packets", bus.packets)
sys.exit(0 if ok else 1)
