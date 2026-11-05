#!/usr/bin/env python3
"""pnp-profile on a sandbox COPY of the real ~/.openpnp2, judged by the real OpenPnP 2.6:
byte-exact round trip, the lumen profile loads with the intended settings and nothing else
changed, tuning done in each profile survives switching, hooks follow the profile."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "profile", "pnp_profile.py")
SRC = os.path.expanduser(os.environ.get("OPENPNP_CONFIG_SRC", "~/.openpnp2"))
JAVA = os.environ.get("JAVA", "/usr/lib/jvm/java-17-openjdk-amd64/bin/java")
OPENPNP = os.environ.get("OPENPNP_HOME", "/opt/openpnp")
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def openpnp(mode, cfg):
    jar = [f for f in os.listdir(OPENPNP) if f.startswith("openpnp-gui-") and f.endswith(".jar")][0]
    r = subprocess.run([JAVA, "-Djava.awt.headless=true", "--add-opens=java.base/java.lang=ALL-UNNAMED",
                        "--add-opens=java.desktop/java.awt=ALL-UNNAMED", "--add-opens=java.desktop/java.awt.color=ALL-UNNAMED",
                        "-cp", "%s/%s:%s/lib/*" % (OPENPNP, jar, OPENPNP), "org.python.util.jython",
                        os.path.join(HERE, "openpnp_dump.py"), mode, cfg], capture_output=True, text=True, timeout=300)
    for line in r.stdout.splitlines():
        if line.startswith("JSON "):
            return json.loads(line[5:])
    raise RuntimeError("OpenPnP load failed:\n" + r.stdout[-2000:] + r.stderr[-3000:])


def tool(cfg, *args):
    env = dict(os.environ, OPENPNP_CONFIG=cfg)
    return subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, env=env)


def read(cfg, f):
    return open(os.path.join(cfg, f)).read()


def main():
    cfg = tempfile.mkdtemp(prefix="profile-", dir=os.environ.get("SIM_WORKDIR"))
    for f in os.listdir(SRC):
        if f.endswith(".xml"):
            shutil.copy2(os.path.join(SRC, f), cfg)
    os.makedirs(os.path.join(cfg, "scripts", "Events"))
    A = {f: read(cfg, f) for f in ("machine.xml", "vision-settings.xml")}
    base = openpnp("dump", cfg)

    print("P1 round trip without OpenPnP in between")
    r = tool(cfg, "use", "lumen")
    check("use lumen", r.returncode == 0, r.stdout.strip().splitlines()[0] if r.stdout else r.stderr)
    r = tool(cfg, "use", "original")
    check("use original", r.returncode == 0)
    check("byte-identical round trip (both files)", all(read(cfg, f) == A[f] for f in A))

    print("P2 lumen profile as OpenPnP sees it")
    r = tool(cfg, "use", "lumen")
    check("use lumen again", r.returncode == 0, r.stderr.strip())
    lum = openpnp("dump", cfg)
    ok = all(n["class"] == "ContactProbeNozzle" and n["method"] == "VacuumSense" and n["feeder_probing"] == "AfterHoming"
             and n["part_probing"] == "Once" for n in lum["nozzles"].values())
    check("nozzles are ContactProbeNozzle VacuumSense / AfterHoming / Once", ok, {k: (v["class"], v.get("method")) for k, v in lum["nozzles"].items()})
    common = ("head_offsets", "vac", "vac_sense", "rotation_mode", "tips")
    check("all other nozzle settings unchanged", all(lum["nozzles"][k][c] == base["nozzles"][k][c]
                                                      for k in base["nozzles"] for c in common))
    check("bottom vision size check BodySize 25 %", lum["bvs"] == {"method": "BodySize", "tolerance": 25}, lum["bvs"])
    ev = os.path.join(cfg, "scripts", "Events")
    check("lumen hooks linked", sorted(os.listdir(ev)) == ["Feeder.AfterFeed.py", "Vision.PartAlignment.After.py"])

    print("P3 tune in lumen (OpenPnP saves), switch back")
    t = openpnp("tune", cfg)
    check("OpenPnP saved lumen tuning", t["nozzles"]["N1"]["depth"] == 3.3 and t["bvs"]["tolerance"] == 30, t["bvs"])
    r = tool(cfg, "use", "original")
    o = openpnp("dump", cfg)
    check("original: plain ReferenceNozzle again", all(n["class"] == "ReferenceNozzle" for n in o["nozzles"].values()))
    check("original: bottom vision as before", o["bvs"] == base["bvs"], o["bvs"])
    check("common edit made in lumen kept (N1 head offset)", "-23.5" in o["nozzles"]["N1"]["head_offsets"], o["nozzles"]["N1"]["head_offsets"])
    # control: the same edit made directly in the original profile (OpenPnP moves dependent
    # locations itself when a head offset changes, so compare against OpenPnP, not against A)
    ctl = tempfile.mkdtemp(prefix="profile-control-", dir=os.environ.get("SIM_WORKDIR"))
    for f in os.listdir(SRC):
        if f.endswith(".xml"):
            shutil.copy2(os.path.join(SRC, f), ctl)
    openpnp("tune", ctl)
    check("machine.xml == same edit made in the original profile (byte-identical)",
          read(cfg, "machine.xml") == read(ctl, "machine.xml"))
    check("vision-settings.xml identical to the original", read(cfg, "vision-settings.xml") == A["vision-settings.xml"])
    check("hooks removed in original", os.listdir(ev) == [])

    print("P4 back to lumen: tuning restored")
    tool(cfg, "use", "lumen")
    l2 = openpnp("dump", cfg)
    check("lumen tuning restored (depth 3.3, tolerance 30)", l2["nozzles"]["N1"]["depth"] == 3.3 and l2["bvs"]["tolerance"] == 30,
          (l2["nozzles"]["N1"].get("depth"), l2["bvs"]))
    check("common edit still there", "-23.5" in l2["nozzles"]["N1"]["head_offsets"])

    print("P5 safety")
    tool(cfg, "use", "original")
    open(os.path.join(ev, "Feeder.AfterFeed.py"), "w").write("# user script\n")
    r = tool(cfg, "use", "lumen")
    check("refuses to replace a user's own hook", r.returncode != 0 and "not ours" in r.stderr, r.stderr.strip())
    check("user hook untouched", open(os.path.join(ev, "Feeder.AfterFeed.py")).read() == "# user script\n")
    backups = os.listdir(os.path.join(cfg, "lumen", "profile-backups"))
    check("a backup per switch", len(backups) >= 6, len(backups))
    r = tool(cfg, "status")
    check("status reports the active profile", "active (file):   original" in r.stdout or "active (file):   lumen" in r.stdout, r.stdout.splitlines()[1])
    print("\n%d/%d checks passed" % (sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
