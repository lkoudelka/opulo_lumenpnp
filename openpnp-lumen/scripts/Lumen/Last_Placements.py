# Scripts > Lumen > Last Placements   (study §6: view last placed components, undo)
#
# Newest placements of the open job first (from the placement journal, see install.sh
# --journal).  "Mark not placed" clears OpenPnP's Placed flag, so the next job run places
# the part again - the same as unticking "Placed" in the job table.  "Go to" moves the top
# camera over the placement.  Without the journal, the job's placed placements are listed
# (without order) so they can still be marked.
from __future__ import absolute_import, division, print_function

import os
import sys

_LIB = os.path.join(str(scripting.getScriptsDirectory().getParent()), "lumen", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
import lumen.oppnp
import lumen.helptext
import lumen.uihelp
import lumen.jobinfo
import lumen.journal
reload(lumen.oppnp)
reload(lumen.helptext)
reload(lumen.uihelp)
reload(lumen.jobinfo)
reload(lumen.journal)
from lumen import jobinfo, journal, oppnp
from lumen.oppnp import JavaException

from java.awt import BorderLayout, Dimension, FlowLayout
from java.lang import String
from javax.swing import (BorderFactory, JButton, JFrame, JLabel, JOptionPane, JPanel, JScrollPane,
                         JTable, ListSelectionModel, WindowConstants)
from javax.swing.table import AbstractTableModel
from org.openpnp.util import MovableUtils, Utils2D
from org.openpnp.util.UiUtils import submitUiMachineTask

COLS = ["Time", "Board", "Placement", "Part", "Nozzle", "Placed now"]


class Model(AbstractTableModel):
    def __init__(self):
        AbstractTableModel.__init__(self)
        self.rows = []      # dicts: t, bl, pl, part, nozzle

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
        job = gui.getJobTab().getJob()
        placed = job.retrievePlacedStatus(x["bl"], x["pl"].getId()) if x["bl"] is not None else False
        return [x["t"], x["board"], x["pl"].getId(), x["part"], x["nozzle"], "yes" if placed else "no"][c]


class LastPlacements(object):
    def __init__(self):
        self.model = Model()
        self.log = oppnp.FileLog(scripting, "last-placements")
        f = self.frame = JFrame("Last placements")
        f.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        f.setAlwaysOnTop(True)
        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8))
        self.info = JLabel(" ")
        root.add(self.info, BorderLayout.NORTH)
        self.table = JTable(self.model)
        self.table.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION)
        sp = JScrollPane(self.table)
        sp.setPreferredSize(Dimension(760, 320))
        root.add(sp, BorderLayout.CENTER)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        b.add(JButton("Refresh", actionPerformed=lambda e: self.refresh()))
        b.add(JButton("Go to (camera)", actionPerformed=lambda e: self.goto()))
        b.add(JButton("Mark selected NOT placed", actionPerformed=lambda e: self.unplace(self.selected())))
        b.add(JButton("Mark LAST NOT placed", actionPerformed=lambda e: self.unplace(self.model.rows[:1])))
        b.add(JButton("Close", actionPerformed=lambda e: f.dispose()))
        root.add(b, BorderLayout.SOUTH)
        f.setContentPane(lumen.uihelp.wrap(root, "last_placements"))
        f.pack()
        f.setLocationRelativeTo(gui)
        self.refresh()
        f.setVisible(True)

    def refresh(self):
        job = gui.getJobTab().getJob()
        rows = []
        if job is not None:
            bls = dict((bl.getUniqueId(), bl) for bl in job.getBoardLocations())
            job_file = str(job.getFile().getAbsolutePath()) if job.getFile() is not None else None
            recs = journal.tail(scripting, job_file)
            for r in recs:
                bl = bls.get(r.get("board"))
                pl = bl.getPlacementsHolder().getPlacements().get(r.get("placement")) if bl is not None else None
                if pl is not None:
                    rows.append({"t": r["t"][11:], "bl": bl, "pl": pl, "board": r.get("board_name") or r.get("board"),
                                 "part": r.get("part"), "nozzle": r.get("nozzle")})
            source = "journal"
            if not recs:
                source = "no journal entries (install.sh --journal) - showing placed placements, unordered"
                for bl, pl, placed in jobinfo.job_placements(job):
                    if placed:
                        rows.append({"t": "-", "bl": bl, "pl": pl, "board": bl.getPlacementsHolder().getName(),
                                     "part": pl.getPart().getId() if pl.getPart() else "", "nozzle": "-"})
            self.info.setText("%d row(s), source: %s" % (len(rows), source))
        else:
            self.info.setText("no job open")
        self.model.rows = rows
        self.model.fireTableDataChanged()

    def selected(self):
        return [self.model.rows[i] for i in self.table.getSelectedRows()]

    def unplace(self, rows):
        if not rows:
            JOptionPane.showMessageDialog(self.frame, "Nothing selected.")
            return
        job = gui.getJobTab().getJob()
        names = ", ".join("%s/%s" % (x["board"], x["pl"].getId()) for x in rows)
        if JOptionPane.showConfirmDialog(self.frame, "Mark as NOT placed (will be placed again on the next run)?\n"
                                         + names, "Mark not placed", JOptionPane.OK_CANCEL_OPTION) != JOptionPane.OK_OPTION:
            return
        for x in rows:
            job.storePlacedStatus(x["bl"], x["pl"].getId(), False)
            self.log("marked NOT placed: board %s placement %s part %s" % (x["board"], x["pl"].getId(), x["part"]))
        try:
            gui.getJobTab().getJobPlacementsPanel().refresh()
            gui.getJobTab().getJobPlacementsPanel().updateActivePlacements()
        except (Exception, JavaException):
            pass
        self.model.fireTableDataChanged()

    def goto(self):
        rows = self.selected()
        if len(rows) != 1:
            JOptionPane.showMessageDialog(self.frame, "Select one placement.")
            return
        if not oppnp.confirm_ready(machine, gui, self.frame, "Cannot move"):
            return
        x = rows[0]

        def move():
            loc = Utils2D.calculateBoardPlacementLocation(x["bl"], x["pl"])
            cam = machine.getDefaultHead().getDefaultCamera()
            MovableUtils.moveToLocationAtSafeZ(cam, loc)
        submitUiMachineTask(move)


LastPlacements()
