# Scripts > Lumen > Job Readiness   (study §5: view limited to the current job)
#
# Only the parts and feeders the open job uses: quantity, remaining, feeder(s), part
# height, blocking issues.  Optional: show the job's Photon feeders on their LEDs
# (green = needed and ready, red = needed but has an issue, off = not used by the job).
# Camera to the selected line: the top camera goes over the part's feeder or its next placement on
# the board (repeated presses step through them).  Camera moves only (safe Z).
# Read-only towards the job and the machine configuration.
from __future__ import absolute_import, division, print_function

import os
import sys

_LIB = os.path.join(str(scripting.getScriptsDirectory().getParent()), "lumen", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
import lumen.photon
import lumen.oppnp
import lumen.helptext
import lumen.uihelp
import lumen.jobinfo
import lumen.feedercheck
import lumen.lastjob
import lumen.gotofix
reload(lumen.photon)
reload(lumen.oppnp)
reload(lumen.helptext)
reload(lumen.uihelp)
reload(lumen.jobinfo)
reload(lumen.feedercheck)
reload(lumen.lastjob)
reload(lumen.gotofix)
from lumen import feedercheck, gotofix, jobinfo, lastjob, oppnp, photon
from lumen.oppnp import JavaException

from java.awt import BorderLayout, Color, Dimension, FlowLayout
from java.awt.event import MouseAdapter, WindowAdapter
from java.lang import String
from javax.swing import (BorderFactory, JButton, JFrame, JLabel, JOptionPane, JPanel, JScrollPane,
                         JTable, WindowConstants)
from javax.swing.table import AbstractTableModel, DefaultTableCellRenderer

COLS = ["Part", "Package", "Height mm", "Total", "Remaining", "Feeder(s)", "Issues"]


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
        return [x["part_id"], x["package"], "%.2f" % x["height"] if x["height"] > 0 else "?",
                str(x["total"]), str(x["remaining"]),
                ", ".join(jobinfo.feeder_text(f) for f in x["feeders"]) or "-",
                "; ".join(x["issues"]) or "; ".join(["OK"] + x.get("notes", []))][c]


class IssueRenderer(DefaultTableCellRenderer):
    def __init__(self, model):
        DefaultTableCellRenderer.__init__(self)
        self.model = model

    def getTableCellRendererComponent(self, table, value, sel, focus, row, col):
        c = DefaultTableCellRenderer.getTableCellRendererComponent(self, table, value, sel, focus, row, col)
        if not sel:
            c.setBackground(Color(255, 225, 225) if self.model.rows[row]["issues"] else Color.WHITE)
        return c


class Readiness(object):
    def __init__(self):
        self.model = Model()
        self.log = oppnp.FileLog(scripting, "job-readiness")
        f = self.frame = JFrame("Job readiness")
        f.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8))
        self.summary = JLabel(" ")
        root.add(self.summary, BorderLayout.NORTH)
        table = self.table = JTable(self.model)
        rd = self

        class _Dbl(MouseAdapter):
            def mouseClicked(self, e):
                if e.getClickCount() == 2:
                    rd.camera_feeder()
        table.addMouseListener(_Dbl())
        self.step = {}                               # (part_id, "feeder"|"placement") -> next index
        r = IssueRenderer(self.model)
        for i in range(len(COLS)):
            table.getColumnModel().getColumn(i).setCellRenderer(r)
        for i, w in enumerate((160, 110, 70, 50, 70, 300, 320)):
            table.getColumnModel().getColumn(i).setPreferredWidth(w)
        sp = JScrollPane(table)
        sp.setPreferredSize(Dimension(1080, 380))
        root.add(sp, BorderLayout.CENTER)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        b.add(JButton("Go to problem", actionPerformed=lambda e: self.go_problem()))
        b.add(JButton("Next problem >>", actionPerformed=lambda e: self.next_problem()))
        b.add(JButton("Camera to feeder", actionPerformed=lambda e: self.camera_feeder()))
        b.add(JButton("Camera to next placement", actionPerformed=lambda e: self.camera_placement()))
        b.add(JButton("Refresh", actionPerformed=lambda e: self.refresh()))
        b.add(JButton("Show on feeder LEDs", actionPerformed=lambda e: self.leds(True)))
        b.add(JButton("Feeder LEDs off", actionPerformed=lambda e: self.leds(False)))
        b.add(JButton("Close", actionPerformed=lambda e: f.dispose()))
        self.info = JLabel(" ")
        south = JPanel(BorderLayout())
        south.add(self.info, BorderLayout.CENTER)
        south.add(b, BorderLayout.EAST)
        root.add(south, BorderLayout.SOUTH)
        f.setContentPane(lumen.uihelp.wrap(root, "job_readiness"))
        f.pack()
        f.setLocationRelativeTo(gui)
        self.at = None                               # (part_id, fix index) of the last problem shown
        self.refresh()

        class _Back(WindowAdapter):
            def windowActivated(self, e):            # back from fixing something in OpenPnP: show the new state
                rd.refresh()
        f.addWindowListener(_Back())
        f.setVisible(True)

    def refresh(self):
        job = gui.getJobTab().getJob()
        rows = jobinfo.readiness(job, machine) if job else []
        i = self.table.getSelectedRow()
        keep = self.model.rows[self.table.convertRowIndexToModel(i)]["part_id"] if i >= 0 else None
        self.model.rows = rows
        self.model.fireTableDataChanged()
        for k, x in enumerate(rows):
            if x["part_id"] == keep:
                self.select_row(k)
        blocking = len([x for x in rows if x["issues"]])
        name = job.getFile().getName() if job and job.getFile() else "(unsaved job)"
        zero = lastjob.unplaced_boards(job) if job else []
        self.summary.setText("<html><b>%s</b>: %d part type(s), %d placement(s), %d remaining &nbsp; %s%s</html>" % (
            name, len(rows), sum(x["total"] for x in rows), sum(x["remaining"] for x in rows),
            "<font color='red'>%d part(s) with issues</font>" % blocking if blocking else
            "<font color='green'>no blocking issue found</font>",
            "<br><font color='red'>Board %s at X 0 / Y 0: position not set (board added again?) - open the saved job "
            "(File &gt; Open Recent) or set the board location</font>" % ", ".join(zero) if zero else ""))

    # -- go to where a problem is fixed (lumen.gotofix) ---------------------------------------------
    def select_row(self, i):
        v = self.table.convertRowIndexToView(i)
        if v >= 0:
            self.table.setRowSelectionInterval(v, v)
            self.table.scrollRectToVisible(self.table.getCellRect(v, 0, True))

    def go_fix(self, x, j):
        f = x["fixes"][j]
        try:
            if f["kind"] == "assign":
                text = gotofix.open_assign(scripting, f["target"])
            else:
                text = gotofix.show(gui, f)
        except (Exception, JavaException) as e:
            text = "could not open it: %s" % e
        if len(x["fixes"]) > 1:
            text += " (%d/%d for %s)" % (j + 1, len(x["fixes"]), x["part_id"])
        self.at = (x["part_id"], j)
        self.info.setText(text)
        self.log(text)

    def go_problem(self):
        x = self.selected()
        if x is None:
            return
        fx = x.get("fixes") or []
        if not fx:
            JOptionPane.showMessageDialog(self.frame, "%s: %s" % (x["part_id"], "; ".join(x["issues"]) if x["issues"] else
                                          "no problem.") + ("" if not x["issues"] else
                                          "\n(no OpenPnP tab to open for this one: fix it in the job / board)"))
            return
        j = 0
        if len(fx) > 1:
            texts = [f["text"] for f in fx]
            c = JOptionPane.showInputDialog(self.frame, "%s has %d problems - which one?" % (x["part_id"], len(fx)),
                                            "Go to problem", JOptionPane.QUESTION_MESSAGE, None, texts, texts[0])
            if c is None:
                return
            j = texts.index(c)
        self.go_fix(x, j)

    def next_problem(self):
        rows = self.model.rows
        at = None
        if self.at is not None:
            for k, x in enumerate(rows):
                if x["part_id"] == self.at[0]:
                    at = (k, self.at[1])
        if at is None and self.table.getSelectedRow() >= 0:
            at = (self.table.convertRowIndexToModel(self.table.getSelectedRow()), -1)
        p = gotofix.next_problem(rows, at)
        if p is None:
            self.info.setText("No problem left that an OpenPnP tab or the Feeders window fixes.")
            return
        self.select_row(p[0])
        self.go_fix(rows[p[0]], p[1])

    # -- camera to the selected line -------------------------------------------------------------
    def selected(self):
        i = self.table.getSelectedRow()
        if i < 0:
            JOptionPane.showMessageDialog(self.frame, "Select a line (part) first.")
            return None
        return self.model.rows[self.table.convertRowIndexToModel(i)]

    def next_of(self, x, kind, n):
        k = (x["part_id"], kind)
        i = self.step.get(k, 0) % n
        self.step[k] = i + 1
        return i

    def can_move(self):
        if not oppnp.confirm_ready(machine, gui, self.frame, "Cannot move the camera"):
            return False
        if not machine.isHomed():
            JOptionPane.showMessageDialog(self.frame, "Cannot move the camera: the machine is not homed.\n"
                                          "Home it first (nozzles up, visual home free of the disc).")
            return False
        return True

    def move_camera(self, what, target):
        """target() runs in a machine task, moves the top camera and returns the text for the status line."""
        self.info.setText("moving the camera to %s ..." % what)

        def work():
            try:
                text = oppnp.run_machine_task(machine, target)
            except (Exception, JavaException) as e:
                text = "camera not moved (%s): %s" % (what, e)
            self.log(text)
            oppnp.on_ui(lambda: self.info.setText(text))
        oppnp.in_background(work)

    def camera_feeder(self):
        x = self.selected()
        if x is None:
            return
        fs = jobinfo.feeders_to_look_at(x)
        if not fs:
            JOptionPane.showMessageDialog(self.frame, "%s: no feeder has this part." % x["part_id"])
            return
        if not self.can_move():
            return
        i = self.next_of(x, "feeder", len(fs))
        f = fs[i]

        def target():
            p = feedercheck.go_to(machine, f)
            return "camera at the pick location of %s (%s, feeder %d/%d) X %.3f Y %.3f" % (
                f.getName(), x["part_id"], i + 1, len(fs), p.getX(), p.getY())
        self.move_camera("feeder %s" % f.getName(), target)

    def camera_placement(self):
        from org.openpnp.model import LengthUnit
        from org.openpnp.util import MovableUtils, Utils2D
        x = self.selected()
        if x is None:
            return
        job = gui.getJobTab().getJob()
        pls = jobinfo.part_placements(job, x["part_id"]) if job else []
        if not pls:
            JOptionPane.showMessageDialog(self.frame, "%s: no placement in the open job." % x["part_id"])
            return
        if not self.can_move():
            return
        i = self.next_of(x, "placement", len(pls))
        bl, pl, placed = pls[i]

        def target():
            loc = Utils2D.calculateBoardPlacementLocation(bl, pl).convertToUnits(LengthUnit.Millimeters)
            MovableUtils.moveToLocationAtSafeZ(machine.getDefaultHead().getDefaultCamera(), loc)
            return "camera at %s %s (%s, placement %d/%d%s) X %.3f Y %.3f" % (
                bl.getBoard().getName() if bl.getBoard() is not None else "board", pl.getId(), x["part_id"],
                i + 1, len(pls), ", placed" if placed else "", loc.getX(), loc.getY())
        self.move_camera("placement %s" % pl.getId(), target)

    def leds(self, show):
        if not oppnp.confirm_ready(machine, gui, self.frame, "Cannot talk to the feeders"):
            return
        rows = self.model.rows
        wanted = {}                                  # slot -> (r, g, b)
        for x in rows:
            for f in x["enabled_feeders"]:
                if hasattr(f, "getSlotAddress") and f.getSlotAddress() is not None:
                    wanted[int(f.getSlotAddress())] = (1, 0, 0) if x["issues"] else (0, 1, 0)
        slots = sorted(oppnp.photon_feeders(machine))

        def work():
            bus = photon.Bus(oppnp.ActuatorTransport(machine))
            done = []

            def task():
                for a in slots:
                    fd = photon.Feeder(bus, a)
                    r = fd.app(photon.GET_FEEDER_ID, retries=1)
                    if not r or r[0] != 0 or len(r) < 13 or not fd.initialize(r[1:13]):
                        done.append((a, "no answer"))
                        continue
                    rgb = wanted.get(a, (0, 0, 0)) if show else (0, 0, 0)
                    done.append((a, "set" if fd.set_led(*rgb) else "refused"))
            try:
                oppnp.run_machine_task(machine, task)
                self.log("LEDs %s: %s" % ("job view" if show else "off", done))
            except (Exception, JavaException) as e:
                self.log("LEDs failed: %s" % e)
        oppnp.in_background(work)


Readiness()
