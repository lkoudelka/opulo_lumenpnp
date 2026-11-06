# 1) restore the target's orientation (N1 left it at rot 180 at 240.625/189.376; N1 e = -0.007/+0.017)
# 2) calibrate N2 (N08) with the same target, returning it in its original orientation
from lumen import zprobe, nozzlecal
reload(zprobe)
reload(nozzlecal)
from java.io import File
from javax.imageio import ImageIO

def save(name, img):
    p = os.path.join(os.path.dirname(trace_path), "%s-%s.png" % (name, time.strftime("%H%M%S")))
    ImageIO.write(img, "png", File(p))
    say("  image %s" % p)
n1, n2 = machine.getDefaultHead().getNozzles()[0], machine.getDefaultHead().getNozzles()[1]
C = (240.720, 189.430)
try:
    f, _ = oppnp.run_machine_task(machine, lambda: nozzlecal.look_disc(machine, C[0], C[1], 5.45, 5.3))
    say("  target now at %.3f/%.3f" % f[:2])
    oppnp.run_machine_task(machine, lambda: nozzlecal.restore(n1, f[:2], C, 180.0, 0.0, (-0.007, 0.017), 6.9, 5.0, say))
    g, img = oppnp.run_machine_task(machine, lambda: nozzlecal.look_disc(machine, C[0], C[1], 5.45, 5.3))
    save("cal-restored", img)
    say("  target restored at %.3f/%.3f (%.3f mm from C)" % (g[0], g[1], ((g[0] - C[0]) ** 2 + (g[1] - C[1]) ** 2) ** 0.5))
    r = oppnp.run_machine_task(machine, lambda: nozzlecal.calibrate(machine, n2, C, 5.3, 5.45, 7.0, 5.0, log=say, save=save))
    say("  RESULT N2 %s" % r)
    check("N2 calibrated, target returned within 0.15 mm", r.get("final") is not None and
          ((r["final"][0] - r["C"][0]) ** 2 + (r["final"][1] - r["C"][1]) ** 2) ** 0.5 < 0.15, r)
except Exception as e:
    say("  STOPPED: %s" % e)
    check("N2 calibration", False, str(e))
