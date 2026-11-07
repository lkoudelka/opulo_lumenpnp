# Scripts > Lumen > Orientation Setup   (optional helper, study §2)
#
# For the parts of the open job where orientation matters: where is the pin-1 / polarity
# mark on the part in the FEEDER (left square, seen from above in machine coordinates, as in
# the top camera view) and in the CAD footprint at 0 deg (right square)?  From the two marks
# the rotation in the feeder is calculated and can be applied to the feeder.
# The CAD mark can be detected automatically from ONE of: the KiCad .kicad_pcb, the top copper
# Gerber X2 (with netlist attributes), or a footprint library (.pretty) - "Load CAD data" takes a
# file, a folder or a zip and says what it found.  With only a position file (.pos) pin 1 is found by
# footprint name: footprint libraries, the OpenPnP package footprint, or the footprint table that
# every import and confirmation fills (pin 1 of a footprint is the same on every board, so a board
# file of another revision still teaches it).  "Detection report" lists per part where pin 1
# comes from, or why it could not be detected and what to load.
# Every mark is confirmed by you in the two squares, and the list
# shows what is confirmed and whether the feeder rotation is correct.  Nothing is changed
# without "Apply".
# "Test placement on the PCB" settles a doubt on the real board: one part is placed on its pads
# (board WITHOUT solder paste), photographed with the top camera, you mark pin 1 of the part (and of
# the board) in the photo, then the part is picked up again and recycled into its feeder
# (Photon: SkipNext; strip / tray: feed count - 1; lumen.testplace).
from __future__ import absolute_import, division, print_function

import math
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
import lumen.orientation
import lumen.inspect
import lumen.testplace
reload(lumen.oppnp)
reload(lumen.helptext)
reload(lumen.uihelp)
reload(lumen.jobinfo)
reload(lumen.orientation)
reload(lumen.inspect)
reload(lumen.testplace)
from lumen import jobinfo, oppnp
from lumen import testplace as tp
from lumen import orientation as ori
from lumen.oppnp import JavaException

from java.awt import (BasicStroke, BorderLayout, Color, Dimension, FlowLayout, Font, FontMetrics, Graphics2D,
                      GridLayout, RenderingHints)
from java.awt.event import MouseAdapter, WindowAdapter
from java.lang import String
from javax.swing import (BorderFactory, BoxLayout, ButtonGroup, JButton, JCheckBox, JComboBox, JFileChooser, JFrame, JLabel,
                         JOptionPane, JPanel, JRadioButton, JScrollPane, JTable, JTextArea, ListSelectionModel,
                         WindowConstants)
from javax.swing.filechooser import FileNameExtensionFilter
from javax.swing.table import AbstractTableModel, DefaultTableCellRenderer
from org.openpnp.model import LengthUnit, Placement
from org.openpnp.util import MovableUtils
from org.openpnp.util.UiUtils import submitUiMachineTask

# square geometry: the 4 pin-1 corners (one per rotation 0/90/180/270) as (fx, fy), Y up
POS = {"TL": (-1, 1), "TR": (1, 1), "BL": (-1, -1), "BR": (1, -1)}


class _G(object):
    """Calls Graphics methods through the public Graphics2D interface: Java 17 forbids Jython to
    call them on the JDK-internal implementation class (sun.java2d.SunGraphics2D)."""

    def __init__(self, g):
        self._g = g

    def __getattr__(self, name):
        m = getattr(Graphics2D, name)
        return lambda *a: m(self._g, *a)


class _Click(MouseAdapter):
    def __init__(self, panel):
        MouseAdapter.__init__(self)
        self.panel = panel

    def mouseClicked(self, e):
        self.panel.click(e.getX(), e.getY())


class DotSquare(JPanel):
    """A part body seen from above with 4 clickable pin-1 corners; optional pads drawing."""

    def __init__(self, title, subtitle, on_change):
        JPanel.__init__(self)
        self.title, self.subtitle, self.on_change = title, subtitle, on_change
        self.dot = None
        self.pads = []          # [(number, x, y)] mm, drawn on the body (CAD: footprint; feeder: predicted)
        self.pads_dim = False   # predicted pads (feeder square) are drawn lighter
        self.image = None       # optional camera image (feeder square)
        self.ring = None        # second mark (test placement: pin 1 of the BOARD), drawn as a green ring
        self.pad_mm = None      # pads at true scale: the square shows pad_mm x pad_mm (photo of a placed part)
        self.click_sets = "dot"  # "ring": a click moves the green ring instead of the red dot
        self.hint = ""
        self.setPreferredSize(Dimension(320, 380))
        self.setBackground(Color.WHITE)
        self.addMouseListener(_Click(self))

    def geometry(self):
        w, h = self.getWidth(), self.getHeight()
        s = min(w - 40, h - 130)
        cx, cy = w / 2.0, 60 + s / 2.0
        return cx, cy, s

    def mark_xy(self, d):
        cx, cy, s = self.geometry()
        fx, fy = POS[d]
        r = s * 0.36
        return cx + fx * r, cy - fy * r

    def click(self, x, y):
        best, bd = None, 1e9
        for d in POS:
            mx, my = self.mark_xy(d)
            dist = math.hypot(x - mx, y - my)
            if dist < bd:
                best, bd = d, dist
        if bd < self.geometry()[2] * 0.2:
            if self.click_sets == "ring":
                self.ring = best
            else:
                self.dot = best
            self.repaint()
            if self.on_change:
                self.on_change()

    def paintComponent(self, graphics):
        self.super__paintComponent(graphics)
        g = _G(graphics)
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        cx, cy, s = self.geometry()
        g.setColor(Color.BLACK)
        g.setFont(Font(Font.SANS_SERIF, Font.BOLD, 14))
        g.drawString(self.title, 10, 20)
        g.setFont(Font(Font.SANS_SERIF, Font.PLAIN, 11))
        g.drawString(self.subtitle, 10, 38)
        x0, y0 = int(cx - s / 2), int(cy - s / 2)
        if self.image is not None:
            g.drawImage(self.image, x0, y0, int(s), int(s), None)
        else:
            g.setColor(Color(225, 225, 225))
            g.fillRect(x0, y0, int(s), int(s))
        g.setColor(Color(90, 90, 90))
        g.setStroke(BasicStroke(2))
        g.drawRect(x0, y0, int(s), int(s))
        if self.pads:
            ext = max([max(abs(x), abs(y)) for _, x, y in self.pads] + [0.1])
            k = s / self.pad_mm if self.pad_mm else s * 0.44 / ext
            for n, x, y in self.pads:
                if self.pads_dim:
                    g.setColor(Color(225, 120, 120) if n == "1" else Color(215, 190, 120))
                else:
                    g.setColor(Color(200, 40, 40) if n == "1" else Color(184, 134, 11))
                pw = max(3, int(s * (0.07 if len(self.pads) <= 4 else 0.025)))
                g.fillRect(int(cx + x * k - pw / 2), int(cy - y * k - pw / 2), pw, pw)
        if self.ring in POS:
            mx, my = self.mark_xy(self.ring)
            rr = s * 0.055 * 2.2
            g.setColor(Color(0, 170, 0))
            g.setStroke(BasicStroke(4))
            g.drawOval(int(mx - rr), int(my - rr), int(rr * 2), int(rr * 2))
        for d in POS:
            mx, my = self.mark_xy(d)
            rr = s * 0.055
            if d == self.dot:
                g.setColor(Color(200, 0, 0))
                g.fillOval(int(mx - rr * 1.4), int(my - rr * 1.4), int(rr * 2.8), int(rr * 2.8))
            else:
                g.setColor(Color(150, 150, 150))
                g.setStroke(BasicStroke(1))
                g.drawOval(int(mx - rr), int(my - rr), int(rr * 2), int(rr * 2))
        # axes
        ax, ay = 14, int(cy + s / 2 + 34)
        g.setColor(Color(60, 60, 160))
        g.setStroke(BasicStroke(2))
        g.drawLine(ax, ay, ax + 30, ay)
        g.drawLine(ax, ay, ax, ay - 30)
        g.drawString("X", ax + 34, ay + 4)
        g.drawString("Y", ax - 4, ay - 34)
        g.setColor(Color.BLACK)
        words, line, y = self.hint.split(), "", ay - 8
        fm = g.getFontMetrics()                          # JDK-internal class: call via FontMetrics
        for w in words:                                  # wrap the hint into the panel width
            if line and FontMetrics.stringWidth(fm, line + " " + w) > self.getWidth() - 70:
                g.drawString(line, 60, y)
                line, y = w, y + 14
            else:
                line = (line + " " + w).strip()
        g.drawString(line, 60, y)


class CheckDialog(object):
    """Two squares for one part / feeder pair."""

    def __init__(self, owner, row):
        self.owner, self.row = owner, row
        f = self.frame = JFrame("Orientation check: %s" % row["part_id"])
        f.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8))
        sq = JPanel(GridLayout(1, 2, 12, 0))
        self.left = DotSquare("PIN 1 of the part in the feeder", "seen from above, X right / Y up; light pads = predicted",
                              self.update)
        self.right = DotSquare("PIN 1 in the CAD footprint at 0 deg", row.get("footprint") or "(footprint unknown)",
                               self.update)
        self.right.pads = row.get("pads") or []
        self.right.dot = row.get("cad_dot")
        self.left.dot = row.get("feeder_dot") or row.get("feeder_preset")
        what = ori.pin1_hint(row.get("footprint"), row.get("refs"))
        self.left.hint = ("Preset from the feeder rotation - click the real pin-1 corner. " if not row.get("feeder_dot")
                          and row.get("feeder_preset") else "Click the pin-1 corner. ") + what[0].upper() + what[1:].rstrip(".") + "."
        self.right.hint = ("Detected from %s (red pad = pad 1). Correct it by clicking if needed." % row["cad_source"]) \
            if row.get("cad_source") else "Click where pin 1 is in the footprint (red pad = pad 1 when known)."
        sq.add(self.left)
        sq.add(self.right)
        root.add(sq, BorderLayout.CENTER)
        bottom = JPanel(BorderLayout())
        self.result = JLabel(" ")
        self.result.setFont(Font(Font.SANS_SERIF, Font.BOLD, 14))
        bottom.add(self.result, BorderLayout.NORTH)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        if row.get("feeder") is not None:
            b.add(JButton("Show top camera at the feeder", actionPerformed=lambda e: self.camera()))
        b.add(JButton("Confirm", actionPerformed=lambda e: self.confirm(False)))
        self.apply_btn = JButton("Confirm and apply rotation to feeder", actionPerformed=lambda e: self.confirm(True))
        self.apply_btn.setEnabled(row.get("feeder") is not None)
        b.add(self.apply_btn)
        b.add(JButton("Cancel", actionPerformed=lambda e: f.dispose()))
        bottom.add(b, BorderLayout.SOUTH)
        root.add(bottom, BorderLayout.SOUTH)
        f.setContentPane(lumen.uihelp.wrap(root, "orientation_check"))
        f.pack()
        f.setLocationRelativeTo(owner.frame)
        self.update()
        f.setVisible(True)

    def need(self):
        return ori.rotation_needed(self.left.dot, self.right.dot)

    def update(self):
        n = self.need()
        # feeder square: the CAD pads rotated by the chosen rotation = how the part would sit
        self.left.pads = ori.rotate_points(self.right.pads, n) if n is not None else []
        self.left.pads_dim = True
        self.left.repaint()
        cur = self.row.get("feeder_rot")
        if n is None:
            txt = "Click the pin-1 corner in both squares."
        else:
            txt = "Rotation in feeder: %+.0f deg" % n
            if cur is not None:
                txt += "   (feeder now %+.0f deg: %s)" % (ori.norm(cur), "OK" if abs(ori.norm(cur - n)) < 1 else "CHANGE NEEDED")
        self.result.setText(txt)

    def camera(self):
        feeder = self.row["feeder"]
        if not oppnp.confirm_ready(machine, gui, self.frame, "Cannot move the camera"):
            return

        def task():
            cam = machine.getDefaultHead().getDefaultCamera()
            MovableUtils.moveToLocationAtSafeZ(cam, feeder.getPickLocation())
            img = cam.settleAndCapture()
            w, h = img.getWidth(), img.getHeight()
            s = min(w, h) // 3                       # centre crop around the pick location
            self.left.image = img.getSubimage(w // 2 - s // 2, h // 2 - s // 2, s, s)
            oppnp.on_ui(self.left.repaint)
        submitUiMachineTask(task)

    def confirm(self, apply):
        r = self.row
        if not self.right.dot:
            JOptionPane.showMessageDialog(self.frame, "Set the CAD mark (right square).")
            return
        st = self.owner.store
        src = r.get("cad_source") if self.right.dot == r.get("cad_dot") else "manual"
        st.set_cad(r["part_id"], self.right.dot, src or "manual", True)
        if r.get("footprint"):                         # pin 1 of the footprint: reused on every later board
            st.set_footprint(r["footprint"], {"dot": self.right.dot, "pins": r.get("pins"), "pads": r.get("pads")},
                             (src or "manual").replace("table:", ""), True)
        applied = None
        if r.get("feeder") is not None and self.left.dot:
            need = self.need()
            if apply:
                cur = r.get("feeder_rot")
                if JOptionPane.showConfirmDialog(self.frame, "Set the rotation of %s from %s to %+.0f deg?" % (
                        r["feeder"].getName(), "?" if cur is None else "%+.0f deg" % cur, need),
                        "Apply rotation", JOptionPane.OK_CANCEL_OPTION) != JOptionPane.OK_OPTION:
                    return
                try:
                    applied = oppnp.set_feeder_rotation(r["feeder"], need)
                    self.owner.log("%s / %s: rotation %s -> %+.0f deg" % (r["part_id"], r["feeder"].getName(), cur, applied))
                except (Exception, JavaException) as e:
                    JOptionPane.showMessageDialog(self.frame, "Not applied: %s" % e)
                    return
            st.set_feeder(r["part_id"], str(r["feeder"].getId()), self.left.dot, True, applied)
        st.save()
        self.owner.log("confirmed %s: CAD %s (%s), feeder %s %s" % (r["part_id"], self.right.dot, src,
                                                                   r.get("feeder_name"), self.left.dot))
        self.frame.dispose()
        self.owner.refresh()


class _Closing(WindowAdapter):
    def __init__(self, dlg):
        WindowAdapter.__init__(self)
        self.dlg = dlg

    def windowClosing(self, e):
        self.dlg.close()


class TestDialog(object):
    """Test placement of one part on its pads (board without paste): photo, pin-1 marks, recycle.
    The machine part is lumen.testplace; this is the window around it."""
    AFTER = [("return", "return the part to its feeder (recommended)"), ("discard", "discard it (discard location)"),
             ("leave", "leave it on the board (I remove it by hand)")]

    def __init__(self, owner, row, on_done=None):
        self.owner, self.row, self.on_done = owner, row, on_done
        self.state, self.res, self.busy = None, None, False
        self.bl = self.pl = self.nz = None
        part, feeder = row["part"], row["feeder"]
        job = gui.getJobTab().getJob()
        self.cands = [(bl, pl, placed) for bl, pl, placed in (jobinfo.job_placements(job) if job is not None else [])
                      if pl.getPart() == part]
        self.nozzles = tp.compatible_nozzles(machine, part)
        f = self.frame = JFrame("Test placement: %s" % row["part_id"])
        f.setDefaultCloseOperation(WindowConstants.DO_NOTHING_ON_CLOSE)
        f.addWindowListener(_Closing(self))
        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8))
        form = JPanel(GridLayout(0, 2, 6, 2))
        form.add(JLabel("Placement"))
        labels = ["%s on %s%s" % (pl.getId(), bl.getBoard().getName() if bl.getBoard() is not None else "?",
                                  " (placed already)" if placed else "") for bl, pl, placed in self.cands]
        self.where = JComboBox(labels or ["(the job has no placement of this part)"])
        if self.cands:
            self.where.setSelectedIndex(tp.placement_choices([(l, c[2]) for l, c in zip(labels, self.cands)]))
        form.add(self.where)
        form.add(JLabel("Nozzle"))
        self.nozzle = JComboBox([n.getName() + " (" + n.getNozzleTip().getName() + ")" for n in self.nozzles]
                                or ["none: load a compatible nozzle tip first"])
        form.add(self.nozzle)
        form.add(JLabel("After the decision"))
        self.after = JComboBox([t for _, t in self.AFTER])
        form.add(self.after)
        north = JPanel(BorderLayout(4, 4))
        north.add(form, BorderLayout.NORTH)
        rot = row.get("feeder_rot")
        north.add(JLabel("<html>Feeder <b>%s</b> (%s): recycling = %s.<br>Feeder rotation now %s; CAD pin 1 %s.</html>" % (
            feeder.getName(), feeder.getClass().getSimpleName(), tp.recycle_text(feeder.getClass().getSimpleName()),
            "?" if rot is None else "%+.0f deg" % ori.norm(rot),
            row.get("cad_dot") or "unknown (click the board's pin 1 in the photo)")), BorderLayout.CENTER)
        chk = JPanel(GridLayout(0, 1))
        self.nopaste = JCheckBox("The pads of this placement have NO solder paste (bare or test board)", False)
        self.align = JCheckBox("Bottom vision alignment as in the job", True)
        chk.add(self.nopaste)
        chk.add(self.align)
        north.add(chk, BorderLayout.SOUTH)
        root.add(north, BorderLayout.NORTH)
        centre = JPanel(BorderLayout(8, 0))
        self.square = DotSquare("Placed part, top camera (X right / Y up)",
                                "red dot = pin 1 of the PART, green ring = pin 1 of the BOARD", self.update)
        self.square.setPreferredSize(Dimension(420, 480))
        self.square.hint = "Start the test placement; the photo of the placed part appears here."
        centre.add(self.square, BorderLayout.CENTER)
        side = self.side = JPanel()
        side.setLayout(BoxLayout(side, BoxLayout.Y_AXIS))
        side.setPreferredSize(Dimension(320, 480))
        self.mark_part = JRadioButton("Click marks pin 1 of the PART (red dot)", True, actionPerformed=lambda e: self.click_mode())
        self.mark_board = JRadioButton("Click marks pin 1 of the BOARD (green ring)", False,
                                       actionPerformed=lambda e: self.click_mode())
        grp = ButtonGroup()
        grp.add(self.mark_part)
        grp.add(self.mark_board)
        self.camera_txt = JLabel(" ")
        self.golden = JCheckBox("Save as golden sample of the package", False)
        for c in (self.mark_part, self.mark_board, self.golden, self.camera_txt):
            c.setAlignmentX(0.0)
            side.add(c)
        centre.add(side, BorderLayout.EAST)
        root.add(centre, BorderLayout.CENTER)
        bottom = JPanel(BorderLayout())
        self.result = JLabel(" ")
        self.result.setFont(Font(Font.SANS_SERIF, Font.BOLD, 14))
        bottom.add(self.result, BorderLayout.NORTH)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        self.start_btn = JButton("Start test placement", actionPerformed=lambda e: self.start())
        self.retake_btn = JButton("Retake photo", actionPerformed=lambda e: self.retake())
        self.finish_btn = JButton("Finish: recycle the part, store the result", actionPerformed=lambda e: self.finish())
        for x in (self.start_btn, self.retake_btn, self.finish_btn, JButton("Close", actionPerformed=lambda e: self.close())):
            b.add(x)
        bottom.add(b, BorderLayout.SOUTH)
        root.add(bottom, BorderLayout.SOUTH)
        f.setContentPane(lumen.uihelp.wrap(root, "orientation_test"))
        f.pack()
        f.setLocationRelativeTo(owner.frame)
        self.update()
        f.setVisible(True)

    def selection(self):
        i, j = self.where.getSelectedIndex(), self.nozzle.getSelectedIndex()
        bl, pl, _ = self.cands[i] if 0 <= i < len(self.cands) else (None, None, None)
        return bl, pl, (self.nozzles[j] if 0 <= j < len(self.nozzles) else None)

    def click_mode(self):
        self.square.click_sets = "ring" if self.mark_board.isSelected() else "dot"

    def evaluation(self):
        return tp.evaluate(self.square.dot, self.square.ring, self.row.get("feeder_rot"))

    def update(self):
        on = self.state is not None and self.state.get("on_board")
        self.start_btn.setEnabled(not self.busy and not on)
        self.retake_btn.setEnabled(not self.busy and bool(on))
        self.finish_btn.setEnabled(not self.busy and bool(on))
        ev = self.evaluation()
        self.golden.setEnabled(bool(ev["ok"]) and self.res is not None)
        if self.busy:
            return
        self.result.setText("No test yet." if self.state is None else ev["text"])

    # -- machine work --------------------------------------------------------------------
    def start(self):
        bl, pl, nz = self.selection()
        feeder = self.row["feeder"]
        if pl is None:
            JOptionPane.showMessageDialog(self.frame, "The job has no placement of %s." % self.row["part_id"])
            return False
        probs = tp.problems(machine, bl, pl, feeder, nz)
        if not self.nopaste.isSelected():
            probs.insert(0, "tick 'NO solder paste': the part is put on the bare pads and picked up again")
        if probs:
            JOptionPane.showMessageDialog(self.frame, "Cannot start the test placement:\n- " + "\n- ".join(probs))
            return False
        if not oppnp.confirm_ready(machine, gui, self.frame, "Test placement"):
            return False
        msg = ("The machine will now:\n 1. feed one %s from %s and pick it with %s\n 2. %s\n 3. place it on %s - pads WITHOUT "
               "solder paste\n 4. photograph it with the top camera\nThe part stays on the board until you finish; then it is "
               "picked up and recycled (%s).\n\nStart?" % (
                   self.row["part_id"], feeder.getName(), nz.getName(),
                   "align it with bottom vision" if self.align.isSelected() else "no bottom vision",
                   self.where.getSelectedItem(), tp.recycle_text(feeder.getClass().getSimpleName())))
        if JOptionPane.showConfirmDialog(self.frame, msg, "Test placement", JOptionPane.OK_CANCEL_OPTION) != JOptionPane.OK_OPTION:
            return False
        self.busy = True
        self.result.setText("Running: feed, pick, align, place, photo ...")
        self.update()
        golden_root = os.path.join(oppnp.lumen_dir(scripting), "inspection")
        save = os.path.join(oppnp.lumen_dir(scripting), "testplace")
        align = self.align.isSelected()

        def work():
            err = None
            try:
                st = oppnp.run_machine_task(machine, lambda: tp.run_test(machine, bl, pl, feeder, nz, align, self.owner.log))
                self.state, self.bl, self.pl, self.nz = st, bl, pl, nz
                self.res = oppnp.run_machine_task(machine, lambda: tp.photo(machine, bl, pl, st, golden_root, save))
            except (Exception, JavaException) as e:
                err = e
            oppnp.on_ui(lambda: self.done(err, "Test placement"))
        oppnp.in_background(work)
        return True

    def retake(self):
        if not oppnp.confirm_ready(machine, gui, self.frame, "Retake photo"):
            return
        self.busy = True
        self.update()
        golden_root = os.path.join(oppnp.lumen_dir(scripting), "inspection")
        save = os.path.join(oppnp.lumen_dir(scripting), "testplace")

        def work():
            err = None
            try:
                self.res = oppnp.run_machine_task(machine, lambda: tp.photo(machine, self.bl, self.pl, self.state, golden_root, save))
            except (Exception, JavaException) as e:
                err = e
            oppnp.on_ui(lambda: self.done(err, "Photo"))
        oppnp.in_background(work)

    def done(self, err, what):
        self.busy = False
        if err is not None:
            where = getattr(err, "where", None)
            text = "%s stopped: %s%s" % (what, err, "\nThe part: %s" % where if where else "")
            if self.state is not None and self.state.get("on_board"):
                text += "\nThe part IS ON THE BOARD: Retake photo, or Finish to pick it up and recycle it."
            self.owner.log(text.replace("\n", " | "))
            JOptionPane.showMessageDialog(self.frame, text)
        if self.res is not None:
            self.show_photo()
        self.update()

    def show_photo(self):
        r, st, sq = self.res, self.state, self.square
        sq.image, sq.pad_mm = r["crop"], r["crop_mm"]
        sq.pads = ori.rotate_points(self.row.get("pads") or [], st["placement_rot"])
        sq.pads_dim = True
        if sq.ring is None:
            sq.ring = tp.board_mark(self.row.get("cad_dot"), st["placement_rot"])
        if sq.dot is None and r.get("proposal") is not None and sq.ring:
            sq.dot = ori.rotate_dot(sq.ring, r["proposal"])
        lines = []
        bd = r.get("body")
        if bd is not None:
            lines.append("Body: found %.2f mm from the place location, %+.1f deg" % (
                math.hypot(bd["dx"], bd["dy"]), bd["angle_err"]) if bd.get("found") else "Body: %s" % bd.get("why"))
        else:
            lines.append("Body: size unknown (%s)" % r.get("size_source"))
        lines.append("Camera: " + r["proposal_why"] + ("" if r.get("proposal") is None else " - preset, check it"))
        if tp.off90(st["placement_rot"]) > 1.0:
            lines.append("Placement rotation %.1f deg is not a multiple of 90: the corners are the nearest ones" % st["placement_rot"])
        for w in (r.get("view_warning"), st.get("warning")):
            if w:
                lines.append("<font color='red'>%s</font>" % w)
        lines.append("Photo: lumen/testplace/%s" % os.path.basename(r.get("image") or "-"))
        self.camera_txt.setText("<html><div style='width:230px'>%s</div></html>" % "<br><br>".join(lines))
        self.side.revalidate()
        sq.hint = ("Pads from CAD drawn light (red = pad 1). " if sq.pads else "") + \
                  "Click pin 1 of the part; the green ring is pin 1 of the board%s." % (
                      " from CAD - move it if the board marking says otherwise" if self.row.get("cad_dot") else " - click it")
        sq.repaint()

    def finish(self, no_result=False):
        if self.busy or self.state is None or not self.state.get("on_board"):
            return False
        feeder = self.row["feeder"]
        mode = "return" if no_result else self.AFTER[self.after.getSelectedIndex()][0]
        ev = {"turn": None, "ok": None, "new_rotation": None, "text": "no result"} if no_result else self.evaluation()
        apply_rot = None
        if not no_result:
            if ev["turn"] is None:
                if JOptionPane.showConfirmDialog(self.frame, "Pin 1 is not marked in the photo - finish WITHOUT a result?",
                                                 "Finish", JOptionPane.OK_CANCEL_OPTION) != JOptionPane.OK_OPTION:
                    return False
            elif ev["ok"] is False and ev["new_rotation"] is not None:
                q = JOptionPane.showConfirmDialog(
                    self.frame, "%s\n\nSet the rotation of %s to %+.0f deg AFTER the part is back in the feeder?\n"
                    "Yes = set it    No = only record the result" % (ev["text"], feeder.getName(), ev["new_rotation"]),
                    "Finish", JOptionPane.YES_NO_CANCEL_OPTION)
                if q not in (JOptionPane.YES_OPTION, JOptionPane.NO_OPTION):
                    return False
                if q == JOptionPane.YES_OPTION:
                    apply_rot = ev["new_rotation"]
        self.busy = True
        self.result.setText("Running: pick the part up from the board, %s ..." % dict(self.AFTER)[mode])
        self.update()
        body = self.res.get("body") if self.res else None
        st, nz, pl = self.state, self.nz, self.pl

        def work():
            out, err = None, None
            try:
                out = oppnp.run_machine_task(machine, lambda: tp.recycle(machine, feeder, nz, pl, st, mode, body, self.owner.log))
            except (Exception, JavaException) as e:
                err = e
            oppnp.on_ui(lambda: self.finished(ev, apply_rot, out, err))
        oppnp.in_background(work)
        return True

    def finished(self, ev, apply_rot, out, err):
        self.busy = False
        r = self.row
        msgs = ["Part: %s" % out] if err is None else ["Recycling FAILED: %s%s" % (err, " - " + err.where if getattr(err, "where", None) else "")]
        applied = None
        if apply_rot is not None:
            try:
                applied = oppnp.set_feeder_rotation(r["feeder"], apply_rot)
                msgs.append("Feeder %s: rotation set to %+.0f deg." % (r["feeder"].getName(), applied))
            except (Exception, JavaException) as e:
                msgs.append("Rotation NOT set: %s" % e)
        if self.golden.isSelected() and ev.get("ok") and self.res is not None and self.res.get("length"):
            pkg = r["part"].getPackage()
            p = lumen.inspect.save_golden(os.path.join(oppnp.lumen_dir(scripting), "inspection"), str(pkg.getId()),
                                          self.res["_image"], self.res["upp"], self.res["axis_rot"], self.res["length"],
                                          self.res["width"], "test placement %s" % self.state["ref"])
            msgs.append("Golden sample saved: %s" % p)
        self.store_result(ev, applied, out, err)
        self.owner.log("test placement %s / %s: %s; %s" % (r["part_id"], self.state["ref"], ev["text"], "; ".join(msgs)))
        JOptionPane.showMessageDialog(self.frame, "%s\n\n%s" % (ev["text"], "\n".join(msgs)))
        if self.state.get("on_board"):
            self.update()                                   # still on the board: Finish again (e.g. "leave")
            return
        self.frame.dispose()
        self.owner.refresh()
        if self.on_done:
            self.on_done()

    def store_result(self, ev, applied, out, err):
        r, sq, st = self.row, self.square, self.state
        store = self.owner.store
        rec = {"t": st["t"], "ref": st["ref"], "feeder": r["feeder"].getName(), "nozzle": st["nozzle"],
               "part_mark": sq.dot, "board_mark": sq.ring, "placement_rot": st["placement_rot"], "turn": ev["turn"],
               "result": "correct" if ev["ok"] else "wrong" if ev["ok"] is False else "no result",
               "rotation_applied": applied, "recycle": str(out) if err is None else "FAILED: %s" % err,
               "photo": (self.res or {}).get("image")}
        store.part(r["part_id"]).setdefault("tests", []).append(rec)
        if ev["turn"] is not None:
            cad = tp.cad_from_board(sq.ring, st["placement_rot"])
            src = r.get("cad_source") if cad == r.get("cad_dot") and r.get("cad_source") else "test placement"
            store.set_cad(r["part_id"], cad, src, True)
            if r.get("footprint"):
                store.set_footprint(r["footprint"], {"dot": cad, "pins": r.get("pins"), "pads": r.get("pads")},
                                    src.replace("table:", ""), True)
            fdot = tp.feeder_dot_for(cad, ev["new_rotation"])
            if fdot:
                store.set_feeder(r["part_id"], str(r["feeder"].getId()), fdot, True, applied)
        store.save()

    def close(self):
        if self.busy:
            JOptionPane.showMessageDialog(self.frame, "The machine is working - wait until it is done.")
            return
        if self.state is not None and self.state.get("on_board"):
            q = JOptionPane.showConfirmDialog(
                self.frame, "The test part is still on the board (%s).\nPick it up and return it to the feeder now (no result "
                "stored)?\nNo = leave it there, I remove it by hand." % self.state["ref"], "Close", JOptionPane.YES_NO_CANCEL_OPTION)
            if q == JOptionPane.YES_OPTION:
                self.finish(no_result=True)
                return
            if q != JOptionPane.NO_OPTION:
                return
            self.owner.log("test placement %s: closed, part LEFT ON THE BOARD" % self.state["ref"])
        self.frame.dispose()
        if self.on_done:
            self.on_done()


COLS = ["Part", "Footprint", "Refs", "Orientation", "CAD pin 1", "Feeder", "Feeder mark", "Needs", "Feeder now", "Status"]


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
        cad = "-" if not x.get("cad_dot") else "%s (%s%s)" % (x["cad_dot"], "confirmed" if x["cad_ok"] else "auto",
                                                            "" if x["cad_ok"] or not x.get("cad_source") else ": " + x["cad_source"])
        fm = "-" if not x.get("feeder_dot") else "%s (%s)" % (x["feeder_dot"], "confirmed" if x["feeder_ok"] else "?")
        return [x["part_id"], (x.get("footprint") or "").split(":")[-1], x["refs"],
                {True: "matters", False: "not relevant", None: "?"}[x["matters"]], cad, x.get("feeder_name") or "-", fm,
                "-" if x["need"] is None else "%+.0f" % x["need"],
                "-" if x.get("feeder_rot") is None else "%+.0f" % ori.norm(x["feeder_rot"]), x["status"]][c]


class StatusRenderer(DefaultTableCellRenderer):
    def __init__(self, model):
        DefaultTableCellRenderer.__init__(self)
        self.model = model

    def getTableCellRendererComponent(self, table, value, sel, focus, row, col):
        c = DefaultTableCellRenderer.getTableCellRendererComponent(self, table, value, sel, focus, row, col)
        if not sel:
            s = self.model.rows[row]["status"]
            c.setBackground(Color(210, 245, 210) if s.startswith("CORRECT") else Color(255, 215, 215)
                            if s.startswith("MISMATCH") else Color.WHITE if s == "orientation not relevant"
                            else Color(255, 243, 205))
        return c


class OrientationSetup(object):
    def __init__(self):
        self.store = ori.Store(os.path.join(oppnp.lumen_dir(scripting), "orientation.json"))
        self.log = oppnp.FileLog(scripting, "orientation")
        self._parsed = {}          # (source, board) -> verified match result
        self._files = {}           # path -> parsed .kicad_pcb / Gerber
        self.unverified = {}       # (board, ref) -> why the file could not be used for it
        self.last_import = ""
        self.fp_conflicts = {}
        self.refusals = []         # (file, board, why) of files refused this session
        self._lib_index = None
        self._lib_cache = {}
        self.model = Model()
        f = self.frame = JFrame("Orientation setup (optional helper)")
        f.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8))
        top = JPanel(BorderLayout())
        self.summary = JLabel(" ")
        top.add(self.summary, BorderLayout.NORTH)
        srow = JPanel(FlowLayout(FlowLayout.LEFT))
        srow.add(JButton("Load CAD data (board / Gerber / library)...", actionPerformed=lambda e: self.load_cad()))
        srow.add(JButton("Detection report...", actionPerformed=lambda e: self.report()))
        self.only = JCheckBox("only parts where orientation matters", True, actionPerformed=lambda e: self.refresh())
        srow.add(self.only)
        self.sources = JLabel(" ")
        srow.add(self.sources)
        top.add(srow, BorderLayout.SOUTH)
        root.add(top, BorderLayout.NORTH)
        self.table = JTable(self.model)
        self.table.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION)
        rend = StatusRenderer(self.model)
        for i, w in enumerate((140, 170, 120, 80, 150, 170, 100, 50, 70, 330)):
            self.table.getColumnModel().getColumn(i).setPreferredWidth(w)
            self.table.getColumnModel().getColumn(i).setCellRenderer(rend)
        sp = JScrollPane(self.table)
        sp.setPreferredSize(Dimension(1380, 380))
        root.add(sp, BorderLayout.CENTER)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        b.add(JButton("Check selected (two squares)...", actionPerformed=lambda e: self.check()))
        b.add(JButton("Test placement on the PCB...", actionPerformed=lambda e: self.test()))
        b.add(JButton("Toggle 'orientation matters'", actionPerformed=lambda e: self.toggle()))
        b.add(JButton("Refresh", actionPerformed=lambda e: self.refresh()))
        b.add(JButton("Close", actionPerformed=lambda e: f.dispose()))
        root.add(b, BorderLayout.SOUTH)
        f.setContentPane(lumen.uihelp.wrap(root, "orientation"))
        f.pack()
        f.setLocationRelativeTo(gui)
        self.refresh()
        f.setVisible(True)

    # -- CAD sources (bound to the OpenPnP board they were imported for) -------------------
    @staticmethod
    def board_key(bl):
        b = bl.getBoard()
        f = b.getFile() if b is not None else None
        return str(f.getAbsolutePath()) if f is not None else "name:%s" % (b.getName() if b is not None else "?")

    def sources_for(self, bkey):
        """Legacy global sources (older orientation.json) + the ones imported for this board."""
        return list(self.store.data["sources"]) + [s for s in self.store.data["board_sources"].get(bkey, [])
                                                   if s not in self.store.data["sources"]]

    def cad_for(self, bl):
        """{ref: cad info} VERIFIED for this board; self.unverified[(board, ref)] = why not."""
        bkey = self.board_key(bl)
        cad = {}
        for src in self.sources_for(bkey):
            res = self.load_source(src, bl, quiet=True)
            for ref, r in res["results"].items():
                if r["ok"]:
                    if ref not in cad or src.startswith("kicad:"):
                        cad[ref] = r
                    self.unverified.pop((bkey, ref), None)
                elif ref not in cad:
                    self.unverified[(bkey, ref)] = "%s: %s" % (os.path.basename(src.split(":", 1)[1]), r["reason"])
        return cad

    @staticmethod
    def board_placements(bl):
        """The board's placements in the position-file frame (mm), as the matchers expect them."""
        out = []
        for p in bl.getPlacementsHolder().getPlacements():
            if p.getType() != Placement.Type.Placement:
                continue
            loc = p.getLocation().convertToUnits(LengthUnit.Millimeters)
            part = p.getPart()
            pk = str(part.getPackage().getId()) if part is not None and part.getPackage() is not None else ""
            out.append({"ref": str(p.getId()), "x": loc.getX(), "y": loc.getY(), "rot": ori.norm(loc.getRotation()),
                        "side": str(p.getSide()).lower(), "footprint": pk})
        return out

    def load_source(self, src, bl, quiet=False):
        """Verified match of a .kicad_pcb / copper Gerber to the placements of this board."""
        key = (src, self.board_key(bl))
        if key in self._parsed:
            return self._parsed[key]
        kind, path = src.split(":", 1)
        name = os.path.basename(path)
        try:
            if path not in self._files:
                self._files[path] = ori.parse_kicad_pcb_list(path) if kind == "kicad" else ori.parse_gerber(path)
            pl = self.board_placements(bl)
            res = (ori.match_kicad_pcb if kind == "kicad" else ori.match_gerber)(self._files[path], pl, kind + ":" + name)
        except (Exception, JavaException) as e:
            res = {"results": {}, "verified": 0, "placements": 0, "refused": "cannot read %s: %s" % (name, e)}
        self._parsed[key] = res
        if kind == "kicad" and path in self._files:
            # footprint-local pads of EVERY footprint in a board file are exact, whatever the job
            learn = [i for i in self._files[path] if i["side"] == "top"]
        else:                                                    # Gerber: only what was verified
            learn = [dict(r, ref=ref, side="top") for ref, r in res["results"].items() if r["ok"]]
        good, bad = ori.learn_footprints(learn)                  # pin 1 by footprint name, for later boards
        res["learned"] = len(good)
        for k, i in good.items():
            c = self.store.set_footprint(k, i, i["source"], False)
            if c:
                self.fp_conflicts[k] = "%s says %s" % (i["source"], c)
        for k, dots in bad.items():
            self.fp_conflicts[k] = "refs disagree (%s) in %s" % (", ".join(dots), name)
        if not quiet:
            self.log("imported %s for %s: %d of %d placements verified%s" % (
                path, self.board_key(bl), res["verified"], res["placements"],
                "; REFUSED: " + res["refused"] if res.get("refused") else ""))
        return res

    def load_cad(self):
        """One entry for every CAD input: file, folder or zip; classified, then imported / added."""
        ch = JFileChooser(self.store.data.get("last_dir") or os.path.expanduser("~"))
        ch.setFileSelectionMode(JFileChooser.FILES_AND_DIRECTORIES)
        ch.setDialogTitle("KiCad board, top copper Gerber X2 (file / folder / zip) or footprint library folder")
        ch.setAcceptAllFileFilterUsed(True)
        ch.setFileFilter(FileNameExtensionFilter("Board, Gerber, zip (*.kicad_pcb, *.gbr, *.gtl, *.zip)",
                                                 ["kicad_pcb", "gbr", "gtl", "gbx", "zip", "kicad_mod"]))
        if ch.showOpenDialog(self.frame) != JFileChooser.APPROVE_OPTION:
            return
        return self.load_path(str(ch.getSelectedFile().getAbsolutePath()))

    def load_path(self, path):
        r = ori.classify_input(path, os.path.join(oppnp.lumen_dir(scripting), "cad"))
        self.log("load %s: %s" % (path, r))
        if not r.get("kind"):
            JOptionPane.showMessageDialog(self.frame, "Not loaded:\n%s" % r["error"])
            return r
        if r["kind"] == "library":
            self.add_library_dir(r["path"])
        else:
            self.add_source(r["kind"], r["path"])
        return r

    def why_unknown(self, x, unver, fkey, sources):
        """Why the CAD pin 1 of a part is not known, and what to do."""
        if unver:
            return "; ".join(unver[:2]) + (" +%d" % (len(unver) - 2) if len(unver) > 2 else "")
        if not sources and not ori.library_dirs(self.store.data["lib_dirs"]) and not self.store.data["footprints"]:
            return "no CAD data loaded - Load CAD data (board, top copper Gerber X2 or footprint library), or set pin 1 in Check"
        li = self.lib_info(fkey) if fkey else None
        if li is not None and not li.get("dot"):
            return "footprint %s in the library: %s - set pin 1 in Check" % (fkey, li.get("note") or "pin 1 unknown")
        if not fkey:
            return "the part has no package / footprint name - load the board file (.kicad_pcb), or set pin 1 in Check"
        return ("footprint %s is not in the loaded board / Gerber / libraries - load the board or library that has it, "
                "or set pin 1 in Check" % fkey)

    def report(self):
        """Detection report: per part where orientation matters, where CAD pin 1 comes from, or why not."""
        rows = {}
        for x in self.all_rows:
            rows.setdefault(x["part_id"], x)
        rel = [x for x in rows.values() if x["matters"] is not False]
        got = [x for x in rel if x.get("cad_dot")]
        miss = [x for x in rel if not x.get("cad_dot")]
        L = ["Orientation detection report  %s" % time.strftime("%Y-%m-%d %H:%M"), ""]
        L.append("CAD data: %s" % self.sources.getText().replace("CAD: ", ""))
        for fn, bname, why in self.refusals:
            L.append("REFUSED %s for %s: %s" % (fn, bname, why))
        L.append("")
        L.append("Parts where orientation matters: %d - pin 1 detected %d, NOT detected %d; not relevant (hidden): %d"
                 % (len(rel), len(got), len(miss), len(rows) - len(rel)))
        L.append("")
        for x in sorted(miss, key=lambda x: x["part_id"]):
            L.append("NOT DETECTED  %-28s %-34s %s\n              -> %s" % (x["part_id"], (x.get("footprint") or "-").split(":")[-1],
                                                                       x["refs"], x.get("why") or "set pin 1 in Check"))
        for x in sorted(got, key=lambda x: x["part_id"]):
            how = "confirmed" if x["cad_ok"] else "auto, confirm in Check"
            L.append("pin 1 %-6s  %-28s %-34s %s  [%s; %s]" % (x["cad_dot"], x["part_id"], (x.get("footprint") or "-").split(":")[-1],
                                                               x["refs"], x.get("cad_source") or "?", how))
        text = "\n".join(L)
        p = os.path.join(oppnp.lumen_dir(scripting), "logs", "orientation-report-%s.txt" % time.strftime("%Y%m%d-%H%M%S"))
        f = open(p, "w")
        try:
            f.write(text + "\n")
        finally:
            f.close()
        ta = JTextArea(text, 24, 120)
        ta.setEditable(False)
        ta.setFont(Font("Monospaced", Font.PLAIN, 12))
        JOptionPane.showMessageDialog(self.frame, JScrollPane(ta), "Detection report (saved: %s)" % p, JOptionPane.PLAIN_MESSAGE)
        self.log("detection report %s: %d detected, %d not detected" % (p, len(got), len(miss)))
        return text

    def import_file(self, kind):
        ch = JFileChooser(self.store.data.get("last_dir") or os.path.expanduser("~"))
        if kind == "kicad":
            ch.setFileFilter(FileNameExtensionFilter("KiCad board (*.kicad_pcb)", ["kicad_pcb"]))
        else:
            ch.setFileFilter(FileNameExtensionFilter("Gerber copper layer (*.gbr, *.gtl)", ["gbr", "gtl", "gbl"]))
        if ch.showOpenDialog(self.frame) != JFileChooser.APPROVE_OPTION:
            return
        path = str(ch.getSelectedFile().getAbsolutePath())
        self.add_source(kind, path)

    def add_source(self, kind, path):
        """Import for the board(s) of the open job; used only where it is verified against the job."""
        job = gui.getJobTab().getJob()
        bls = [bl for bl in (job.getBoardLocations() if job is not None else []) if bl.getBoard() is not None]
        if not bls:
            JOptionPane.showMessageDialog(self.frame, "Open the job with the board first.")
            return
        src = "%s:%s" % (kind, path)
        for k in [k for k in self._parsed if k[0] == src]:
            del self._parsed[k]
        self._files.pop(path, None)
        lines = []
        seen = set()
        for bl in bls:
            bkey = self.board_key(bl)
            if bkey in seen:
                continue
            seen.add(bkey)
            res = self.load_source(src, bl)
            bname = bl.getBoard().getName() or bkey
            if res.get("refused"):
                lines.append("%s: NOT USED for the positions - %s" % (bname, res["refused"]))
                if (os.path.basename(path), bname, res["refused"]) not in self.refusals:
                    self.refusals.append((os.path.basename(path), bname, res["refused"]))
                if res.get("learned"):
                    lines.append("   but pin 1 BY FOOTPRINT NAME was taken from it for %d footprint(s): right if the footprints "
                                 "did not change between the revisions - confirm once per part in Check." % res["learned"])
                continue
            lst = self.store.data["board_sources"].setdefault(bkey, [])
            if src not in lst:
                lst.append(src)
            why = {}
            for ref, r in sorted(res["results"].items()):
                if not r["ok"]:
                    why.setdefault(r["reason"], []).append(ref)
            lines.append("%s: %d of %d placements verified (pin 1 from the file)." % (bname, res["verified"], res["placements"]))
            for reason, refs in sorted(why.items(), key=lambda kv: -len(kv[1]))[:8]:
                lines.append("   not verified (%d): %s - %s" % (len(refs), ", ".join(refs[:6]) + (" ..." if len(refs) > 6 else ""), reason))
        self.last_import = "\n".join(lines)
        JOptionPane.showMessageDialog(self.frame, "%s\n\n%s" % (os.path.basename(path), self.last_import))
        self.store.data["last_dir"] = os.path.dirname(path)
        self.store.save()
        self.refresh()

    def add_library(self):
        ch = JFileChooser(self.store.data.get("last_dir") or os.path.expanduser("~"))
        ch.setFileSelectionMode(JFileChooser.DIRECTORIES_ONLY)
        ch.setDialogTitle("Folder with KiCad footprints (a .pretty folder or a folder of them)")
        if ch.showOpenDialog(self.frame) != JFileChooser.APPROVE_OPTION:
            return
        self.add_library_dir(str(ch.getSelectedFile().getAbsolutePath()))

    def add_library_dir(self, path):
        n = len(ori.index_libraries([path]))
        if n == 0:
            JOptionPane.showMessageDialog(self.frame, "No .kicad_mod footprints found in %s" % path)
            return
        if path not in self.store.data["lib_dirs"]:
            self.store.data["lib_dirs"].append(path)
        self.store.data["last_dir"] = os.path.dirname(path)
        self.store.save()
        self._lib_index = None
        self.log("footprint library %s: %d footprints" % (path, n))
        self.refresh()

    def lib_info(self, key):
        if self._lib_index is None:
            self._lib_index = ori.index_libraries(ori.library_dirs(self.store.data["lib_dirs"]))
        path = self._lib_index.get(key)
        if path is None:
            return None
        if path not in self._lib_cache:
            try:
                self._lib_cache[path] = ori.parse_kicad_mod(path)
            except Exception:
                self._lib_cache[path] = None
        return self._lib_cache[path]

    @staticmethod
    def package_info(part):
        pk = part.getPackage()
        fp = pk.getFootprint() if pk is not None else None
        if fp is None or not fp.getPads():
            return None
        return ori.package_cad_info(str(pk.getId()), [(str(p.getName() or ""), p.getX(), p.getY()) for p in fp.getPads()])

    def footprint(self, part, infos):
        key = ori.footprint_key(infos[0]["footprint"] if infos else
                                (str(part.getPackage().getId()) if part.getPackage() is not None else ""))
        if not key:
            return key, None
        r = ori.resolve_footprint(key, self.store.data["footprints"].get(key), self.package_info(part), self.lib_info(key))
        if r is not None and key in self.fp_conflicts:
            r["conflict"] = r["conflict"] + [self.fp_conflicts[key]]
        return key, r

    # -- list ---------------------------------------------------------------------------
    def refresh(self):
        job = gui.getJobTab().getJob()
        rows = []
        by_part = {}
        cads = {}
        self.board_srcs = set()
        if job is not None:
            for bl, pl, placed in jobinfo.job_placements(job):
                part = pl.getPart()
                if part is None:
                    continue
                bk = self.board_key(bl)
                if bk not in cads:
                    cads[bk] = self.cad_for(bl)
                    self.board_srcs.update(self.sources_for(bk))
                ent = by_part.setdefault(str(part.getId()), (part, [], [], []))
                ent[1].append(str(pl.getId()))
                if str(pl.getId()) in cads[bk]:
                    ent[2].append(cads[bk][str(pl.getId())])
                elif (bk, str(pl.getId())) in self.unverified:
                    ent[3].append("%s %s" % (pl.getId(), self.unverified[(bk, str(pl.getId()))]))
        for pid, (part, refs, infos, unver) in sorted(by_part.items()):
            dots = sorted(set(i["dot"] for i in infos if i["dot"]))
            fkey, fp = self.footprint(part, infos)
            sp = self.store.data["parts"].get(pid, {})
            matters = sp.get("matters")
            if matters is None and infos:
                matters = any(i["matters"] for i in infos)
            if matters is None:                        # position file only: footprint pins, else the reference
                matters = ori.orientation_matters(refs[0], fkey, fp["pins"] if fp and fp.get("pins") else None)
            cad_rec = sp.get("cad") or {}
            board_dot = dots[0] if len(dots) == 1 else None
            cad_dot = cad_rec.get("dot") or board_dot or (fp["dot"] if fp and not dots else None)
            note = "" if len(dots) <= 1 else "refs disagree on pin 1 (%s): " % ", ".join(dots)
            if fp and fp["conflict"]:
                note += "footprint sources disagree: %s (%s) vs %s: " % (fp["dot"], fp["source"], "; ".join(fp["conflict"]))
            elif fp and fp["confirmed"] and board_dot and board_dot != fp["dot"]:
                note += "board says %s, confirmed footprint %s: " % (board_dot, fp["dot"])
            from_fp = bool(fp) and not cad_rec.get("dot") and not dots
            fp_ok = bool(fp) and fp["confirmed"] and fp["dot"] == cad_dot and not fp["conflict"]
            base = {"part_id": pid, "part": part, "refs": ", ".join(refs[:6]) + (" +%d" % (len(refs) - 6) if len(refs) > 6 else ""),
                    "footprint": infos[0]["footprint"] if infos else fkey,
                    "pads": infos[0]["pads"] if infos else (fp["pads"] if fp else []), "matters": matters, "cad_dot": cad_dot,
                    "pins": infos[0]["pins"] if infos else (fp["pins"] if fp else None),
                    "cad_ok": (bool(cad_rec.get("confirmed")) and cad_rec.get("dot") == cad_dot) or fp_ok,
                    "cad_source": cad_rec.get("source") if cad_rec else (infos[0]["source"] if infos else
                                                                         (fp["source"] if from_fp else None))}
            feeders = [f for f in machine.getFeeders() if f.getPart() == part]
            for f in feeders or [None]:
                x = dict(base)
                if f is not None:
                    fr = sp.get("feeders", {}).get(str(f.getId()), {})
                    rot = oppnp.feeder_rotation(f)
                    x.update({"feeder": f, "feeder_name": f.getName(), "feeder_rot": rot, "feeder_dot": fr.get("dot"),
                              "feeder_ok": bool(fr.get("confirmed")),
                              "feeder_preset": ori.rotate_dot(cad_dot, round(rot / 90.0) * 90) if cad_dot and rot is not None else None})
                else:
                    x.update({"feeder": None, "feeder_rot": None, "feeder_dot": None, "feeder_ok": False})
                need, st = ori.status(matters, cad_dot, x["cad_ok"], x["feeder_dot"], x["feeder_ok"], x["feeder_rot"])
                if f is None and matters is not False and cad_dot:
                    st = "no feeder has this part" + ("" if x["cad_ok"] else " (CAD mark not confirmed)")
                if unver and not cad_dot:                  # a CAD file is loaded but could not verify these refs
                    st = "NOT VERIFIED %s; %s" % ("; ".join(unver[:2]) + (" +%d" % (len(unver) - 2) if len(unver) > 2 else ""), st)
                elif unver:
                    st = "%s (board file not verified for %s)" % (st, ", ".join(u.split(" ")[0] for u in unver[:3]))
                if not cad_dot and matters is not False:
                    x["why"] = self.why_unknown(x, unver, fkey, self.board_srcs)
                    st = "CAD pin 1 NOT DETECTED: %s" % x["why"]
                x["need"], x["status"] = need, note + st
                rows.append(x)
        self.all_rows = rows
        shown = [x for x in rows if not self.only.isSelected() or x["matters"] is not False]
        self.model.rows = shown
        self.model.fireTableDataChanged()
        rel = [x for x in rows if x["matters"] is not False]
        ok = len([x for x in rel if x["status"].startswith("CORRECT")])
        bad = len([x for x in rel if "MISMATCH" in x["status"]])
        nd = len(set(x["part_id"] for x in rel if not x.get("cad_dot")))
        self.summary.setText("<html>%d part/feeder row(s) where orientation matters: <font color='green'>%d correct "
                             "(confirmed)</font>, <font color='red'>%d mismatch</font>, %d to check%s</html>" % (
                                 len(rel), ok, bad, len(rel) - ok - bad,
                                 "" if not nd else " - <font color='red'><b>CAD pin 1 not detected for %d part(s)</b></font> "
                                 "(Detection report)" % nd))
        names = [os.path.basename(s.split(":", 1)[1]) for s in sorted(self.board_srcs)]
        names += [os.path.basename(d) + "/" for d in ori.library_dirs(self.store.data["lib_dirs"])]
        nfp = len(self.store.data["footprints"])
        self.sources.setText("CAD: " + (", ".join(names) or "none (optional)") + (" | footprint table: %d" % nfp if nfp else ""))

    def selected(self):
        i = self.table.getSelectedRow()
        return self.model.rows[i] if i >= 0 else None

    def check(self):
        x = self.selected()
        if x is None:
            JOptionPane.showMessageDialog(self.frame, "Select a row.")
            return None
        return CheckDialog(self, x)

    def test(self):
        """Test placement of the selected rows' parts, one after the other (each in its own window)."""
        rows = [self.model.rows[i] for i in self.table.getSelectedRows() if self.model.rows[i].get("feeder") is not None]
        rows, skipped = tp.split_rows(rows)
        if skipped:
            msg = ("Orientation is marked 'not relevant' for %s: no test for %s.\n(If it does matter, use "
                   "\"Toggle 'orientation matters'\" first.)" % (", ".join(sorted(set(x["part_id"] for x in skipped))),
                                                                  "it" if len(skipped) == 1 else "them"))
            self.log(msg.replace("\n", " "))
            JOptionPane.showMessageDialog(self.frame, msg)
        if not rows:
            if not skipped:
                JOptionPane.showMessageDialog(self.frame, "Select the row(s) you are not sure about - rows with a feeder "
                                                          "(the test part is taken from it and returned to it).")
            return None
        self._tests = [(x["part_id"], x["feeder"]) for x in rows[1:]]
        return TestDialog(self, rows[0], self._next_test)

    def _next_test(self):
        while getattr(self, "_tests", None):
            pid, feeder = self._tests.pop(0)
            fresh = [r for r in self.model.rows if r["part_id"] == pid and r.get("feeder") == feeder]
            if fresh:
                return TestDialog(self, fresh[0], self._next_test)
        return None

    def toggle(self):
        x = self.selected()
        if x is None:
            return
        p = self.store.part(x["part_id"])
        p["matters"] = not (x["matters"] is not False)
        self.store.save()
        self.refresh()


OrientationSetup()
