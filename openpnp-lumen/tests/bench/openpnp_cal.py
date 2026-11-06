# target to visual home, OpenPnP nozzle offset calibration N1 + N2, target back to its home spot
from lumen import zprobe, nozzlecal
reload(zprobe)
reload(nozzlecal)
from java.io import File
from javax.imageio import ImageIO

def save(name, img):
    p = os.path.join(os.path.dirname(trace_path), "%s-%s.png" % (name, time.strftime("%H%M%S")))
    ImageIO.write(img, "png", File(p))
    say("  image %s" % p)
noz = list(machine.getDefaultHead().getNozzles())
HOME = (240.624, 189.420)            # original park spot (first camera detection, before any test)
try:
    # the target is still 0.4 mm off its home from the earlier tests: look for it around the home spot
    r = oppnp.run_machine_task(machine, lambda: nozzlecal.calibrate_openpnp(machine, noz, HOME, noz[0], log=say, save=save))
    for k, (o, n) in sorted(r["offsets"].items()):
        say("  RESULT %s: %s -> %s" % (k, o, n))
    check("both nozzles calibrated by OpenPnP", len(r["offsets"]) == 2, r["offsets"].keys())
    check("target back home within 0.15 mm", r.get("final") is not None and
          ((r["final"][0] - HOME[0]) ** 2 + (r["final"][1] - HOME[1]) ** 2) ** 0.5 < 0.15, r.get("final"))
except Exception as e:
    say("  STOPPED: %s" % e)
    check("OpenPnP calibration run", False, str(e))
