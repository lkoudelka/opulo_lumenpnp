# -*- coding: utf-8 -*-
"""Placement Inspection: one window for the inspected placements (Jython, Swing).

The picture with the result drawn in (zoom / pan), << Previous / Next >> (also the arrow keys) through the table's
inspected rows in the table's order (optionally only the ones not OK), and the operator's decisions: Camera to part,
Set as OK, Set as NOT OK..., and Draw where the part is: when the detection was wrong, drag a rectangle around the
real part - the verdict then comes from the drawn position, the case is stored for learning (<lumen>/inspection/
learning/, the test set of tests/run_inspection_eval.sh) and, for a package checked with golden samples, the part
becomes one more golden sample (centred where it really is).

owner (scripts/Lumen/Placement_Inspection.py) provides: frame, root, log(text), table / model, title(x),
camera_to_part(x), set_ok(rows, parent), set_not_ok(rows, parent), changed(), run_name(x).
"""
from __future__ import absolute_import, division, print_function

from java.awt import BorderLayout, Dimension, FlowLayout
from java.awt.event import KeyEvent
from javax.swing import (AbstractAction, BorderFactory, BoxLayout, JButton, JCheckBox, JComponent, JEditorPane, JFrame,
                         JLabel, JOptionPane, JPanel, KeyStroke, WindowConstants)

from lumen import inspect as ins
from lumen import zoomview

BUTTONS = ["<< Previous", "Next >>", "Camera to part", "Set as OK", "Set as NOT OK...", "Draw where the part is",
           "Close"]


class _Key(AbstractAction):
    def __init__(self, fn):
        AbstractAction.__init__(self)
        self.fn = fn

    def actionPerformed(self, e):
        self.fn()


class Viewer(object):
    def __init__(self, owner, x):
        self.o, self.x = owner, x
        f = self.frame = JFrame("Inspection")
        f.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(6, 6, 6, 6))
        self.text = JEditorPane("text/html", "")
        self.text.setEditable(False)
        self.text.setPreferredSize(Dimension(1100, 70))
        root.add(self.text, BorderLayout.NORTH)
        self.view = zoomview.ImageView(None, size=(1100, 640))
        root.add(self.view, BorderLayout.CENTER)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        self.only_bad = JCheckBox("only not OK", False)
        self.buttons = {}
        acts = {"<< Previous": lambda: self.step(-1), "Next >>": lambda: self.step(1),
                "Camera to part": lambda: self.o.camera_to_part(self.x),
                "Set as OK": lambda: self.decide(self.o.set_ok), "Set as NOT OK...": lambda: self.decide(self.o.set_not_ok),
                "Draw where the part is": self.draw, "Close": f.dispose}
        b.add(self.only_bad)
        for name in BUTTONS:
            btn = JButton(name, actionPerformed=lambda e, fn=acts[name]: fn())
            self.buttons[name] = btn
            b.add(btn)
        root.add(b, BorderLayout.SOUTH)
        im, am = root.getInputMap(JComponent.WHEN_IN_FOCUSED_WINDOW), root.getActionMap()
        for key, name, fn in ((KeyEvent.VK_LEFT, "prev", lambda: self.step(-1)), (KeyEvent.VK_RIGHT, "next", lambda: self.step(1)),
                              (KeyEvent.VK_ESCAPE, "cancel", lambda: self.cancel_draw())):
            im.put(KeyStroke.getKeyStroke(key, 0), name)
            am.put(name, _Key(fn))
        f.setContentPane(root)
        self.show(x)
        f.pack()
        f.setLocationRelativeTo(owner.frame)
        f.setVisible(True)

    # -- rows ---------------------------------------------------------------------------------
    def rows(self):
        """Inspected rows in the table's order (sorted / filtered as shown), optionally only the ones not OK."""
        t, out = self.o.table, []
        for i in range(t.getRowCount()):
            x = self.o.model.rows[t.convertRowIndexToModel(i)]
            r = x.get("res") or {}
            if not (r.get("_image") is not None or r.get("image")):
                continue
            if self.only_bad.isSelected() and r.get("verdict", "").startswith("OK") and x is not self.x:
                continue
            out.append(x)
        return out

    def step(self, d):
        rows = self.rows()
        if not rows:
            return
        i = rows.index(self.x) if self.x in rows else -1
        j = i + d
        if not 0 <= j < len(rows):
            self.view.repaint()
            return
        self.show(rows[j])

    # -- one placement ------------------------------------------------------------------------
    def show(self, x):
        from java.io import File
        from javax.imageio import ImageIO
        self.cancel_draw()
        self.x = x
        res = x["res"]
        img = ins.annotate(res["_image"], res, self.o.title(x)) if res.get("_image") is not None else \
            ImageIO.read(File(res["image"]))
        self.view.set_image(img)
        size, upp = res.get("expect_size") or [None, None], res.get("upp")
        if size[0] and upp:                              # open zoomed on the part: ~4x its size fills the view
            self.view.zoom_centre(min(img.getWidth(), img.getHeight()) / (4.0 * max(size) / upp))
        rows = self.rows()
        pos = "%d of %d" % (rows.index(x) + 1, len(rows)) if x in rows else "-"
        self.frame.setTitle("Inspection: %s %s (%s)" % (x["ref"], x["part"], pos))
        self.text.setText(
            "<html><body style='font-family:sans-serif;font-size:11pt'><b>%s</b> %s (%s, board %s): <b>%s</b><br>"
            "Cyan dashed: where the part should be, cross = placement location; coloured box: the part found; magenta: "
            "drawn by hand. Detection wrong? <i>Draw where the part is</i>. &larr; / &rarr;: previous / next.</body>"
            "</html>" % (x["ref"], x["part"], x["package"], x["board"], _esc(res.get("verdict", ""))))
        self.buttons["<< Previous"].setEnabled(x in rows and rows.index(x) > 0)
        self.buttons["Next >>"].setEnabled(x in rows and rows.index(x) < len(rows) - 1)

    def decide(self, fn):
        fn([self.x], self.frame)
        self.show(self.x)

    # -- the operator draws the part ----------------------------------------------------------
    def draw(self):
        if self.x["res"].get("_image") is None:
            JOptionPane.showMessageDialog(self.frame, "The picture of this run is not in memory (inspect again).")
            return
        self.view.start_rect(self.drawn)
        self.text.setText("<html><body style='font-family:sans-serif;font-size:11pt'><b>Drag a rectangle around the "
                          "part</b> (its body with the terminations / leads; zoom with the wheel first). Esc: cancel."
                          "</body></html>")

    def cancel_draw(self):
        if self.view.on_rect is not None:
            self.view.start_rect(None)

    def drawn(self, x0, y0, x1, y1):
        self.view.on_rect = None
        if self.o.mark_detection(self.x, (x0, y0, x1, y1), self.frame):
            self.show(self.x)
        else:
            self.view.start_rect(None)
            self.show(self.x)


def ask_mark(parent, x, verdict, golden_possible):
    """The confirmation after drawing: (learn, golden) or None (cancelled)."""
    box = JPanel()
    box.setLayout(BoxLayout(box, BoxLayout.Y_AXIS))
    box.add(JLabel("<html><b>%s</b> (%s): %s</html>" % (x["ref"], x["part"], _esc(verdict))))
    learn = JCheckBox("save for learning (picture + where the part really is: test set for the detection)", True)
    box.add(learn)
    gold = JCheckBox("add as golden sample of package %s (centred where you drew it)" % x["package"], golden_possible)
    gold.setEnabled(golden_possible)
    box.add(gold)
    if JOptionPane.showConfirmDialog(parent, box, "Detection was wrong: the part is here", JOptionPane.OK_CANCEL_OPTION) \
            != JOptionPane.OK_OPTION:
        return None
    return learn.isSelected(), gold.isSelected()


def ask_limits(parent):
    """The operator's OK / CHECK limits (lumen.inspect.USER_LIMITS) with live examples: {key: value} or None."""
    from java.awt import GridBagConstraints, GridBagLayout, Insets
    from javax.swing import JSpinner, SpinnerNumberModel
    box = JPanel(GridBagLayout())
    c = GridBagConstraints()
    c.insets = Insets(3, 4, 3, 4)
    c.anchor = GridBagConstraints.WEST
    spins = {}
    ex = JLabel()

    def values():
        out = {}
        for k, label, unit, lo, hi, step in ins.USER_LIMITS:
            v = float(spins[k].getValue())
            out[k] = v / 100.0 if unit.startswith("%") else v
        return out

    def update(e=None):
        lim = dict(ins.LIMITS)
        lim.update(values())
        ex.setText("<html>A placement is OK when its offset is within both limits (and the total offset within the "
                   "larger one) and its rotation within the limit; otherwise CHECK.<br><br>With these values:<br>"
                   + "<br>".join(_esc(t) for t in ins.limits_text(lim)) + "</html>")
    row = 0
    for k, label, unit, lo, hi, step in ins.USER_LIMITS:
        pct = unit.startswith("%")
        f = 100.0 if pct else 1.0
        m = SpinnerNumberModel(round(ins.LIMITS[k] * f, 2), lo * f, hi * f, step * f)
        sp = spins[k] = JSpinner(m)
        sp.setPreferredSize(Dimension(80, sp.getPreferredSize().height))
        sp.addChangeListener(lambda e: update())
        c.gridy, c.gridx = row, 0
        box.add(JLabel(label), c)
        c.gridx = 1
        box.add(sp, c)
        c.gridx = 2
        box.add(JLabel("%s (default %g)" % (unit, ins.DEFAULT_LIMITS[k] * f)), c)
        row += 1

    def defaults(e):
        for k, label, unit, lo, hi, step in ins.USER_LIMITS:
            spins[k].setValue(ins.DEFAULT_LIMITS[k] * (100.0 if unit.startswith("%") else 1.0))
    c.gridy, c.gridx = row, 1
    box.add(JButton("Defaults", actionPerformed=defaults), c)
    c.gridy, c.gridx, c.gridwidth = row + 1, 0, 3
    box.add(ex, c)
    update()
    if JOptionPane.showConfirmDialog(parent, box, "Inspection limits: OK or CHECK", JOptionPane.OK_CANCEL_OPTION,
                                     JOptionPane.PLAIN_MESSAGE) != JOptionPane.OK_OPTION:
        return None
    return values()


def _esc(t):
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
