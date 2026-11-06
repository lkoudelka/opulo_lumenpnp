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
import lumen.tapevision
import lumen.feedercheck
import lumen.feedwatch
import lumen.pickvac
reload(lumen.oppnp)
reload(lumen.tapevision)
reload(lumen.feedercheck)
reload(lumen.feedwatch)
reload(lumen.pickvac)
from lumen import feedercheck, feedwatch, oppnp, pickvac
from lumen.oppnp import JavaException

from java.awt import BorderLayout, Dimension, FlowLayout
from java.lang import Boolean, Integer, String
from javax.swing import (BorderFactory, JButton, JCheckBox, JComboBox, JFrame, JLabel, JOptionPane, JPanel, JScrollPane,
                         JTable, JTextField, WindowConstants)
from javax.swing.table import AbstractTableModel

COLS = ["Check", "While feeding", "Feeder", "Slot", "Part", "Tape", "Part at pick", "Pick vs pocket mm", "Result"]


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
        return Boolean if c in (0, 1) else Integer if c == 3 else String

    def isCellEditable(self, r, c):
        return c in (0, 1) and not self.locked

    def getValueAt(self, r, c):
        x = self.rows[r]
        res = x.get("res") or {}
        f = x["feeder"]
        if c == 0:
            return Boolean(x["sel"])
        if c == 1:
            return Boolean(x["hwid"] in self.owner.watch)
        if c == 3:
            slot = res.get("slot", f.getSlotAddress() if hasattr(f, "getSlotAddress") else None)
            return None if slot is None else Integer(int(slot))
        part = f.getPart().getId() if f.getPart() is not None else "-"
        at = res.get("part_at_pick")
        at = "-" if "part_at_pick" not in res else "?" if at is None else "YES" if at else "EMPTY"
        pick = "-" if res.get("pocket_dx") is None else "%+.2f / %+.2f" % (res["pocket_dx"], res["pocket_dy"])
        tape = res.get("method") or "-"
        return {2: f.getName(), 4: str(part), 5: tape, 6: at, 7: pick, 8: x.get("status", "")}[c]

    def setValueAt(self, v, r, c):
        if c == 0:
            self.rows[r]["sel"] = bool(v)
        elif c == 1:
            self.owner.set_watch(self.rows[r]["hwid"], bool(v))
        self.fireTableCellUpdated(r, c)


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
        fw = dict(feedwatch.DEFAULTS)
        fw.update(self.settings.get("feedwatch", {}) or {})
        self.fw = fw
        self.watch = set(str(h).upper() for h in fw["feeders"])
        self.model = Model(self)
        feeders = [f for f in machine.getFeeders() if isinstance(f, PhotonFeeder)]
        feeders.sort(key=lambda f: (f.getSlotAddress() is None, f.getSlotAddress() or 0, f.getName()))
        self.model.rows = [{"feeder": f, "sel": False, "hwid": str(f.getHardwareId()).upper()} for f in feeders]
        self.busy = False
        fr = self.frame = JFrame("Feeder part check (camera only)")
        fr.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8))
        north = JPanel(BorderLayout())
        self.info = JLabel("Tick feeders and press Check. The top camera visits each pick location; no feed, no pick.")
        north.add(self.info, BorderLayout.NORTH)
        opts = JPanel(FlowLayout(FlowLayout.LEFT))
        opts.add(JLabel("While feeding (ticked feeders): check every"))
        self.every = JTextField(str(fw["every"]), 3)
        opts.add(self.every)
        opts.add(JLabel("feeds;"))
        self.confirm = JCheckBox("confirm before moving the pick location", bool(fw["confirm"]))
        opts.add(self.confirm)
        self.skip = JCheckBox("skip the feed if a part is at pick", bool(fw["skip_if_part"]))
        opts.add(self.skip)
        opts.add(JLabel("max correction mm"))
        self.maxmm = JTextField("%.2f" % fw["max_mm"], 4)
        opts.add(self.maxmm)
        opts.add(JButton("Save options", actionPerformed=lambda e: self.save_options()))
        north.add(opts, BorderLayout.CENTER)
        pv = dict(pickvac.DEFAULTS)
        pv.update(self.settings.get("pickvac", {}) or {})
        self.pv = pv
        vrow = JPanel(FlowLayout(FlowLayout.LEFT))
        self.pv_on = JCheckBox("Pick vacuum check: re-centre a feeder when its pick vacuum is closer to free air than usual by",
                               bool(pv["enabled"]))
        vrow.add(self.pv_on)
        self.pv_fields = {}
        tips = sorted(set([str(t.getName()) for t in machine.getNozzleTips()] + [k for k in pv["threshold"] if k != "*"]))
        for t in tips + ["*"]:
            vrow.add(JLabel(t if t != "*" else "other tips"))
            fld = JTextField("%.1f" % pickvac.threshold_for(pv, t), 3)
            self.pv_fields[t] = fld
            vrow.add(fld)
        vrow.add(JLabel("counts (default ~30 % of free air - covered: N045 3, N08 7); then"))
        self.pv_action = JComboBox(["log only", "re-centre at the next feed", "recycle, synchronise and pick again"])
        self.pv_action.setSelectedIndex(list(pickvac.ACTIONS).index(pv.get("action", "recenter")))
        vrow.add(self.pv_action)
        vrow.add(JButton("Save", actionPerformed=lambda e: self.save_pickvac()))
        vrow.add(JButton("Pick retries for the job's parts...", actionPerformed=lambda e: self.pick_retries()))
        north.add(vrow, BorderLayout.SOUTH)
        root.add(north, BorderLayout.NORTH)
        self.table = JTable(self.model)
        self.table.setAutoCreateRowSorter(True)
        for i, w in enumerate((50, 90, 220, 45, 190, 170, 90, 120, 380)):
            self.table.getColumnModel().getColumn(i).setPreferredWidth(w)
        sp = JScrollPane(self.table)
        sp.setPreferredSize(Dimension(1380, 380))
        root.add(sp, BorderLayout.CENTER)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        self.check_btn = JButton("Check selected", actionPerformed=lambda e: self.check())
        b.add(JButton("Select all", actionPerformed=lambda e: self.select(lambda x: True)))
        b.add(JButton("Select none", actionPerformed=lambda e: self.select(lambda x: False)))
        b.add(self.check_btn)
        b.add(JButton("Apply offset to selected", actionPerformed=lambda e: self.apply()))
        b.add(JButton("Go to pick location", actionPerformed=lambda e: self.go_to()))
        b.add(JButton("Identify (blink LED)", actionPerformed=lambda e: self.identify()))
        b.add(JButton("Close", actionPerformed=lambda e: fr.dispose()))
        root.add(b, BorderLayout.SOUTH)
        fr.setContentPane(root)
        fr.pack()
        fr.setLocationRelativeTo(gui)
        fr.setVisible(True)

    # -- options ------------------------------------------------------------------------
    def set_watch(self, hwid, on):
        if on:
            self.watch.add(hwid)
        else:
            self.watch.discard(hwid)
        self.save_options(quiet=True)

    def save_options(self, quiet=False):
        try:
            every = max(1, int(self.every.getText()))
            maxmm = max(0.05, float(self.maxmm.getText()))
        except ValueError:
            JOptionPane.showMessageDialog(self.frame, "'every' must be a whole number, 'max correction' a number.")
            return
        self.fw.update(every=every, max_mm=maxmm, confirm=bool(self.confirm.isSelected()),
                       skip_if_part=bool(self.skip.isSelected()), feeders=sorted(self.watch))
        self.settings.set("feedwatch", self.fw)
        self.log("options: %s" % self.fw)
        if not quiet:
            self.info.setText("options saved: %d feeder(s) checked while feeding, every %d feeds" % (len(self.watch), every))

    def save_pickvac(self):
        try:
            thr = dict((t, float(f.getText())) for t, f in self.pv_fields.items())
        except ValueError:
            JOptionPane.showMessageDialog(self.frame, "Thresholds must be numbers (vacuum counts).")
            return
        if any(v <= 0 for v in thr.values()):
            JOptionPane.showMessageDialog(self.frame, "Thresholds must be above 0.")
            return
        self.pv.update(enabled=bool(self.pv_on.isSelected()), threshold=thr,
                       action=pickvac.ACTIONS[self.pv_action.getSelectedIndex()])
        self.settings.set("pickvac", self.pv)
        self.log("pick vacuum check: %s" % self.pv)
        self.info.setText("pick vacuum check %s, thresholds %s, action %s" % ("ON" if self.pv["enabled"] else "off", thr,
                                                                             self.pv["action"]))
        if self.pv["enabled"] and self.pv["action"] == "repick":
            zero = self.job_parts_without_retry()
            if zero:
                JOptionPane.showMessageDialog(self.frame, "'Pick again' needs the part's pick retry count >= 1.\n"
                                              "%d part(s) of the open job have 0 (then only re-centring is done):\n%s\n\n"
                                              "Use 'Pick retries for the job's parts...' to set them."
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
        i = self.table.getSelectedRow()
        if i < 0:
            JOptionPane.showMessageDialog(self.frame, "Click a feeder row first.")
            return None
        return self.model.rows[self.table.convertRowIndexToModel(i)]

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
