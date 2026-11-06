# -*- coding: utf-8 -*-
"""Feeder options per feeder (pure Python: CPython tests and Jython in OpenPnP).

Every Photon feeder can have its own value for each option below; an option without an own value
takes the default (Feeder Part Check, "Defaults" = settings.json keys "feedwatch" and "pickvac").
Own values: settings.json key "feeder_options" = {HARDWARE_ID: {option: value, ...}}.
The options follow the physical feeder (hardware id), not the part or the slot.

Older settings had one "feedwatch.feeders" list of the feeders checked while feeding: a feeder in it
counts as "watch" = on until it gets an own value.
"""
from __future__ import absolute_import, division, print_function

# option key -> (settings section, key in that section or None, default)
OPTIONS = [
    ("watch", None, None, False),                        # check while feeding
    ("every", "feedwatch", "every", 5),
    ("confirm", "feedwatch", "confirm", True),
    ("skip_if_part", "feedwatch", "skip_if_part", True),
    ("max_mm", "feedwatch", "max_mm", 0.5),
    ("pickvac", "pickvac", "enabled", False),            # pick vacuum check
    ("threshold", None, None, None),                     # counts; None = the tip's default threshold
    ("action", "pickvac", "action", "recenter"),
    ("fallback_feed_next", "pickvac", "fallback_feed_next", False),
]
KEYS = [o[0] for o in OPTIONS]
ACTIONS = ("log", "recenter", "return", "discard")
SECTION = "feeder_options"


def _hw(hwid):
    return str(hwid).upper()


def defaults(data):
    """Option defaults from the settings dict (sections feedwatch / pickvac, else built-in)."""
    out = {}
    for key, section, skey, dflt in OPTIONS:
        v = dflt
        if section is not None:
            v = (data.get(section) or {}).get(skey, dflt)
        out[key] = v
    if out["action"] == "repick":
        out["action"] = "discard"
    return out


def own(data, hwid):
    """The feeder's own values only (a copy)."""
    return dict((data.get(SECTION) or {}).get(_hw(hwid)) or {})


def effective(data, hwid):
    """All options of one feeder: own value, else default."""
    out = defaults(data)
    legacy = [_hw(x) for x in (data.get("feedwatch") or {}).get("feeders", [])]
    if _hw(hwid) in legacy:
        out["watch"] = True
    for k, v in own(data, hwid).items():
        if k in out:
            out[k] = v
    if out["action"] == "repick":
        out["action"] = "discard"
    return out


def validate(key, value):
    """Normalised value or ValueError (with a message for the operator)."""
    if key not in KEYS:
        raise ValueError("unknown option %s" % key)
    if key in ("watch", "confirm", "skip_if_part", "pickvac", "fallback_feed_next"):
        return bool(value)
    if key == "every":
        v = int(float(str(value)))                       # str(): also a java.lang.Integer from a table cell
        if v < 1:
            raise ValueError("'every' must be 1 or more")
        return v
    if key == "max_mm":
        v = float(str(value))
        if not 0.05 <= v <= 2.0:
            raise ValueError("max correction must be 0.05 ... 2.0 mm")
        return v
    if key == "threshold":
        if value is None or str(value).strip() in ("", "-", "tip default"):
            return None
        v = float(str(value))
        if v <= 0:
            raise ValueError("the threshold must be above 0 counts")
        return v
    if key == "action":
        v = "discard" if value == "repick" else str(value)
        if v not in ACTIONS:
            raise ValueError("action must be one of %s" % (ACTIONS,))
        return v


def set_own(data, hwid, key, value):
    """Give the feeder its own value (validated).  Returns the stored value."""
    v = validate(key, value)
    fo = data.setdefault(SECTION, {})
    d = fo.setdefault(_hw(hwid), {})
    if key == "threshold" and v is None:
        d.pop("threshold", None)                         # threshold: blank = tip default, never "own None"
    else:
        d[key] = v
    if key == "watch":                                   # the legacy list no longer decides for this feeder
        fw = data.get("feedwatch") or {}
        if fw.get("feeders"):
            fw["feeders"] = [x for x in fw["feeders"] if _hw(x) != _hw(hwid)]
    if not d:
        fo.pop(_hw(hwid), None)
    return v


def clear_own(data, hwid, keep=("watch",)):
    """Back to the defaults (the 'check while feeding' tick is kept unless keep=())."""
    fo = data.get(SECTION) or {}
    d = fo.get(_hw(hwid)) or {}
    for k in list(d):
        if k not in keep:
            del d[k]
    if not d:
        fo.pop(_hw(hwid), None)


def summary(data, hwid):
    """Short text for the log / table: which options are the feeder's own."""
    o = own(data, hwid)
    o.pop("watch", None)
    return "defaults" if not o else "own: " + ", ".join(sorted(o))
