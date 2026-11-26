# -*- coding: utf-8 -*-
"""Pool OpenPnP's scripting engines only while a job runs (Jython; installed by events/Startup.py).

Without pooling OpenPnP loads a new Python engine for every event script: ~0.6 s per Lumen hook call, ~1.9 s per
part (bench 2026-11-26, "Engine pooling disabled ... loaded in 619 ms").  Pooled engines keep the Python modules
they imported, so changed Lumen code reaches the hooks only after a restart.  Wanted (bench): pooled while the
job runs, fresh code whenever the job is stopped or paused.

OpenPnP reads Machine.isPoolScriptingEngines() on every script run and has Scripting.clearScriptingEnginePool(),
but no pause event.  So a 1 s Swing timer watches the job panel state:
- Running / Pausing / Stopping (hooks may still run): pooling on;
- Paused / Stopped: pooling off and the pool emptied (the next run loads the current code).
Only when 'Pool scripting engines?' is OFF in the configuration: with it on, OpenPnP pools permanently and this
does nothing.  settings.json "engine_pool_auto_on" remembers that pooling was switched on by this module, so a
configuration saved during a job (pool-scripting-engines="true") is put back at the next start.
"""
from __future__ import absolute_import, division, print_function

ON_STATES = ("Running", "Pausing", "Stopping")
MARK = "engine_pool_auto_on"
PROP = "lumen.enginepool.auto"


def want_pool(state):
    return state in ON_STATES


def _log(text):
    try:
        from org.pmw.tinylog import Logger
        Logger.info("Lumen engine pool: %s" % text)
    except Exception:
        print("Lumen engine pool: %s" % text)


class Auto(object):
    """tick() switches pooling with the job state.  state_fn() -> 'Running' / 'Paused' / 'Stopped' / ..."""

    def __init__(self, machine, scripting_engine, settings, state_fn):
        self.machine, self.engine, self.settings, self.state_fn = machine, scripting_engine, settings, state_fn
        self.on = False

    def tick(self):
        state = self.state_fn()
        want = want_pool(state)
        if want == self.on:
            return None
        self.machine.setPoolScriptingEngines(want)
        self.on = want
        self.settings.set(MARK, want)
        if not want:
            n = self.engine.getScriptingEnginePoolObjectCount()
            self.engine.clearScriptingEnginePool()
            text = "job %s: pooling off, %d pooled engine(s) cleared (fresh code for the next run)" % (state, n)
        else:
            text = "job %s: scripting engines pooled while the job runs" % state
        _log(text)
        return text


def start(machine, scripting_engine, settings, state_fn, timer_ms=1000, timer=None):
    """Install the automatic mode.  Returns the Auto object, or None when OpenPnP already pools permanently."""
    from java.lang import System
    if settings.get(MARK) and machine.isPoolScriptingEngines():
        machine.setPoolScriptingEngines(False)         # left on by us (configuration saved during a job)
        settings.set(MARK, False)
        _log("pooling had been left on by the automatic mode (configuration saved during a job): off again")
    if machine.isPoolScriptingEngines():
        _log("'Pool scripting engines?' is on in the configuration: OpenPnP pools permanently, automatic mode not used")
        System.clearProperty(PROP)
        return None
    auto = Auto(machine, scripting_engine, settings, state_fn)
    if timer is None:
        from javax.swing import Timer
        from java.awt.event import ActionListener

        class _Tick(ActionListener):
            def actionPerformed(self, e):
                try:
                    auto.tick()
                except:                                  # bare: Java exceptions too; never stop the timer
                    pass
        timer = Timer(timer_ms, _Tick())
        timer.start()
    auto.timer = timer
    System.setProperty(PROP, "1")
    _log("automatic: pooled while a job runs, fresh engines when stopped / paused")
    return auto


def is_auto():
    from java.lang import System
    return System.getProperty(PROP) == "1"
