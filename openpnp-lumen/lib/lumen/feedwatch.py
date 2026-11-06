# -*- coding: utf-8 -*-
"""Pick location centring while feeding (Feeder.BeforeFeed hook, Jython, OpenPnP).

For the feeders with "While feeding" on (Scripts > Lumen > Feeder Part Check, options per feeder:
lumen.feederopts), every N-th feed of that feeder:
the top camera looks at the pick pocket before the feed;
- a part already in the pick pocket -> OpenPnP's feed option SkipNext (this feed is skipped);
- pick location off the pocket centre (sprocket-hole geometry) by min..max mm -> moved onto the
  centre, after a confirmation dialog if "confirm" is set.
Settings: ~/.openpnp2/lumen/settings.json: defaults in key "feedwatch", own values per feeder in
"feeder_options" (every, confirm, skip_if_part, max_mm can differ per feeder).  Never raises into the job (the event
wrapper catches everything); feed counters live in JVM system properties (pooled script engines).
"""
from __future__ import absolute_import, division, print_function

import json
import math
import os
import time

DEFAULTS = {"feeders": [], "every": 5, "confirm": True, "skip_if_part": True, "min_mm": 0.05, "max_mm": 0.5,
            "save_images": False}


def config_dir():
    from org.openpnp.model import Configuration
    return str(Configuration.get().getConfigurationDirectory())


def read_all():
    """The whole settings.json as a dict ({} if missing / unreadable)."""
    p = os.path.join(config_dir(), "lumen", "settings.json")
    try:
        f = open(p)
        try:
            return json.load(f)
        finally:
            f.close()
    except (IOError, OSError, ValueError):
        return {}


def load_settings():
    out = dict(DEFAULTS)
    out.update(read_all().get("feedwatch") or {})
    return out


def feeder_settings(hwid, data=None):
    """Defaults + this feeder's own options (lumen.feederopts)."""
    from lumen import feederopts
    data = read_all() if data is None else data
    out = dict(DEFAULTS)
    out.update(data.get("feedwatch") or {})
    out.update(feederopts.effective(data, hwid))
    return out


def _log(msg):
    d = os.path.join(config_dir(), "lumen", "logs")
    if not os.path.isdir(d):
        os.makedirs(d)
    f = open(os.path.join(d, "feedwatch-%s.log" % time.strftime("%Y%m%d")), "a")
    f.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
    f.close()
    try:
        from org.pmw.tinylog import Logger
        Logger.info("Lumen feedwatch: " + msg)
    except Exception:
        pass


def _count(hwid):
    from java.lang import System
    k = "lumen.feedwatch.count." + hwid
    n = int(System.getProperty(k, "0")) + 1
    System.setProperty(k, str(n))
    return n


def _ask(text):
    """YES apply / NO skip / CANCEL = stop centring this feeder (modal, on the Swing thread)."""
    from javax.swing import JOptionPane, SwingUtilities
    box = {}
    from java.lang import Runnable

    class Ask(Runnable):
        def run(self):
            box["a"] = JOptionPane.showOptionDialog(None, text, "Lumen: centre pick location", JOptionPane.DEFAULT_OPTION,
                                                    JOptionPane.QUESTION_MESSAGE, None,
                                                    ["Apply", "Skip", "Stop for this feeder"], "Apply")
    SwingUtilities.invokeAndWait(Ask())
    return {0: "apply", 1: "skip", 2: "stop"}.get(box.get("a"), "skip")


def _disable(hwid):
    """'Stop for this feeder': its own 'while feeding' option off."""
    from lumen import feederopts
    p = os.path.join(config_dir(), "lumen", "settings.json")
    d = read_all()
    feederopts.set_own(d, hwid, "watch", False)
    tmp = p + ".tmp"
    f = open(tmp, "w")
    json.dump(d, f, indent=2, sort_keys=True)
    f.close()
    os.rename(tmp, p)


def before_feed(machine, feeder, nozzle=None):
    hwid = str(feeder.getHardwareId()).upper() if hasattr(feeder, "getHardwareId") and feeder.getHardwareId() else None
    if hwid is None:
        return None
    from lumen import pickvac
    pickvac.check_block(feeder)                         # raises FeedBlocked if the next feed is refused
    if nozzle is not None:
        try:
            pickvac.remember_feed(nozzle, feeder)       # which feeder supplies this nozzle's pick (no motion)
        except Exception:
            pass
    from java.lang import System
    forced = System.getProperty("lumen.feedwatch.force." + hwid) == "1"   # set by the pick vacuum check
    st = feeder_settings(hwid)
    if not forced and not st.get("watch"):
        return None
    n = _count(hwid)
    every = max(1, int(st.get("every", 5)))
    if not forced and (n - 1) % every:
        return None
    if forced:
        System.clearProperty("lumen.feedwatch.force." + hwid)
        _log("%s feed %d: re-centring check requested by the pick vacuum check" % (feeder.getName(), n))
    from lumen import feedercheck
    save = os.path.join(config_dir(), "lumen", "feeder-check") if st.get("save_images") else None
    res = feedercheck.check_feeder(machine, feeder, save)
    name = feeder.getName()
    if res.get("error"):
        _log("%s feed %d: not checked: %s" % (name, n, res["error"]))
        return res
    if st.get("skip_if_part") and res.get("part_at_pick"):
        from org.openpnp.machine.reference import ReferenceFeeder
        feeder.setFeedOptions(ReferenceFeeder.FeedOptions.SkipNext)
        _log("%s feed %d: part already in the pick pocket -> this feed skipped (SkipNext)" % (name, n))
    d = math.hypot(res["pocket_dx"], res["pocket_dy"])
    if d < st["min_mm"]:
        _log("%s feed %d: centred (%.3f mm)" % (name, n, d))
        return res
    if d > st["max_mm"]:
        _log("%s feed %d: pick %.2f mm off the pocket centre - more than %.2f mm, NOT changed (check the feeder)"
             % (name, n, d, st["max_mm"]))
        return res
    answer = "apply"
    if st.get("confirm"):
        answer = _ask("%s: the pick location is %+.2f / %+.2f mm off the pocket centre\n(%s).\n\nMove it onto the centre?"
                      % (name, res["pocket_dx"], res["pocket_dy"], res.get("method", "")))
    if answer == "apply":
        before, after = feedercheck.apply_pocket_offset(feeder, res["pocket_dx"], res["pocket_dy"], st["max_mm"])
        _log("%s feed %d: centred %+.3f/%+.3f mm: pick %.3f/%.3f -> %.3f/%.3f" % (
            name, n, res["pocket_dx"], res["pocket_dy"], before.getX(), before.getY(), after.getX(), after.getY()))
    elif answer == "stop":
        _disable(hwid)
        _log("%s: centring while feeding switched off by the operator" % name)
    else:
        _log("%s feed %d: correction %+.3f/%+.3f skipped by the operator" % (name, n, res["pocket_dx"], res["pocket_dy"]))
    return res
