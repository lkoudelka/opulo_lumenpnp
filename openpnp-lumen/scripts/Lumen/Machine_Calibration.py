# Scripts > Lumen > Machine Calibration   (Opulo LumenPnP V4.1 calibration guide, automated)
#
# The fundamental and optional steps of https://docs.opulo.io/openpnp/v4-1/ (Issues & Solutions) in
# the guide's order, each done by OpenPnP's own Issues & Solutions routine; this window moves the
# camera / nozzles there, measures the touching Z by vacuum contact, changes tips with you, carries
# the calibration target and checks every result.  Where your hands are needed it stops and shows
# what to do with a picture.  At the end: homing verified, configuration saved (you confirm) - the
# machine is ready for File > New Job / Import Board.   Safety rules: lib/lumen/machinecal.py.
from __future__ import absolute_import, division, print_function

import os
import sys
import threading
import time

_LIB = os.path.join(str(scripting.getScriptsDirectory().getParent()), "lumen", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
import lumen.oppnp
import lumen.helptext
import lumen.uihelp
import lumen.zprobe
import lumen.tapevision
import lumen.nozzlecal
import lumen.machinecal
reload(lumen.oppnp)
reload(lumen.helptext)
reload(lumen.uihelp)
reload(lumen.zprobe)
reload(lumen.tapevision)
reload(lumen.nozzlecal)
reload(lumen.machinecal)
from lumen import machinecal, oppnp
from lumen.oppnp import JavaException

from java.awt import BorderLayout, Color, Desktop, Dimension, FlowLayout, GridLayout
from java.io import File
from java.net import URI
from javax.imageio import ImageIO
from javax.swing import (BorderFactory, BoxLayout, ImageIcon, JButton, JCheckBox, JComboBox, JEditorPane, JFrame,
                         JLabel, JPanel, JScrollPane, JSpinner, JSplitPane, JTable, JTextArea, JTextField,
                         ListSelectionModel, SpinnerNumberModel, WindowConstants)
from javax.swing.table import AbstractTableModel, DefaultTableCellRenderer

PICTURES = os.path.join(_LIB, "lumen", "pictures")
COLS = ["#", "Step", "Type", "Status", "Result"]
Z_METHODS = ["vacuum contact (automatic)", "jog by hand (as in the Opulo guide)"]
COLOURS = {"done": Color(200, 235, 200), "failed": Color(250, 200, 200), "running": Color(255, 240, 180),
           "skipped": Color(230, 230, 230), "waiting for you": Color(255, 220, 150)}


def picture(name, width=500):
    p = os.path.join(PICTURES, name)
    if not os.path.isfile(p):
        return JLabel("(picture %s missing)" % name)
    img = ImageIO.read(File(p))
    if img.getWidth() > width:
        img = img.getScaledInstance(width, int(img.getHeight() * width / img.getWidth()), 4)
    return JLabel(ImageIcon(img))


class Model(AbstractTableModel):
    def __init__(self, status):
        AbstractTableModel.__init__(self)
        self.status = status

    def getRowCount(self):
        return len(machinecal.STEPS)

    def getColumnCount(self):
        return len(COLS)

    def getColumnName(self, c):
        return COLS[c]

    def getValueAt(self, r, c):
        s = machinecal.STEPS[r]
        st = self.status.get(s.key, {})
        return [str(r + 1), s.title, s.kind, st.get("status", ""), st.get("result", "")][c]


class Renderer(DefaultTableCellRenderer):
    def __init__(self, model):
        DefaultTableCellRenderer.__init__(self)
        self.model = model

    def getTableCellRendererComponent(self, table, value, sel, focus, row, col):
        c = DefaultTableCellRenderer.getTableCellRendererComponent(self, table, value, sel, focus, row, col)
        st = self.model.getValueAt(row, 3)
        if not sel:
            c.setBackground(COLOURS.get(st, Color.WHITE))
        c.setToolTipText(str(value) if col == 4 and value else None)
        return c


class MachineCal(object):
    def __init__(self):
        self.settings = oppnp.Settings(scripting)
        self.log = oppnp.FileLog(scripting, "machine-calibration")
        self.status = self.settings.get("machine_cal_status", {})
        self.busy = False
        self.stop_flag = False
        self.answer = None
        self.answered = threading.Event()
        self.cal = None
        f = self.frame = JFrame("Machine Calibration - Opulo LumenPnP V4.1 guide, automated")
        f.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)

        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(6, 6, 6, 6))
        self.model = Model(self.status)
        t = self.table = JTable(self.model)
        t.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        t.setDefaultRenderer(t.getColumnClass(0), Renderer(self.model))
        for i, w in enumerate((24, 330, 80, 110, 260)):
            t.getColumnModel().getColumn(i).setPreferredWidth(w)
        t.getSelectionModel().addListSelectionListener(lambda e: None if e.getValueIsAdjusting() else self.show_step())
        left = JScrollPane(t)
        left.setPreferredSize(Dimension(780, 460))

        self.right = JPanel(BorderLayout(4, 4))
        self.right.setPreferredSize(Dimension(560, 460))
        split = JSplitPane(JSplitPane.HORIZONTAL_SPLIT, left, self.right)
        split.setResizeWeight(0.55)
        root.add(split, BorderLayout.CENTER)

        south = JPanel(BorderLayout(4, 4))
        opts = JPanel(FlowLayout(FlowLayout.LEFT))
        opts.add(JLabel("Fiducial Z:"))
        self.zm = JComboBox(Z_METHODS)
        self.zm.setSelectedIndex(1 if self.settings.get("machine_cal_z") == "hand" else 0)
        opts.add(self.zm)
        self.opt_box = JCheckBox("optional steps (backlash X/Y, up to 15 min each)", self.settings.get("machine_cal_optional", True))
        opts.add(self.opt_box)
        self.pause_box = JCheckBox("pause for my check before every Accept", self.settings.get("machine_cal_pause", False))
        opts.add(self.pause_box)
        self.swap_box = JCheckBox("swap N1 tip for the bottom camera to:", self.settings.get("machine_cal_swap", False))
        opts.add(self.swap_box)
        self.tip = JTextField(self.settings.get("machine_cal_tip", "N08"), 5)
        self.tip.setToolTipText(lumen.uihelp._html(lumen.helptext.HELP["machine_cal"]["tips"]["swap N1 tip"]))
        opts.add(self.tip)
        park = self.settings.get("target_park", list(machinecal.DEFAULT_PARK))
        opts.add(JLabel("Target park X/Y:"))
        self.px = JTextField("%.3f" % park[0], 7)
        self.py = JTextField("%.3f" % park[1], 7)
        opts.add(self.px)
        opts.add(self.py)
        south.add(opts, BorderLayout.NORTH)
        self.text = JTextArea(9, 120)
        self.text.setEditable(False)
        south.add(JScrollPane(self.text), BorderLayout.CENTER)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        self.all_btn = JButton("Run all from the selected step", actionPerformed=lambda e: self.start(True))
        self.one_btn = JButton("Run the selected step only", actionPerformed=lambda e: self.start(False))
        self.stop_btn = JButton("Stop after this step", actionPerformed=lambda e: self.request_stop())
        self.stop_btn.setEnabled(False)
        self.reset_btn = JButton("Clear status", actionPerformed=lambda e: self.clear_status())
        b.add(self.all_btn)
        b.add(self.one_btn)
        b.add(self.stop_btn)
        b.add(self.reset_btn)
        b.add(JButton("Close", actionPerformed=lambda e: self.close()))
        south.add(b, BorderLayout.SOUTH)
        root.add(south, BorderLayout.SOUTH)

        f.setContentPane(lumen.uihelp.wrap(root, "machine_cal"))
        f.pack()
        f.setLocationRelativeTo(gui)
        first = 0
        for i, s in enumerate(machinecal.STEPS):
            if self.status.get(s.key, {}).get("status") not in ("done", "skipped"):
                first = i
                break
        t.setRowSelectionInterval(first, first)
        self.show_step()
        f.setVisible(True)
        self.say("Steps in the order of the Opulo V4.1 guide. Start with step 1. The machine must be connected (enabled).")

    # ------------------------------------------------------------------ UI helpers
    def say(self, s):
        line = self.log(s)
        oppnp.on_ui(lambda: self.text.append(line + "\n"))
        oppnp.on_ui(lambda: self.text.setCaretPosition(self.text.getDocument().getLength()))

    def html_pane(self, html):
        p = JEditorPane("text/html", "<html><body style='font-family:sans-serif;font-size:11pt'>%s</body></html>" % html)
        p.setEditable(False)
        p.setCaretPosition(0)
        return p

    def set_right(self, north, pictures, buttons):
        r = self.right
        r.removeAll()
        top = JScrollPane(north)
        top.setPreferredSize(Dimension(520, 190))
        r.add(top, BorderLayout.NORTH)
        if pictures:
            pics = JPanel()
            pics.setLayout(BoxLayout(pics, BoxLayout.Y_AXIS))
            for name in pictures:
                pics.add(picture(name))
            sp = JScrollPane(pics)
            sp.getVerticalScrollBar().setUnitIncrement(16)
            r.add(sp, BorderLayout.CENTER)
        if buttons is not None:
            r.add(buttons, BorderLayout.SOUTH)
        r.revalidate()
        r.repaint()

    def show_step(self):
        if self.answer == "waiting":
            return
        i = self.table.getSelectedRow()
        if i < 0:
            return
        s = machinecal.STEPS[i]
        html = ("<h3>%d. %s</h3><p><i>%s</i></p><p>%s</p><p><b>Moves:</b> %s</p>%s"
                % (i + 1, s.title, s.kind, s.what, s.moves,
                   ("<p><b>Your hands:</b> %s</p>" % s.manual) if s.manual else ""))
        b = JPanel(FlowLayout(FlowLayout.LEFT))
        ob = JButton("Open the Opulo guide page", actionPerformed=lambda e, u=s.doc: self.browse(u))
        ob.setToolTipText(lumen.uihelp._html(lumen.helptext.HELP["machine_cal"]["tips"]["Open the Opulo guide page"]))
        b.add(ob)
        self.set_right(self.html_pane(html), PICS.get(s.key, []), b)

    def browse(self, url):
        def go():
            try:
                Desktop.getDesktop().browse(URI(url))
            except (Exception, JavaException) as e:
                self.say("cannot open the browser (%s): %s" % (e, url))
        oppnp.in_background(go)

    # ------------------------------------------------------------------ the ui object for machinecal.Calibrator
    def ask(self, title, html, pictures, buttons, extra=None):
        """Blocks the worker thread until a button is pressed; shows text, pictures and buttons on the right."""
        self.answered.clear()
        self.answer = "waiting"
        oppnp.on_ui(lambda: self.show_question(title, html, pictures, buttons, extra))
        self.say("WAITING FOR YOU: %s" % title)
        self.answered.wait()
        a = self.answer
        self.answer = None
        self.say("  you pressed: %s" % a)
        oppnp.on_ui(self.show_step)
        return a

    def show_question(self, title, html, pictures, buttons, extra=None):
        row = JPanel(FlowLayout(FlowLayout.LEFT))
        if extra is not None:
            row.add(extra)
        for label in buttons:
            qb = JButton(label, actionPerformed=lambda e, l=label: self.answer_with(l))
            qb.setToolTipText("Your answer: %s. %s" % (label, "Nothing moves after Cancel." if label == "Cancel" else
                                                         "The run continues."))
            row.add(qb)
        self.set_right(self.html_pane("<h3 style='color:#a05000'>%s</h3>%s" % (title, html)), pictures, row)
        self.frame.toFront()

    def answer_with(self, label):
        self.answer = label
        self.answered.set()

    def visual_check(self, issue, camera, expected_px, reason):
        spin = JSpinner(SpinnerNumberModel(int(self.cal.feature_px(issue)), 3, 2000, 1))
        panel = JPanel(FlowLayout(FlowLayout.LEFT))
        panel.add(JLabel("Feature diameter (px):"))
        panel.add(spin)

        def preview(e):
            v = int(spin.getValue())
            oppnp.in_background(lambda: self.cal.feature_px(issue, v))
        panel.add(JButton("Show detection", actionPerformed=preview))
        bottom = camera.getLooking().toString() == "Up"
        a = self.ask("Check the detection in the OpenPnP camera view",
                     "<p>%s</p><p>Look at the camera view of <b>%s</b> in OpenPnP. The green circle must hug %s. Change "
                     "the diameter and press <i>Show detection</i> until it does (expected about %.0f px), then "
                     "<i>Accept</i>.</p>" % (reason, camera.getName(),
                                             "the <b>inner opening</b> of the tip, not its outer edge" if bottom
                                             else "the <b>fiducial dot</b>", expected_px),
                     ["cal-bottom-circle.png" if bottom else "cal-fid-circle.png"], ["Accept", "Cancel"], extra=panel)
        if a == "Accept":
            self.cal.feature_px(issue, int(spin.getValue()))
            return "accept"
        return "cancel"

    def stop_requested(self):
        return self.stop_flag

    # ------------------------------------------------------------------ run
    def options(self):
        try:
            park = (float(self.px.getText()), float(self.py.getText()))
        except ValueError:
            raise ValueError("target park X/Y must be numbers")
        o = {"z_method": "hand" if self.zm.getSelectedIndex() == 1 else "probe",
             "optional": self.opt_box.isSelected(), "pause_each": self.pause_box.isSelected(),
             "swap_tip": self.swap_box.isSelected(), "bottom_tip": self.tip.getText().strip() or "N08", "park": park}
        self.settings.set("machine_cal_z", o["z_method"])
        self.settings.set("machine_cal_optional", o["optional"])
        self.settings.set("machine_cal_pause", o["pause_each"])
        self.settings.set("machine_cal_tip", o["bottom_tip"])
        self.settings.set("machine_cal_swap", o["swap_tip"])
        self.settings.set("target_park", list(park))
        return o

    def set_status(self, key, status, result=""):
        self.status[key] = {"status": status, "result": result, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.settings.set("machine_cal_status", self.status)
        oppnp.on_ui(lambda: self.model.fireTableDataChanged())

    def clear_status(self):
        if self.busy:
            return
        self.status.clear()
        self.settings.set("machine_cal_status", self.status)
        self.model.fireTableDataChanged()

    def request_stop(self):
        self.stop_flag = True
        self.say("Stop requested: the run stops after the current step (for an emergency use OpenPnP's stop / disable).")

    def close(self):
        if self.busy:
            self.request_stop()
            if self.answer == "waiting":
                self.answer_with("Cancel")
        self.frame.dispose()

    def start(self, run_all):
        if self.busy:
            return
        i = self.table.getSelectedRow()
        if i < 0:
            return
        try:
            opts = self.options()
        except ValueError as e:
            self.say(str(e))
            return
        if not oppnp.confirm_ready(machine, gui, self.frame, "Cannot calibrate"):
            return
        keys = [s.key for s in machinecal.STEPS[i:]] if run_all else [machinecal.STEPS[i].key]
        if self.cal is None:
            self.cal = machinecal.Calibrator(machine, self, opts, oppnp.lumen_dir(scripting))
        self.cal.opt = opts
        if keys[0] != "prepare" and not machine.isHomed():
            self.say("The machine is not homed: start with step 1 (it checks the nozzles and the target first).")
            return
        self.busy = True
        self.stop_flag = False
        for btn in (self.all_btn, self.one_btn, self.reset_btn):
            btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        def steps():
            try:
                for k in keys:
                    if self.stop_flag:
                        self.say("stopped before '%s'" % machinecal.BY_KEY[k].title)
                        break
                    step = machinecal.BY_KEY[k]
                    self.set_status(k, "running")
                    self.say("== %s" % step.title)
                    try:
                        res = self.cal.run(k) or ""
                        self.set_status(k, "skipped" if res.startswith("skipped") else "done", res)
                        self.say("   %s" % res)
                    except machinecal.Stop as e:
                        self.set_status(k, "failed", str(e))
                        self.say("STOPPED: %s" % e)
                        break
                    except (Exception, JavaException) as e:
                        self.set_status(k, "failed", str(e))
                        self.say("FAILED: %s" % e)
                        break
                else:
                    if "verify" in keys:
                        self.say("Calibration complete. Next: File > New Job, then import the board (Feeders: Assign feeders, "
                                 "Job Readiness).")
            finally:
                try:
                    oppnp.run_machine_task(machine, lambda: machine.getDefaultHead().moveToSafeZ())
                except (Exception, JavaException):
                    pass

        def work():
            try:
                oppnp.at_speed(machine, oppnp.CAL_SPEED, steps, log=self.say)     # 50 %, previous speed restored
            except (Exception, JavaException) as e:
                self.say("FAILED: %s" % e)
            finally:
                self.busy = False

                def ui():
                    for btn in (self.all_btn, self.one_btn, self.reset_btn):
                        btn.setEnabled(True)
                    self.stop_btn.setEnabled(False)
                oppnp.on_ui(ui)
        oppnp.in_background(work)


PICS = {
    "prepare": ["cal-nozzles-level.png", "cal-home-free.png", "cal-disc-park.png", "cal-home-disc.png"],
    "primary_fid": ["cal-fid-circle.png", "cal-home-free.png"],
    "secondary_fid": ["cal-fid-circle.png"],
    "n1_primary": ["cal-z-contact.png"],
    "n1_secondary": ["cal-z-contact.png"],
    "n2_primary": ["cal-z-contact.png"],
    "bottom_cam": ["cal-tip-swap.png", "cal-bottom-circle.png"],
    "tips_back": ["cal-tip-swap.png"],
    "precise": ["cal-disc-park.png", "cal-home-disc.png"],
    "verify": ["cal-nozzles-level.png", "cal-home-free.png"],
}

MachineCal()
