# -*- coding: utf-8 -*-
"""OpenPnP bindings for the Lumen scripts (Jython 2.7 inside OpenPnP only).

Nothing here changes OpenPnP or machine.xml: feeder packets go through the
existing "PhotonFeederData" actuator (M485 {Value} -> rs485-reply), exactly as
OpenPnP's own PhotonFeeder does; machine work runs as normal machine tasks.
"""
from __future__ import absolute_import, division, print_function

import json
import os
import time

from java.lang import Exception as JavaException
from java.lang import Runnable, Thread
from java.util.concurrent import Callable
from javax.swing import JOptionPane, SwingUtilities
from org.pmw.tinylog import Logger

PHOTON_ACTUATOR = "PhotonFeederData"


def lumen_dir(scripting):
    d = os.path.join(str(scripting.getScriptsDirectory().getParent()), "lumen")
    for sub in ("", "logs"):
        p = os.path.join(d, sub)
        if not os.path.isdir(p):
            os.makedirs(p)
    return d


class Settings(object):
    """Small JSON settings file in ~/.openpnp2/lumen/settings.json."""

    def __init__(self, scripting):
        self.path = os.path.join(lumen_dir(scripting), "settings.json")
        try:
            self.data = json.load(open(self.path))
        except (IOError, ValueError):
            self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        tmp = self.path + ".tmp"
        f = open(tmp, "w")
        json.dump(self.data, f, indent=2, sort_keys=True)
        f.close()
        os.rename(tmp, self.path)


class FileLog(object):
    """Log to ~/.openpnp2/lumen/logs/<name>-<time>.log and to OpenPnP.log (INFO)."""

    def __init__(self, scripting, name):
        self.tag = name
        self.path = os.path.join(lumen_dir(scripting), "logs",
                                 "%s-%s.log" % (name, time.strftime("%Y%m%d-%H%M%S")))
        self.f = open(self.path, "a")

    def __call__(self, text):
        line = "%s %s" % (time.strftime("%H:%M:%S"), text)
        self.f.write(line + "\n")
        self.f.flush()
        Logger.info("Lumen %s: %s" % (self.tag, text))
        return line


class ActuatorTransport(object):
    """Photon packets through OpenPnP's PhotonFeederData actuator."""

    def __init__(self, machine):
        self.actuator = machine.getActuatorByName(PHOTON_ACTUATOR)
        if self.actuator is None:
            raise RuntimeError("actuator '%s' not found in the machine configuration" % PHOTON_ACTUATOR)

    def transact_hex(self, hexs):
        try:
            v = self.actuator.read(hexs)
        except (Exception, JavaException):
            return None
        return None if v is None else str(v)


def job_state(gui):
    """'Stopped', 'Running', 'Paused', ... of the job panel ('Unknown' if not readable)."""
    try:
        jp = gui.getJobTab()
        f = jp.getClass().getDeclaredField("state")
        f.setAccessible(True)
        return str(f.get(jp))
    except (Exception, JavaException):
        return "Unknown"


UNKNOWN_JOB_STATE = "the job state could not be read"


def machine_ready(machine, gui):
    """None if machine work may start, otherwise the reason why not.  Returns
    UNKNOWN_JOB_STATE if only the job state is unknown (caller asks the user)."""
    if not machine.isEnabled():
        return "the machine is not enabled (connect first)"
    if machine.isBusy():
        return "the machine is busy with another task"
    state = job_state(gui)
    if state == "Unknown":
        return UNKNOWN_JOB_STATE
    if state != "Stopped":
        return "a job is %s - stop it first" % state.lower()
    return None


def confirm_ready(machine, gui, parent, action):
    """machine_ready() with UI: shows the reason, or asks when the job state is unknown.
    Returns True if the action may proceed."""
    why = machine_ready(machine, gui)
    if why is None:
        return True
    if why == UNKNOWN_JOB_STATE:
        return JOptionPane.showConfirmDialog(
            parent, "Could not determine whether a job is running.\nMake sure no job is running. Continue?",
            action, JOptionPane.YES_NO_OPTION) == JOptionPane.YES_OPTION
    JOptionPane.showMessageDialog(parent, "%s: %s" % (action, why))
    return False


class _Call(Callable):
    def __init__(self, fn):
        self.fn = fn

    def call(self):
        return self.fn()


def run_machine_task(machine, fn):
    """Run fn() as a machine task (serialised with all other machine activity); blocks the
    calling thread - call from a background thread, never from the Swing thread.
    Results and exceptions are carried back explicitly, so Python exceptions raised in fn
    arrive unchanged (machine.execute would wrap them in Java exceptions)."""
    box = {}

    def wrapped():
        try:
            box["result"] = fn()
        except (Exception, JavaException) as e:
            box["error"] = e
        return None
    machine.execute(_Call(wrapped))
    if "error" in box:
        raise box["error"]
    return box.get("result")


def in_background(fn):
    class _R(Runnable):
        def run(self):
            fn()
    t = Thread(_R())
    t.setDaemon(True)
    t.start()
    return t


def on_ui(fn):
    class _R(Runnable):
        def run(self):
            fn()
    SwingUtilities.invokeLater(_R())


def photon_feeders(machine):
    """OpenPnP Photon feeders: {slot_address: feeder} (feeders without a slot are skipped)."""
    from org.openpnp.machine.photon import PhotonFeeder
    out = {}
    for f in machine.getFeeders():
        if isinstance(f, PhotonFeeder) and f.getSlotAddress() is not None:
            out[int(f.getSlotAddress())] = f
    return out
