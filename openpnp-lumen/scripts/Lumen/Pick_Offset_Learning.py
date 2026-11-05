# Scripts > Lumen > Pick Offset Learning   (study §3 layer A, §2 orientation hints; lumen profile)
#
# Per feeder: systematic pick error learned from the bottom-vision offsets recorded by the
# lumen-profile hooks (pnp-profile use lumen).  Nothing is changed automatically: select a
# Photon feeder with a suggestion and press Apply (damped, limited step, logged, undoable).
# After a correction only newer samples count; if they get worse the row says "undo".
from __future__ import absolute_import, division, print_function

import os
import sys
import time

_LIB = os.path.join(str(scripting.getScriptsDirectory().getParent()), "lumen", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
import lumen.oppnp
import lumen.learning
reload(lumen.oppnp)
reload(lumen.learning)
from lumen import learning, oppnp
from lumen.oppnp import JavaException

from java.awt import BorderLayout, Dimension, FlowLayout
from java.lang import String
from javax.swing import (BorderFactory, JButton, JFrame, JLabel, JOptionPane, JPanel, JScrollPane,
                         JTable, ListSelectionModel, WindowConstants)
from javax.swing.table import AbstractTableModel
from org.openpnp.model import LengthUnit, Location
import json

COLS = ["Feeder", "Parts", "Samples", "Mean X mm", "Mean Y mm", "Scatter mm", "Rot deg", "Status / hint"]


class Model(AbstractTableModel):
    def __init__(self):
        AbstractTableModel.__init__(self)
        self.rows = []

    def getRowCount(self):
        return len(self.rows)

    def getColumnCount(self):
        return len(COLS)

    def getColumnName(self, c):
        return COLS[c]

    def getColumnClass(self, c):
        return String

    def getValueAt(self, r, c):
        x = self.rows[r]
        status = x["status"] + ("; " + x["orientation_hint"] if x["orientation_hint"] else "")
        return [x["feeder"] or x["feeder_id"], ", ".join(x["parts"]), str(x["n"]), "%+.3f" % x["mean_x"],
                "%+.3f" % x["mean_y"], "%.3f" % x["std"], "%+.1f" % x["mean_rot"], status][c]


class Learning(object):
    def __init__(self):
        d = oppnp.lumen_dir(scripting)
        self.rec_path = os.path.join(d, "pick-offsets.jsonl")
        self.corr_path = os.path.join(d, "offset-corrections.jsonl")
        self.settings = oppnp.Settings(scripting)
        self.log = oppnp.FileLog(scripting, "pick-offset-learning")
        self.model = Model()
        f = self.frame = JFrame("Pick offset learning")
        f.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8))
        self.info = JLabel(" ")
        root.add(self.info, BorderLayout.NORTH)
        self.table = JTable(self.model)
        self.table.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        for i, w in enumerate((200, 130, 60, 80, 80, 80, 60, 420)):
            self.table.getColumnModel().getColumn(i).setPreferredWidth(w)
        sp = JScrollPane(self.table)
        sp.setPreferredSize(Dimension(1110, 300))
        root.add(sp, BorderLayout.CENTER)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        b.add(JButton("Refresh", actionPerformed=lambda e: self.refresh()))
        b.add(JButton("Apply suggestion to selected feeder", actionPerformed=lambda e: self.apply()))
        b.add(JButton("Undo last correction of selected", actionPerformed=lambda e: self.undo()))
        b.add(JButton("Close", actionPerformed=lambda e: f.dispose()))
        root.add(b, BorderLayout.SOUTH)
        f.setContentPane(root)
        f.pack()
        f.setLocationRelativeTo(gui)
        self.refresh()
        f.setVisible(True)

    def refresh(self):
        recs = learning.load_jsonl(self.rec_path)
        self.corrections = learning.load_jsonl(self.corr_path)
        res = learning.analyse(recs, self.corrections, self.settings.get("learning", {}))
        self.model.rows = sorted(res.values(), key=lambda x: (x["suggest"] is None and not x["worse"], x["feeder"] or ""))
        self.model.fireTableDataChanged()
        prof = oppnp.active_profile(machine)
        self.info.setText("<html>%d sample(s) from %d feeder(s); profile: <b>%s</b>%s</html>" % (
            len(recs), len(res), prof, "" if prof == "lumen" else
            " &nbsp;<font color='#b06000'>(no new samples: recording hooks are active in the lumen profile only)</font>"))

    def feeder(self, fid):
        for f in machine.getFeeders():
            if str(f.getId()) == fid:
                return f
        return None

    def selected(self):
        i = self.table.getSelectedRow()
        return self.model.rows[i] if i >= 0 else None

    def apply(self):
        x = self.selected()
        if x is None or x["suggest"] is None:
            JOptionPane.showMessageDialog(self.frame, "Select a feeder that has a suggestion.")
            return
        f = self.feeder(x["feeder_id"])
        if f is None or not hasattr(f, "getOffset") or f.getOffset() is None:
            JOptionPane.showMessageDialog(self.frame, "Only Photon feeders with a pick offset can be corrected here.")
            return
        sx, sy = x["suggest"]
        old = f.getOffset().convertToUnits(LengthUnit.Millimeters)
        if JOptionPane.showConfirmDialog(self.frame, "Move the pick location of %s by %+.3f / %+.3f mm?\n(current offset %s)\n\n"
                                         "Learned from %d picks, mean error %.3f mm. Undo is possible." % (
                                             x["feeder"], sx, sy, old, x["n"], x["mean"]),
                                         "Apply pick offset correction", JOptionPane.OK_CANCEL_OPTION) != JOptionPane.OK_OPTION:
            return
        new = old.add(Location(old.getUnits(), sx, sy, 0, 0))
        f.setOffset(new)
        rec = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "feeder_id": x["feeder_id"], "feeder": x["feeder"],
               "dx": sx, "dy": sy, "old": [old.getX(), old.getY(), old.getZ(), old.getRotation()],
               "new": [new.getX(), new.getY(), new.getZ(), new.getRotation()], "residual_before": x["mean"], "n": x["n"]}
        learning.append_jsonl(self.corr_path, rec)
        self.log("applied %s: offset %s -> %s (mean %.3f mm from %d samples)" % (x["feeder"], old, new, x["mean"], x["n"]))
        self.refresh()

    def undo(self):
        x = self.selected()
        if x is None:
            JOptionPane.showMessageDialog(self.frame, "Select a feeder.")
            return
        mine = [c for c in self.corrections if c["feeder_id"] == x["feeder_id"] and not c.get("undone")]
        if not mine:
            JOptionPane.showMessageDialog(self.frame, "No correction to undo for this feeder.")
            return
        c = mine[-1]
        f = self.feeder(x["feeder_id"])
        if f is None:
            return
        if JOptionPane.showConfirmDialog(self.frame, "Restore the offset of %s to %s?" % (x["feeder"], c["old"]),
                                         "Undo correction", JOptionPane.OK_CANCEL_OPTION) != JOptionPane.OK_OPTION:
            return
        cur = f.getOffset()
        f.setOffset(Location(cur.getUnits(), c["old"][0], c["old"][1], c["old"][2], c["old"][3]))
        learning.append_jsonl(self.corr_path, {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "feeder_id": c["feeder_id"],
                                               "feeder": c["feeder"], "undo_of": c["t"], "restored": c["old"]})
        allc = learning.load_jsonl(self.corr_path)          # mark the undone correction itself
        for k in allc:
            if k["feeder_id"] == c["feeder_id"] and k["t"] == c["t"] and not k.get("undo_of"):
                k["undone"] = True
        tmp = self.corr_path + ".tmp"
        fh = open(tmp, "w")
        for k in allc:
            fh.write(json.dumps(k) + "\n")
        fh.close()
        os.rename(tmp, self.corr_path)
        self.log("undone correction of %s from %s" % (x["feeder"], c["t"]))
        self.refresh()



Learning()
