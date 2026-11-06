# Lumen: pick vacuum check (linked by openpnp-lumen install.sh).
# Does nothing unless enabled in Scripts > Lumen > Feeder Part Check ("Pick vacuum check").
# An edge pick seals worse -> vacuum closer to free air than the feeder's typical pick -> the next
# feed of that feeder runs the camera re-centring check, or (action "repick") the pick is made to
# fail on purpose so OpenPnP recycles the part and picks again.  Raises into the job ONLY for that.
# Variables from OpenPnP: nozzle, part.
try:
    import os as _os
    import sys as _sys
    from org.openpnp.model import Configuration as _C
    _lib = _os.path.join(str(_C.get().getConfigurationDirectory()), "lumen", "lib")
    if _lib not in _sys.path:
        _sys.path.insert(0, _lib)
    from lumen import pickvac as _pv
    _pv.after_pick(_C.get().getMachine(), nozzle, part)
except:                                   # bare: also Java exceptions/errors (Jython)
    if getattr(_sys.exc_info()[1], "lumen_repick", False):
        raise                             # deliberate: OpenPnP discards the part and picks again
    try:
        from org.pmw.tinylog import Logger as _L
        _L.warn("Lumen pickvac hook: %s" % (_sys.exc_info()[1],))
    except:
        pass
