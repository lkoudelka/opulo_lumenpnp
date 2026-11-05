# Scripts > Lumen > Preflight   (study §4: one-click checklist before a job)
#
# Runs the checks enabled in ~/.openpnp2/lumen/preflight.json (created with defaults on the
# first run; edit it to switch steps on/off or change severity) and shows PASS / WARN / FAIL.
# Only "home" moves the machine (and only if enabled and needed).  It does not start or
# block the job - it tells you whether it is ready.
from __future__ import absolute_import, division, print_function

import json
import os
import sys

_LIB = os.path.join(str(scripting.getScriptsDirectory().getParent()), "lumen", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
import lumen.photon
import lumen.oppnp
import lumen.jobinfo
reload(lumen.photon)
reload(lumen.oppnp)
reload(lumen.jobinfo)
from lumen import jobinfo, oppnp, photon
from lumen.oppnp import JavaException

from java.awt import BorderLayout, Color, Dimension, FlowLayout
from java.awt import Desktop
from java.io import File
from java.lang import String
from javax.swing import BorderFactory, JButton, JFrame, JLabel, JPanel, JScrollPane, JTable, WindowConstants
from javax.swing.table import AbstractTableModel, DefaultTableCellRenderer

DEFAULT = {
    "_help": "on: run the step; severity: fail = must be fixed, warn = attention. Steps run in this order.",
    "steps": [
        {"id": "machine_enabled", "on": True, "severity": "fail"},
        {"id": "job_open", "on": True, "severity": "fail"},
        {"id": "home", "on": True, "severity": "fail", "mode": "if_needed"},
        {"id": "lights", "on": True, "severity": "warn", "actuator": "LED"},
        {"id": "nozzle_tips", "on": True, "severity": "warn"},
        {"id": "vacuum_sensors", "on": True, "severity": "warn"},
        {"id": "job_readiness", "on": True, "severity": "fail"},
        {"id": "feeder_bus", "on": True, "severity": "fail", "min_version": ""},
    ],
}
COLS = ["Step", "Result", "Detail"]


def load_config():
    p = os.path.join(oppnp.lumen_dir(scripting), "preflight.json")
    if not os.path.isfile(p):
        f = open(p, "w")
        json.dump(DEFAULT, f, indent=2)
        f.close()
    try:
        return p, json.load(open(p))
    except ValueError as e:
        return p, {"steps": [], "_error": "preflight.json is not valid JSON: %s" % e}


def vtuple(v):
    import re
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


# --- steps: each returns (ok, detail); ok None = skipped ------------------------------
def st_machine_enabled(cfg, ctx):
    return machine.isEnabled(), "enabled" if machine.isEnabled() else "machine not enabled: connect first"


def st_job_open(cfg, ctx):
    job = gui.getJobTab().getJob()
    n = len(jobinfo.job_placements(job)) if job else 0
    return n > 0, "%d placement(s) in the job" % n


def st_home(cfg, ctx):
    if machine.isHomed() and cfg.get("mode", "if_needed") == "if_needed":
        return True, "already homed"
    machine.home()
    return machine.isHomed(), "homed" if machine.isHomed() else "homing did not complete"


def st_lights(cfg, ctx):
    a = machine.getActuatorByName(cfg.get("actuator", "LED"))
    if a is None:
        return None, "actuator '%s' not found" % cfg.get("actuator", "LED")
    a.actuate(True)
    return True, "'%s' on" % a.getName()


def st_nozzle_tips(cfg, ctx):
    missing = [n.getName() for n in machine.getDefaultHead().getNozzles() if n.getNozzleTip() is None]
    return not missing, "no tip on: %s" % ", ".join(missing) if missing else "all nozzles have a tip"


def st_vacuum_sensors(cfg, ctx):
    out, ok = [], True
    for n in machine.getDefaultHead().getNozzles():
        a = n.getVacuumSenseActuator() if hasattr(n, "getVacuumSenseActuator") else None
        if a is None:
            out.append("%s: no sensor configured" % n.getName())
            continue
        try:
            out.append("%s: %s" % (n.getName(), a.read()))
        except (Exception, JavaException) as e:
            ok = False
            out.append("%s: read failed (%s)" % (n.getName(), e))
    return ok, "; ".join(out)


def st_job_readiness(cfg, ctx):
    job = gui.getJobTab().getJob()
    rows = jobinfo.readiness(job, machine) if job else []
    bad = [r for r in rows if r["issues"] and r["remaining"] > 0]
    ctx["readiness"] = rows
    return not bad, ("; ".join("%s: %s" % (r["part_id"], ", ".join(r["issues"])) for r in bad[:6])
                     or "%d part type(s) ready" % len(rows))


def st_feeder_bus(cfg, ctx):
    rows = ctx.get("readiness") or jobinfo.readiness(gui.getJobTab().getJob(), machine)
    slots = sorted(set(int(f.getSlotAddress()) for r in rows if r["remaining"] > 0 for f in r["enabled_feeders"]
                       if hasattr(f, "getSlotAddress") and f.getSlotAddress() is not None))
    if not slots:
        return None, "the job uses no Photon feeder"
    bus = photon.Bus(oppnp.ActuatorTransport(machine))
    found = photon.scan(bus, slots)
    missing = [a for a in slots if a not in found]
    minv = cfg.get("min_version") or ""
    old = [a for a in found if minv and vtuple(found[a].version or "0") < vtuple(minv)]
    detail = "%d/%d job feeders answer" % (len(found), len(slots))
    if missing:
        detail += "; no answer: %s" % missing
    if old:
        detail += "; firmware older than %s: %s" % (minv, old)
    return not missing and not old, detail


STEPS = dict((k[3:], v) for k, v in globals().items() if k.startswith("st_"))


class Model(AbstractTableModel):
    def __init__(self):
        AbstractTableModel.__init__(self)
        self.rows = []

    def getRowCount(self):
        return len(self.rows)

    def getColumnCount(self):
        return 3

    def getColumnName(self, c):
        return COLS[c]

    def getColumnClass(self, c):
        return String

    def getValueAt(self, r, c):
        return self.rows[r][c]


class Colour(DefaultTableCellRenderer):
    COL = {"PASS": Color(210, 245, 210), "WARN": Color(255, 240, 200), "FAIL": Color(255, 215, 215)}

    def __init__(self, model):
        DefaultTableCellRenderer.__init__(self)
        self.model = model

    def getTableCellRendererComponent(self, table, value, sel, focus, row, col):
        c = DefaultTableCellRenderer.getTableCellRendererComponent(self, table, value, sel, focus, row, col)
        if not sel:
            c.setBackground(self.COL.get(self.model.rows[row][1], Color.WHITE))
        return c


class Preflight(object):
    def __init__(self):
        self.path, self.cfg = load_config()
        self.log = oppnp.FileLog(scripting, "preflight")
        self.model = Model()
        f = self.frame = JFrame("Preflight")
        f.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8))
        self.head = JLabel("checklist: %s" % self.path)
        root.add(self.head, BorderLayout.NORTH)
        t = JTable(self.model)
        r = Colour(self.model)
        for i, w in enumerate((150, 70, 640)):
            t.getColumnModel().getColumn(i).setCellRenderer(r)
            t.getColumnModel().getColumn(i).setPreferredWidth(w)
        sp = JScrollPane(t)
        sp.setPreferredSize(Dimension(880, 260))
        root.add(sp, BorderLayout.CENTER)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        self.run_btn = JButton("Run checks", actionPerformed=lambda e: self.run())
        b.add(self.run_btn)
        b.add(JButton("Edit checklist", actionPerformed=lambda e: self.edit()))
        b.add(JButton("Close", actionPerformed=lambda e: f.dispose()))
        root.add(b, BorderLayout.SOUTH)
        f.setContentPane(root)
        f.pack()
        f.setLocationRelativeTo(gui)
        f.setVisible(True)
        if self.cfg.get("_error"):
            self.model.rows = [["checklist", "FAIL", self.cfg["_error"]]]
            self.model.fireTableDataChanged()

    def edit(self):
        try:
            Desktop.getDesktop().open(File(self.path))
        except (Exception, JavaException):
            self.head.setText("edit by hand: %s" % self.path)

    def run(self):
        if machine.isEnabled() and not oppnp.confirm_ready(machine, gui, self.frame, "Cannot run preflight"):
            return
        self.path, self.cfg = load_config()
        steps = [s for s in self.cfg.get("steps", []) if s.get("on")]
        self.model.rows = [[s["id"], "...", ""] for s in steps]
        self.model.fireTableDataChanged()
        self.run_btn.setEnabled(False)

        def work():
            ctx = {}
            fails = warns = 0
            for i, s in enumerate(steps):
                fn = STEPS.get(s["id"])
                if fn is None:
                    res, detail = "WARN", "unknown step id"
                else:
                    try:
                        if s["id"] in ("machine_enabled", "job_open"):
                            ok, detail = fn(s, ctx)
                        elif not machine.isEnabled():
                            ok, detail = None, "skipped: machine not enabled"
                        else:
                            ok, detail = oppnp.run_machine_task(machine, lambda fn=fn, s=s: fn(s, ctx))
                    except (Exception, JavaException) as e:
                        ok, detail = False, "error: %s" % e
                    res = "SKIP" if ok is None else "PASS" if ok else ("FAIL" if s.get("severity") == "fail" else "WARN")
                fails += res == "FAIL"
                warns += res == "WARN"
                self.model.rows[i] = [s["id"], res, detail]
                self.log("%-16s %-4s %s" % (s["id"], res, detail))
                oppnp.on_ui(self.model.fireTableDataChanged)
            verdict = "READY" if not fails else "NOT READY"
            self.log("verdict: %s (%d fail, %d warn)" % (verdict, fails, warns))

            def ui():
                self.head.setText("<html><b>%s</b> - %d fail, %d warn &nbsp; (checklist: %s)</html>" % (
                    verdict, fails, warns, self.path))
                self.run_btn.setEnabled(True)
            oppnp.on_ui(ui)
        oppnp.in_background(work)


Preflight()
