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

Options per feeder (lumen.feederopts, settings.json key "feeder_options"): on/off, threshold (counts,
any tip; blank = the tip's threshold below), action and "fallback_feed_next" can differ per feeder;
a feeder without an own value takes the default from key "pickvac":
    {"enabled": false, "threshold": {"N045": 3, "N08": 7, "*": 3}, "window": 10, "min_samples": 3,
     "action": "recenter"}      # "log" | "recenter" | "return" | "discard"

Actions on an edge pick:
- log:      only the log line;
- recenter: the next feed of that feeder runs the camera re-centring check;
- return:   "return to feeder, synchronise and pick again" (recycle, nothing wasted):
            OpenPnP's Feeder.takeBackPart() puts the part back into its pocket (Photon: nozzle back
            to the pick location, place, part-off check, feeder set to SkipNext so the tape does not
            move), re-centring is requested and the pick is made to fail (RepickRequested).  OpenPnP's
            job processor then "discards" an empty nozzle (does nothing), feeds again (the Feeder.
            BeforeFeed hook re-centres = synchronise; the Photon feed is skipped) and picks the SAME
            part again at the corrected location.  If the feeder cannot take the part back, falls
            back to "discard" - and then, unless "fallback_feed_next" is set, the NEXT feed of that
            feeder is refused (Feeder.BeforeFeed raises FeedBlocked): OpenPnP retries the feed (its
            feed retry count), disables the feeder and stops the job with the Lumen message, so the
            operator checks the feeder (the part may lie loose on it) before it feeds again;
- discard:  "discard, synchronise and pick again": the part goes to the discard location (wasted),
            OpenPnP feeds the next part, re-centres and picks again.
"return" and "discard" need the PART's "pick retry count" >= 1 (OpenPnP's retry loop); with 0
OpenPnP would stop the job, so then only "recenter" is done and the log says why.
("repick" from an earlier version means "discard".)
The pure decision is assess(); the OpenPnP side is after_pick() (Nozzle.AfterPick hook).
"""
from __future__ import absolute_import, division, print_function

import json
import time

DEFAULTS = {"enabled": False, "threshold": {"N045": 3.0, "N08": 7.0, "*": 3.0}, "window": 10, "min_samples": 3,
            "action": "recenter", "fallback_feed_next": False}
FEED_MAX_AGE_S = 60.0
ACTIONS = ("log", "recenter", "return", "discard")


class FeedBlocked(Exception):
    """Raised from Feeder.BeforeFeed: the feed of the next part is refused (operator check needed)."""
    lumen_block = True


BLOCK = "lumen.pickvac.block."
BLOCK_MAX_AGE_S = 60.0          # OpenPnP's feed retries follow immediately; an older block is stale


def check_block(feeder):
    """Called first in Feeder.BeforeFeed: raise FeedBlocked while a block is set for this feeder.
    The block lasts for OpenPnP's feed retries of this one feed, then clears itself."""
    hw = str(feeder.getHardwareId()).upper() if hasattr(feeder, "getHardwareId") and feeder.getHardwareId() else str(feeder.getId())
    raw = _prop(BLOCK + hw)
    if not raw:
        return
    info = json.loads(raw)
    from java.lang import System
    if time.time() - float(info.get("t", 0)) > BLOCK_MAX_AGE_S:     # stale (e.g. job resumed later): never block
        System.clearProperty(BLOCK + hw)
        return
    left = int(info.get("left", 1)) - 1
    if left > 0:
        info["left"] = left
        _set(BLOCK + hw, json.dumps(info))
    else:
        System.clearProperty(BLOCK + hw)
    raise FeedBlocked("Lumen pick vacuum check: %s - next feed refused (option 'if the return fails: feed the next "
                      "part' is off). Check the feeder (the part may lie loose on it), then re-enable the feeder."
                      % info.get("why", "the part could not be returned to the feeder"))


class RepickRequested(Exception):
    """Raised from Nozzle.AfterPick to make OpenPnP discard the part and pick again."""
    lumen_repick = True           # a pick belongs to the feeder fed on that nozzle within this time


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


def load_settings(data=None):
    if data is None:
        from lumen import feedwatch
        data = feedwatch.read_all()
    out = dict(DEFAULTS)
    out.update(data.get("pickvac") or {})
    return out


def feeder_settings(hwid, data=None):
    """Defaults + this feeder's own options: enabled, feeder_threshold (None = per tip), action, fallback."""
    from lumen import feederopts
    if data is None:
        from lumen import feedwatch
        data = feedwatch.read_all()
    out = load_settings(data)
    e = feederopts.effective(data, hwid)
    out.update(enabled=e["pickvac"], feeder_threshold=e["threshold"], action=e["action"],
               fallback_feed_next=e["fallback_feed_next"])
    return out


def after_pick(machine, nozzle, part):
    """Nozzle.AfterPick: read the vacuum level with the part held, compare with the feeder's typical."""
    raw = _prop("lumen.lastfeed." + str(nozzle.getId()))
    if not raw:
        return None
    feed = json.loads(raw)
    if time.time() - feed["t"] > FEED_MAX_AGE_S or (part is not None and feed.get("part") and feed["part"] != str(part.getId())):
        return None                                       # manual pick or another part: not ours to judge
    st = feeder_settings(feed["feeder"])
    if not st.get("enabled"):
        return None
    level = float(nozzle.readVacuumLevel())
    tip = nozzle.getNozzleTip().getName() if nozzle.getNozzleTip() is not None else "*"
    thr = float(st["feeder_threshold"]) if st.get("feeder_threshold") else threshold_for(st, tip)
    hkey = "lumen.pickvac.history.%s.%s" % (feed["feeder"], tip)
    history = json.loads(_prop(hkey, "[]"))
    flagged, typical, why = assess(history, level, thr, int(st.get("min_samples", 3)))
    _set(hkey, json.dumps(update_history(history, level, flagged, st.get("window", 10))))
    from lumen import feedwatch
    msg = "%s on %s (%s): pick vacuum %s" % (feed["name"], nozzle.getName(), tip, why)
    out = {"level": level, "typical": typical, "flagged": flagged, "why": why, "feeder": feed["feeder"], "action": None}
    if flagged:
        action = st.get("action", "recenter")
        if action == "repick":
            action = "discard"
        if action in ("return", "discard"):
            retries = part.getPickRetryCount() if part is not None else 0
            if retries < 1:
                action = "recenter"
                msg += " (pick again needs the part's pick retry count >= 1, it is 0: only re-centring)"
        if action == "return":
            from java.lang import Throwable
            feeder = find_feeder(machine, feed)
            try:
                if feeder is None or not feeder.canTakeBackPart():
                    raise RuntimeError("feeder cannot take the part back now (feed option %s)" % (
                        feeder.getFeedOptions() if feeder is not None else "-"))
                take_back(feeder, nozzle)
                msg += " -> RETURNED to the feeder pocket, synchronise (re-centre) and pick the same part again"
            except (Exception, Throwable) as e:
                action = "discard"
                msg += " (return to the feeder failed: %s - discarding instead)" % e
                if not st.get("fallback_feed_next", False):
                    # OpenPnP's feed loop makes exactly 1 + feed retry count attempts (ReferencePnpJobProcessor
                    # $Pick.feed: i < 1 + getFeedRetryCount()); the block covers exactly those
                    tries = 1 + (feeder.getFeedRetryCount() if feeder is not None else 3)
                    _set(BLOCK + feed["feeder"], json.dumps({"left": tries, "t": time.time(), "why": "return of %s to %s failed (%s)" % (
                        part.getId() if part is not None else "?", feed["name"], e)}))
                    msg += "; feeding the next part is OFF -> the job stops for the operator"
        if action in ("recenter", "return", "discard"):
            _set("lumen.feedwatch.force." + feed["feeder"], "1")
        if action == "recenter":
            msg += " -> re-centring check at the next feed"
        if action == "discard":
            msg += " -> DISCARD, synchronise (re-centre) and pick the next part"
        out["action"] = action
        feedwatch._log("PICKVAC " + msg)
        if action in ("return", "discard"):
            raise RepickRequested("Lumen pick vacuum check: %s" % msg)
    return out


def find_feeder(machine, feed):
    for f in machine.getFeeders():
        if str(f.getId()) == feed.get("feeder_id"):
            return f
    return None


def take_back(feeder, nozzle):
    """OpenPnP's own take-back: nozzle to the pick location, place, part-off check (Photon: SkipNext)."""
    feeder.takeBackPart(nozzle)
