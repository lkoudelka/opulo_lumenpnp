# -*- coding: utf-8 -*-
"""Preflight > Pick safety: learned body sizes + size check, vacuum part-on / part-off limits (lumen.picksafety).
Everything is a proposal in a table; only the ticked rows change, after a confirmation that lists them."""
from __future__ import absolute_import, division, print_function

import os

from lumen import jobinfo, oppnp, picksafety as ps
from lumen.oppnp import JavaException

from java.awt import BorderLayout, Dimension, FlowLayout, GridLayout
from java.lang import Boolean, String
from javax.swing import (BorderFactory, JButton, JCheckBox, JFrame, JLabel, JOptionPane, JPanel, JScrollPane, JTable,
                         WindowConstants)
from javax.swing.table import AbstractTableModel

SCOLS = ["Apply", "Package", "Job parts", "Measured W x H mm", "Good picks", "Empty picks", "Now W x H mm", "Note"]
VCOLS = ["Part-on", "Nozzle / tip", "Good picks", "Free air", "Part-on now", "Proposed high", "Part-off",
         "Part-off proposal"]


class _Model(AbstractTableModel):
    def __init__(self, cols, values, ticks):
        AbstractTableModel.__init__(self)
        self.cols, self.values, self.ticks, self.rows = cols, values, ticks, []

    def getRowCount(self):
        return len(self.rows)

    def getColumnCount(self):
        return len(self.cols)

    def getColumnName(self, c):
        return self.cols[c]

    def getColumnClass(self, c):
        return Boolean if c in self.ticks else String

    def isCellEditable(self, r, c):
        return c in self.ticks and self.rows[r].get(self.ticks[c] + "_ok")

    def getValueAt(self, r, c):
        x = self.rows[r]
        return Boolean(bool(x.get(self.ticks[c]))) if c in self.ticks else self.values(x)[c]

    def setValueAt(self, v, r, c):
        if c in self.ticks:
            self.rows[r][self.ticks[c]] = bool(v)
        self.fireTableCellUpdated(r, c)


def _wh(w, h):
    return "-" if not w or not h else "%.2f x %.2f" % (w, h)


def size_rows(job, machine, learned):
    """One row per package of the job: learned size, the current body size, ticked when it should change."""
    from org.openpnp.model import LengthUnit
    pkgs = {}
    for bl, pl, placed in jobinfo.job_placements(job):
        part = pl.getPart()
        pk = part.getPackage() if part is not None else None
        if pk is not None:
            pkgs.setdefault(pk.getId(), [pk, set()])[1].add(part.getId())
    rows = []
    for pid in sorted(pkgs):
        pk, parts = pkgs[pid]
        fp = pk.getFootprint()
        f = 1.0 if fp is None or fp.getUnits() == LengthUnit.Millimeters else 25.4
        now = (fp.getBodyWidth() * f, fp.getBodyHeight() * f) if fp is not None else (0.0, 0.0)
        l = learned.get(pid) or {"n": 0, "empties": 0, "ok": False, "why": "never picked in the current log"}
        differs = l["ok"] and (now[0] <= 0 or now[1] <= 0 or abs(now[0] - l["w"]) > 0.25 * l["w"]
                               or abs(now[1] - l["h"]) > 0.25 * l["h"])
        rows.append({"package": pk, "id": pid, "parts": sorted(parts), "learned": l, "now": now,
                     "apply": bool(differs), "apply_ok": bool(l["ok"]),
                     "note": (l["why"] + ("" if differs or not l["ok"] else "; the body size already fits")
                              + ("; %d EMPTY pick(s) seen (accepted by bottom vision)" % l["empties"] if l["empties"] else ""))})
    return rows


def vacuum_rows(machine, parsed, free=None):
    """One row per nozzle with its loaded tip: part-on high proposal, part-off proposal (needs free air)."""
    free = free or {}
    rows = []
    for n in machine.getDefaultHead().getNozzles():
        tip = n.getNozzleTip()
        if tip is None or not hasattr(tip, "getVacuumLevelPartOnHigh"):
            continue
        picks = parsed["picks"].get(str(n.getName()), [])
        levels = ps.good_levels(picks)
        curve = free.get(str(n.getName()))
        fa = ps.steady(curve) if curve else None
        high, why_on = ps.propose_part_on(levels, fa, tip.getVacuumLevelPartOnLow(), tip.getVacuumLevelPartOnHigh())
        probe, low, why_off = ps.propose_part_off(ps.good_curves(picks), curve)
        rows.append({"nozzle": n, "tip": tip, "levels": levels, "free": fa, "high": high, "why_on": why_on,
                     "probe": probe, "low": low, "why_off": why_off,
                     "on": high is not None, "on_ok": high is not None, "off": False, "off_ok": probe is not None})
    return rows


class PickSafety(object):
    def __init__(self, machine, gui, scripting, parent, log):
        self.machine, self.gui, self.log, self.parent = machine, gui, log, parent
        self.config_dir = str(scripting.getScriptsDirectory().getParent())
        self.free = {}
        self.job = gui.getJobTab().getJob()
        f = self.frame = JFrame("Pick safety: empty nozzle / part left on the nozzle")
        f.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8))
        self.info = JLabel("<html>Learned from what the machine measured: bottom-vision sizes and vacuum levels of the "
                           "good picks in OpenPnP's log. Only ticked rows change, after a confirmation.</html>")
        root.add(self.info, BorderLayout.NORTH)
        mid = JPanel(GridLayout(2, 1, 6, 6))
        self.smodel = _Model(SCOLS, lambda x: [None, x["id"], ", ".join(x["parts"][:3]) + (" +%d" % (len(x["parts"]) - 3)
                                                                                      if len(x["parts"]) > 3 else ""),
                                               _wh(x["learned"].get("w"), x["learned"].get("h")),
                                               str(x["learned"]["n"]), str(x["learned"]["empties"]),
                                               _wh(*x["now"]), x["note"]], {0: "apply"})
        st = JTable(self.smodel)
        for i, w in enumerate((45, 200, 220, 120, 70, 75, 110, 520)):
            st.getColumnModel().getColumn(i).setPreferredWidth(w)
        sp = JScrollPane(st)
        p1 = JPanel(BorderLayout(4, 4))
        p1.setBorder(BorderFactory.createTitledBorder("Body sizes from bottom vision (an empty nozzle then fails the size check)"))
        p1.add(sp, BorderLayout.CENTER)
        self.check_box = JCheckBox("size check on: BodySize, tolerance %d %%" % ps.TOLERANCE_PERCENT, True)
        p1.add(self.check_box, BorderLayout.SOUTH)
        mid.add(p1)
        self.vmodel = _Model(VCOLS, lambda x: [None, "%s / %s" % (x["nozzle"].getName(), x["tip"].getName()),
                                               "%d: %.0f..%.0f" % (len(x["levels"]), min(x["levels"]), max(x["levels"]))
                                               if x["levels"] else "0",
                                               "-" if x["free"] is None else "%.0f" % x["free"],
                                               "%.0f..%.0f" % (x["tip"].getVacuumLevelPartOnLow(),
                                                               x["tip"].getVacuumLevelPartOnHigh()),
                                               "%.0f" % x["high"] if x["high"] is not None else x["why_on"], None,
                                               "%d ms, part off >= %.0f" % (x["probe"], x["low"])
                                               if x["probe"] is not None else x["why_off"]],
                             {0: "on", 6: "off"})
        vt = JTable(self.vmodel)
        for i, w in enumerate((60, 120, 110, 70, 90, 330, 60, 520)):
            vt.getColumnModel().getColumn(i).setPreferredWidth(w)
        p2 = JPanel(BorderLayout(4, 4))
        p2.setBorder(BorderFactory.createTitledBorder("Vacuum checks per nozzle (part-off adds its probing time to "
                                                      "every placement)"))
        p2.add(JScrollPane(vt), BorderLayout.CENTER)
        mid.add(p2)
        mid.setPreferredSize(Dimension(1380, 520))
        root.add(mid, BorderLayout.CENTER)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        b.add(JButton("Measure free air...", actionPerformed=lambda e: self.measure()))
        b.add(JButton("Apply ticked...", actionPerformed=lambda e: self.apply()))
        b.add(JButton("Close", actionPerformed=lambda e: f.dispose()))
        root.add(b, BorderLayout.SOUTH)
        from lumen import uihelp
        f.setContentPane(uihelp.wrap(root, "pick_safety"))
        self.load()
        f.pack()
        f.setLocationRelativeTo(parent)
        f.setVisible(True)

    def load(self, lines=None):
        """Read OpenPnP's log (or the given lines) and fill both tables."""
        if lines is None:
            lines = ps.log_lines(self.config_dir)
        from org.openpnp.model import Configuration
        cfg = Configuration.get()

        def package_of(part_id):
            p = cfg.getPart(part_id)
            return p.getPackage().getId() if p is not None and p.getPackage() is not None else None
        self.parsed = ps.parse_log(lines, ps.sense_names(self.machine))
        upp = ps.bottom_upp(self.machine)
        self.learned = ps.learn_sizes(self.parsed["rects"], upp, package_of) if upp else {}
        self.smodel.rows = size_rows(self.job, self.machine, self.learned) if self.job is not None else []
        self.smodel.fireTableDataChanged()
        self.vmodel.rows = vacuum_rows(self.machine, self.parsed, self.free)
        self.vmodel.fireTableDataChanged()
        self.settings = ps.size_check_settings(self.job, self.machine) if self.job is not None else {}
        self.check_box.setText("size check on: BodySize, tolerance %d %% (bottom-vision settings %s)" % (
            ps.TOLERANCE_PERCENT, ", ".join("%s: %s" % (k, str(s.getCheckPartSizeMethod()))
                                            for k, (s, parts) in sorted(self.settings.items())) or "-"))

    def measure(self):
        """Free air per nozzle: vacuum on with the empty nozzle, no motion."""
        if not oppnp.confirm_ready(self.machine, self.gui, self.frame, "Cannot measure"):
            return
        nozzles = [n for n in self.machine.getDefaultHead().getNozzles() if n.getNozzleTip() is not None]
        if any(n.getPart() is not None for n in nozzles):
            JOptionPane.showMessageDialog(self.frame, "A nozzle holds a part (OpenPnP): discard it first.")
            return
        if JOptionPane.showConfirmDialog(self.frame, "Measure free air on %s: vacuum on for 1.5 s each, NO motion.\n"
                                         "Check that NO part sticks on the nozzle tips." % ", ".join(
                                             n.getName() for n in nozzles), "Measure free air",
                                         JOptionPane.OK_CANCEL_OPTION) != JOptionPane.OK_OPTION:
            return
        self.info.setText("measuring free air ...")

        def work():
            try:
                for n in nozzles:
                    self.free[str(n.getName())] = oppnp.run_machine_task(self.machine,
                                                                         lambda n=n: ps.measure_free_air(self.machine, n))
                    self.log("free air %s: %s" % (n.getName(), " ".join("%d:%.0f" % c for c in self.free[str(n.getName())][::5])))
                text = "free air: " + ", ".join("%s %.0f" % (k, ps.steady(v)) for k, v in sorted(self.free.items()))
            except (Exception, JavaException) as e:
                text = "measurement failed: %s" % e

            def done():
                self.vmodel.rows = vacuum_rows(self.machine, self.parsed, self.free)
                self.vmodel.fireTableDataChanged()
                self.info.setText(text)
            oppnp.on_ui(done)
        oppnp.in_background(work)

    def plan(self):
        out = []
        for x in self.smodel.rows:
            if x["apply"]:
                out.append(("size", x, "package %s body %s -> %s mm" % (x["id"], _wh(*x["now"]),
                                                                        _wh(x["learned"]["w"], x["learned"]["h"]))))
        if self.check_box.isSelected():
            for k, (s, parts) in sorted(self.settings.items()):
                if str(s.getCheckPartSizeMethod()) != "BodySize" or s.getCheckSizeTolerancePercent() != ps.TOLERANCE_PERCENT:
                    out.append(("check", s, "bottom vision %s: size check %s %d %% -> BodySize %d %% (%d job part(s))"
                                % (k, s.getCheckPartSizeMethod(), s.getCheckSizeTolerancePercent(),
                                   ps.TOLERANCE_PERCENT, len(parts))))
        for x in self.vmodel.rows:
            if x["on"] and x["high"] is not None:
                out.append(("on", x, "%s / %s part-on high %.0f -> %.0f" % (x["nozzle"].getName(), x["tip"].getName(),
                                                                          x["tip"].getVacuumLevelPartOnHigh(), x["high"])))
            if x["off"] and x["probe"] is not None:
                out.append(("off", x, "%s / %s part-off check after place: vacuum %d ms, part off >= %.0f" % (
                    x["nozzle"].getName(), x["tip"].getName(), x["probe"], x["low"])))
        return out

    def apply(self, ask=True):
        plan = self.plan()
        if not plan:
            JOptionPane.showMessageDialog(self.frame, "Nothing ticked.")
            return []
        if ask and JOptionPane.showConfirmDialog(self.frame, "Apply?\n\n" + "\n".join(t for _, _, t in plan) +
                                                 "\n\nSaved with OpenPnP's configuration (on exit or File > Save).",
                                                 "Pick safety", JOptionPane.OK_CANCEL_OPTION) != JOptionPane.OK_OPTION:
            return []
        done = []
        for kind, x, text in plan:
            try:
                if kind == "size":
                    old = ps.apply_size(x["package"], x["learned"]["w"], x["learned"]["h"])
                elif kind == "check":
                    old = ps.apply_size_check(x)
                elif kind == "on":
                    old = ps.apply_part_on_high(x["tip"], x["high"])
                else:
                    old = ps.apply_part_off(x["tip"], x["probe"], x["low"])
                self.log("pick safety: %s (was %s)" % (text, old))
                done.append(text)
            except (Exception, JavaException) as e:
                self.log("pick safety: NOT applied: %s: %s" % (text, e))
        self.load()
        self.info.setText("%d change(s) applied; saved with OpenPnP's configuration." % len(done))
        return done
