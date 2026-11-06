# Scripts > Lumen > Feeder Assistant   (new board / panel: which set-up feeder holds each part?)
#
# Another project names the same component differently ("C0402-0.1uF" vs "C_0402_1005Metric-100n"), so
# OpenPnP sees a new part without a feeder.  For every part of the open job the assistant reads the
# part name (kind, value, size, voltage / dielectric / tolerance, LED colour, part number) and lists
# the already set-up feeders: the MATCHING ones on top (best first, with why and warnings), then all
# other feeders.  Passives are proposed only with the same kind, value and size.  Nothing changes
# until YOU choose a feeder per part and press Apply (a confirmation lists every change):
# - "the job uses the feeder's part" (recommended): the job's placements of that part take the feeder's
#   part (its height, package, vision, nozzle tips stay as set up); the board / panel files are saved;
# - "the feeder gets the job's part": the feeder's part is replaced (machine configuration).
# Confirmed choices are remembered (~/.openpnp2/lumen/partmatch.json): the same name in a later
# project is proposed first.  "Identify" blinks the feeder's LED (no motion) to find the reel.
from __future__ import absolute_import, division, print_function

import json
import os
import sys

_LIB = os.path.join(str(scripting.getScriptsDirectory().getParent()), "lumen", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
import lumen.oppnp
import lumen.helptext
import lumen.uihelp
import lumen.jobinfo
import lumen.partmatch
import lumen.feedercheck
reload(lumen.oppnp)
reload(lumen.helptext)
reload(lumen.uihelp)
reload(lumen.jobinfo)
reload(lumen.partmatch)
reload(lumen.feedercheck)
from lumen import feedercheck, jobinfo, oppnp
from lumen import partmatch as pm
from lumen.oppnp import JavaException

from java.awt import BorderLayout, Color, Dimension, FlowLayout
from java.lang import Integer, String
from javax.swing import (BorderFactory, JButton, JCheckBox, JComboBox, JFrame, JLabel, JOptionPane, JPanel, JScrollPane,
                         JSplitPane, JTable, ListSelectionModel, WindowConstants)
from javax.swing.table import AbstractTableModel, DefaultTableCellRenderer

PCOLS = ["Part", "Refs", "Qty", "Read as", "Feeder now", "Best proposal", "Score", "Your choice"]
FCOLS = ["Score", "Feeder", "Slot", "Feeder part", "Read as", "Why", "Warnings", "Enabled"]
MODES = ["the job uses the feeder's part (recommended)", "the feeder gets the job's part"]
STRONG = 85


def short(refs, n=6):
    return ", ".join(refs[:n]) + (" +%d" % (len(refs) - n) if len(refs) > n else "")


class PartModel(AbstractTableModel):
    def __init__(self):
        AbstractTableModel.__init__(self)
        self.rows = []

    def getRowCount(self):
        return len(self.rows)

    def getColumnCount(self):
        return len(PCOLS)

    def getColumnName(self, c):
        return PCOLS[c]

    def getColumnClass(self, c):
        return Integer if c in (2, 6) else String

    def repaint_rows(self):
        """Repaint keeping the selected row (fireTableDataChanged would clear it)."""
        if self.rows:
            self.fireTableRowsUpdated(0, len(self.rows) - 1)

    def getValueAt(self, r, c):
        x = self.rows[r]
        best = x["cands"][0] if x["cands"] else None
        if c == 2:
            return Integer(len(x["refs"]))
        if c == 6:
            return Integer(best[0]) if best else None
        if c == 5:
            return ("%s (%s)" % (x["fname"](best[1]), best[2])) if best else "no matching feeder"
        if c == 7:
            return x["fname"](x["choice"]) if x.get("choice") else "-"
        return {0: x["id"], 1: short(x["refs"]), 3: pm.summary(x["desc"]), 4: ", ".join(x["now"]) or "-"}[c]


class FeederModel(AbstractTableModel):
    def __init__(self):
        AbstractTableModel.__init__(self)
        self.rows = []

    def getRowCount(self):
        return len(self.rows)

    def getColumnCount(self):
        return len(FCOLS)

    def getColumnName(self, c):
        return FCOLS[c]

    def getColumnClass(self, c):
        return String

    def getValueAt(self, r, c):
        x = self.rows[r]
        if x.get("sep"):
            return "other feeders (no match by name)" if c == 1 else ""
        f = x["feeder"]
        slot = f.getSlotAddress() if hasattr(f, "getSlotAddress") else None
        return ["" if x["score"] is None else unicode(x["score"]), f.getName(), "" if slot is None else unicode(slot), unicode(f.getPart().getId()),
                pm.summary(x["desc"]), x.get("why", ""), "; ".join(x.get("warn", [])), "yes" if f.isEnabled() else "no"][c]


class ScoreRenderer(DefaultTableCellRenderer):
    """Matching feeders: green (strong), yellow (check), grey (weak); the separator and the rest white."""

    def __init__(self, model):
        DefaultTableCellRenderer.__init__(self)
        self.model = model

    def getTableCellRendererComponent(self, table, value, sel, foc, row, col):
        c = DefaultTableCellRenderer.getTableCellRendererComponent(self, table, value, sel, foc, row, col)
        if not sel:
            x = self.model.rows[row]
            s = x.get("score")
            c.setBackground(Color.WHITE if s is None else Color(200, 240, 200) if s >= STRONG and not x.get("warn")
                            else Color(255, 243, 200) if s >= 40 else Color(235, 235, 235))
        return c


class FeederAssistant(object):
    def __init__(self):
        self.log = oppnp.FileLog(scripting, "feeder-assistant")
        self.store_path = os.path.join(oppnp.lumen_dir(scripting), "partmatch.json")
        self.store = self.load_store()
        self.pmodel = PartModel()
        self.fmodel = FeederModel()
        f = self.frame = JFrame("Feeder assistant (new board / panel)")
        f.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8))
        top = JPanel(FlowLayout(FlowLayout.LEFT))
        self.only = JCheckBox("only parts without an enabled feeder", True, actionPerformed=lambda e: self.refresh())
        top.add(self.only)
        self.info = JLabel(" ")
        top.add(self.info)
        root.add(top, BorderLayout.NORTH)
        self.ptable = JTable(self.pmodel)
        self.ptable.setAutoCreateRowSorter(True)
        self.ptable.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        self.ptable.getSelectionModel().addListSelectionListener(lambda e: None if e.getValueIsAdjusting() else self.show_feeders())
        for i, w in enumerate((230, 150, 40, 190, 160, 330, 50, 200)):
            self.ptable.getColumnModel().getColumn(i).setPreferredWidth(w)
        sp1 = JScrollPane(self.ptable)
        sp1.setPreferredSize(Dimension(1380, 250))
        self.ftable = JTable(self.fmodel)                          # NOT sortable: matching feeders stay on top
        self.ftable.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        rend = ScoreRenderer(self.fmodel)
        for i, w in enumerate((45, 200, 40, 250, 170, 250, 330, 55)):
            self.ftable.getColumnModel().getColumn(i).setPreferredWidth(w)
            self.ftable.getColumnModel().getColumn(i).setCellRenderer(rend)
        sp2 = JScrollPane(self.ftable)
        sp2.setPreferredSize(Dimension(1380, 260))
        lower = JPanel(BorderLayout(4, 4))
        self.flabel = JLabel("Select a part above: the feeders that match are listed first.")
        lower.add(self.flabel, BorderLayout.NORTH)
        lower.add(sp2, BorderLayout.CENTER)
        fb = JPanel(FlowLayout(FlowLayout.LEFT))
        fb.add(JButton("Choose this feeder for the part", actionPerformed=lambda e: self.choose()))
        fb.add(JButton("Identify (blink LED)", actionPerformed=lambda e: self.identify()))
        lower.add(fb, BorderLayout.SOUTH)
        split = JSplitPane(JSplitPane.VERTICAL_SPLIT, sp1, lower)
        split.setResizeWeight(0.5)
        root.add(split, BorderLayout.CENTER)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        b.add(JButton("Pre-select strong matches", actionPerformed=lambda e: self.preselect()))
        b.add(JButton("Clear choice", actionPerformed=lambda e: self.clear()))
        b.add(JLabel("Apply as:"))
        self.mode = JComboBox(MODES)
        b.add(self.mode)
        b.add(JButton("Apply choices...", actionPerformed=lambda e: self.apply()))
        b.add(JButton("Close", actionPerformed=lambda e: f.dispose()))
        root.add(b, BorderLayout.SOUTH)
        f.setContentPane(lumen.uihelp.wrap(root, "feeder_assist"))
        self.refresh()
        f.pack()
        f.setLocationRelativeTo(gui)
        f.setVisible(True)

    # -- data -------------------------------------------------------------------------------
    def load_store(self):
        try:
            fh = open(self.store_path)
            try:
                d = json.load(fh)
            finally:
                fh.close()
        except (IOError, OSError, ValueError):
            d = {}
        d.setdefault("aliases", {})
        return d

    def save_store(self):
        tmp = self.store_path + ".tmp"
        fh = open(tmp, "w")
        try:
            json.dump(self.store, fh, indent=1, sort_keys=True)
        finally:
            fh.close()
        os.rename(tmp, self.store_path)

    @staticmethod
    def describe_part(part, refs=()):
        """unicode(): part names may contain non-ASCII (1\u00b5F, 10\u03a9); str() of those fails in Jython 2."""
        pk = part.getPackage()
        return pm.describe(unicode(part.getId()), unicode(part.getName() or ""), unicode(pk.getId()) if pk is not None else u"", refs)

    def refresh(self):
        old = dict((x["id"], x.get("choice")) for x in self.pmodel.rows)
        self.feeders = dict((unicode(f.getId()), f) for f in machine.getFeeders() if f.getPart() is not None)
        fdesc = [(k, self.describe_part(f.getPart())) for k, f in sorted(self.feeders.items())]
        self.fdesc = dict(fdesc)
        job = gui.getJobTab().getJob()
        parts = {}
        if job is not None:
            for bl, pl, placed in jobinfo.job_placements(job):
                p = pl.getPart()
                if p is None:
                    continue
                e = parts.setdefault(unicode(p.getId()), {"part": p, "refs": [], "holders": []})
                e["refs"].append(unicode(pl.getId()))
                h = bl.getPlacementsHolder()
                if h not in e["holders"]:
                    e["holders"].append(h)
        rows = []
        for pid, e in sorted(parts.items()):
            now = [f for f in self.feeders.values() if f.getPart() == e["part"]]
            if self.only.isSelected() and any(f.isEnabled() for f in now):
                continue
            desc = self.describe_part(e["part"], e["refs"])
            cands = [c for c in pm.rank(desc, fdesc, self.store["aliases"]) if self.feeders[c[1]].getPart() != e["part"]]
            rows.append({"id": pid, "part": e["part"], "refs": e["refs"], "holders": e["holders"], "desc": desc,
                         "now": [f.getName() + ("" if f.isEnabled() else " (disabled)") for f in now], "cands": cands,
                         "choice": old.get(pid), "fname": self.fname})
        self.pmodel.rows = rows
        self.pmodel.fireTableDataChanged()                         # new rows
        strong = len([x for x in rows if x["cands"] and x["cands"][0][0] >= STRONG])
        self.info.setText("%d part(s) listed: %d with a strong proposal, %d with a weaker one, %d with none. Choose per part, then Apply."
                          % (len(rows), strong, len([x for x in rows if x["cands"]]) - strong,
                             len([x for x in rows if not x["cands"]])))
        self.show_feeders()

    def fname(self, fid):
        f = self.feeders.get(fid)
        return f.getName() if f is not None else fid

    def selected_part(self):
        i = self.ptable.getSelectedRow()
        return self.pmodel.rows[self.ptable.convertRowIndexToModel(i)] if i >= 0 else None

    def show_feeders(self):
        x = self.selected_part()
        rows = []
        if x is not None:
            seen = set()
            for s, fid, why, warn in x["cands"]:
                rows.append({"feeder": self.feeders[fid], "fid": fid, "score": s, "why": why, "warn": warn, "desc": self.fdesc[fid]})
                seen.add(fid)
            rows.append({"sep": True})
            rest = [(f.getSlotAddress() if hasattr(f, "getSlotAddress") and f.getSlotAddress() is not None else 9999, f.getName(), fid)
                    for fid, f in self.feeders.items() if fid not in seen]
            for _, _, fid in sorted(rest):
                rows.append({"feeder": self.feeders[fid], "fid": fid, "score": None, "desc": self.fdesc[fid]})
            self.flabel.setText("%s (%s, read as %s): %d matching feeder(s) on top, then all other feeders."
                                % (x["id"], short(x["refs"], 4), pm.summary(x["desc"]), len(x["cands"])))
        self.fmodel.rows = rows
        self.fmodel.fireTableDataChanged()

    # -- choices -------------------------------------------------------------------------------
    def choose(self):
        x = self.selected_part()
        i = self.ftable.getSelectedRow()
        if x is None or i < 0 or self.fmodel.rows[i].get("sep"):
            JOptionPane.showMessageDialog(self.frame, "Select a part above and a feeder below.")
            return
        r = self.fmodel.rows[i]
        if r["score"] is None:
            if JOptionPane.showConfirmDialog(self.frame, "%s does not match %s by name (%s vs %s).\nChoose it anyway?" % (
                    r["feeder"].getName(), x["id"], pm.summary(r["desc"]), pm.summary(x["desc"])), "Not a proposal",
                    JOptionPane.YES_NO_OPTION) != JOptionPane.YES_OPTION:
                return
        x["choice"] = r["fid"]
        self.pmodel.repaint_rows()
        self.info.setText("%s -> %s (not applied yet)" % (x["id"], r["feeder"].getName()))

    def preselect(self):
        n = 0
        for x in self.pmodel.rows:
            if not x.get("choice") and x["cands"] and x["cands"][0][0] >= STRONG and not x["cands"][0][3] \
                    and (len(x["cands"]) == 1 or x["cands"][1][0] < x["cands"][0][0]) \
                    and not self.extra_warnings(x, self.feeders[x["cands"][0][1]], disabled=False):
                x["choice"] = x["cands"][0][1]
                n += 1
        self.pmodel.repaint_rows()
        self.info.setText("%d strong, unambiguous proposal(s) pre-selected - check them, then Apply" % n)

    def clear(self):
        x = self.selected_part()
        if x is not None:
            x["choice"] = None
            self.pmodel.repaint_rows()

    def identify(self):
        i = self.ftable.getSelectedRow()
        if i < 0 or self.fmodel.rows[i].get("sep"):
            JOptionPane.showMessageDialog(self.frame, "Select a feeder below.")
            return
        f = self.fmodel.rows[i]["feeder"]
        if not oppnp.confirm_ready(machine, gui, self.frame, "Cannot identify"):
            return

        def work():
            try:
                addr = oppnp.run_machine_task(machine, lambda: feedercheck.identify(machine, f))
                oppnp.on_ui(lambda: self.info.setText("%s (address %d) is blinking" % (f.getName(), addr)))
            except (Exception, JavaException) as e:
                oppnp.on_ui(lambda: self.info.setText("identify failed: %s" % e))
        oppnp.in_background(work)

    # -- apply ---------------------------------------------------------------------------------
    def plan(self):
        """[(row, feeder, [warnings])] of the chosen assignments."""
        out = []
        for x in self.pmodel.rows:
            if not x.get("choice"):
                continue
            f = self.feeders[x["choice"]]
            fp = f.getPart()
            warn = []
            c = [c for c in x["cands"] if c[1] == x["choice"]]
            warn += c[0][3] if c else ["chosen although the names do not match"]
            warn += self.extra_warnings(x, f)
            out.append((x, f, warn))
        return out

    @staticmethod
    def extra_warnings(x, f, disabled=True):
        """Beyond the name match: another package name on a part where orientation can matter (and a disabled feeder)."""
        warn = []
        jpk, fpk = x["part"].getPackage(), f.getPart().getPackage()
        if jpk is not None and fpk is not None and unicode(jpk.getId()) != unicode(fpk.getId()) and x["desc"]["kind"] not in pm.PASSIVE:
            warn.append("package %s vs %s: check the orientation (Orientation Setup)" % (jpk.getId(), fpk.getId()))
        if disabled and not f.isEnabled():
            warn.append("the feeder is disabled (enable it before the job)")
        return warn

    def apply(self):
        plan = self.plan()
        if not plan:
            JOptionPane.showMessageDialog(self.frame, "Choose a feeder for at least one part first.")
            return
        mode = self.mode.getSelectedIndex()
        lines = []
        files = set()
        for x, f, warn in plan:
            if mode == 0:
                lines.append("%s (%s): placements use the feeder's part %s  [%s]" % (x["id"], short(x["refs"], 4), f.getPart().getId(), f.getName()))
                for h in x["holders"]:
                    files.add(unicode(h.getFile()) if h.getFile() is not None else unicode(h.getName()))
            else:
                lines.append("%s: feeder %s gets this part (was %s)" % (x["id"], f.getName(), f.getPart().getId()))
            for w in warn:
                lines.append("      ! " + w)
        tail = ("\n\nBoard / panel files that will be SAVED:\n  " + "\n  ".join(sorted(files))) if mode == 0 else \
            "\n\nThe machine configuration changes (saved by OpenPnP: File > Save Configuration, or on exit)."
        if JOptionPane.showConfirmDialog(self.frame, "Apply %d assignment(s)?\n\n%s%s" % (len(plan), "\n".join(lines), tail),
                                         "Apply feeder choices", JOptionPane.OK_CANCEL_OPTION) != JOptionPane.OK_OPTION:
            return
        done, errors = self.do_apply(plan, mode)
        self.info.setText("%d applied%s" % (done, ("; ERRORS: " + "; ".join(errors)) if errors else ""))
        if errors:
            JOptionPane.showMessageDialog(self.frame, "Not everything was applied:\n" + "\n".join(errors))
        self.refresh()

    def do_apply(self, plan, mode):
        from org.openpnp.model import Board, Configuration
        done, errors, holders = 0, [], []
        for x, f, warn in plan:
            fp = f.getPart()
            try:
                if mode == 0:
                    for h in x["holders"]:
                        for pl in h.getPlacements():
                            if pl.getPart() == x["part"]:
                                pl.setPart(fp)
                        if h not in holders:
                            holders.append(h)
                    self.store["aliases"][x["id"]] = unicode(fp.getId())
                    self.log("%s (%s) -> placements use %s from %s" % (x["id"], short(x["refs"], 99), fp.getId(), f.getName()))
                else:
                    old = fp.getId()
                    f.setPart(x["part"])
                    self.log("feeder %s: part %s -> %s" % (f.getName(), old, x["id"]))
                x["choice"] = None
                done += 1
            except (Exception, JavaException) as e:
                errors.append("%s: %s" % (x["id"], e))
        for h in holders:
            try:
                h.setDirty(True)
                if isinstance(h, Board):
                    Configuration.get().saveBoard(h)
                else:
                    Configuration.get().savePanel(h)
                self.log("saved %s" % h.getFile())
            except (Exception, JavaException) as e:
                errors.append("saving %s: %s" % (h.getFile(), e))
        if mode == 0:
            self.save_store()
        return done, errors


FeederAssistant()
