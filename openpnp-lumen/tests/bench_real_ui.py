# REAL MACHINE bench test of the Lumen menu scripts (Jython, real OpenPnP classes, real serial port).
#   tests/run_bench_real_ui.sh scan [LAST]          (addresses 1..LAST)
#   tests/run_bench_real_ui.sh update IMAGE.bin ADDR
# Safety:
# - works on a COPY of ~/.openpnp2 (the real configuration is never written);
# - in that copy HOME_COMMAND / MOVE_TO_COMMAND are replaced by an M118 echo, so nothing can
#   home or move even if some code asked for it (any such attempt shows up in the trace);
# - only Feeder Firmware Update is driven: no feed, no pick, no actuator.
from __future__ import print_function
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "lib"))
sandbox, trace_path, mode = sys.argv[1], sys.argv[2], sys.argv[3]
args = sys.argv[4:]

from java.io import File, FileOutputStream, PrintStream
from java.lang import System as _Sys
from org.pmw.tinylog import Configurator, Level
from org.pmw.tinylog.writers import FileWriter
Configurator.currentConfig().writer(FileWriter(trace_path)).level(Level.TRACE).activate()

from org.openpnp.model import Configuration
if not os.path.exists(os.path.join(sandbox, "lumen", "lib")):
    os.makedirs(os.path.join(sandbox, "lumen"))
    os.symlink(os.path.join(ROOT, "lib"), os.path.join(sandbox, "lumen", "lib"))
Configuration.initialize(File(sandbox))
Configuration.get().load()
machine = Configuration.get().getMachine()
results = []


def say(s):
    _Sys.out.println(s)


def check(name, cond, detail=""):
    results.append(bool(cond))
    say("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


class FakeFrame(object):
    def __init__(self, title=""):
        self.visible, self.disposed = False, False

    def __getattr__(self, name):
        return lambda *a, **k: None

    def setVisible(self, v):
        self.visible = v

    def dispose(self):
        self.disposed = True


class FakeOptionPane(object):
    OK_OPTION = YES_OPTION = 0
    NO_OPTION = 1
    OK_CANCEL_OPTION = YES_NO_OPTION = 2
    PLAIN_MESSAGE = -1
    answer = 0
    messages = []

    @classmethod
    def showMessageDialog(cls, parent, msg, *a):
        cls.messages.append(str(msg))
        say("  (dialog) " + str(msg).replace("\n", " | "))

    @classmethod
    def showConfirmDialog(cls, parent, msg, *a):
        cls.messages.append(str(msg))
        say("  (confirm -> OK) " + str(msg).replace("\n", " | "))
        return cls.answer


class FakeScripting(object):
    def getScriptsDirectory(self):
        return File(os.path.join(sandbox, "scripts"))


class FakeGui(object):
    def getJobTab(self):
        return None


def _exec(code, g):
    exec code in g


def load_script(name):
    src = open(os.path.join(ROOT, "scripts", "Lumen", name)).read().rstrip().split("\n")
    g = {"__name__": "__main__", "scripting": FakeScripting(), "machine": machine, "gui": FakeGui()}
    _exec(compile("\n".join(src[:-1]) + "\n", name, "exec"), g)
    g["JFrame"] = FakeFrame
    g["JOptionPane"] = FakeOptionPane
    g["oppnp"].JOptionPane = FakeOptionPane
    g["oppnp"].job_state = lambda gu: "Stopped"      # no job tab here; nothing runs
    return g, src[-1].replace("()", "")


def wait_idle(obj, t=900):
    end = time.time() + t
    time.sleep(0.5)
    while getattr(obj, "busy", False) and time.time() < end:
        time.sleep(0.5)
    time.sleep(0.5)


def rows_text(d):
    return ["%3d  %-26s %-18s %-24s %s" % (r["info"].addr, r["info"].uuid_hex or "-", r["info"].version or r["info"].mode,
                                           r["info"].update_status(), r.get("result", "")) for r in d.model.rows]


def capture_all(tag):
    from javax.imageio import ImageIO
    for cam in list(machine.getDefaultHead().getCameras()) + list(machine.getCameras()):
        try:
            img = cam.settleAndCapture()
            out = os.path.join(os.path.dirname(trace_path), "bench-%s-%s-%s.png" % (tag, cam.getName(), time.strftime("%H%M%S")))
            ImageIO.write(img, "png", File(out))
            check("%s camera image (%s): %dx%d" % (cam.getName(), tag, img.getWidth(), img.getHeight()),
                  img.getWidth() > 640 or img.getHeight() > 480, out)
        except Exception as e:
            check("%s camera image (%s)" % (cam.getName(), tag), False, str(e))


def run_verify(addr):
    """Verified config: visual homing (camera + fiducial vision), camera images, ONE 4 mm feed of ADDR."""
    from lumen import oppnp, photon
    say("homing (visual homing of this configuration: moves the camera to the homing fiducial)")
    t0 = time.time()
    try:
        oppnp.run_machine_task(machine, lambda: machine.home())
        check("homed incl. visual homing in %.1f s" % (time.time() - t0), machine.isHomed())
    except Exception as e:
        check("homing", False, str(e))
        return
    cam = machine.getDefaultHead().getDefaultCamera()
    say("  top camera now at %s" % cam.getLocation())
    capture_all("homed")
    bus = photon.Bus(oppnp.ActuatorTransport(machine))
    fd = photon.Feeder(bus, addr)

    def feed():
        r = fd.app(photon.GET_FEEDER_ID)
        if not r or r[0] != 0:
            return "no answer from feeder %d" % addr
        uuid = r[1:13]
        if not fd.initialize(uuid):
            return "INITIALIZE failed"
        r = bus.transact(addr, 0x04, [40], retries=0)            # MOVE_FEED_FORWARD 4.0 mm, never repeated
        if not r or r[0] != 0:
            return "MOVE_FEED_FORWARD refused / no reply: %s" % r
        ms = (r[1] << 8 | r[2]) if len(r) >= 3 else 1000
        say("  feeder %d (%s): feeding 4 mm, expected %d ms" % (addr, photon.to_hex(uuid), ms))
        time.sleep(ms / 1000.0 + 0.2)
        for _ in range(20):
            r = bus.transact(addr, 0x06, [], retries=0)           # MOVE_FEED_STATUS
            if r:
                return {0: "OK", 4: "still feeding", 5: "FAIL", 6: "COULDNT_REACH"}.get(r[0], "status 0x%02X" % r[0])
            time.sleep(0.2)
        return "no status reply"
    t0 = time.time()
    res = oppnp.run_machine_task(machine, feed)
    check("feeder %d moved 4 mm forward: %s (%.1f s)" % (addr, res, time.time() - t0), res == "OK")


def look(name, x, y, z, out_dir=None):
    """Move the TOP camera to (x, y) at safe Z (view plane z for 3D units per pixel), capture, save
    PNG + JSON sidecar {camera location, mm per pixel, size}.  Returns (path, meta)."""
    import json
    from org.openpnp.model import LengthUnit, Location
    from org.openpnp.util import MovableUtils
    from javax.imageio import ImageIO
    cam = machine.getDefaultHead().getDefaultCamera()
    from lumen import oppnp
    oppnp.run_machine_task(machine, lambda: MovableUtils.moveToLocationAtSafeZ(cam, Location(LengthUnit.Millimeters, x, y, z, 0)))
    img = cam.settleAndCapture()
    loc = cam.getLocation().convertToUnits(LengthUnit.Millimeters)
    from org.openpnp.model import Length
    upp = cam.getUnitsPerPixel(Length(z, LengthUnit.Millimeters)).convertToUnits(LengthUnit.Millimeters)
    d = out_dir or os.path.dirname(trace_path)
    path = os.path.join(d, "look-%s-%s.png" % (name, time.strftime("%H%M%S")))
    ImageIO.write(img, "png", File(path))
    meta = {"name": name, "camera": [loc.getX(), loc.getY(), loc.getZ()], "upp": [upp.getX(), upp.getY()],
            "size": [img.getWidth(), img.getHeight()], "requested": [x, y, z]}
    open(path[:-4] + ".json", "w").write(json.dumps(meta))
    say("  look %s: camera at %.3f/%.3f z %.2f, %.5f mm/px -> %s" % (name, loc.getX(), loc.getY(), loc.getZ(), upp.getX(), path))
    return path, meta


def run_exec(snippet):
    """Home (visual homing of the configuration), then run a reviewed snippet with machine helpers."""
    from lumen import oppnp
    say("homing")
    t0 = time.time()
    oppnp.run_machine_task(machine, lambda: machine.home())
    check("homed in %.1f s" % (time.time() - t0), machine.isHomed())
    g = {"machine": machine, "say": say, "check": check, "look": look, "oppnp": oppnp, "time": time, "os": os,
         "trace_path": trace_path, "args": args[1:], "load_script": load_script, "wait_idle": wait_idle,
         "FakeOptionPane": FakeOptionPane}
    say("running %s" % snippet)
    _exec(compile(open(snippet).read(), snippet, "exec"), g)


def run_preflight(addr, uuid):
    """Test job with one part on Photon feeder ADDR (sandbox config only), Preflight, camera image."""
    global gui
    from org.openpnp.model import (Board, BoardLocation, Job, Length, LengthUnit, Location, Part, Placement,
                                   Abstract2DLocatable)
    from org.openpnp.machine.photon import PhotonFeeder
    mm = LengthUnit.Millimeters
    part = Part("BENCH-R0402")
    part.setHeight(Length(0.4, mm))
    Configuration.get().addPart(part)
    f = PhotonFeeder()
    f.setSlotAddress(addr)
    f.setHardwareId(uuid)
    f.setPart(part)
    f.setEnabled(True)
    machine.addFeeder(f)
    board = Board()
    board.setName("bench")
    pl = Placement("R1")
    pl.setPart(part)
    pl.setLocation(Location(mm, 5, 5, 0, 0))
    pl.setSide(Abstract2DLocatable.Side.Top)
    board.addPlacement(pl)
    bl = BoardLocation(board)
    bl.setGlobalSide(Abstract2DLocatable.Side.Top)
    job = Job()
    job.addBoardOrPanelLocation(bl)

    class Tab(object):
        def getJob(self):
            return job

    class G(object):
        def getJobTab(self):
            return Tab()
    g, cls = load_script("Preflight.py")
    g["gui"] = G()
    p = g[cls]()
    say("Preflight: Run checks (homes the machine)")
    t0 = time.time()
    p.run()
    end = time.time() + 300
    time.sleep(1)
    while not p.run_btn.isEnabled() and time.time() < end:
        time.sleep(0.5)
    for row in p.model.rows:
        say("  %-16s %-5s %s" % tuple(row))
    say("  " + str(p.head.getText()))
    check("Preflight finished in %.1f s" % (time.time() - t0), p.run_btn.isEnabled())
    check("machine homed", machine.isHomed())
    res = dict((r[0], r[1]) for r in p.model.rows)
    check("home / lights / vacuum sensors PASS, nozzle tips reported",
          all(res.get(k) == "PASS" for k in ("home", "lights", "vacuum_sensors")) and res.get("nozzle_tips") in ("PASS", "WARN"), res)
    check("feeder_bus scans feeder %d although it is not fully set up" % addr, res.get("feeder_bus") == "PASS",
          [r[2] for r in p.model.rows if r[0] == "feeder_bus"])
    check("job_readiness reports the feeder-50 problem (no slot location in this config) instead of passing",
          res.get("job_readiness") == "FAIL", [r[2] for r in p.model.rows if r[0] == "job_readiness"])
    from javax.imageio import ImageIO
    for cam in list(machine.getDefaultHead().getCameras()) + list(machine.getCameras()):
        try:
            img = cam.settleAndCapture()
            out = os.path.join(os.path.dirname(trace_path), "bench-%s-camera-%s.png" % (cam.getName(), time.strftime("%H%M%S")))
            ImageIO.write(img, "png", File(out))
            check("%s camera image at the home position (no move): %dx%d" % (cam.getName(), img.getWidth(), img.getHeight()),
                  img.getWidth() > 640 or img.getHeight() > 480, out)
        except Exception as e:
            check("%s camera image" % cam.getName(), False, str(e))


say("connecting OpenPnP to the machine (%s)" % ("verify mode: motion ALLOWED (homing, camera moves, one 4 mm feed)"
    if mode in ("verify", "exec") else "HOME allowed, MOVE blocked" if mode == "preflight" else "HOME and MOVE blocked"))
t0 = time.time()
machine.setEnabled(True)
check("machine enabled (driver connected)", machine.isEnabled(), "%.1f s" % (time.time() - t0))
try:
    g, cls = load_script("Feeder_Firmware_Update.py")
    d = g[cls]()
    if mode in ("preflight", "verify", "exec"):
        d.last_addr.setValue(1)
    check("Feeder Firmware Update dialog opened", d.frame.visible)
    if mode == "scan":
        last = int(args[0]) if args else 50
        d.last_addr.setValue(last)
        t0 = time.time()
        d.scan()
        wait_idle(d)
        rows = d.model.rows
        say("\n".join(rows_text(d)))
        check("scan through OpenPnP's PhotonFeederData actuator: %d feeder(s) in %.1f s" % (len(rows), time.time() - t0),
              len(rows) > 0)
        upd = [r["info"].addr for r in rows if d.model.isCellEditable(rows.index(r), 0)]
        check("only bus-update feeders can be ticked", True, "tickable: %s" % upd)
    elif mode == "update":
        image, addr = args[0], int(args[1])
        d.set_image(image)
        check("image chosen", d.image is not None, "%s %s" % (os.path.basename(image), d.image.version if d.image else "-"))
        d.last_addr.setValue(addr)
        d.scan()
        wait_idle(d)
        rows = d.model.rows
        idx = [i for i, r in enumerate(rows) if r["info"].addr == addr]
        check("feeder %d found and tickable" % addr, idx and d.model.isCellEditable(idx[0], 0), rows_text(d)[-1:] if rows else "-")
        if idx and d.model.isCellEditable(idx[0], 0):
            d.model.set_all(lambda r: False)
            d.model.setValueAt(True, idx[0], 0)
            check("only feeder %d ticked" % addr, [r["info"].addr for r in rows if r["sel"]] == [addr])
            t0 = time.time()
            d.update()
            wait_idle(d)
            r = rows[idx[0]]
            say("\n".join(rows_text(d)[idx[0]:idx[0] + 1]))
            check("update of feeder %d: %s in %.1f s" % (addr, r["result"], time.time() - t0),
                  r["result"].startswith("OK -> " + d.image.version))
            say("  update log: %s" % d.log.path)
    d.close()
    if mode == "preflight":
        run_preflight(int(args[0]), args[1])
    if mode == "verify":
        run_verify(int(args[0]))
    if mode == "exec":
        run_exec(args[0])
finally:
    machine.setEnabled(False)
    say("machine disabled (driver disconnected)")
say("\n%d/%d checks passed" % (sum(results), len(results)))
_Sys.exit(0 if all(results) else 1)
