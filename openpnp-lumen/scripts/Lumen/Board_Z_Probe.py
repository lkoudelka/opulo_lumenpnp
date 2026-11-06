# Scripts > Lumen > Board Z Probe
#
# Measures the board surface Z on the board fiducials of the open job by vacuum contact: the
# nozzle (vacuum on) goes down in 0.05 mm steps at 5 % speed and stops at the first drop of the
# vacuum level (tip covered).  Safety: free-air level read at safe Z; abort if already covered at
# the start height; never more than 2 mm below the start.  Start height: board Z + 1.5 mm, or the
# setting "probe_start_z" (default 6.0) while the board Z is still 0.  Shows Z per fiducial, mean
# and tilt; "Apply" sets the board location Z to the mean (save the job afterwards).
from __future__ import absolute_import, division, print_function

import os
import sys

_LIB = os.path.join(str(scripting.getScriptsDirectory().getParent()), "lumen", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
import lumen.oppnp
import lumen.zprobe
reload(lumen.oppnp)
reload(lumen.zprobe)
from lumen import oppnp, zprobe
from lumen.oppnp import JavaException

from java.awt import BorderLayout, Dimension, FlowLayout
from java.lang import String
from javax.swing import (BorderFactory, JButton, JComboBox, JFrame, JLabel, JOptionPane, JPanel, JScrollPane, JTable,
                         WindowConstants)
from javax.swing.table import AbstractTableModel
from org.openpnp.model import LengthUnit, Location, Placement
from org.openpnp.util import Utils2D

COLS = ["Board", "Fiducial", "X", "Y", "Surface Z", "Result"]
MM = LengthUnit.Millimeters


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
        return [x["board"], x["fid"], "%.3f" % x["x"], "%.3f" % x["y"],
                "-" if x.get("z") is None else "%.3f" % x["z"], x.get("status", "")][c]


def board_fiducials(job):
    """[(boardLocation, placement id, machine location)] of the job's top-side fiducials."""
    out = []
    for bl in job.getBoardLocations():
        if not bl.isEnabled():
            continue
        for pl in bl.getPlacementsHolder().getPlacements():
            if pl.getType() == Placement.Type.Fiducial and pl.isEnabled():
                loc = Utils2D.calculateBoardPlacementLocation(bl, pl.getLocation()).convertToUnits(MM)
                out.append((bl, str(pl.getId()), loc))
    return out


class BoardZ(object):
    def __init__(self):
        self.settings = oppnp.Settings(scripting)
        self.log = oppnp.FileLog(scripting, "board-z-probe")
        self.model = Model()
        self.busy = False
        self.result = {}
        job = gui.getJobTab().getJob()
        fids = board_fiducials(job) if job is not None else []
        self.model.rows = [{"bl": bl, "board": bl.getPlacementsHolder().getName(), "fid": pid, "x": loc.getX(), "y": loc.getY()}
                           for bl, pid, loc in fids]
        f = self.frame = JFrame("Board Z probe (vacuum contact)")
        f.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8))
        top = JPanel(FlowLayout(FlowLayout.LEFT))
        top.add(JLabel("Nozzle:"))
        self.nozzles = list(machine.getDefaultHead().getNozzles())
        self.nozzle_box = JComboBox([n.getName() for n in self.nozzles])
        top.add(self.nozzle_box)
        self.info = JLabel(" %d fiducial(s) in the job. The nozzle touches each fiducial gently (vacuum contact)." % len(fids))
        top.add(self.info)
        root.add(top, BorderLayout.NORTH)
        t = JTable(self.model)
        for i, w in enumerate((160, 90, 80, 80, 80, 520)):
            t.getColumnModel().getColumn(i).setPreferredWidth(w)
        sp = JScrollPane(t)
        sp.setPreferredSize(Dimension(1010, 220))
        root.add(sp, BorderLayout.CENTER)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        self.run_btn = JButton("Probe fiducials", actionPerformed=lambda e: self.run())
        b.add(self.run_btn)
        b.add(JButton("Apply mean Z to board(s)", actionPerformed=lambda e: self.apply()))
        b.add(JButton("Close", actionPerformed=lambda e: f.dispose()))
        root.add(b, BorderLayout.SOUTH)
        f.setContentPane(root)
        f.pack()
        f.setLocationRelativeTo(gui)
        f.setVisible(True)

    def start_z(self, bl):
        z = bl.getLocation().convertToUnits(MM).getZ()
        return z + 1.5 if abs(z) > 0.01 else float(self.settings.get("probe_start_z", 6.0))

    def run(self):
        if not self.model.rows:
            JOptionPane.showMessageDialog(self.frame, "The job has no enabled board fiducials.")
            return
        if not oppnp.confirm_ready(machine, gui, self.frame, "Cannot probe"):
            return
        nozzle = self.nozzles[self.nozzle_box.getSelectedIndex()]
        self.busy = True
        self.run_btn.setEnabled(False)

        def work():
            try:
                for x in self.model.rows:
                    x["z"], x["status"] = None, "probing..."
                    oppnp.on_ui(self.model.fireTableDataChanged)
                    s = self.start_z(x["bl"])
                    try:
                        r = oppnp.run_machine_task(machine, lambda: zprobe.probe(nozzle, x["x"], x["y"], s, s - 2.0))
                        x["z"] = r["z"]
                        x["status"] = "contact (free air %.0f, level %.0f)" % (r["free_air"], r["readings"][-1][1])
                    except (Exception, JavaException) as e:
                        x["status"] = "STOPPED: %s" % e
                    self.log("%s %s at %.3f/%.3f start %.2f: %s %s" % (x["board"], x["fid"], x["x"], x["y"], s, x.get("z"), x["status"]))
                    oppnp.on_ui(self.model.fireTableDataChanged)
                self.summarise()
            finally:
                self.busy = False
                oppnp.on_ui(lambda: self.run_btn.setEnabled(True))
        oppnp.in_background(work)

    def summarise(self):
        self.result = {}
        by = {}
        for x in self.model.rows:
            if x.get("z") is not None:
                by.setdefault(x["board"], (x["bl"], []))[1].append((x["x"], x["y"], x["z"]))
        parts = []
        for name, (bl, pts) in by.items():
            mz, spread, sx, sy = zprobe.plane_tilt(pts)
            self.result[name] = (bl, mz, spread)
            parts.append("%s: mean Z %.3f, spread %.3f mm%s%s" % (
                name, mz, spread, "" if sx is None else " (slope %+.2f / %+.2f mm per 100 mm)" % (sx, sy),
                "  TILTED: check the board support" if spread > 0.2 else ""))
            self.log("result " + parts[-1])
        oppnp.on_ui(lambda: self.info.setText(" " + " | ".join(parts) if parts else " no fiducial measured"))

    def apply(self):
        if not self.result:
            JOptionPane.showMessageDialog(self.frame, "Probe first.")
            return
        txt = "\n".join("%s: board Z %.3f -> %.3f" % (n, bl.getLocation().convertToUnits(MM).getZ(), mz)
                        for n, (bl, mz, _) in self.result.items())
        if JOptionPane.showConfirmDialog(self.frame, "Set the board Z?\n\n" + txt + "\n\nSave the job afterwards.",
                                         "Apply board Z", JOptionPane.OK_CANCEL_OPTION) != JOptionPane.OK_OPTION:
            return
        for n, (bl, mz, _) in self.result.items():
            loc = bl.getLocation().convertToUnits(MM)
            bl.setLocation(Location(MM, loc.getX(), loc.getY(), round(mz, 3), loc.getRotation()))
            self.log("applied %s: board Z %.3f" % (n, mz))
        self.info.setText(" board Z applied - save the job (File > Save Job)")


BoardZ()
