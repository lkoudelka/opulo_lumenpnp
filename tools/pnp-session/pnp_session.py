#!/usr/bin/env python3
"""pnp-session: record a LumenPnP usage/debug session so it can be analysed afterwards.

    pnp-session start "short title"   begin: config snapshot, OpenPnP log level TRACE, notes template
    pnp-session mark "what I did"     timestamped note (from inside OpenPnP: Scripts > Session > Mark)
    pnp-session stop                  collect logs, config diff, summary.md; restore the log level
    pnp-session status | list
    pnp-session install-openpnp-script   adds Scripts > Session > Mark to OpenPnP (menu only, no events)

A session folder (~/claude/opulo/_sessions/<time>-<title>/) contains:
    notes.md         your description: what you did, expected, observed, what to improve
    marks.log        timestamped marks (CLI + OpenPnP "USER-MARK" lines)
    openpnp/         OpenPnP.log files written during the session (TRACE: every G-code + reply)
    tools/           busflash / paste-utility / leash logs written during the session
    config.diff      changes of ~/.openpnp2 (machine.xml, parts, vision, ...) during the session
    summary.md       timeline (marks + key events), errors/warnings, G-code and feeder-bus statistics
    session.json     metadata (times, versions, git revisions, config snapshot ids)

Nothing in ~/.openpnp2 is modified except the OpenPnP log-level preference (only while OpenPnP
is not running, restored at stop) and, on request, the Session/Mark menu script.  The config
history is a separate git repository (_sessions/.openpnp2-history.git).
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

HOME = Path.home()
BASE = Path(os.environ.get("PNP_SESSION_DIR", HOME / "claude/opulo/_sessions"))
OPENPNP = Path(os.environ.get("OPENPNP_CONFIG", HOME / ".openpnp2"))
TOOL_LOGS = Path(os.environ.get("PNP_TOOL_LOGS", HOME / "claude/opulo/_logs"))
PREFS = Path(os.environ.get("PNP_JAVA_PREFS", HOME / ".java/.userPrefs/org/openpnp/gui/prefs.xml"))
LOGLEVEL_KEY = "LogPanel.logLevel"
HIST = BASE / ".openpnp2-history.git"
CURRENT = BASE / "current"
REPOS = Path(os.environ.get("PNP_REPOS", HOME / "claude/opulo"))
CONFIG_FILES = ["machine.xml", "parts.xml", "packages.xml", "boards.xml", "panels.xml",
                "vision-settings.xml", "script-state.xml", "scripts"]
LOG_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}) (\S+) (TRACE|DEBUG|INFO|WARNING|ERROR): (.*)$")
SCRIPT_SRC = Path(__file__).resolve().parent / "openpnp-scripts"


def now():
    return dt.datetime.now()


def ts(t):
    return t.strftime("%Y-%m-%d %H:%M:%S")


def openpnp_running():
    r = subprocess.run(["pgrep", "-f", r"^/usr/lib/jvm/.*openpnp"], capture_output=True)
    return r.returncode == 0


# ---- OpenPnP log-level preference ------------------------------------------
def get_loglevel():
    if not PREFS.exists():
        return None
    for e in ET.parse(PREFS).getroot().iter("entry"):
        if e.get("key") == LOGLEVEL_KEY:
            return e.get("value")
    return None


def set_loglevel(value):
    """value None = remove the key (OpenPnP default INFO)."""
    if PREFS.exists():
        tree = ET.parse(PREFS)
        root = tree.getroot()
    else:
        PREFS.parent.mkdir(parents=True, exist_ok=True)
        root = ET.Element("map", MAP_XML_VERSION="1.0")
        tree = ET.ElementTree(root)
    found = None
    for e in root.iter("entry"):
        if e.get("key") == LOGLEVEL_KEY:
            found = e
    if value is None:
        if found is not None:
            root.remove(found)
    elif found is not None:
        found.set("value", value)
    else:
        ET.SubElement(root, "entry", key=LOGLEVEL_KEY, value=value)
    tmp = PREFS.with_suffix(".xml.tmp")
    with open(tmp, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
                b'<!DOCTYPE map SYSTEM "http://java.sun.com/dtd/preferences.dtd">\n')
        tree.write(f, encoding="UTF-8")
    os.replace(tmp, PREFS)


# ---- config history (separate git dir, work tree = ~/.openpnp2) --------------
def git_hist(*args, check=True):
    cmd = ["git", f"--git-dir={HIST}", f"--work-tree={OPENPNP}", *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def snapshot(message):
    if not HIST.exists():
        subprocess.run(["git", "init", "-q", "--bare", str(HIST)], check=True)
        git_hist("config", "core.bare", "false")
        git_hist("config", "user.name", "pnp-session")
        git_hist("config", "user.email", "pnp-session@localhost")
    paths = [p for p in CONFIG_FILES if (OPENPNP / p).exists()]
    git_hist("add", "-A", "--", *paths)
    git_hist("commit", "-q", "--allow-empty", "-m", message)
    return git_hist("rev-parse", "HEAD").stdout.strip()


# ---- environment facts ---------------------------------------------------------
def repo_revisions():
    revs = {}
    if not REPOS.exists():
        return revs
    for d in sorted(REPOS.iterdir()):
        if (d / ".git").exists():
            r = subprocess.run(["git", "-C", str(d), "describe", "--always", "--dirty", "--all"],
                               capture_output=True, text=True)
            revs[d.name] = r.stdout.strip()
    return revs


def usb_devices():
    r = subprocess.run(["lsusb"], capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if re.search(r"0483:|LumenPnP|camera|Camera", l)]


# ---- session handling ------------------------------------------------------------
def current():
    if CURRENT.is_symlink() or CURRENT.exists():
        return CURRENT.resolve()
    return None


def load(sdir):
    return json.loads((sdir / "session.json").read_text())


def save(sdir, meta):
    (sdir / "session.json").write_text(json.dumps(meta, indent=2, default=str))


def cmd_start(a):
    if current():
        sys.exit(f"a session is already running: {current()}  (pnp-session stop first)")
    t = now()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", a.title).strip("-")[:40] or "session"
    sdir = BASE / f"{t.strftime('%Y%m%d-%H%M%S')}-{slug}"
    sdir.mkdir(parents=True)
    meta = {"title": a.title, "start": ts(t), "stop": None, "openpnp_running_at_start": openpnp_running(),
            "loglevel_before": get_loglevel(), "loglevel_changed": False,
            "config_start": snapshot(f"session start: {a.title} ({ts(t)})"),
            "repos": repo_revisions(), "usb": usb_devices()}
    if not a.no_trace:
        if meta["openpnp_running_at_start"]:
            print("NOTE: OpenPnP is running: set the log level yourself (Log tab -> Global level: TRACE),\n"
                  "      otherwise only INFO lines (no G-code) are recorded.")
        elif meta["loglevel_before"] != "TRACE":
            set_loglevel("TRACE")
            meta["loglevel_changed"] = True
    save(sdir, meta)
    (sdir / "notes.md").write_text(f"""# {a.title}

*Session {ts(t)}. Describe it in your own words; exact times are not needed, the marks and logs carry them.*

## Goal
-

## What I did (in order) -> what I expected -> what happened
1.

## Not working / not user friendly / could be improved
-

## Ideas
-
""")
    (sdir / "marks.log").write_text(f"{ts(t)} START {a.title}\n")
    if CURRENT.is_symlink():
        CURRENT.unlink()
    CURRENT.symlink_to(sdir)
    print(f"session started: {sdir}")
    print("  marks:  pnp-session mark \"...\"   (or OpenPnP: Scripts > Session > Mark)")
    print("  notes:  " + str(sdir / "notes.md"))
    print("  end:    pnp-session stop")


def cmd_mark(a):
    sdir = current()
    if not sdir:
        sys.exit("no session running (pnp-session start \"title\")")
    with open(sdir / "marks.log", "a") as f:
        f.write(f"{ts(now())} MARK {a.text}\n")
    print("marked")


def parse_openpnp_logs(files, t0, t1):
    """Yield (time, class, level, message, extra_lines) for entries inside [t0, t1]."""
    for path in files:
        entry = None
        with open(path, errors="replace") as f:
            for line in f:
                m = LOG_RE.match(line.rstrip("\n"))
                if m:
                    if entry:
                        yield entry
                    t = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f")
                    entry = [t, m.group(2), m.group(3), m.group(4), []] if t0 <= t <= t1 else None
                elif entry is not None:
                    entry[4].append(line.rstrip("\n"))
        if entry:
            yield entry


def summarize(sdir, meta, logs, t0, t1):
    levels, warn, err = Counter(), Counter(), Counter()
    timeline, gsent, grecv = [], Counter(), 0
    m485 = timeouts = marlin_err = 0
    exceptions = []
    for t, cls, lvl, msg, extra in parse_openpnp_logs(logs, t0, t1):
        levels[lvl] += 1
        if cls == "GcodeDriver" and " >> " in msg:
            cmd = msg.split(" >> ", 1)[1].rsplit(",", 1)[0].strip()
            word = cmd.split()[0] if cmd else "?"
            gsent[word] += 1
            if word == "M485":
                m485 += 1
            continue
        if cls == "GcodeDriver" and " << " in msg:
            grecv += 1
            if "rs485-reply: TIMEOUT" in msg or "rs485-timeout" in msg:
                timeouts += 1
            if re.search(r"<< (echo:)?Error", msg, re.I):
                marlin_err += 1
                timeline.append((t, "MARLIN", msg.split(" << ", 1)[1]))
            continue
        if msg.startswith("USER-MARK:"):
            timeline.append((t, "MARK", msg[len("USER-MARK:"):].strip()))
        elif lvl == "ERROR":
            err[f"{cls}: {msg[:160]}"] += 1
            timeline.append((t, "ERROR", f"{cls}: {msg[:200]}"))
        elif lvl == "WARNING":
            warn[f"{cls}: {msg[:160]}"] += 1
        elif lvl == "INFO" and re.search(r"(?i)job|home|homed|connect|disconnect|setEnabled|nozzle tip|calibrat|feeder", msg):
            timeline.append((t, "EVENT", f"{cls}: {msg[:200]}"))
        if any("Exception" in x or x.lstrip().startswith("at ") for x in extra[:3]) or "Exception" in msg:
            exceptions.append((t, cls, msg[:200], [x for x in extra[:8]]))
    for line in (sdir / "marks.log").read_text().splitlines():
        try:
            t = dt.datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        kind, _, what = line[20:].partition(" ")
        timeline.append((t, kind, what))
    timeline.sort(key=lambda x: x[0])

    out = [f"# Session summary: {meta['title']}", "",
           f"- **Time:** {meta['start']} → {meta['stop']}",
           f"- **OpenPnP log files:** {len(logs)}; levels: " + ", ".join(f"{k} {v}" for k, v in levels.most_common()),
           f"- **Log level at start:** {meta.get('loglevel_before') or 'INFO (default)'}"
           + (" (switched to TRACE for this session)" if meta.get("loglevel_changed") else ""),
           f"- **G-code sent:** {sum(gsent.values())} ({', '.join(f'{k} {v}' for k, v in gsent.most_common(8))}); replies {grecv}",
           f"- **Feeder bus:** {m485} M485 packets, {timeouts} TIMEOUT replies; Marlin errors: {marlin_err}",
           f"- **Config changes:** {'see config.diff' if (sdir / 'config.diff').stat().st_size else 'none'}",
           "", "## Timeline (marks, key events, errors)", "", "| Time | Kind | What |", "|---|---|---|"]
    for t, kind, what in timeline[:400]:
        out.append(f"| {t.strftime('%H:%M:%S')} | {kind} | {what.replace('|', '/')} |")
    if err:
        out += ["", "## Errors (grouped)", ""] + [f"- {n}× {m}" for m, n in err.most_common(30)]
    if warn:
        out += ["", "## Warnings (grouped)", ""] + [f"- {n}× {m}" for m, n in warn.most_common(30)]
    if exceptions:
        out += ["", "## Exceptions", ""]
        for t, cls, msg, extra in exceptions[:20]:
            out += [f"- {t.strftime('%H:%M:%S')} {cls}: {msg}", "  ```", *("  " + x for x in extra), "  ```"]
    (sdir / "summary.md").write_text("\n".join(out) + "\n")


def cmd_stop(a):
    sdir = current()
    if not sdir:
        sys.exit("no session running")
    meta = load(sdir)
    t0 = dt.datetime.strptime(meta["start"], "%Y-%m-%d %H:%M:%S")
    t1 = now()
    meta["stop"] = ts(t1)
    with open(sdir / "marks.log", "a") as f:
        f.write(f"{ts(t1)} STOP\n")
    # logs written during the session (OpenPnP rotates OpenPnP.log -> OpenPnP.N.log on every start)
    logs = []
    (sdir / "openpnp").mkdir(exist_ok=True)
    for p in sorted((OPENPNP / "log").glob("OpenPnP*.log")):
        if dt.datetime.fromtimestamp(p.stat().st_mtime) >= t0:
            dst = sdir / "openpnp" / p.name
            shutil.copy2(p, dst)
            logs.append(dst)
    logs.sort(key=lambda p: p.stat().st_mtime)
    (sdir / "tools").mkdir(exist_ok=True)
    if TOOL_LOGS.exists():
        for p in TOOL_LOGS.iterdir():
            if p.is_file() and dt.datetime.fromtimestamp(p.stat().st_mtime) >= t0:
                shutil.copy2(p, sdir / "tools" / p.name)
    meta["config_stop"] = snapshot(f"session stop: {meta['title']} ({ts(t1)})")
    diff = git_hist("diff", meta["config_start"], meta["config_stop"], check=False).stdout
    (sdir / "config.diff").write_text(diff)
    if meta.get("loglevel_changed") and not a.keep_trace:
        if openpnp_running():
            print("NOTE: OpenPnP is still running; the log level stays TRACE until you set it back "
                  "(Log tab) - restoring now would be overwritten when OpenPnP exits.")
        else:
            set_loglevel(meta["loglevel_before"])
    meta["usb_stop"] = usb_devices()
    save(sdir, meta)
    summarize(sdir, meta, logs, t0, t1)
    CURRENT.unlink()
    print(f"session stopped: {sdir}")
    print(f"  {len(logs)} OpenPnP log file(s), config diff {len(diff.splitlines())} lines, summary: {sdir / 'summary.md'}")
    print("  please fill in notes.md (what you did / what was not good) - that is the input for the next fix")


def cmd_status(a):
    s = current()
    print(f"running: {s}" if s else "no session running")
    print(f"OpenPnP running: {openpnp_running()}, log level pref: {get_loglevel() or 'INFO (default)'}")


def cmd_list(a):
    for d in sorted(BASE.glob("2*")):
        m = load(d) if (d / "session.json").exists() else {}
        print(f"{d.name:50s} {m.get('start', '?')} -> {m.get('stop') or 'RUNNING'}")


def cmd_install_script(a):
    dst = OPENPNP / "scripts" / "Session"
    dst.mkdir(parents=True, exist_ok=True)
    for p in SCRIPT_SRC.glob("Session/*"):
        shutil.copy2(p, dst / p.name)
        print(f"installed {dst / p.name}")
    print("OpenPnP: Scripts > Refresh Scripts (or restart) -> Scripts > Session > Mark")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start"); s.add_argument("title"); s.add_argument("--no-trace", action="store_true")
    s = sub.add_parser("mark"); s.add_argument("text")
    s = sub.add_parser("stop"); s.add_argument("--keep-trace", action="store_true")
    sub.add_parser("status"); sub.add_parser("list"); sub.add_parser("install-openpnp-script")
    a = ap.parse_args()
    BASE.mkdir(parents=True, exist_ok=True)
    {"start": cmd_start, "mark": cmd_mark, "stop": cmd_stop, "status": cmd_status, "list": cmd_list,
     "install-openpnp-script": cmd_install_script}[a.cmd](a)


if __name__ == "__main__":
    main()
