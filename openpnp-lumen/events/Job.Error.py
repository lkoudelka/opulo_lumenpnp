# Lumen job error explanation (linked by openpnp-lumen install.sh).  OpenPnP event "Job.Error" (globals: job,
# jobProcessor, exception).  Adds the cause in words to OpenPnP's low-level message, e.g. which part has no loaded
# compatible nozzle tip behind "Can't move y ... soft limit" (lib/lumen/joberror.py).  Changes nothing.
try:
    import os as _os
    import sys as _sys
    from org.openpnp.model import Configuration as _C
    _lib = _os.path.join(str(_C.get().getConfigurationDirectory()), "lumen", "lib")
    if _lib not in _sys.path:
        _sys.path.insert(0, _lib)
    from lumen import joberror as _je
    _je.on_error(job, _C.get().getMachine(), exception)
except:                                   # bare: also Java exceptions (Jython); never disturb OpenPnP's error handling
    try:
        from org.pmw.tinylog import Logger as _L
        _L.warn("Lumen job error explanation failed: %s" % (_sys.exc_info()[1],))
    except:
        pass
