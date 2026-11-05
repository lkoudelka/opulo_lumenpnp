# Lumen profile hook (linked by "pnp-profile use lumen", removed by "use original").
# Remembers which feeder supplied each nozzle, for Vision.PartAlignment.After (study §3).
# Shared through JVM system properties because OpenPnP runs event scripts in pooled engines.
# Never raises into the job.  Variables from OpenPnP: feeder, nozzle, part.
try:
    import json as _json
    import time as _time
    from java.lang import System as _S
    _pl = None
    try:
        _l = feeder.getPickLocation()
        _pl = [_l.getX(), _l.getY(), _l.getZ(), _l.getRotation()]
    except:
        pass
    _slot = None
    try:
        _slot = int(feeder.getSlotAddress())
    except:
        pass
    _S.setProperty("lumen.feed." + str(nozzle.getId()), _json.dumps({
        "t": _time.time(), "feeder_id": str(feeder.getId()), "feeder": str(feeder.getName()), "slot": _slot,
        "part": str(part.getId()) if part is not None else None, "pick": _pl}))
except:
    pass
