# Scripts > Lumen > Job Readiness   (study §5: view limited to the current job)
#
# Only the parts and feeders the open job uses: quantity, remaining, feeder(s), part
# height, blocking issues.  Optional: show the job's Photon feeders on their LEDs
# (green = needed and ready, red = needed but has an issue, off = not used by the job).
# Read-only towards the job and the machine configuration.
from __future__ import absolute_import, division, print_function

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
                "; ".join(x["issues"]) or "OK"][c]


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
        table = JTable(self.model)
        r = IssueRenderer(self.model)
        for i in range(len(COLS)):
            table.getColumnModel().getColumn(i).setCellRenderer(r)
        for i, w in enumerate((160, 110, 70, 50, 70, 300, 320)):
            table.getColumnModel().getColumn(i).setPreferredWidth(w)
        sp = JScrollPane(table)
        sp.setPreferredSize(Dimension(1080, 380))
        root.add(sp, BorderLayout.CENTER)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        b.add(JButton("Refresh", actionPerformed=lambda e: self.refresh()))
        b.add(JButton("Show on feeder LEDs", actionPerformed=lambda e: self.leds(True)))
        b.add(JButton("Feeder LEDs off", actionPerformed=lambda e: self.leds(False)))
        b.add(JButton("Close", actionPerformed=lambda e: f.dispose()))
        root.add(b, BorderLayout.SOUTH)
        f.setContentPane(root)
        f.pack()
        f.setLocationRelativeTo(gui)
        self.refresh()
        f.setVisible(True)

    def refresh(self):
        job = gui.getJobTab().getJob()
        rows = jobinfo.readiness(job, machine) if job else []
        self.model.rows = rows
        self.model.fireTableDataChanged()
        blocking = len([x for x in rows if x["issues"]])
        name = job.getFile().getName() if job and job.getFile() else "(unsaved job)"
        self.summary.setText("<html><b>%s</b>: %d part type(s), %d placement(s), %d remaining &nbsp; %s</html>" % (
            name, len(rows), sum(x["total"] for x in rows), sum(x["remaining"] for x in rows),
            "<font color='red'>%d part(s) with issues</font>" % blocking if blocking else
            "<font color='green'>no blocking issue found</font>"))

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
