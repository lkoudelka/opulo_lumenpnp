# -*- coding: utf-8 -*-
"""Pick vacuum check: an off-centre (edge) pick seals the nozzle worse, so the vacuum level read right
after the pick is closer to free air than for a good pick.  That is the sign the pick location needs
re-centring.

Per feeder the typical good-pick level is the median of its recent good picks (so big parts that
seal better and small parts are each compared with themselves).  A pick whose level is more than
`threshold` counts above (= towards free air) that median is flagged: logged, and the feeder's next
feed runs the camera re-centring check (lumen.feedwatch), with confirmation if that option is set.

Default thresholds (counts) are ~30 % of the free-air / covered span measured on the bench
2026-11-06: N045 free air 233-234, covered 223-224 -> 3;  N08 free 247, covered 224 -> 7.

Settings ~/.openpnp2/lumen/settings.json key "pickvac":
    {"enabled": false, "threshold": {"N045": 3, "N08": 7, "*": 3}, "window": 10, "min_samples": 3,
     "action": "recenter"}      # or "log"
The pure decision is assess(); the OpenPnP side is after_pick() (Nozzle.AfterPick hook).
"""
from __future__ import absolute_import, division, print_function

import json
import time

DEFAULTS = {"enabled": False, "threshold": {"N045": 3.0, "N08": 7.0, "*": 3.0}, "window": 10, "min_samples": 3,
            "action": "recenter"}
FEED_MAX_AGE_S = 60.0           # a pick belongs to the feeder fed on that nozzle within this time


def median(v):
    s = sorted(v)
    n = len(s)
    return None if not n else (s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0)


def threshold_for(settings, tip_name):
    t = settings.get("threshold", DEFAULTS["threshold"])
    if not isinstance(t, dict):
        return float(t)
    return float(t.get(tip_name, t.get("*", DEFAULTS["threshold"]["*"])))


def assess(history, level, threshold, min_samples=3):
    """history: recent GOOD pick levels of this feeder.  Returns (flagged, typical or None, why).
    Higher level = weaker vacuum (closer to free air)."""
    typical = median(history)
    if typical is None or len(history) < min_samples:
        return False, typical, "learning (%d of %d good picks)" % (len(history), min_samples)
    d = level - typical
    if d > threshold:
        return True, typical, "level %.1f is %.1f above the typical %.1f (threshold %.1f): edge pick?" % (level, d, typical, threshold)
    return False, typical, "ok (%.1f, typical %.1f)" % (level, typical)


def update_history(history, level, flagged, window):
    """Only good picks feed the typical level."""
    if not flagged:
        history = (list(history) + [level])[-int(window):]
    return history


# ---------------------------------------------------------------------------------------
# OpenPnP side (Jython)
# ---------------------------------------------------------------------------------------
def _prop(key, default=None):
    from java.lang import System
    return System.getProperty(key, default)


def _set(key, value):
    from java.lang import System
    System.setProperty(key, value)


def remember_feed(nozzle, feeder):
    """Called by the Feeder.BeforeFeed hook: which feeder supplies this nozzle's next pick."""
    hw = str(feeder.getHardwareId()).upper() if hasattr(feeder, "getHardwareId") and feeder.getHardwareId() else str(feeder.getId())
    part = feeder.getPart()
    _set("lumen.lastfeed." + str(nozzle.getId()), json.dumps({"feeder": hw, "feeder_id": str(feeder.getId()),
                                                               "name": feeder.getName(), "part": str(part.getId()) if part else None,
                                                               "t": time.time()}))


def load_settings():
    from lumen import feedwatch
    import os
    p = os.path.join(feedwatch.config_dir(), "lumen", "settings.json")
    try:
        f = open(p)
        try:
            d = json.load(f)
        finally:
            f.close()
    except (IOError, OSError, ValueError):
        d = {}
    out = dict(DEFAULTS)
    out.update(d.get("pickvac") or {})
    return out


def after_pick(machine, nozzle, part):
    """Nozzle.AfterPick: read the vacuum level with the part held, compare with the feeder's typical."""
    st = load_settings()
    if not st.get("enabled"):
        return None
    raw = _prop("lumen.lastfeed." + str(nozzle.getId()))
    if not raw:
        return None
    feed = json.loads(raw)
    if time.time() - feed["t"] > FEED_MAX_AGE_S or (part is not None and feed.get("part") and feed["part"] != str(part.getId())):
        return None                                       # manual pick or another part: not ours to judge
    level = float(nozzle.readVacuumLevel())
    tip = nozzle.getNozzleTip().getName() if nozzle.getNozzleTip() is not None else "*"
    thr = threshold_for(st, tip)
    hkey = "lumen.pickvac.history.%s.%s" % (feed["feeder"], tip)
    history = json.loads(_prop(hkey, "[]"))
    flagged, typical, why = assess(history, level, thr, int(st.get("min_samples", 3)))
    _set(hkey, json.dumps(update_history(history, level, flagged, st.get("window", 10))))
    from lumen import feedwatch
    msg = "%s on %s (%s): pick vacuum %s" % (feed["name"], nozzle.getName(), tip, why)
    if flagged:
        if st.get("action", "recenter") == "recenter":
            _set("lumen.feedwatch.force." + feed["feeder"], "1")
            msg += " -> re-centring check at the next feed"
        feedwatch._log("PICKVAC " + msg)
    return {"level": level, "typical": typical, "flagged": flagged, "why": why, "feeder": feed["feeder"]}
