# Scripts > Lumen > Feeder Part Check
#
# For the ticked feeders: the top camera goes to each pick location (camera only, at safe Z, no
# nozzle down, no feed), finds the tape's sprocket holes and pockets and tells whether a part is in
# the pick pocket, how far the pick location is from the pocket centre, the measured pocket pitch
# (vs. the feeder's configured pitch) and how many parts are visible.  Images with the detection
# drawn in are saved in ~/.openpnp2/lumen/feeder-check/.  "Apply offset" moves the pick location
# of the selected feeder onto the pocket centre (Photon: feeder offset; read back, max 1 mm).
from __future__ import absolute_import, division, print_function

import os
import sys

_LIB = os.path.join(str(scripting.getScriptsDirectory().getParent()), "lumen", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
import lumen.oppnp
import lumen.tapevision
import lumen.feedercheck
reload(lumen.oppnp)
reload(lumen.tapevision)
reload(lumen.feedercheck)
from lumen import feedercheck, oppnp
from lumen.oppnp import JavaException

from java.awt import BorderLayout, Dimension, FlowLayout
from java.lang import Boolean, String
from javax.swing import (BorderFactory, JButton, JFrame, JLabel, JOptionPane, JPanel, JScrollPane, JTable,
                         WindowConstants)
from javax.swing.table import AbstractTableModel

COLS = ["Check", "Feeder", "Slot", "Part", "Pitch mm", "Part at pick", "Parts in view", "Pick vs pocket mm", "Result"]


class Model(AbstractTableModel):
    def __init__(self):
        AbstractTableModel.__init__(self)
        self.rows = []
        self.locked = False

    def getRowCount(self):
        return len(self.rows)

    def getColumnCount(self):
        return len(COLS)

    def getColumnName(self, c):
        return COLS[c]

    def getColumnClass(self, c):
        return Boolean if c == 0 else String

    def isCellEditable(self, r, c):
        return c == 0 and not self.locked

    def getValueAt(self, r, c):
        x = self.rows[r]
        res = x.get("res") or {}
        f = x["feeder"]
        part = f.getPart().getId() if f.getPart() is not None else "-"
        pitch = "-"
        if res.get("pitch_mm"):
            pitch = "%.2f (set %s)" % (res["pitch_mm"], res.get("configured_pitch", "?"))
        elif hasattr(f, "getPartPitch"):
            pitch = "set %s" % f.getPartPitch()
        pick = "-" if res.get("pocket_dx") is None else "%+.2f / %+.2f" % (res["pocket_dx"], res["pocket_dy"])
        at = "-" if res.get("part_at_pick") is None else ("yes" if res["part_at_pick"] else "EMPTY")
        seen = "-" if res.get("pockets") is None else "%d of %d" % (res["parts_visible"], res["pockets"])
        slot = res.get("slot", f.getSlotAddress() if hasattr(f, "getSlotAddress") else None)
        return [Boolean(x["sel"]), f.getName(), "-" if slot is None else str(slot), str(part), pitch, at, seen, pick,
                x.get("status", "")][c]

    def setValueAt(self, v, r, c):
        if c == 0:
            self.rows[r]["sel"] = bool(v)
            self.fireTableCellUpdated(r, c)


def verdict(res):
    if res.get("error"):
        return "NOT FOUND: " + res["error"]
    notes = []
    if not res.get("part_at_pick"):
        notes.append("no part in the pick pocket")
    cp = res.get("configured_pitch")
    if cp and res.get("pitch_mm") and abs(res["pitch_mm"] - cp) > 0.4:
        notes.append("pitch %.1f mm but feeder set to %s mm" % (res["pitch_mm"], cp))
    if res.get("pocket_dx") is not None and (res["pocket_dx"] ** 2 + res["pocket_dy"] ** 2) ** 0.5 > 0.15:
        notes.append("pick %.2f mm off the pocket centre (Apply offset)" % ((res["pocket_dx"] ** 2 + res["pocket_dy"] ** 2) ** 0.5))
    return "OK" if not notes else "; ".join(notes)


class PartCheck(object):
    def __init__(self):
        from org.openpnp.machine.photon import PhotonFeeder
        self.log = oppnp.FileLog(scripting, "feeder-part-check")
        self.save_dir = os.path.join(oppnp.lumen_dir(scripting), "feeder-check")
        self.model = Model()
        feeders = [f for f in machine.getFeeders() if isinstance(f, PhotonFeeder)]
        feeders.sort(key=lambda f: (f.getSlotAddress() is None, f.getSlotAddress() or 0, f.getName()))
        self.model.rows = [{"feeder": f, "sel": False} for f in feeders]
        self.busy = False
        fr = self.frame = JFrame("Feeder part check (camera only)")
        fr.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8))
        self.info = JLabel("Tick feeders and press Check. The top camera visits each pick location; no feed, no pick.")
        root.add(self.info, BorderLayout.NORTH)
        self.table = JTable(self.model)
        for i, w in enumerate((50, 220, 45, 190, 110, 90, 90, 120, 380)):
            self.table.getColumnModel().getColumn(i).setPreferredWidth(w)
        sp = JScrollPane(self.table)
        sp.setPreferredSize(Dimension(1300, 360))
        root.add(sp, BorderLayout.CENTER)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        self.check_btn = JButton("Check selected", actionPerformed=lambda e: self.check())
        b.add(JButton("Select all", actionPerformed=lambda e: self.select(lambda x: True)))
        b.add(JButton("Select none", actionPerformed=lambda e: self.select(lambda x: False)))
        b.add(self.check_btn)
        b.add(JButton("Apply offset to selected", actionPerformed=lambda e: self.apply()))
        b.add(JButton("Close", actionPerformed=lambda e: fr.dispose()))
        root.add(b, BorderLayout.SOUTH)
        fr.setContentPane(root)
        fr.pack()
        fr.setLocationRelativeTo(gui)
        fr.setVisible(True)

    def select(self, pred):
        for x in self.model.rows:
            x["sel"] = pred(x)
        self.model.fireTableDataChanged()

    def selected(self):
        return [x for x in self.model.rows if x["sel"]]

    def check(self, wait=False):
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
            try:
                for i, x in enumerate(rows):
                    oppnp.on_ui(lambda i=i: self.info.setText("checking %d of %d: %s" % (i + 1, len(rows), x["feeder"].getName())))
                    try:
                        res = oppnp.run_machine_task(machine, lambda f=x["feeder"]: feedercheck.check_feeder(machine, f, self.save_dir))
                    except (Exception, JavaException) as e:
                        res = {"error": str(e)}
                    x["res"] = res
                    x["status"] = verdict(res)
                    self.log("%s slot %s: %s | %s" % (x["feeder"].getName(), res.get("slot"), x["status"], res))
                    oppnp.on_ui(self.model.fireTableDataChanged)
                n_ok = len([x for x in rows if x.get("status") == "OK"])
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
