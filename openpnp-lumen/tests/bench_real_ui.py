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


say("connecting OpenPnP to the machine (motion commands blocked in this configuration copy)")
t0 = time.time()
machine.setEnabled(True)
check("machine enabled (driver connected)", machine.isEnabled(), "%.1f s" % (time.time() - t0))
try:
    g, cls = load_script("Feeder_Firmware_Update.py")
    d = g[cls]()
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
finally:
    machine.setEnabled(False)
    say("machine disabled (driver disconnected)")
say("\n%d/%d checks passed" % (sum(results), len(results)))
_Sys.exit(0 if all(results) else 1)
