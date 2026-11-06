# nozzle offset calibration with the target disc (5.3 mm, top Z 5.45, plate 4.55): N1
from lumen import zprobe, nozzlecal
reload(zprobe)
reload(nozzlecal)
from java.io import File
from javax.imageio import ImageIO

def save(name, img):
    p = os.path.join(os.path.dirname(trace_path), "%s-%s.png" % (name, time.strftime("%H%M%S")))
    ImageIO.write(img, "png", File(p))
    say("  image %s" % p)

n1 = machine.getDefaultHead().getNozzles()[0]
try:
    r = oppnp.run_machine_task(machine, lambda: nozzlecal.calibrate(machine, n1, (240.624, 189.420), 5.3, 5.45, 7.0, 5.0, log=say, save=save))
    say("  RESULT %s" % r)
    check("N1 calibrated, disc returned within 0.15 mm", r.get("final") is not None and
          ((r["final"][0] - r["C"][0]) ** 2 + (r["final"][1] - r["C"][1]) ** 2) ** 0.5 < 0.15, r)
except Exception as e:
    say("  STOPPED: %s" % e)
    check("calibration", False, str(e))
