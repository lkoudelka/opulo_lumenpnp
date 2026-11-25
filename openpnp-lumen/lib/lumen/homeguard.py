# -*- coding: utf-8 -*-
"""Safe homing for OpenPnP's own Home: the Machine Controls button, Machine > Home and the H hotkey (Jython).

OpenPnP sends G28 at once, also with a nozzle down (bench 2026-11-25: N1 left at Z 3.2, Home pressed ->
Marlin "Homing Failed", kill).  install(gui, machine) puts a guard in front of that action:
- machine homed (positions known): every nozzle to safe Z and the visual home checked free of the calibration
  target first (machinecal.safe_home), then homing;
- not homed (positions unknown: power-up, after a kill / E-stop): the person confirms with pictures that the
  nozzles are up and level and the target is parked, then homing.
OpenPnP's action stays (enabled state, icon, homed indication); only what a press does changes.  Installed at
start-up by events/Startup.py.  machine.xml is not changed.
"""
from __future__ import absolute_import, division, print_function

import os

_PICTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pictures")
_LIB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lib_on_path():
    """The guard runs on threads that did not run a Lumen script (Swing thread, OpenPnP's machine thread).  In
    Jython each thread can have its own sys (path and loaded modules): without this, a later `from lumen import
    ...` there fails with "No module named lumen" (bench 2026-11-25 15:03, after the nozzles were raised)."""
    import sys
    if _LIB not in sys.path:
        sys.path.insert(0, _LIB)


def _log(text):
    try:
        from org.pmw.tinylog import Logger
        Logger.info("Lumen home-guard: %s" % text)
    except Exception:
        print("Lumen home-guard: %s" % text)


def unsafe_nozzles(machine):
    """[(name, z mm)] of the nozzles outside their safe Z zone; [] when the machine is not homed (unknown)."""
    from org.openpnp.model import LengthUnit
    if not machine.isHomed():
        return []
    out = []
    for n in machine.getDefaultHead().getNozzles():
        loc = n.getLocation()
        if not n.isInSafeZZone(loc.getLengthZ()):
            out.append((n.getName(), loc.convertToUnits(LengthUnit.Millimeters).getZ()))
    return out


def confirm_unhomed(parent, title="Home the machine?", who="OpenPnP"):
    """Not homed: the person checks by eye (pictures) that the nozzles are up and level and the calibration target
    is parked.  True = home."""
    from java.awt import BorderLayout, GridLayout
    from java.io import File
    from javax.imageio import ImageIO
    from javax.swing import ImageIcon, JLabel, JOptionPane, JPanel
    pics = JPanel(GridLayout(1, 0, 6, 0))
    for name in ("cal-nozzles-level.png", "cal-home-free.png"):
        p = os.path.join(_PICTURES, name)
        if os.path.isfile(p):
            pics.add(JLabel(ImageIcon(ImageIO.read(File(p)))))
    box = JPanel(BorderLayout(0, 6))
    box.add(JLabel("<html>The machine is not homed, so the nozzle heights are not known. Before %s homes it, "
                   "check by eye:<br>1. both nozzles are <b>up and level</b> (no nozzle lowered); 2. the "
                   "<b>calibration target is on its park spot</b>, not on the visual home.<br>Home now?</html>" % who),
            BorderLayout.NORTH)
    box.add(pics, BorderLayout.CENTER)
    return JOptionPane.showConfirmDialog(parent, box, title, JOptionPane.YES_NO_OPTION) == JOptionPane.YES_OPTION


def home_pressed(machine, parent, confirm=None, submit=None, message=None):
    """What a press on Home does (Swing thread).  confirm / submit / message: for tests (defaults: the dialog,
    OpenPnP's UiUtils.submitUiMachineTask, JOptionPane)."""
    _lib_on_path()
    from lumen import machinecal
    confirm = confirm or confirm_unhomed
    if submit is None:
        from org.openpnp.util import UiUtils
        submit = UiUtils.submitUiMachineTask
    if message is None:
        from javax.swing import JOptionPane

        def message(text):
            JOptionPane.showMessageDialog(parent, text, "Home", JOptionPane.WARNING_MESSAGE)
    homed = machine.isHomed()
    if not homed and not confirm(parent):
        _log("homing cancelled (not homed, nozzles / target not confirmed)")
        return
    low = unsafe_nozzles(machine) if homed else []

    def task():
        _lib_on_path()                                   # OpenPnP's machine thread
        if low:
            _log("nozzle(s) below safe Z before homing, raised first: %s"
                 % ", ".join("%s at Z %.2f" % x for x in low))
        try:
            _log(machinecal.safe_home(machine, confirmed_unhomed=not homed))
        except machinecal.Stop as e:
            _log("homing refused: %s" % e)
            from lumen.oppnp import on_ui
            on_ui(lambda: message("Not homed: %s" % e))
    submit(task)


def _guard(machine, parent_fn):
    from java.beans import PropertyChangeListener
    from javax.swing import AbstractAction

    class Guard(AbstractAction):
        """Takes the place of OpenPnP's HomeAction in its buttons / menu items / hotkeys.  Name, icon, tooltip and
        enabled state are OpenPnP's (read through, changes passed on), only a press does something else."""
        lumen_home_guard = True

        def __init__(self, original):
            AbstractAction.__init__(self)
            self.original = original
            guard = self

            class Relay(PropertyChangeListener):
                def propertyChange(self, e):
                    guard.firePropertyChange(e.getPropertyName(), e.getOldValue(), e.getNewValue())
            self.relay = Relay()
            original.addPropertyChangeListener(self.relay)

        def isEnabled(self):
            return self.original.isEnabled()

        def getValue(self, key):
            return self.original.getValue(key)

        def actionPerformed(self, e):
            home_pressed(machine, parent_fn())
    return Guard


def _walk(c):
    from javax.swing import JMenu
    yield c
    kids = list(c.getMenuComponents()) if isinstance(c, JMenu) else list(c.getComponents()) if hasattr(c, "getComponents") else []
    for k in kids:
        for x in _walk(k):
            yield x


def install(gui, machine, windows=None):
    """Guard OpenPnP's Home in its button(s), menu item(s) and hotkey(s).  Idempotent.  Returns the number of
    places guarded."""
    from java.awt import Window
    from javax.swing import AbstractButton
    original = gui.getMachineControls().homeAction
    Guard = _guard(machine, lambda: gui)
    guard = None
    n = 0
    for w in (windows if windows is not None else Window.getWindows()):
        for c in _walk(w):
            if isinstance(c, AbstractButton) and c.getAction() is original:
                guard = guard or Guard(original)
                c.setAction(guard)                   # (removeActionListener(action) would detach the action)
                n += 1
    hot = gui.getHotkeyActionMap()
    for k in list(hot.keySet()):
        if hot.get(k) is original:
            guard = guard or Guard(original)
            hot.put(k, guard)
            n += 1
    _log("guarding OpenPnP's Home in %d place(s): nozzles to safe Z / confirmation before homing" % n)
    return n
