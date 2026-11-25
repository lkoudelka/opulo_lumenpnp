# Safe homing guard (lib/lumen/homeguard.py) on OpenPnP's SIMULATED machine (stock config, NullDriver), headless.
#   tests/run_homeguard_sim.sh
# Real: machine, head, nozzles, safe Z zones, homing, Swing actions / buttons / menu items.  Faked: OpenPnP's main
# window (a stand-in with the real HomeAction-like action, a button, a menu item and the hotkey map), the dialogs.
import os
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sandbox = sys.argv[1]

from java.io import File
from java.lang import System as _Sys
from java.util import HashMap
from javax.swing import AbstractAction, JButton, JMenu, JMenuBar, JMenuItem, JPanel, KeyStroke
from org.openpnp.model import Configuration, LengthUnit, Location

Configuration.initialize(File(sandbox))
Configuration.get().load()
machine = Configuration.get().getMachine()
mm = LengthUnit.Millimeters
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    _Sys.out.println("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


from lumen import homeguard, machinecal, oppnp

head = machine.getDefaultHead()
n1 = head.getNozzles()[0]
machine.setEnabled(True)
oppnp.run_machine_task(machine, lambda: machine.home())
check("simulated machine homed", machine.isHomed())
zone = n1.getSafeZZone()
check("stock N1 has a safe Z zone", zone is not None and zone[0] is not None, zone)
safe_low = zone[0].convertToUnits(mm).getValue()


class Rec(object):
    """The machine, recording the nozzle heights at the moment homing starts (G28 in the real driver)."""

    def __init__(self, m):
        self.m, self.at_home = m, []

    def home(self):
        self.at_home.append([(n.getName(), n.getLocation().convertToUnits(mm).getZ()) for n in head.getNozzles()])
        return self.m.home()

    def __getattr__(self, k):
        return getattr(self.m, k)


def run_task(task):
    oppnp.run_machine_task(machine, task)


# -- homed, N1 left down (the bench case) ---------------------------------------------------------------------------
low_z = safe_low - 20.0
oppnp.run_machine_task(machine, lambda: n1.moveTo(Location(mm, 50, 50, low_z, 0)))
low = homeguard.unsafe_nozzles(machine)
check("N1 lowered below safe Z is reported", [x[0] for x in low] == [n1.getName()] and abs(low[0][1] - low_z) < 0.01, low)
rec = Rec(machine)
asked = []
homeguard.home_pressed(rec, None, confirm=lambda p: asked.append(1) or True, submit=run_task,
                       message=lambda t: asked.append(t))
check("homed: no question asked (heights known)", not asked, asked)
check("homed: homing ran once", len(rec.at_home) == 1, rec.at_home)
check("homed: every nozzle at safe Z when homing started (raised first)",
      rec.at_home and all(z >= safe_low - 1e-6 for _, z in rec.at_home[0]), rec.at_home)
check("homed again after the guarded Home", machine.isHomed())

# -- OpenPnP runs the task on its machine thread, whose Jython state may not have the Lumen library on its path
#    (bench 2026-11-25 15:03: "ImportError: No module named lumen" in target_on_visual_home after raising the nozzles)
from org.python.core import Py, PySystemState
from java.lang import Thread as _JThread, Runnable as _JRunnable


def run_task_fresh_state(task):
    box = {}

    class _R(_JRunnable):
        def run(self):
            Py.setSystemState(PySystemState())          # like a thread whose Python state comes from another engine
            try:
                oppnp.run_machine_task(machine, task)
            except BaseException as e:
                box["e"] = e
    t = _JThread(_R())
    t.start()
    t.join()
    if "e" in box:
        raise box["e"]


oppnp.run_machine_task(machine, lambda: n1.moveTo(Location(mm, 50, 50, low_z, 0)))
rec = Rec(machine)
try:
    homeguard.home_pressed(rec, None, confirm=lambda p: True, submit=run_task_fresh_state, message=lambda t: None)
    err = None
except BaseException as e:
    err = e
check("machine thread without the Lumen path: nozzles raised AND homed (no ImportError)",
      err is None and len(rec.at_home) == 1 and all(z >= safe_low - 1e-6 for _, z in rec.at_home[0]), (err, rec.at_home))

box2 = {}


class _R2(_JRunnable):
    def run(self):
        Py.setSystemState(PySystemState())
        try:
            box2["r"] = oppnp.run_machine_task(machine, lambda: __import__("lumen.nozzlecal").nozzlecal.__name__)
        except BaseException as e:
            box2["e"] = e
_t2 = _JThread(_R2())
_t2.start()
_t2.join()
check("any Lumen machine task (oppnp.run_machine_task) imports lumen on a thread without the path",
      box2.get("r") == "lumen.nozzlecal", box2)

# -- not homed: question first ---------------------------------------------------------------------------------------
machine.setHomed(False)
check("not homed: heights unknown -> nothing reported", homeguard.unsafe_nozzles(machine) == [])
rec = Rec(machine)
submitted = []
homeguard.home_pressed(rec, None, confirm=lambda p: False, submit=lambda t: submitted.append(t), message=None)
check("not homed + 'No' in the confirmation: nothing submitted, no homing", not submitted and not rec.at_home)
homeguard.home_pressed(rec, None, confirm=lambda p: True, submit=run_task, message=lambda t: None)
check("not homed + 'Yes': homes", len(rec.at_home) == 1 and machine.isHomed(), rec.at_home)

# -- a refused safe_home (e.g. target on the visual home) shows the reason, does not home -----------------------------
orig = machinecal.target_on_visual_home
machinecal.target_on_visual_home = lambda m: True
rec = Rec(machine)
msgs = []
homeguard.home_pressed(rec, None, confirm=lambda p: True, submit=run_task, message=lambda t: msgs.append(t))
from javax.swing import SwingUtilities
from java.lang import Runnable


class _Flush(Runnable):
    def run(self):
        pass
SwingUtilities.invokeAndWait(_Flush())
machinecal.target_on_visual_home = orig
check("target seen on the visual home: no homing, the reason is shown",
      not rec.at_home and msgs and "calibration target" in msgs[0], msgs)

# -- install: OpenPnP's Home button, menu item and hotkey ------------------------------------------------------------
pressed = []


class HomeAction(AbstractAction):                 # stands in for MachineControlsPanel.HomeAction
    def __init__(self):
        AbstractAction.__init__(self, "Home")

    def actionPerformed(self, e):
        pressed.append("plain")


orig_action = HomeAction()


class Controls(object):
    homeAction = orig_action


hot = HashMap()
hot.put(KeyStroke.getKeyStroke("ctrl H"), orig_action)
class Other(AbstractAction):
    def actionPerformed(self, e):
        pass


hot.put(KeyStroke.getKeyStroke("ctrl J"), Other())


class Gui(object):
    def getMachineControls(self):
        return Controls()

    def getHotkeyActionMap(self):
        return hot


panel = JPanel()
btn = JButton(orig_action)
other = JButton("Jog")
panel.add(btn)
panel.add(other)
bar = JMenuBar()
menu = JMenu("Machine")
item = JMenuItem(orig_action)
menu.add(item)
bar.add(menu)
panel.add(bar)
guard_calls = []
homeguard.home_pressed = lambda m, p, **k: guard_calls.append(m)
n = homeguard.install(Gui(), machine, windows=[panel])
check("install: button, menu item and hotkey guarded", n == 3, n)
btn.doClick()
item.doClick()
hot.get(KeyStroke.getKeyStroke("ctrl H")).actionPerformed(None)
check("Home button / menu / hotkey run the guard, not the plain G28 action", len(guard_calls) == 3 and not pressed,
      (guard_calls, pressed))
orig_action.setEnabled(False)
SwingUtilities.invokeAndWait(_Flush())
check("guarded Home follows OpenPnP's enabled state (button and hotkey)",
      not btn.isEnabled() and not hot.get(KeyStroke.getKeyStroke("ctrl H")).isEnabled(),
      (btn.isEnabled(), hot.get(KeyStroke.getKeyStroke("ctrl H")).isEnabled(), item.isEnabled()))
orig_action.setEnabled(True)
orig_action.putValue(AbstractAction.SHORT_DESCRIPTION, "homed")
SwingUtilities.invokeAndWait(_Flush())
check("guarded Home keeps OpenPnP's look (text, tooltip changes passed on)",
      btn.getText() == "Home" and item.getText() == "Home" and btn.getToolTipText() == "homed" and btn.isEnabled(),
      (btn.getText(), btn.getToolTipText()))
check("install twice changes nothing", homeguard.install(Gui(), machine, windows=[panel]) == 0)
check("other buttons and hotkeys untouched", list(other.getActionListeners()) == [] and
      not getattr(hot.get(KeyStroke.getKeyStroke("ctrl J")), "lumen_home_guard", False))

ok = sum(results)
_Sys.out.println("%d/%d checks passed" % (ok, len(results)))
_Sys.exit(0 if ok == len(results) else 1)
