# Build an inspection test set from saved Placement Inspection runs (Jython, OpenPnP classes; read-only on the
# configuration: a copy is loaded).  Per run directory <out>/<run>/: the raw pictures + meta.json with what
# inspect.inspect_placement() used: package, body size, axis rotation, mm/px at the part top - and the truth.
#   tests/run_inspection_dataset.sh <openpnp config dir> <job file> <out dir> <run dir>... [-- truth.json]
# truth.json: {"<run name>": {"missing": [refs], "shifted": [refs], "uncertain": [refs]}}; every other placement is
# present and OK (the operator accepted it).  missing must FAIL, shifted must not be OK.
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
cfg_dir, job_file, out = sys.argv[1], sys.argv[2], sys.argv[3]
args = sys.argv[4:]
truth = {}
if "--" in args:
    i = args.index("--")
    truth = json.load(open(args[i + 1]))
    args = args[:i]

from java.io import File
from org.openpnp.model import Configuration, Length, LengthUnit
from org.openpnp.util import Utils2D

Configuration.initialize(File(cfg_dir))
Configuration.get().load()
cfg = Configuration.get()
machine = cfg.getMachine()
mm = LengthUnit.Millimeters
from lumen import inspect as ins, jobinfo

job = cfg.loadJob(File(job_file))
cam = machine.getDefaultHead().getDefaultCamera()
by_ref = {}
for bl, pl, placed in jobinfo.job_placements(job):
    part = pl.getPart()
    if part is None:
        continue
    pkg = part.getPackage()
    loc = Utils2D.calculateBoardPlacementLocation(bl, pl.getLocation()).convertToUnits(mm)
    z = bl.getLocation().convertToUnits(mm).getZ() + part.getHeight().convertToUnits(mm).getValue()
    upp = cam.getUnitsPerPixel(Length(z, mm)).convertToUnits(mm).getX()
    length, width, src = ins.body_size(pkg)
    rot = loc.getRotation()
    fp = pkg.getFootprint() if pkg is not None else None
    if fp is not None and fp.getBodyHeight() > fp.getBodyWidth():
        rot += 90.0
    by_ref[str(pl.getId())] = {"part": str(part.getId()), "package": str(pkg.getId()) if pkg else None,
                               "length": length, "width": width, "size_source": src, "axis_rot": rot, "upp": upp,
                               "z": z, "placement_rot": loc.getRotation()}
for run in args:
    name = os.path.basename(run.rstrip("/"))
    t = truth.get(name, {})
    d = os.path.join(out, name)
    if not os.path.isdir(d):
        os.makedirs(d)
    meta = {}
    for f in sorted(os.listdir(run)):
        if not f.endswith("-raw.png"):
            continue
        ref = f[:-len("-raw.png")]
        if ref not in by_ref:
            continue
        shutil.copy2(os.path.join(run, f), os.path.join(d, f))
        m = dict(by_ref[ref])
        m["truth"] = "ok"
        for k in ("missing", "shifted", "uncertain"):
            if ref in t.get(k, []):
                m["truth"] = k
        meta[ref] = m
    fh = open(os.path.join(d, "meta.json"), "w")
    try:
        json.dump({"source": name, "parts": meta}, fh, indent=1, sort_keys=True)
    finally:
        fh.close()
    print("%s: %d placements" % (name, len(meta)))
