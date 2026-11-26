# Scripts > Lumen > Placement Inspection   (top camera, already assembled parts)
#
# Tick placements of the open job and press Inspect: the top camera visits each placement (camera
# only, at safe Z; view plane = board Z + part height) and checks the part:
# - size method: the body (package footprint body size, else pads, else KiCad name) near the
#   location -> found / offset / rotation;
# - golden sample: once a good placement of a package is marked "golden", later inspections compare
#   with it (rotated to the placement) -> match score, offset, and "matches better turned 180 deg"
#   (polarity).
# Verdict OK / CHECK / FAIL is an aid: every image is saved (~/.openpnp2/lumen/inspection/<job>-<time>/),
# Export CSV writes the report.  Columns sort by clicking the header.
from __future__ import absolute_import, division, print_function

import csv
import os
import sys
import time

_LIB = os.path.join(str(scripting.getScriptsDirectory().getParent()), "lumen", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
import lumen.oppnp
import lumen.helptext
import lumen.uihelp
import lumen.jobinfo
import lumen.tapevision
import lumen.inspect
import lumen.zoomview
reload(lumen.oppnp)
reload(lumen.helptext)
reload(lumen.uihelp)
reload(lumen.jobinfo)
reload(lumen.tapevision)
reload(lumen.inspect)
reload(lumen.zoomview)
from lumen import inspect as ins
from lumen import jobinfo, oppnp, zoomview
from lumen.oppnp import JavaException

from java.awt import BorderLayout, Dimension, FlowLayout
from java.awt.event import MouseAdapter
from java.io import File
from java.lang import Boolean, Double, String
from javax.imageio import ImageIO
from javax.swing import (BorderFactory, JButton, JCheckBox, JFrame, JLabel, JOptionPane, JPanel, JScrollPane, JTable,
                         WindowConstants)
from javax.swing.table import AbstractTableModel

COLS = ["Check", "Board", "Ref", "Part", "Package", "Placed", "Result", "Offset mm", "Angle err", "Golden score", "Body size from"]


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
        return Boolean if c in (0, 5) else Double if c in (7, 8, 9) else String

    def isCellEditable(self, r, c):
        return c == 0 and not self.locked

    def getValueAt(self, r, c):
        x = self.rows[r]
        res = x.get("res") or {}
        b = res.get("body") or {}
        g = res.get("golden")
        if c == 0:
            return Boolean(x["sel"])
        if c == 5:
            return Boolean(x["placed"])
        if c == 7:
            return Double(round((b["dx"] ** 2 + b["dy"] ** 2) ** 0.5, 3)) if b.get("found") else None
        if c == 8:
            return Double(round(b["angle_err"], 1)) if b.get("found") else None
        if c == 9:
            return Double(round(g["score"], 2)) if g else None
        return {1: x["board"], 2: x["ref"], 3: x["part"], 4: x["package"],
                6: res.get("verdict", ""), 10: res.get("size_source", "")}[c]

    def setValueAt(self, v, r, c):
        if c == 0:
            self.rows[r]["sel"] = bool(v)
            self.fireTableCellUpdated(r, c)


class Inspection(object):
    def __init__(self):
        self.log = oppnp.FileLog(scripting, "placement-inspection")
        self.root = os.path.join(oppnp.lumen_dir(scripting), "inspection")
        self.model = Model()
        self.busy = False
        self.out_dir = None
        self.all_rows = []
        job = gui.getJobTab().getJob()
        if job is not None:
            for bl, pl, placed in jobinfo.job_placements(job):
                part = pl.getPart()
                pkg = part.getPackage() if part is not None else None
                self.all_rows.append({"bl": bl, "pl": pl, "sel": False, "placed": bool(placed),
                                      "board": bl.getPlacementsHolder().getName(), "ref": str(pl.getId()),
                                      "part": str(part.getId()) if part else "-", "package": str(pkg.getId()) if pkg else "-"})
        self.job_name = os.path.splitext(os.path.basename(str(job.getFile())))[0] if job is not None and job.getFile() else "job"
        f = self.frame = JFrame("Placement inspection (top camera)")
        f.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8))
        top = JPanel(FlowLayout(FlowLayout.LEFT))
        self.only_placed = JCheckBox("only placed", True, actionPerformed=lambda e: self.filter())
        top.add(self.only_placed)
        self.info = JLabel(" ")
        top.add(self.info)
        root.add(top, BorderLayout.NORTH)
        self.table = JTable(self.model)
        self.table.setAutoCreateRowSorter(True)
        for i, w in enumerate((50, 150, 70, 190, 160, 55, 420, 75, 70, 85, 120)):
            self.table.getColumnModel().getColumn(i).setPreferredWidth(w)
        owner = self

        class _Dbl(MouseAdapter):
            def mouseClicked(self, e):
                if e.getClickCount() == 2:
                    owner.show_image()
        self.table.addMouseListener(_Dbl())
        sp = JScrollPane(self.table)
        sp.setPreferredSize(Dimension(1460, 420))
        root.add(sp, BorderLayout.CENTER)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        b.add(JButton("Select all", actionPerformed=lambda e: self.select(lambda x: True)))
        b.add(JButton("Select none", actionPerformed=lambda e: self.select(lambda x: False)))
        b.add(JButton("Select not OK", actionPerformed=lambda e: self.select(
            lambda x: bool(x.get("res")) and not x["res"].get("verdict", "").startswith("OK"))))
        self.run_btn = JButton("Inspect selected", actionPerformed=lambda e: self.run())
        b.add(self.run_btn)
        b.add(JButton("Make golden from selected", actionPerformed=lambda e: self.make_golden()))
        b.add(JButton("Show image", actionPerformed=lambda e: self.show_image()))
        b.add(JButton("Camera to part", actionPerformed=lambda e: self.camera_to_part()))
        b.add(JButton("Set as OK", actionPerformed=lambda e: self.set_ok()))
        b.add(JButton("Export CSV", actionPerformed=lambda e: self.export()))
        b.add(JButton("Close", actionPerformed=lambda e: f.dispose()))
        root.add(b, BorderLayout.SOUTH)
        f.setContentPane(lumen.uihelp.wrap(root, "inspection"))
        self.filter()
        f.pack()
        f.setLocationRelativeTo(gui)
        f.setVisible(True)

    def filter(self):
        self.model.rows = [x for x in self.all_rows if x["placed"] or not self.only_placed.isSelected()]
        self.model.fireTableDataChanged()
        self.info.setText("%d placement(s) shown of %d in the job" % (len(self.model.rows), len(self.all_rows)))

    def select(self, pred):
        for x in self.model.rows:
            x["sel"] = pred(x)
        self.changed()

    def selected_row(self):
        i = self.table.getSelectedRow()
        return self.model.rows[self.table.convertRowIndexToModel(i)] if i >= 0 else None

    def run(self):
        rows = [x for x in self.model.rows if x["sel"]]
        if not rows:
            JOptionPane.showMessageDialog(self.frame, "Tick at least one placement.")
            return
        if not oppnp.confirm_ready(machine, gui, self.frame, "Cannot inspect"):
            return
        self.out_dir = os.path.join(self.root, "%s-%s" % (self.job_name, time.strftime("%Y%m%d-%H%M%S")))
        self.busy = True
        self.model.locked = True
        self.run_btn.setEnabled(False)

        def work():
            try:
                for i, x in enumerate(rows):
                    oppnp.on_ui(lambda i=i: self.info.setText("inspecting %d of %d: %s" % (i + 1, len(rows), x["ref"])))
                    try:
                        res = oppnp.run_machine_task(machine, lambda x=x: ins.inspect_placement(machine, x["bl"], x["pl"], self.out_dir, self.root))
                    except (Exception, JavaException) as e:
                        res = {"error": str(e), "verdict": "ERROR: %s" % e}
                    x["res"] = res
                    self.log("%s %s %s: %s" % (x["board"], x["ref"], x["part"], res.get("verdict")))
                    oppnp.on_ui(self.model.fireTableDataChanged)
                bad = len([x for x in rows if not x["res"].get("verdict", "").startswith("OK")])
                oppnp.on_ui(lambda: self.info.setText("%d inspected, %d not OK. Images: %s" % (len(rows), bad, self.out_dir)))
            finally:
                self.busy = False
                self.model.locked = False
                oppnp.on_ui(lambda: self.run_btn.setEnabled(True))
        oppnp.in_background(work)

    def make_golden(self):
        x = self.selected_row()
        if x is None or not (x.get("res") or {}).get("_image"):
            JOptionPane.showMessageDialog(self.frame, "Select (click) an inspected row whose part is good.")
            return
        res = x["res"]
        size = (res.get("body") or {}).get("size")
        pkg = x["pl"].getPart().getPackage() if x["pl"].getPart() else None
        length, width, _ = ins.body_size(pkg)
        length, width = length or (size or (1.0, 0.5))[0], width or (size or (1.0, 0.5))[1]
        if JOptionPane.showConfirmDialog(self.frame, "Use %s (%s) as the golden sample of package %s?\nLater inspections of this "
                                         "package compare with it." % (x["ref"], x["part"], x["package"]),
                                         "Golden sample", JOptionPane.OK_CANCEL_OPTION) != JOptionPane.OK_OPTION:
            return
        p = ins.save_golden(self.root, x["package"], res["_image"], res["upp"], res["axis_rot"], length, width,
                            "%s %s %s" % (self.job_name, x["board"], x["ref"]))
        self.log("golden for %s from %s: %s" % (x["package"], x["ref"], p))
        self.info.setText("golden sample saved for %s - inspect again to use it" % x["package"])

    def selected_rows(self):
        return [self.model.rows[self.table.convertRowIndexToModel(i)] for i in self.table.getSelectedRows()]

    @staticmethod
    def title(x):
        return "%s  %s" % (x["ref"], x["part"])

    def show_image(self):
        """The saved picture with the result drawn in, zoomable; from there also Camera to part / Set as OK."""
        x = self.selected_row()
        res = (x or {}).get("res") or {}
        if not res.get("_image") and not res.get("image"):
            JOptionPane.showMessageDialog(self.frame, "Select an inspected row.")
            return
        img = ins.annotate(res["_image"], res, self.title(x)) if res.get("_image") is not None else \
            ImageIO.read(File(res["image"]))
        text = ("<b>%s</b> (%s, board %s): <b>%s</b><br>Cyan dashed: where the part should be (body size, placement "
                "rotation), cross = placement location; coloured box: the body found. Saved: %s"
                % (x["ref"], x["part"], x["board"], res.get("verdict", ""), res.get("image", "-")))
        zoomview.image_window("Inspection: %s %s" % (x["ref"], x["part"]), img, text, buttons=[
            ("Camera to part", lambda w: self.camera_to_part(x), "Top camera over this placement (part top in focus)."),
            ("Set as OK", lambda w: self.set_ok([x], w), "Accept this placement as OK (your decision, logged).")],
            parent=self.frame)

    def camera_to_part(self, x=None):
        x = x or self.selected_row()
        if x is None:
            JOptionPane.showMessageDialog(self.frame, "Select a placement.")
            return
        if self.busy or not oppnp.confirm_ready(machine, gui, self.frame, "Cannot move the camera"):
            return
        if not machine.isHomed():
            JOptionPane.showMessageDialog(self.frame, "Cannot move the camera: the machine is not homed.")
            return
        self.info.setText("camera to %s ..." % x["ref"])

        def work():
            try:
                loc, z = oppnp.run_machine_task(machine, lambda: ins.go_to_placement(machine, x["bl"], x["pl"]))
                text = "camera over %s (%s) X %.3f Y %.3f, focus Z %.2f" % (x["ref"], x["part"], loc.getX(), loc.getY(), z)
            except (Exception, JavaException) as e:
                text = "camera not moved to %s: %s" % (x["ref"], e)
            self.log(text)
            oppnp.on_ui(lambda: self.info.setText(text))
        oppnp.in_background(work)

    def set_ok(self, rows=None, parent=None):
        rows = [x for x in (rows or self.selected_rows()) if x.get("res") and not x["res"].get("verdict", "").startswith("OK")]
        if not rows:
            JOptionPane.showMessageDialog(parent or self.frame, "Select inspected placement(s) that are not OK.")
            return
        if JOptionPane.showConfirmDialog(parent or self.frame, "Set as OK (you checked them):\n%s" % "\n".join(
                "%s %s: %s" % (x["ref"], x["part"], x["res"]["verdict"]) for x in rows[:12]), "Set as OK",
                JOptionPane.OK_CANCEL_OPTION) != JOptionPane.OK_OPTION:
            return
        for x in rows:
            was = x["res"]["verdict"]
            x["res"]["verdict"] = "OK (set by hand; was %s)" % was
            x["res"]["manual_ok"] = True
            try:
                ins.save_annotated(x["res"], self.title(x))
            except (Exception, JavaException) as e:
                self.log("%s: image not updated: %s" % (x["ref"], e))
            self.log("%s %s %s: set as OK by hand (was %s)" % (x["board"], x["ref"], x["part"], was))
        self.changed()
        self.info.setText("%d placement(s) set as OK by hand" % len(rows))

    def changed(self):
        """Table data changed, the clicked row(s) stay selected (a data change clears the selection)."""
        keep = [self.table.convertRowIndexToModel(i) for i in self.table.getSelectedRows()]
        self.model.fireTableDataChanged()
        for m in keep:
            if m < len(self.model.rows):
                v = self.table.convertRowIndexToView(m)
                self.table.addRowSelectionInterval(v, v)

    def export(self):
        rows = [x for x in self.all_rows if x.get("res")]
        if not rows:
            JOptionPane.showMessageDialog(self.frame, "Nothing inspected yet.")
            return
        d = self.out_dir or self.root
        if not os.path.isdir(d):
            os.makedirs(d)
        p = os.path.join(d, "inspection.csv")
        f = open(p, "wb")
        try:
            w = csv.writer(f)
            w.writerow(["board", "ref", "part", "package", "placed", "verdict", "dx_mm", "dy_mm", "angle_err",
                        "golden_score", "golden_score_180", "body_size_from", "image"])
            for x in rows:
                r = x["res"]
                b = r.get("body") or {}
                g = r.get("golden") or {}
                w.writerow([x["board"], x["ref"], x["part"], x["package"], x["placed"], r.get("verdict", ""),
                            "%.3f" % b["dx"] if b.get("found") else "", "%.3f" % b["dy"] if b.get("found") else "",
                            "%.1f" % b["angle_err"] if b.get("found") else "",
                            "%.2f" % g["score"] if g else "", "%.2f" % g["score180"] if g else "",
                            r.get("size_source", ""), r.get("image", "")])
        finally:
            f.close()
        self.info.setText("report: %s" % p)
        self.log("exported %s" % p)


Inspection()
