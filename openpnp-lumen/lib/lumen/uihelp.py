# -*- coding: utf-8 -*-
"""In-tool help for the Lumen windows (Jython / Swing).

- wrap(root, key): a folding help panel ("Help" button -> text window with the description of the
  tool, its options and columns) above the window content, and tooltips on every option, button and
  input field (matched by the visible text, see lumen.helptext), and on the table column headers.
- missing(root, key): controls that have no description (used by the tests).
"""
from __future__ import absolute_import, division, print_function

from lumen import helptext

_W = 360            # tooltip width in px (HTML wrap)


def _html(text):
    return "<html><div style='width:%dpx'>%s</div></html>" % (_W, text)


def _tip_for(text, tips):
    t = (text or "").strip()
    if not t:
        return None
    best = None
    for k, v in tips.items():
        if t == k or t.startswith(k):
            if best is None or len(k) > len(best[0]):
                best = (k, v)
    return best[1] if best else None


def _walk(c):
    yield c
    if hasattr(c, "getComponents"):
        for k in c.getComponents():
            for x in _walk(k):
                yield x


def decorate(root, key):
    """Tooltips on buttons / checkboxes / labels (and the field after a label), column header tips."""
    from javax.swing import AbstractButton, JComboBox, JLabel, JSpinner, JTable, JTextField
    h = helptext.HELP[key]
    tips = h.get("tips", {})
    for c in list(_walk(root)):
        if isinstance(c, AbstractButton) or isinstance(c, JLabel):
            tip = _tip_for(c.getText(), tips)
            if tip:
                c.setToolTipText(_html(tip))
                if isinstance(c, JLabel):                   # the inputs right after a label explain themselves by it
                    sibs = list(c.getParent().getComponents()) if c.getParent() is not None else []
                    i = sibs.index(c) if c in sibs else -1
                    j = i + 1
                    while 0 <= i and j < len(sibs) and isinstance(sibs[j], (JTextField, JComboBox, JSpinner)):
                        sibs[j].setToolTipText(_html(tip))
                        j += 1
        if isinstance(c, JTable):
            column_tips(c, h.get("columns", {}))


def column_tips(table, cols):
    from javax.swing.table import JTableHeader

    class Header(JTableHeader):
        def getToolTipText(self, event=None):
            if event is None:                                # Swing also calls the no-argument form
                return JTableHeader.getToolTipText(self)
            i = self.columnAtPoint(event.getPoint())
            if i < 0:
                return None
            name = str(self.getColumnModel().getColumn(i).getHeaderValue())
            t = cols.get(name)
            return _html("<b>%s</b>: %s" % (name, t)) if t else None
    from javax.swing import JScrollPane, SwingUtilities
    hd = Header(table.getColumnModel())
    hd.setToolTipText("")                                    # registers the header with the tooltip manager
    table.setTableHeader(hd)
    sp = SwingUtilities.getAncestorOfClass(JScrollPane, table)
    if sp is not None:                                       # the scroll pane shows the header: give it the new one
        sp.setColumnHeaderView(hd)
    table.putClientProperty("lumen.column_tips", cols)


def help_panel(key):
    """Folding help: a button that opens / closes a text window with the tool's description."""
    from java.awt import BorderLayout, Dimension, FlowLayout
    from javax.swing import JButton, JEditorPane, JPanel, JScrollPane, SwingUtilities
    h = helptext.HELP[key]
    p = JPanel(BorderLayout())
    bar = JPanel(FlowLayout(FlowLayout.LEFT, 0, 0))
    btn = JButton(u"▸ Help: %s" % h["title"])
    btn.setToolTipText(_html("Show / hide the description of this tool, its options and columns."))
    bar.add(btn)
    p.add(bar, BorderLayout.NORTH)
    text = JEditorPane("text/html", "<html><body style='font-family:sans-serif;font-size:11pt'>%s%s</body></html>"
                       % (h["html"], _columns_html(h.get("columns", {}))))
    text.setEditable(False)
    text.setCaretPosition(0)
    sp = JScrollPane(text)
    sp.setPreferredSize(Dimension(900, 230))
    sp.setVisible(False)
    p.add(sp, BorderLayout.CENTER)

    def toggle(e):
        sp.setVisible(not sp.isVisible())
        btn.setText((u"▾" if sp.isVisible() else u"▸") + u" Help: %s" % h["title"])
        w = SwingUtilities.getWindowAncestor(p)
        if w is not None:
            w.pack()
        p.revalidate()
    btn.addActionListener(toggle)
    p.putClientProperty("lumen.help.toggle", btn)
    p.putClientProperty("lumen.help.text", sp)
    return p


def _columns_html(cols):
    if not cols:
        return ""
    rows = "".join("<tr><td valign='top'><b>%s</b></td><td>%s</td></tr>" % (k, v) for k, v in cols.items())
    return "<h3>Columns</h3><table cellpadding='2'>%s</table>" % rows


def wrap(root, key):
    """Content pane = help panel (top) + the tool's own content; all controls decorated."""
    from java.awt import BorderLayout
    from javax.swing import JPanel
    decorate(root, key)
    outer = JPanel(BorderLayout(0, 4))
    outer.add(help_panel(key), BorderLayout.NORTH)
    outer.add(root, BorderLayout.CENTER)
    return outer


def missing(root, key):
    """Visible controls without a tooltip and table columns without a description."""
    from javax.swing import AbstractButton, JComboBox, JScrollBar, JSpinner, JTable, JTextField
    out = []
    inner = set()                     # Swing's own parts: scroll bar arrows, combo box / spinner internals
    for c in _walk(root):
        if isinstance(c, (JScrollBar, JComboBox, JSpinner)):
            for k in list(_walk(c))[1:]:
                inner.add(k)
    for c in _walk(root):
        if c in inner:
            continue
        if isinstance(c, (AbstractButton, JTextField, JComboBox, JSpinner)) and not c.getToolTipText():
            out.append("%s '%s'" % (c.getClass().getSimpleName(), getattr(c, "getText", lambda: "")() if hasattr(c, "getText") else ""))
        if isinstance(c, JTable):
            cols = helptext.HELP[key].get("columns", {})
            for i in range(c.getColumnCount()):
                n = str(c.getColumnName(i))
                if n not in cols:
                    out.append("column '%s'" % n)
    return out
