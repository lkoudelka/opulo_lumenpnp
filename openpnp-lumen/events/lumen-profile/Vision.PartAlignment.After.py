# Lumen profile hook (linked by "pnp-profile use lumen", removed by "use original").
# Appends the bottom-vision offset of every aligned part, with the feeder that supplied it,
# to ~/.openpnp2/lumen/pick-offsets.jsonl (study §3 pick-offset learning, §2 orientation hints).
# Never raises into the job.  Variables from OpenPnP: part, nozzle, offsets (PartAlignmentOffset).
try:
    import json as _json
    import os as _os
    import time as _time
    from java.lang import System as _S
    _feed = _S.getProperty("lumen.feed." + str(nozzle.getId()))
    _feed = _json.loads(_feed) if _feed else {}
    _o = offsets.getLocation()
    _rot = None
    try:
        _rot = nozzle.getLocation().getRotation()
    except:
        pass
    _rec = {"t": _time.strftime("%Y-%m-%dT%H:%M:%S"), "nozzle": str(nozzle.getName()),
            "part": str(part.getId()) if part is not None else None,
            "feeder_id": _feed.get("feeder_id"), "feeder": _feed.get("feeder"), "slot": _feed.get("slot"),
            "feed_age_s": round(_time.time() - _feed["t"], 1) if _feed else None, "pick": _feed.get("pick"),
            "dx": _o.getX(), "dy": _o.getY(), "drot": _o.getRotation(), "units": str(_o.getUnits()),
            "nozzle_rot": _rot, "pre_rotated": bool(offsets.getPreRotated())}
    _d = _os.path.join(str(scripting.getScriptsDirectory().getParent()), "lumen")
    if not _os.path.isdir(_d):
        _os.makedirs(_d)
    _f = open(_os.path.join(_d, "pick-offsets.jsonl"), "a")
    _f.write(_json.dumps(_rec) + "\n")
    _f.close()
except:
    try:
        import sys as _sys
        from org.pmw.tinylog import Logger as _L
        _L.warn("Lumen pick-offset hook: %s" % (_sys.exc_info()[1],))
    except:
        pass
