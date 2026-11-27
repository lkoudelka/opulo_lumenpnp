# -*- coding: utf-8 -*-
"""Go to where a job problem is fixed (Jython): the OpenPnP tab and row, or the Lumen Feeders window.

jobinfo.readiness() gives every problem row a list of fixes, {kind, text, target}:
- "feeder":  a feeder of the part that OpenPnP will not use (switched off, no slot, no offset, not on the bus)
             -> Feeders tab, that feeder selected (its settings below the table);
- "assign":  no feeder has the part -> Scripts > Lumen > Feeders, tab Assign feeders, the part selected;
- "package": nozzle tip compatibility or body size -> Packages tab, the package selected;
- "part":    part height -> Parts tab, the part selected;
- "count":   a tray / strip feeder that is empty or holds fewer parts than the job needs -> the refill dialog
             (ask_count / apply_count: parts in it now, switch it on again);
- "measure": a package without body size -> measure it with the bottom camera (lumen.sizemeasure; Job Readiness
             asks before the pick and before applying).
OpenPnP's tables have a search field; a leftover search text would hide the row, so it is cleared first (as
OpenPnP's own "show feeder for part" does).
"""
from __future__ import absolute_import, division, print_function

TABS = {"feeder": "Feeders", "package": "Packages", "part": "Parts"}


def fix(kind, text, target):
    return {"kind": kind, "text": text, "target": target}


def _clear_search(panel):
    """Empty the panel's search field and re-filter (private searchTextField / search() of OpenPnP's panels)."""
    try:
        c = panel.getClass()
        fld = c.getDeclaredField("searchTextField")
        fld.setAccessible(True)
        tf = fld.get(panel)
        if tf is not None and str(tf.getText() or ""):
            tf.setText("")
            m = c.getDeclaredMethod("search")
            m.setAccessible(True)
            m.invoke(panel)
    except:                                              # bare: Java reflection exceptions too; selecting still works
        pass


def show(gui, f):
    """Open the OpenPnP tab of fix f with its row selected.  'assign' is not handled here (open_assign).
    Returns the text for a status line."""
    kind, t = f["kind"], f["target"]
    if kind == "feeder":
        panel = gui.getFeedersTab()
        gui.showTab("Feeders")
        _clear_search(panel)
        panel.selectFeederInTable(t)
    elif kind == "package":
        panel = gui.getPackagesTab()
        gui.showTab("Packages")
        _clear_search(panel)
        panel.selectPackageInTable(t)
    elif kind == "part":
        panel = gui.getPartsTab()
        gui.showTab("Parts")
        _clear_search(panel)
        panel.selectPartInTable(t)
    else:
        raise ValueError("no OpenPnP tab for a fix of kind %s" % kind)
    return "OpenPnP %s tab: %s selected - %s" % (TABS[kind], t.getName() if kind == "feeder" else t.getId(), f["text"])


def ask_count(parent, f, part_id, needed):
    """Refill dialog for a feeder that counts its parts: (parts left, switch on) or None (cancelled)."""
    from javax.swing import BoxLayout, JCheckBox, JLabel, JOptionPane, JPanel, JSpinner, SpinnerNumberModel
    from lumen import jobinfo
    left, cap = jobinfo.stock(f)
    box = JPanel()
    box.setLayout(BoxLayout(box, BoxLayout.Y_AXIS))
    box.add(JLabel("<html><b>%s</b> (part %s, id %s)<br>%d of %d picked, %d left; the job needs %d more.<br><br>"
                   "Parts in the feeder now:</html>" % (f.getName(), part_id, f.getId(), cap - left, cap, left, needed)))
    sp = JSpinner(SpinnerNumberModel(cap, 0, cap, 1))
    box.add(sp)
    box.add(JLabel("<html><br>The feeder uses its pockets in order and continues after the ones counted as picked:<br>"
                   "with fewer parts than %d, put them in the last pockets. <i>Camera to feeder</i> shows the next "
                   "pick.</html>" % cap))
    on = JCheckBox("switch the feeder on (OpenPnP switched it off when it ran empty)", not f.isEnabled())
    on.setEnabled(not f.isEnabled())
    box.add(on)
    if JOptionPane.showConfirmDialog(parent, box, "Refill / set count", JOptionPane.OK_CANCEL_OPTION) \
            != JOptionPane.OK_OPTION:
        return None
    return int(sp.getValue()), on.isSelected()


def apply_count(f, part_id, left, switch_on):
    """Set the feeder's count (and switch it on); returns the text for the status line / log."""
    from lumen import jobinfo
    cap = jobinfo.stock(f)[1]
    old = jobinfo.set_stock(f, left)
    if switch_on and not f.isEnabled():
        f.setEnabled(True)
    return "%s (%s, id %s): picked %d -> %d of %d (%d left)%s" % (
        f.getName(), part_id, f.getId(), old, f.getFeedCount(), cap, left,
        ", switched on" if switch_on else "" if f.isEnabled() else ", still switched off")


def open_assign(scripting, part_id):
    """Scripts > Lumen > Feeders on the tab Assign feeders with part_id selected."""
    import os
    from java.io import File
    from java.util import HashMap
    path = os.path.join(str(scripting.getScriptsDirectory()), "Lumen", "Feeders.py")
    g = HashMap()
    g.put("lumen_focus", {"tab": "assign", "part": part_id})
    scripting.execute(File(path), g)
    return "Feeders window, tab Assign feeders: %s selected" % part_id


def next_problem(rows, at):
    """(row index, fix index) after position at = (row, fix) or None, through all rows' fixes in order; wraps
    around.  None when no row has a fix."""
    flat = [(i, j) for i, r in enumerate(rows) for j in range(len(r.get("fixes") or []))]
    if not flat:
        return None
    if at is None:
        return flat[0]
    later = [p for p in flat if p > tuple(at)]
    return later[0] if later else flat[0]
