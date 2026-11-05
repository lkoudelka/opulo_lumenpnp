# OpenPnP event hook (installed only with: openpnp-lumen/install.sh --journal)
# Appends one line per completed placement to ~/.openpnp2/lumen/placement-journal.jsonl
# for Scripts > Lumen > Last Placements.  Never raises: a journal problem must not
# disturb the job.  Variables from OpenPnP: part, nozzle, placement, boardLocation,
# placementLocation, jobProcessor.
try:
    import os
    import sys
    _LIB = os.path.join(str(scripting.getScriptsDirectory().getParent()), "lumen", "lib")
    if _LIB not in sys.path:
        sys.path.insert(0, _LIB)
    from lumen import journal as _journal
    _job_file = None
    try:
        from org.openpnp.gui import MainFrame as _MF
        _job = _MF.get().getJobTab().getJob()
        if _job is not None and _job.getFile() is not None:
            _job_file = str(_job.getFile().getAbsolutePath())
    except:
        pass
    _journal.record(scripting, _job_file, part, nozzle, placement, boardLocation, placementLocation)
except:  # Python and Java exceptions alike
    try:
        from org.pmw.tinylog import Logger as _L
        _L.warn("Lumen placement journal: %s" % (sys.exc_info()[1],))
    except:
        pass
