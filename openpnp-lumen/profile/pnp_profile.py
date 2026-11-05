#!/usr/bin/env python3
"""pnp-profile: switch the OpenPnP configuration between "original" and "lumen".

    pnp-profile status
    pnp-profile use lumen       ContactProbeNozzle (auto Z), bottom-vision size check, learning hooks
    pnp-profile use original    exactly the original Opulo V4.1 behaviour again
    pnp-profile diff            what the lumen profile changes (as a unified diff, nothing written)

Only the elements listed in lumen-profile.json are touched, as minimal text edits.
- "use original" strips exactly the ContactProbeNozzle-only attributes/elements (and puts
  the bottom-vision values back), so everything else you changed in either profile (camera /
  nozzle calibration, feeders, offsets, ...) is kept in both profiles.
- The stripped lumen settings (your tuning, probed heights) are stored and come back on the
  next "use lumen".
- original -> lumen -> original without other changes gives back the identical file.
OpenPnP must not be running (it rewrites its files on exit).  Every switch first copies the
current files to ~/.openpnp2/lumen/profile-backups/<time>/.
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = Path(os.environ.get("OPENPNP_CONFIG", Path.home() / ".openpnp2"))
SPEC = Path(os.environ.get("LUMEN_PROFILE_SPEC", HERE / "lumen-profile.json"))
HOOKS_SRC = HERE.parent / "events" / "lumen-profile"
STATE = CFG / "lumen" / "profile-state.json"
FILES = ("machine.xml", "vision-settings.xml")

REF = "org.openpnp.machine.reference.ReferenceNozzle"
CPN = "org.openpnp.machine.reference.ContactProbeNozzle"
# Everything ContactProbeNozzle adds to a ReferenceNozzle (OpenPnP 2.6 fields), matched by
# name pattern because OpenPnP's hyphen style is irregular (maxZOffsetMm -> "max-Z-offset-mm")
# and some fields are only written once set (calibration offsets, contact probe actuator).
# ReferenceNozzle itself has no attribute/element matching these patterns.
CPN_ATTR_RE = re.compile(r"^(contact-probe-|sniffle-|feeder-height-probing$|part-height-probing$|"
                         r"discard-probing$|max-z-offset)", re.I)
CPN_ELEMENT_RE = re.compile(r"^(contact-probe-|sniffle-|calibration-offset-z$|unloaded-calibration-offset-z$|"
                            r"probed-)", re.I)

# <nozzle class=...> ... </nozzle> (a nozzle always has children such as head-offsets;
# a self-closing <nozzle .../> is left untouched)
NOZZLE_RE = re.compile(r'(<nozzle class="(%s|%s)"[^>]*?)(?<!/)(>)(.*?)(</nozzle>)' % (
    re.escape(REF), re.escape(CPN)), re.S)


class ProfileError(Exception):
    pass


def attr(tag, name):
    m = re.search(r'\s%s="([^"]*)"' % re.escape(name), tag)
    return m.group(1) if m else None


def set_attr(tag, name, value):
    if attr(tag, name) is None:
        return tag + ' %s="%s"' % (name, value)
    return re.sub(r'(\s%s=")[^"]*(")' % re.escape(name), lambda m: m.group(1) + value + m.group(2), tag, count=1)


def del_attr(tag, name):
    return re.sub(r'\s%s="[^"]*"' % re.escape(name), "", tag, count=1)


def child_re(name):
    # self-closing or with content; include the indentation and the line break before it
    return re.compile(r'\n[ \t]*<%s\b[^>]*?(?:/>|>.*?</%s>)' % (re.escape(name), re.escape(name)), re.S)


# ---- machine.xml: nozzles -----------------------------------------------------------
def nozzles_to_lumen(text, spec, state):
    want = spec["contact_probe_nozzles"]
    stored = state.setdefault("nozzles", {})
    count = 0

    def repl(m):
        nonlocal count
        start, cls, close, body, end = m.groups()
        nid = attr(start, "id")
        if cls == CPN or (want.get("nozzles", "all") != "all" and nid not in want["nozzles"]):
            return m.group(0)
        start = start.replace('class="%s"' % REF, 'class="%s"' % CPN, 1)
        s = stored.get(nid)
        for k, v in (s["attrs"] if s else list(want["attributes"].items())):
            start = set_attr(start, k, v)
        if s and s["elements"]:
            tail = re.search(r"\n[ \t]*$", body)          # indentation before </nozzle>
            cut = tail.start() if tail else len(body)
            body = body[:cut] + "".join(s["elements"]) + body[cut:]
        count += 1
        return start + close + body + end
    return NOZZLE_RE.sub(repl, text), count


def nozzles_to_original(text, state):
    stored = state.setdefault("nozzles", {})
    count = 0

    def repl(m):
        nonlocal count
        start, cls, close, body, end = m.groups()
        if cls != CPN:
            return m.group(0)
        nid = attr(start, "id")
        attrs = []
        for am in list(re.finditer(r'\s([\w-]+)="([^"]*)"', start)):
            if CPN_ATTR_RE.match(am.group(1)):
                attrs.append([am.group(1), am.group(2)])
        for k, _ in attrs:
            start = del_attr(start, k)
        elements = []
        names = []
        for em in re.finditer(r"\n[ \t]*<([\w-]+)\b", body):
            if CPN_ELEMENT_RE.match(em.group(1)) and em.group(1) not in names:
                names.append(em.group(1))
        for name in names:
            for em in child_re(name).finditer(body):
                elements.append(em.group(0))
            body = child_re(name).sub("", body)
        stored[nid] = {"attrs": attrs, "elements": elements}
        start = start.replace('class="%s"' % CPN, 'class="%s"' % REF, 1)
        count += 1
        return start + close + body + end
    return NOZZLE_RE.sub(repl, text), count


# ---- vision-settings.xml: bottom vision ----------------------------------------------
def vision_switch(text, spec, state, to):
    store = state.setdefault("vision", {})
    count = 0
    for vid, values in spec["bottom_vision"]["settings"].items():
        m = re.search(r'<vision-settings class="org.openpnp.model.BottomVisionSettings"[^>]*\sid="%s"[^>]*>' % re.escape(vid), text)
        if not m:
            continue
        tag = m.group(0)
        rec = store.setdefault(vid, {})
        rec[("lumen" if to == "original" else "original")] = {k: attr(tag, k) for k in values}
        target = rec.get(to) or (values if to == "lumen" else None)
        if target is None:
            continue
        new = tag
        for k, v in target.items():
            if v is not None:
                new = set_attr(new[:-1], k, v) + ">" if attr(new, k) is None else set_attr(new, k, v)
        if new != tag:
            text = text[:m.start()] + new + text[m.end():]
            count += 1
    return text, count


# ---- event hooks -----------------------------------------------------------------------
def hooks(spec, on):
    ev = CFG / "scripts" / "Events"
    ev.mkdir(parents=True, exist_ok=True)
    done = []
    for h in spec["event_hooks"]["hooks"]:
        dst, src = ev / (h + ".py"), HOOKS_SRC / (h + ".py")
        if on:
            if dst.exists() and not (dst.is_symlink() and Path(os.readlink(dst)) == src):
                raise ProfileError("%s exists and is not ours - not replacing it" % dst)
            if dst.is_symlink():
                dst.unlink()
            dst.symlink_to(src)
            done.append("linked " + dst.name)
        elif dst.is_symlink() and Path(os.readlink(dst)) == src:
            dst.unlink()
            done.append("removed " + dst.name)
    return done


# ---- state / helpers ---------------------------------------------------------------------
def load_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, STATE)


def detect(text):
    return "lumen" if 'class="%s"' % CPN in text else "original"


def openpnp_running():
    return subprocess.run(["pgrep", "-f", r"^/usr/lib/jvm/.*openpnp"], capture_output=True).returncode == 0


def transform(to, texts, spec, state):
    m, v = texts["machine.xml"], texts["vision-settings.xml"]
    if to == "lumen":
        m, n = nozzles_to_lumen(m, spec, state)
    else:
        m, n = nozzles_to_original(m, state)
    v, nv = vision_switch(v, spec, state, to)
    return {"machine.xml": m, "vision-settings.xml": v}, n, nv


def cmd_status(a):
    st = load_state()
    m = (CFG / "machine.xml").read_text()
    print("config dir:      %s" % CFG)
    print("active (file):   %s" % detect(m))
    print("active (state):  %s" % st.get("active", "original (never switched)"))
    print("stored lumen tuning for nozzles: %s" % (", ".join(st.get("nozzles", {})) or "-"))
    ev = CFG / "scripts" / "Events"
    print("lumen hooks:     %s" % (", ".join(p.name for p in sorted(ev.glob("*.py")) if p.is_symlink()
                                       and str(os.readlink(p)).startswith(str(HOOKS_SRC))) or "-"))


def cmd_diff(a):
    import difflib
    spec = json.loads(SPEC.read_text())
    texts = {f: (CFG / f).read_text() for f in FILES}
    cur = detect(texts["machine.xml"])
    to = "original" if cur == "lumen" else "lumen"
    new, _, _ = transform(to, texts, spec, json.loads(json.dumps(load_state())))
    for f in FILES:
        sys.stdout.writelines(difflib.unified_diff(texts[f].splitlines(True), new[f].splitlines(True),
                                                   "%s (%s)" % (f, cur), "%s (%s)" % (f, to)))


def cmd_use(a):
    to = a.profile
    if openpnp_running() and not a.force:
        raise ProfileError("OpenPnP is running: close it first (it rewrites machine.xml on exit)")
    spec = json.loads(SPEC.read_text())
    state = load_state()
    texts = {f: (CFG / f).read_text() for f in FILES}
    cur = detect(texts["machine.xml"])
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    bdir = CFG / "lumen" / "profile-backups" / ("%s-%s-to-%s" % (stamp, cur, to))
    bdir.mkdir(parents=True)                     # unique per switch (microseconds)
    for f in FILES:
        shutil.copy2(CFG / f, bdir / f)
    new, n, nv = transform(to, texts, spec, state)
    for f in FILES:
        if new[f] != texts[f]:
            tmp = CFG / (f + ".pnp-profile.tmp")
            tmp.write_text(new[f])
            os.replace(tmp, CFG / f)
    hook_msgs = hooks(spec, to == "lumen")
    state["active"] = to
    state.setdefault("history", []).append({"t": stamp, "from": cur, "to": to, "backup": str(bdir)})
    save_state(state)
    print("profile %s -> %s: %d nozzle(s), %d bottom-vision setting(s); %s" % (
        cur, to, n, nv, "; ".join(hook_msgs) or "no hook change"))
    print("backup of the previous files: %s" % bdir)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("diff")
    u = sub.add_parser("use")
    u.add_argument("profile", choices=("original", "lumen"))
    u.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    try:
        {"status": cmd_status, "diff": cmd_diff, "use": cmd_use}[a.cmd](a)
    except ProfileError as e:
        sys.exit("pnp-profile: %s" % e)


if __name__ == "__main__":
    main()
