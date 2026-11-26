# Lumen start-up (linked by openpnp-lumen install.sh).  OpenPnP event "Startup" (main window shown).
# 1. Safe homing.  2. Scripting engines pooled only while a job runs (lib/lumen/enginepool.py).
# 3. Empty job at start -> offer to reopen the last job (board positions live in the job file).
# Puts lib/lumen/homeguard.py in front of OpenPnP's Home (button, Machine > Home, hotkey): homed -> nozzles to
# safe Z (and the visual home checked free of the calibration target) before G28; not homed -> the person confirms
# nozzles up / target parked first.  machine.xml is not changed; remove the link to go back to plain Home.
try:
    import os as _os
    import sys as _sys
    from org.openpnp.model import Configuration as _C
    from org.openpnp.gui import MainFrame as _MF
    _lib = _os.path.join(str(_C.get().getConfigurationDirectory()), "lumen", "lib")
    if _lib not in _sys.path:
        _sys.path.insert(0, _lib)
    from lumen import homeguard as _hg
    _hg.install(_MF.get(), _C.get().getMachine())
except:                                   # bare: also Java exceptions/errors (Jython); OpenPnP must start anyway
    try:
        from org.pmw.tinylog import Logger as _L
        _L.warn("Lumen home-guard NOT installed: %s" % (_sys.exc_info()[1],))
    except:
        pass
try:
    from lumen import enginepool as _ep, oppnp as _op
    _ep_auto = _ep.start(_C.get().getMachine(), _C.get().getScripting(), _op.Settings(scripting),
                         lambda: _op.job_state(_MF.get()))
except:
    try:
        from org.pmw.tinylog import Logger as _L
        _L.warn("Lumen engine pool automatic mode NOT installed: %s" % (_sys.exc_info()[1],))
    except:
        pass
try:
    from lumen import lastjob as _lj
    _lj.offer_later(_MF.get())
except:
    try:
        from org.pmw.tinylog import Logger as _L
        _L.warn("Lumen last-job offer NOT run: %s" % (_sys.exc_info()[1],))
    except:
        pass
