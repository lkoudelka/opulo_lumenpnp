# Scripts > Lumen > Feeder Part Check
#
# Tick feeders and press Check: the top camera visits each pick location (camera only, no feed, no
# nozzle down).  The pocket centre is found from the sprocket holes (EIA tape geometry: paper, clear
# and black tape, any part size); "part at pick" is detected on paper tape (shown "?" otherwise).
# A part already in the pick pocket sets OpenPnP's feed option SkipNext (the next feed is skipped).
# "Apply offset" moves the pick location onto the pocket centre (read back, max 2 mm).
# "While feeding": the same check runs during the job every N feeds of the ticked feeders
# (Events/Feeder.BeforeFeed): skip the feed if a part is at pick, centre the pick location
# (optionally after confirmation).  Columns sort by clicking the header.
# Tab "Options per feeder": every feeder can have its own while-feeding and pick-vacuum options
# (lumen.feederopts); without an own value the Defaults apply (shown grey).
# "Pick vacuum check" (Events/Nozzle.AfterPick): after each pick the vacuum level is compared with the
# feeder's typical good pick; clearly closer to free air (edge pick) -> the next feed of that feeder
# runs the camera re-centring check.  Thresholds per nozzle tip in vacuum counts.
# "Go to pick location" moves the top camera over the clicked feeder; "Identify" blinks its LED.
from __future__ import absolute_import, division, print_function

import os
import sys

_LIB = os.path.join(str(scripting.getScriptsDirectory().getParent()), "lumen", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
import lumen.oppnp
import lumen.helptext
import lumen.uihelp
import lumen.tapevision
import lumen.feedercheck
import lumen.feedwatch
import lumen.pickvac
import lumen.feederopts
reload(lumen.oppnp)
reload(lumen.helptext)
reload(lumen.uihelp)
reload(lumen.tapevision)
reload(lumen.feedercheck)
reload(lumen.feedwatch)
reload(lumen.pickvac)
reload(lumen.feederopts)
from lumen import feedercheck, feederopts, feedwatch, oppnp, pickvac
from lumen.oppnp import JavaException

from java.awt import BorderLayout, Color, Dimension, FlowLayout, Font, GridLayout
from java.lang import Boolean, Double, Integer, String
from javax.swing import (BorderFactory, DefaultCellEditor, JButton, JCheckBox, JComboBox, JFrame, JLabel, JOptionPane, JPanel,
                         JScrollPane, JTabbedPane, JTable, JTextField, WindowConstants)
from javax.swing.table import AbstractTableModel, DefaultTableCellRenderer, TableCellRenderer

COLS = ["Check", "Feeder", "Slot", "Part", "Tape", "Part at pick", "Pick vs pocket mm", "Result"]
# options per feeder (lumen.feederopts): column -> option key
OCOLS = ["Feeder", "Slot", "Part", "While feeding", "Every N", "Confirm", "Skip if part", "Max mm", "Vac check",
         "Vac threshold", "Edge pick action", "Return fails: feed next", "Own values"]
OKEY = {3: "watch", 4: "every", 5: "confirm", 6: "skip_if_part", 7: "max_mm", 8: "pickvac", 9: "threshold", 10: "action",
        11: "fallback_feed_next"}
ACTION_LABELS = ["log only", "re-centre at next feed", "return to feeder + pick again", "discard + pick again"]


def slot_of(f, res=None):
    slot = (res or {}).get("slot", f.getSlotAddress() if hasattr(f, "getSlotAddress") else None)
    return None if slot is None else Integer(int(slot))


class Model(AbstractTableModel):
    def __init__(self, owner):
        AbstractTableModel.__init__(self)
        self.owner = owner
        self.rows = []
        self.locked = False

    def getRowCount(self):
        return len(self.rows)

    def getColumnCount(self):
        return len(COLS)

    def getColumnName(self, c):
        return COLS[c]

    def getColumnClass(self, c):
        return Boolean if c == 0 else Integer if c == 2 else String

    def isCellEditable(self, r, c):
        return c == 0 and not self.locked

    def getValueAt(self, r, c):
        x = self.rows[r]
        res = x.get("res") or {}
        f = x["feeder"]
        if c == 0:
            return Boolean(x["sel"])
        if c == 2:
            return slot_of(f, res)
        part = f.getPart().getId() if f.getPart() is not None else "-"
        at = res.get("part_at_pick")
        at = "-" if "part_at_pick" not in res else "?" if at is None else "YES" if at else "EMPTY"
        pick = "-" if res.get("pocket_dx") is None else "%+.2f / %+.2f" % (res["pocket_dx"], res["pocket_dy"])
        tape = res.get("method") or "-"
        return {1: f.getName(), 3: str(part), 4: tape, 5: at, 6: pick, 7: x.get("status", "")}[c]

    def setValueAt(self, v, r, c):
        if c == 0:
            self.rows[r]["sel"] = bool(v)
        self.fireTableCellUpdated(r, c)


class OptModel(AbstractTableModel):
    """One row per feeder, its effective options; an edit = own value (all highlighted rows)."""

    def __init__(self, owner):
        AbstractTableModel.__init__(self)
        self.owner = owner
        self.rows = []
        self.locked = False

    def getRowCount(self):
        return len(self.rows)

    def getColumnCount(self):
        return len(OCOLS)

    def getColumnName(self, c):
        return OCOLS[c]

    def getColumnClass(self, c):
        return (Boolean if c in (3, 5, 6, 8, 11) else Integer if c in (1, 4) else Double if c == 7 else String)

    def isCellEditable(self, r, c):
        return c in OKEY and not self.locked

    def getValueAt(self, r, c):
        x = self.rows[r]
        f = x["feeder"]
        data = self.owner.settings.data
        if c == 0:
            return f.getName()
        if c == 1:
            return slot_of(f)
        if c == 2:
            return str(f.getPart().getId()) if f.getPart() is not None else "-"
        if c == 12:
            return feederopts.summary(data, x["hwid"])
        e = feederopts.effective(data, x["hwid"])
        v = e[OKEY[c]]
        if c in (3, 5, 6, 8, 11):
            return Boolean(bool(v))
        if c == 4:
            return Integer(int(v))
        if c == 7:
            return Double(float(v))
        if c == 9:
            return "per tip" if v is None else "%.1f" % v
        return ACTION_LABELS[list(feederopts.ACTIONS).index(v)] if v in feederopts.ACTIONS else str(v)

    def setValueAt(self, v, r, c):
        if c not in OKEY:
            return
        key = OKEY[c]
        if key == "action":
            v = feederopts.ACTIONS[ACTION_LABELS.index(v)] if v in ACTION_LABELS else v
        targets = self.owner.highlighted_rows(r)
        self.owner.set_feeder_option([self.rows[i]["hwid"] for i in targets], key, v)
        self.refresh()

    def refresh(self):
        """Repaint all rows, keeping the highlighted rows (fireTableDataChanged would clear them)."""
        if self.rows:
            self.fireTableRowsUpdated(0, len(self.rows) - 1)


class OwnRenderer(DefaultTableCellRenderer):
    """Text / number cells: the feeder's own value in black, a default (inherited) value grey italic."""

    def __init__(self, owner):
        DefaultTableCellRenderer.__init__(self)
        self.owner = owner

    def getTableCellRendererComponent(self, table, value, sel, foc, row, col):
        comp = DefaultTableCellRenderer.getTableCellRendererComponent(self, table, value, sel, foc, row, col)
        mc = table.convertColumnIndexToModel(col)
        if mc in OKEY:
            x = self.owner.opt_model.rows[table.convertRowIndexToModel(row)]
            mine = OKEY[mc] in feederopts.own(self.owner.settings.data, x["hwid"])
            f = comp.getFont()
            comp.setFont(f.deriveFont(Font.PLAIN if mine else Font.ITALIC))
            if not sel:
                comp.setForeground(Color.BLACK if mine else Color.GRAY)
        if mc in (4, 7):
            comp.setHorizontalAlignment(JLabel.RIGHT)
        return comp


class OwnBoolRenderer(TableCellRenderer):
    """Tick cells: a default (inherited) value is drawn greyed out, the feeder's own value normal."""

    def __init__(self, owner, base):
        self.owner = owner
        self.base = base

    def getTableCellRendererComponent(self, table, value, sel, foc, row, col):
        comp = self.base.getTableCellRendererComponent(table, value, sel, foc, row, col)
        mc = table.convertColumnIndexToModel(col)
        x = self.owner.opt_model.rows[table.convertRowIndexToModel(row)]
        comp.setEnabled(OKEY[mc] == "watch" or OKEY[mc] in feederopts.own(self.owner.settings.data, x["hwid"]))
        return comp


def verdict(res):
    if res.get("error"):
        return "NOT FOUND: " + res["error"]
    notes = []
    if res.get("part_at_pick") is False:
        notes.append("no part in the pick pocket")
    elif res.get("part_at_pick") is None:
        notes.append("part presence not detected on this tape")
    d = (res["pocket_dx"] ** 2 + res["pocket_dy"] ** 2) ** 0.5
    if d > 0.15:
        notes.append("pick %.2f mm off the pocket centre (Apply offset)" % d)
    return "OK" if not notes else "; ".join(notes)


class PartCheck(object):
    def __init__(self):
        from org.openpnp.machine.photon import PhotonFeeder
        self.settings = oppnp.Settings(scripting)
        self.log = oppnp.FileLog(scripting, "feeder-part-check")
        self.save_dir = os.path.join(oppnp.lumen_dir(scripting), "feeder-check")
        self.model = Model(self)
        self.opt_model = OptModel(self)
        feeders = [f for f in machine.getFeeders() if isinstance(f, PhotonFeeder)]
        feeders.sort(key=lambda f: (f.getSlotAddress() is None, f.getSlotAddress() or 0, f.getName()))
        self.model.rows = [{"feeder": f, "sel": False, "hwid": str(f.getHardwareId()).upper()} for f in feeders]
        self.opt_model.rows = self.model.rows
        self.busy = False
        dflt = feederopts.defaults(self.settings.data)
        pv = dict(pickvac.DEFAULTS)
        pv.update(self.settings.get("pickvac", {}) or {})
        fr = self.frame = JFrame("Feeder part check (camera only)")
        fr.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8))
        self.info = JLabel("Tick feeders and press Check selected (camera only). Help above explains every option.")
        root.add(self.info, BorderLayout.NORTH)
        self.tabs = JTabbedPane()
        # -- tab 1: check now ------------------------------------------------------------------
        t1 = JPanel(BorderLayout(6, 6))
        self.table = JTable(self.model)
        self.table.setAutoCreateRowSorter(True)
        for i, w in enumerate((50, 220, 45, 190, 170, 90, 120, 420)):
            self.table.getColumnModel().getColumn(i).setPreferredWidth(w)
        sp = JScrollPane(self.table)
        sp.setPreferredSize(Dimension(1380, 360))
        t1.add(sp, BorderLayout.CENTER)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        self.check_btn = JButton("Check selected", actionPerformed=lambda e: self.check())
        b.add(JButton("Select all", actionPerformed=lambda e: self.select(lambda x: True)))
        b.add(JButton("Select none", actionPerformed=lambda e: self.select(lambda x: False)))
        b.add(self.check_btn)
        b.add(JButton("Apply offset to selected", actionPerformed=lambda e: self.apply()))
        t1.add(b, BorderLayout.SOUTH)
        self.tabs.addTab("Check", None, t1, lumen.helptext.HELP["part_check"]["tabs"]["Check"])
        # -- tab 2: options per feeder ---------------------------------------------------------------
        t2 = JPanel(BorderLayout(6, 6))
        defs = JPanel(GridLayout(0, 1))
        defs.setBorder(BorderFactory.createTitledBorder(
            "Defaults - used by every feeder without its own value (grey / italic in the table)"))
        opts = JPanel(FlowLayout(FlowLayout.LEFT))
        opts.add(JLabel("While feeding: check every"))
        self.every = JTextField(str(dflt["every"]), 3)
        opts.add(self.every)
        opts.add(JLabel("feeds;"))
        self.confirm = JCheckBox("confirm moves", bool(dflt["confirm"]))
        opts.add(self.confirm)
        self.skip = JCheckBox("skip feed if part at pick", bool(dflt["skip_if_part"]))
        opts.add(self.skip)
        opts.add(JLabel("max correction mm"))
        self.maxmm = JTextField("%.2f" % dflt["max_mm"], 4)
        opts.add(self.maxmm)
        defs.add(opts)
        vrow = JPanel(FlowLayout(FlowLayout.LEFT))
        self.pv_on = JCheckBox("Pick vacuum check, threshold (counts):", bool(dflt["pickvac"]))
        vrow.add(self.pv_on)
        self.pv_fields = {}
        tips = sorted(set([str(t.getName()) for t in machine.getNozzleTips()] + [k for k in pv["threshold"] if k != "*"]))
        for t in tips + ["*"]:
            vrow.add(JLabel(t if t != "*" else "other tips"))
            fld = JTextField("%.1f" % pickvac.threshold_for(pv, t), 3)
            self.pv_fields[t] = fld
            vrow.add(fld)
        defs.add(vrow)
        arow = JPanel(FlowLayout(FlowLayout.LEFT))
        arow.add(JLabel("action:"))
        self.pv_action = JComboBox(ACTION_LABELS)
        self.pv_action.setSelectedIndex(list(feederopts.ACTIONS).index(dflt["action"]) if dflt["action"] in feederopts.ACTIONS else 1)
        arow.add(self.pv_action)
        self.pv_feed_next = JCheckBox("return fails: feed next part", bool(dflt["fallback_feed_next"]))
        arow.add(self.pv_feed_next)
        arow.add(JButton("Save defaults", actionPerformed=lambda e: self.save_defaults()))
        arow.add(JButton("Pick retries...", actionPerformed=lambda e: self.pick_retries()))
        defs.add(arow)
        t2.add(defs, BorderLayout.NORTH)
        self.opt_table = JTable(self.opt_model)
        self.opt_table.setAutoCreateRowSorter(True)
        for i, w in enumerate((200, 45, 160, 90, 65, 65, 85, 65, 75, 95, 190, 150, 170)):
            self.opt_table.getColumnModel().getColumn(i).setPreferredWidth(w)
        txt = OwnRenderer(self)
        boolr = OwnBoolRenderer(self, self.opt_table.getDefaultRenderer(Boolean))
        for c in OKEY:
            col = self.opt_table.getColumnModel().getColumn(c)
            col.setCellRenderer(boolr if self.opt_model.getColumnClass(c) == Boolean else txt)
        self.opt_table.getColumnModel().getColumn(10).setCellEditor(DefaultCellEditor(JComboBox(ACTION_LABELS)))
        sp2 = JScrollPane(self.opt_table)
        sp2.setPreferredSize(Dimension(1380, 280))
        t2.add(sp2, BorderLayout.CENTER)
        ob = JPanel(FlowLayout(FlowLayout.LEFT))
        ob.add(JLabel("Edit a cell = own value for that feeder. Several rows highlighted (Shift / Ctrl + click): "
                      "the edit applies to all of them."))
        ob.add(JButton("Reset highlighted to defaults", actionPerformed=lambda e: self.reset_highlighted()))
        t2.add(ob, BorderLayout.SOUTH)
        self.tabs.addTab("Options per feeder", None, t2, lumen.helptext.HELP["part_check"]["tabs"]["Options per feeder"])
        root.add(self.tabs, BorderLayout.CENTER)
        b2 = JPanel(FlowLayout(FlowLayout.RIGHT))
        b2.add(JButton("Go to pick location", actionPerformed=lambda e: self.go_to()))
        b2.add(JButton("Identify (blink LED)", actionPerformed=lambda e: self.identify()))
        b2.add(JButton("Close", actionPerformed=lambda e: fr.dispose()))
        root.add(b2, BorderLayout.SOUTH)
        fr.setContentPane(lumen.uihelp.wrap(root, "part_check"))
        fr.pack()
        fr.setLocationRelativeTo(gui)
        fr.setVisible(True)

    # -- options ------------------------------------------------------------------------
    def _write(self, change):
        """Re-read settings.json (the feed hook may have changed it during a job), change, write."""
        self.settings.__init__(scripting)
        change(self.settings.data)
        self.settings.set("feeder_options", self.settings.data.get("feeder_options", {}))

    def highlighted_rows(self, r):
        """Model rows an edit of row r applies to: all highlighted rows if r is one of them."""
        sel = [self.opt_table.convertRowIndexToModel(i) for i in self.opt_table.getSelectedRows()]
        return sel if r in sel else [r]

    def set_feeder_option(self, hwids, key, value):
        try:
            feederopts.validate(key, value)
        except (ValueError, TypeError) as e:
            JOptionPane.showMessageDialog(self.frame, "Not changed: %s" % e)
            return

        def change(data):
            for h in hwids:
                feederopts.set_own(data, h, key, value)
        self._write(change)
        names = [x["feeder"].getName() for x in self.model.rows if x["hwid"] in hwids]
        self.log("own option %s = %s for %s" % (key, value, ", ".join(names)))
        label = dict((k, OCOLS[c]) for c, k in OKEY.items())[key]
        shown = (ACTION_LABELS[list(feederopts.ACTIONS).index(value)] if key == "action" else
                 ("on" if value else "off") if isinstance(value, bool) else value if value not in (None, "") else "per tip")
        self.info.setText("%s = %s for %d feeder(s): %s" % (label, shown, len(names), ", ".join(names)[:160]))
        if key == "action" and value in ("return", "discard"):
            self.warn_retries()

    def reset_highlighted(self):
        rows = [self.opt_model.rows[self.opt_table.convertRowIndexToModel(i)] for i in self.opt_table.getSelectedRows()]
        if not rows:
            JOptionPane.showMessageDialog(self.frame, "Highlight (click) the feeder rows to reset.")
            return

        def change(data):
            for x in rows:
                feederopts.clear_own(data, x["hwid"])
        self._write(change)
        self.opt_model.refresh()
        self.log("own options reset to defaults: %s" % [x["feeder"].getName() for x in rows])
        self.info.setText("%d feeder(s) use the defaults again ('While feeding' tick kept)" % len(rows))

    def save_defaults(self):
        try:
            every = feederopts.validate("every", self.every.getText().strip())
            maxmm = feederopts.validate("max_mm", self.maxmm.getText().strip())
            thr = dict((t, float(f.getText())) for t, f in self.pv_fields.items())
        except ValueError as e:
            JOptionPane.showMessageDialog(self.frame, "Not saved: %s\n('every' whole number >= 1, max correction "
                                          "0.05 ... 2 mm, thresholds numbers in vacuum counts)." % e)
            return
        if any(v <= 0 for v in thr.values()):
            JOptionPane.showMessageDialog(self.frame, "Thresholds must be above 0.")
            return
        action = feederopts.ACTIONS[self.pv_action.getSelectedIndex()]

        def change(data):
            fw = data.setdefault("feedwatch", {})
            fw.update(every=every, max_mm=maxmm, confirm=bool(self.confirm.isSelected()),
                      skip_if_part=bool(self.skip.isSelected()))
            pvd = data.setdefault("pickvac", {})
            pvd.update(enabled=bool(self.pv_on.isSelected()), threshold=thr, action=action,
                       fallback_feed_next=bool(self.pv_feed_next.isSelected()))
        self._write(change)
        self.opt_model.refresh()
        self.log("defaults: feedwatch %s | pickvac %s" % (self.settings.data["feedwatch"], self.settings.data["pickvac"]))
        self.info.setText("defaults saved: every %d feeds, max %.2f mm, pick vacuum %s (%s) - feeders with own values unchanged"
                          % (every, maxmm, "ON" if self.pv_on.isSelected() else "off", action))
        if self.pv_on.isSelected() and action in ("return", "discard"):
            self.warn_retries()

    def warn_retries(self):
        zero = self.job_parts_without_retry()
        if zero:
            JOptionPane.showMessageDialog(self.frame, "'Pick again' needs the part's pick retry count >= 1.\n"
                                          "%d part(s) of the open job have 0 (then only re-centring is done):\n%s\n\n"
                                          "Use 'Pick retries...' to set them."
                                          % (len(zero), ", ".join(sorted(str(p.getId()) for p in zero)[:12])))

    def job_parts_without_retry(self):
        from lumen import jobinfo
        job = gui.getJobTab().getJob() if gui is not None and gui.getJobTab() is not None else None
        parts = {}
        if job is not None:
            for bl, pl, placed in jobinfo.job_placements(job):
                if pl.getPart() is not None:
                    parts[str(pl.getPart().getId())] = pl.getPart()
        return [p for p in parts.values() if p.getPickRetryCount() < 1]

    def pick_retries(self):
        zero = self.job_parts_without_retry()
        if not zero:
            JOptionPane.showMessageDialog(self.frame, "All parts of the open job have a pick retry count >= 1 (or no job is open).")
            return
        if JOptionPane.showConfirmDialog(self.frame, "Set the pick retry count to 2 for %d part(s) of the open job?\n%s\n\n"
                                         "OpenPnP then discards a failed pick and picks again (also its own vacuum check).\n"
                                         "This changes parts.xml when the configuration is saved." % (
                                             len(zero), ", ".join(sorted(str(p.getId()) for p in zero)[:20])),
                                         "Pick retries", JOptionPane.OK_CANCEL_OPTION) != JOptionPane.OK_OPTION:
            return
        for p in zero:
            p.setPickRetryCount(2)
        self.log("pick retry count set to 2 for: %s" % sorted(str(p.getId()) for p in zero))
        self.info.setText("pick retry count 2 set for %d part(s) - save the configuration to keep it" % len(zero))

    # -- one feeder: go to / identify -----------------------------------------------------
    def clicked(self):
        t = self.opt_table if self.tabs.getSelectedIndex() == 1 else self.table
        i = t.getSelectedRow()
        if i < 0:
            JOptionPane.showMessageDialog(self.frame, "Click a feeder row first.")
            return None
        return self.model.rows[t.convertRowIndexToModel(i)]

    def go_to(self):
        x = self.clicked()
        if x is None or not oppnp.confirm_ready(machine, gui, self.frame, "Cannot move"):
            return

        def work():
            try:
                pick = oppnp.run_machine_task(machine, lambda: feedercheck.go_to(machine, x["feeder"]))
                oppnp.on_ui(lambda: self.info.setText("camera at the pick location of %s: %.3f / %.3f" % (
                    x["feeder"].getName(), pick.getX(), pick.getY())))
            except (Exception, JavaException) as e:
                oppnp.on_ui(lambda: self.info.setText("go to failed: %s" % e))
        oppnp.in_background(work)

    def identify(self):
        x = self.clicked()
        if x is None or not oppnp.confirm_ready(machine, gui, self.frame, "Cannot identify"):
            return

        def work():
            try:
                addr = oppnp.run_machine_task(machine, lambda: feedercheck.identify(machine, x["feeder"]))
                oppnp.on_ui(lambda: self.info.setText("%s (address %d) is blinking" % (x["feeder"].getName(), addr)))
            except (Exception, JavaException) as e:
                oppnp.on_ui(lambda: self.info.setText("identify failed: %s" % e))
        oppnp.in_background(work)

    # -- check --------------------------------------------------------------------------
    def select(self, pred):
        for x in self.model.rows:
            x["sel"] = pred(x)
        self.model.fireTableDataChanged()

    def selected(self):
        return [x for x in self.model.rows if x["sel"]]

    def check(self):
        rows = self.selected()
        if not rows:
            JOptionPane.showMessageDialog(self.frame, "Tick at least one feeder.")
            return
        if not oppnp.confirm_ready(machine, gui, self.frame, "Cannot check"):
            return
        self.busy = True
        self.model.locked = True
        self.check_btn.setEnabled(False)

        def work():
            from org.openpnp.machine.reference import ReferenceFeeder
            try:
                for i, x in enumerate(rows):
                    oppnp.on_ui(lambda i=i: self.info.setText("checking %d of %d: %s" % (i + 1, len(rows), x["feeder"].getName())))
                    try:
                        res = oppnp.run_machine_task(machine, lambda f=x["feeder"]: feedercheck.check_feeder(machine, f, self.save_dir))
                    except (Exception, JavaException) as e:
                        res = {"error": str(e)}
                    x["res"] = res
                    x["status"] = verdict(res)
                    if res.get("part_at_pick"):
                        x["feeder"].setFeedOptions(ReferenceFeeder.FeedOptions.SkipNext)
                        x["status"] += "; next feed SKIPPED (part already at pick)"
                    self.log("%s slot %s: %s | %s" % (x["feeder"].getName(), res.get("slot"), x["status"],
                                                       dict((k, v) for k, v in res.items() if k != "holes")))
                    oppnp.on_ui(self.model.fireTableDataChanged)
                n_ok = len([x for x in rows if x.get("status", "").startswith("OK")])
                oppnp.on_ui(lambda: self.info.setText("%d checked, %d OK. Images: %s" % (len(rows), n_ok, self.save_dir)))
            finally:
                self.busy = False
                self.model.locked = False
                oppnp.on_ui(lambda: self.check_btn.setEnabled(True))
        oppnp.in_background(work)

    def apply(self):
        rows = [x for x in self.selected() if (x.get("res") or {}).get("pocket_dx") is not None]
        if not rows:
            JOptionPane.showMessageDialog(self.frame, "Check the feeders first (rows with a measured pocket offset).")
            return
        txt = "\n".join("%s: move pick %+.2f / %+.2f mm" % (x["feeder"].getName(), x["res"]["pocket_dx"], x["res"]["pocket_dy"])
                        for x in rows)
        if JOptionPane.showConfirmDialog(self.frame, "Move the pick location onto the pocket centre?\n\n" + txt,
                                         "Apply offset", JOptionPane.OK_CANCEL_OPTION) != JOptionPane.OK_OPTION:
            return
        for x in rows:
            try:
                before, after = feedercheck.apply_pocket_offset(x["feeder"], x["res"]["pocket_dx"], x["res"]["pocket_dy"])
                x["status"] = "offset applied: pick %.3f/%.3f -> %.3f/%.3f (check again)" % (
                    before.getX(), before.getY(), after.getX(), after.getY())
                self.log("%s: %s" % (x["feeder"].getName(), x["status"]))
            except (Exception, JavaException) as e:
                x["status"] = "not applied: %s" % e
            x["res"]["pocket_dx"] = None
        self.model.fireTableDataChanged()


PartCheck()
