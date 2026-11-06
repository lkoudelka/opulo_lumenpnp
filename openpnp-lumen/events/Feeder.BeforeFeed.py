# Lumen: pick location centring while feeding (linked by openpnp-lumen install.sh).
# Does nothing unless feeders are enabled in Scripts > Lumen > Feeder Part Check ("While feeding").
# Never raises into the job.  Variables from OpenPnP: feeder, nozzle, part, machine.
try:
    import os as _os
    import sys as _sys
    from org.openpnp.model import Configuration as _C
    _lib = _os.path.join(str(_C.get().getConfigurationDirectory()), "lumen", "lib")
    if _lib not in _sys.path:
        _sys.path.insert(0, _lib)
    from lumen import feedwatch as _fw
    _fw.before_feed(_C.get().getMachine(), feeder)
except:                                   # bare: also Java exceptions/errors (Jython)
    try:
        from org.pmw.tinylog import Logger as _L
        _L.warn("Lumen feedwatch hook: %s" % (_sys.exc_info()[1],))
    except:
        pass
