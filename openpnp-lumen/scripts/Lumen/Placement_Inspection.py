# Scripts > Lumen > Placement Inspection   (top camera, already assembled parts)
#
# Tick placements of the open job and press Inspect: the top camera visits each placement (camera
# only, at safe Z; view plane = board Z + part height) and checks the part:
# - size method: the body (package footprint body size, else pads, else KiCad name) near the
#   location -> found / offset / rotation;
# - golden sample: once a good placement of a package is marked "golden", later inspections compare
#   with it (rotated to the placement) -> match score, offset, and "matches better turned 180 deg"
#   (polarity).
# Verdict OK / CHECK / FAIL is an aid: every image is saved (~/.openpnp2/lumen/inspection/<job>-<time>/, with
# <ref>.json: what was used and found), Export CSV writes the report.  Columns sort by clicking the header.
# Show image: << Previous / Next >> through the results; Draw where the part is when the detection was wrong
# (saved for learning in inspection/learning/, optionally one more golden sample); Set as OK adds golden samples.
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
import lumen.inspectview
reload(lumen.oppnp)
reload(lumen.helptext)
reload(lumen.uihelp)
reload(lumen.jobinfo)
reload(lumen.tapevision)
reload(lumen.inspect)
reload(lumen.zoomview)
reload(lumen.inspectview)
from lumen import inspect as ins
from lumen import inspectview, jobinfo, oppnp, zoomview
from lumen.oppnp import JavaException

from java.awt import BorderLayout, Dimension, FlowLayout
from java.awt.event import MouseAdapter
from java.io import File
from java.lang import Boolean, Double, String
from javax.imageio import ImageIO
from javax.swing import (BorderFactory, JButton, JCheckBox, JFrame, JLabel, JOptionPane, JPanel, JScrollPane, JTable,
                         WindowConstants)
from javax.swing.table import AbstractTableModel

NOT_OK = ["not assembled (part missing)", "bad rotation", "shifted / offset", "wrong part", "other"]
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
        ins.load_limits(self.root)                  # the operator's OK / CHECK limits (Limits...)
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
        b.add(JButton("Set as NOT OK...", actionPerformed=lambda e: self.set_not_ok()))
        b.add(JButton("Limits...", actionPerformed=lambda e: self.limits()))
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

    def limits(self):
        """Offset / rotation limits between OK and CHECK: saved (<lumen>/inspection/limits.json), used by the next
        inspections and applied now to the results in the table (decisions by hand kept)."""
        old = dict((k[0], ins.LIMITS[k[0]]) for k in ins.USER_LIMITS)
        v = inspectview.ask_limits(self.frame)
        if v is None:
            return
        try:
            ins.save_limits(self.root, v)
        except (Exception, JavaException) as e:
            JOptionPane.showMessageDialog(self.frame, "Limits not saved: %s" % e)
            return
        changed = ["%s %g -> %g" % (k, old[k], v[k]) for k in sorted(v) if abs(v[k] - old[k]) > 1e-9]
        moves, kept = {}, 0
        for x in self.all_rows:
            r = x.get("res")
            if not r:
                continue
            d = ins.reverdict(r)
            if d is None:
                kept += 1 if "(set by hand" in (r.get("verdict") or "") else 0
                continue
            a, b = d[0].split(":")[0].split(" ")[0], d[1].split(":")[0].split(" ")[0]
            if a != b:
                moves["%s -> %s" % (a, b)] = moves.get("%s -> %s" % (a, b), 0) + 1
        text = "limits %s; results now: %s%s" % (", ".join(changed) or "unchanged",
                                                  ", ".join("%d %s" % (n, m) for m, n in sorted(moves.items())) or "no verdict changed",
                                                  "; %d Set as OK / NOT OK kept" % kept if kept else "")
        self.log(text)
        self.changed()
        self.info.setText(text)

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
        """The picture with the result drawn in, zoomable, << Previous / Next >> through the inspected rows; there also
        Camera to part, Set as OK / NOT OK and Draw where the part is (lumen.inspectview)."""
        x = self.selected_row()
        res = (x or {}).get("res") or {}
        if not res.get("_image") and not res.get("image"):
            JOptionPane.showMessageDialog(self.frame, "Select an inspected row.")
            return
        return inspectview.Viewer(self, x)

    def run_name(self, x):
        """The inspection run the row's picture belongs to (its directory name)."""
        p = (x.get("res") or {}).get("image")
        return os.path.basename(os.path.dirname(p)) if p else "%s-%s" % (self.job_name, time.strftime("%Y%m%d"))

    def uses_golden(self, x):
        return ins.load_golden(self.root, x["package"]) is not None or bool((x.get("res") or {}).get("golden"))

    def mark_detection(self, x, rect, parent=None):
        """The operator drew where the part really is (image px x0, y0, x1, y1): the verdict from that position, the
        case saved for learning, optionally one more golden sample centred on it.  True when applied."""
        res = x["res"]
        dx, dy, verdict, truth = ins.hand_position(res, *rect)
        ans = inspectview.ask_mark(parent or self.frame, x, verdict, self.uses_golden(x) or not res.get("expect_size"))
        if ans is None:
            return False
        learn, golden = ans
        was = res.setdefault("detected_verdict", res.get("verdict", ""))    # what the detection said, kept
        res.update(hand_box=list(rect), hand_dx=dx, hand_dy=dy, manual_ok=truth == "ok",
                   verdict="%s (was %s)" % (verdict, was))
        notes = []
        if learn:
            d = ins.save_learning(self.root, self.run_name(x), x["ref"], res, x["package"], x["part"], truth)
            notes.append("saved for learning: %s" % d)
        if golden:
            size = res.get("expect_size") or [abs(rect[2] - rect[0]) * res["upp"], abs(rect[3] - rect[1]) * res["upp"]]
            p = ins.add_golden_sample(self.root, x["package"], res["_image"], res["upp"], res.get("axis_rot") or 0.0,
                                      size[0], size[1], "%s %s (drawn by hand)" % (self.run_name(x), x["ref"]),
                                      centre_px=((rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0))
            notes.append("golden sample added: %s" % p)
        try:
            ins.save_annotated(res, self.title(x))
        except (Exception, JavaException) as e:
            notes.append("image not updated: %s" % e)
        self.log("%s %s %s: detection corrected by hand: %s (was %s)%s" % (
            x["board"], x["ref"], x["part"], verdict, was, "".join("; " + n for n in notes)))
        self.changed()
        self.info.setText("%s: %s" % (x["ref"], verdict))
        return True

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
        from javax.swing import BoxLayout
        box = JPanel()
        box.setLayout(BoxLayout(box, BoxLayout.Y_AXIS))
        box.add(JLabel("<html>Set as OK (you checked them):<br>%s</html>" % "<br>".join(
            "%s %s: %s" % (x["ref"], x["part"], x["res"]["verdict"].replace("<", "&lt;")) for x in rows[:12])))
        learnable = [x for x in rows if x["res"].get("_image") is not None and self.uses_golden(x)]
        learn = JCheckBox("learn: add them as golden samples of their package (%d placement(s) checked with golden "
                          "samples)" % len(learnable), bool(learnable))
        learn.setEnabled(bool(learnable))
        box.add(learn)
        if JOptionPane.showConfirmDialog(parent or self.frame, box, "Set as OK", JOptionPane.OK_CANCEL_OPTION) \
                != JOptionPane.OK_OPTION:
            return
        for x in rows:
            was = x["res"]["verdict"]
            x["res"]["verdict"] = "OK (set by hand; was %s)" % was
            x["res"]["manual_ok"] = True
            if learn.isSelected() and x in learnable:
                r = x["res"]
                size = r.get("expect_size") or [2.0, 2.0]
                try:
                    p = ins.add_golden_sample(self.root, x["package"], r["_image"], r["upp"], r.get("axis_rot") or 0.0,
                                              size[0], size[1], "%s %s (set as OK)" % (self.run_name(x), x["ref"]))
                    self.log("%s: golden sample added for %s: %s" % (x["ref"], x["package"], p))
                except (Exception, JavaException) as e:
                    self.log("%s: golden sample not added: %s" % (x["ref"], e))
            try:
                ins.save_annotated(x["res"], self.title(x))
            except (Exception, JavaException) as e:
                self.log("%s: image not updated: %s" % (x["ref"], e))
            self.log("%s %s %s: set as OK by hand (was %s)" % (x["board"], x["ref"], x["part"], was))
        self.changed()
        self.info.setText("%d placement(s) set as OK by hand" % len(rows))

    def set_not_ok(self, rows=None, parent=None):
        """Your verdict: why the placement is not OK.  'not assembled' can also be marked NOT placed in the job, so
        the next job run places it again (the job file keeps it only when you save the job)."""
        from javax.swing import BoxLayout, ButtonGroup, JRadioButton
        rows = rows or self.selected_rows()
        if not rows:
            JOptionPane.showMessageDialog(parent or self.frame, "Select the placement(s) first (click the row).")
            return
        box = JPanel()
        box.setLayout(BoxLayout(box, BoxLayout.Y_AXIS))
        box.add(JLabel("<html>%s: why NOT OK?</html>" % ", ".join("%s (%s)" % (x["ref"], x["part"]) for x in rows[:8])))
        group, radios = ButtonGroup(), []
        for i, reason in enumerate(NOT_OK):
            rb = JRadioButton(reason, i == 0)
            group.add(rb)
            radios.append(rb)
            box.add(rb)
        again = JCheckBox("mark NOT placed in the job: the next job run places it again", True)
        box.add(again)
        box.add(JLabel("<html><i>(for a placed part with bad rotation / shift / wrong part: remove the part from the board "
                       "first, then mark it not placed)</i></html>"))
        for rb in radios:
            rb.addActionListener(lambda e: again.setSelected(radios[0].isSelected()))
        if JOptionPane.showConfirmDialog(parent or self.frame, box, "Set as NOT OK", JOptionPane.OK_CANCEL_OPTION) \
                != JOptionPane.OK_OPTION:
            return
        reason = [rb.getText() for rb in radios if rb.isSelected()][0]
        job = gui.getJobTab().getJob()
        for x in rows:
            res = x.get("res") or {}
            was = res.get("verdict", "not inspected")
            res["verdict"] = "FAIL: %s (set by hand; was %s)" % (reason, was)
            res["manual_ok"] = False
            x["res"] = res
            if res.get("_image") is not None:
                try:
                    ins.save_annotated(res, self.title(x))
                except (Exception, JavaException) as e:
                    self.log("%s: image not updated: %s" % (x["ref"], e))
            if again.isSelected() and job is not None:
                job.storePlacedStatus(x["bl"], x["pl"].getId(), False)
                x["placed"] = False
            self.log("%s %s %s: set as NOT OK by hand: %s%s (was %s)" % (
                x["board"], x["ref"], x["part"], reason, "; marked NOT placed in the job" if again.isSelected() else "", was))
        if again.isSelected():
            try:
                gui.getJobTab().getJobPlacementsPanel().refresh()
                gui.getJobTab().getJobPlacementsPanel().updateActivePlacements()
            except (Exception, JavaException):
                pass
        self.changed()
        self.info.setText("%d placement(s) set as NOT OK (%s)%s" % (len(rows), reason, ": marked not placed, the next job "
                          "run places them again" if again.isSelected() else ""))

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
