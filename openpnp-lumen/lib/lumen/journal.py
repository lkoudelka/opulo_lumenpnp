# -*- coding: utf-8 -*-
"""Placement journal: one JSON line per completed placement (~/.openpnp2/lumen/placement-journal.jsonl)."""
from __future__ import absolute_import, division, print_function

import json
import os
import time


def path(scripting):
    return os.path.join(str(scripting.getScriptsDirectory().getParent()), "lumen", "placement-journal.jsonl")


def _loc(l):
    if l is None:
        return None
    return [round(l.getX(), 4), round(l.getY(), 4), round(l.getZ(), 4), round(l.getRotation(), 3), str(l.getUnits())]


def record(scripting, job_file, part, nozzle, placement, board_location, placement_location):
    rec = {
        "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "job": job_file,
        "board": board_location.getUniqueId() if board_location is not None else None,
        "board_name": board_location.getPlacementsHolder().getName() if board_location is not None else None,
        "placement": placement.getId() if placement is not None else None,
        "part": part.getId() if part is not None else None,
        "nozzle": nozzle.getName() if nozzle is not None else None,
        "tip": nozzle.getNozzleTip().getName() if nozzle is not None and nozzle.getNozzleTip() is not None else None,
        "location": _loc(placement_location),
    }
    p = path(scripting)
    d = os.path.dirname(p)
    if not os.path.isdir(d):
        os.makedirs(d)
    f = open(p, "a")
    f.write(json.dumps(rec) + "\n")
    f.close()


def tail(scripting, job_file=None, n=200):
    p = path(scripting)
    if not os.path.isfile(p):
        return []
    f = open(p)
    lines = f.readlines()[-5000:]
    f.close()
    out = []
    for line in reversed(lines):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if job_file is None or r.get("job") == job_file:
            out.append(r)
            if len(out) >= n:
                break
    return out
