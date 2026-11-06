# Scripts > Lumen > Orientation Setup   (optional helper, study §2)
#
# For the parts of the open job where orientation matters: where is the pin-1 / polarity
# mark on the part in the FEEDER (left square, seen from above in machine coordinates, as in
# the top camera view) and in the CAD footprint at 0 deg (right square)?  From the two marks
# the rotation in the feeder is calculated and can be applied to the feeder.
# The CAD mark can be detected automatically from the KiCad .kicad_pcb or from KiCad copper
# Gerbers with X2 attributes.  With only a position file (.pos) it is found by footprint name:
# footprint libraries (.pretty), the OpenPnP package footprint, or the footprint table that
# every import and confirmation fills (pin 1 of a footprint is the same on every board).
# Every mark is confirmed by you in the two squares, and the list
# shows what is confirmed and whether the feeder rotation is correct.  Nothing is changed
# without "Apply".
from __future__ import absolute_import, division, print_function

import math
import os
import sys

_LIB = os.path.join(str(scripting.getScriptsDirectory().getParent()), "lumen", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
import lumen.oppnp
import lumen.jobinfo
import lumen.orientation
reload(lumen.oppnp)
reload(lumen.jobinfo)
reload(lumen.orientation)
from lumen import jobinfo, oppnp
from lumen import orientation as ori
from lumen.oppnp import JavaException

from java.awt import (BasicStroke, BorderLayout, Color, Dimension, FlowLayout, Font, FontMetrics, Graphics2D,
                      GridLayout, RenderingHints)
from java.awt.event import MouseAdapter
from java.lang import String
from javax.swing import (BorderFactory, JButton, JCheckBox, JFileChooser, JFrame, JLabel, JOptionPane, JPanel,
                         JScrollPane, JTable, ListSelectionModel, WindowConstants)
from javax.swing.filechooser import FileNameExtensionFilter
from javax.swing.table import AbstractTableModel, DefaultTableCellRenderer
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
            k = s * 0.44 / ext
            for n, x, y in self.pads:
                if self.pads_dim:
                    g.setColor(Color(225, 120, 120) if n == "1" else Color(215, 190, 120))
                else:
                    g.setColor(Color(200, 40, 40) if n == "1" else Color(184, 134, 11))
                pw = max(3, int(s * (0.07 if len(self.pads) <= 4 else 0.025)))
                g.fillRect(int(cx + x * k - pw / 2), int(cy - y * k - pw / 2), pw, pw)
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
        f.setContentPane(root)
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
        self._parsed = {}          # (source, board) -> {ref: cad info}
        self.fp_conflicts = {}
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
        srow.add(JButton("Import KiCad board (.kicad_pcb)...", actionPerformed=lambda e: self.import_file("kicad")))
        srow.add(JButton("Import copper Gerber (X2)...", actionPerformed=lambda e: self.import_file("gerber")))
        srow.add(JButton("Footprint library (.pretty)...", actionPerformed=lambda e: self.add_library()))
        self.only = JCheckBox("only parts where orientation matters", True, actionPerformed=lambda e: self.refresh())
        srow.add(self.only)
        self.sources = JLabel(" ")
        srow.add(self.sources)
        top.add(srow, BorderLayout.SOUTH)
        root.add(top, BorderLayout.NORTH)
        self.table = JTable(self.model)
        self.table.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        rend = StatusRenderer(self.model)
        for i, w in enumerate((140, 170, 120, 80, 150, 170, 100, 50, 70, 330)):
            self.table.getColumnModel().getColumn(i).setPreferredWidth(w)
            self.table.getColumnModel().getColumn(i).setCellRenderer(rend)
        sp = JScrollPane(self.table)
        sp.setPreferredSize(Dimension(1380, 380))
        root.add(sp, BorderLayout.CENTER)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        b.add(JButton("Check selected (two squares)...", actionPerformed=lambda e: self.check()))
        b.add(JButton("Toggle 'orientation matters'", actionPerformed=lambda e: self.toggle()))
        b.add(JButton("Refresh", actionPerformed=lambda e: self.refresh()))
        b.add(JButton("Close", actionPerformed=lambda e: f.dispose()))
        root.add(b, BorderLayout.SOUTH)
        f.setContentPane(root)
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
        bkey = self.board_key(bl)
        cad = {}
        for src in self.sources_for(bkey):
            found = self.load_source(src, bl, quiet=True)
            for ref, i in found.items():
                if ref not in cad or src.startswith("kicad:"):
                    cad[ref] = i
        return cad

    def load_source(self, src, bl, quiet=False):
        key = (src, self.board_key(bl) if src.startswith("gerber:") else None)
        if key in self._parsed:
            return self._parsed[key]
        kind, path = src.split(":", 1)
        try:
            if kind == "kicad":
                found = ori.parse_kicad_pcb(path)
            else:
                pl = {}
                for p in bl.getPlacementsHolder().getPlacements():
                    pk = p.getPart().getPackage().getId() if p.getPart() and p.getPart().getPackage() else ""
                    pl[str(p.getId())] = (p.getLocation().getRotation(), pk)
                found = ori.gerber_cad_info(ori.parse_gerber_pins(path), pl)
                for i in found.values():
                    i["source"] = "gerber:" + os.path.basename(path)
            self._parsed[key] = found
            good, bad = ori.learn_footprints(found.values())       # pin 1 by footprint name, for later boards
            for k, i in good.items():
                c = self.store.set_footprint(k, i, i["source"], False)
                if c:
                    self.fp_conflicts[k] = "%s says %s" % (i["source"], c)
            for k, dots in bad.items():
                self.fp_conflicts[k] = "refs disagree (%s) in %s" % (", ".join(dots), os.path.basename(path))
            if not quiet:
                self.log("imported %s: %d footprints, %d with pin 1" % (path, len(found),
                                                                        len([i for i in found.values() if i["dot"]])))
            return found
        except (Exception, JavaException) as e:
            if not quiet:
                JOptionPane.showMessageDialog(self.frame, "Cannot read %s: %s" % (path, e))
            self._parsed[key] = {}
            return {}

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
        """Import for the board(s) of the open job (refs are only meaningful on their own board)."""
        job = gui.getJobTab().getJob()
        bls = [bl for bl in (job.getBoardLocations() if job is not None else []) if bl.getBoard() is not None]
        if not bls:
            JOptionPane.showMessageDialog(self.frame, "Open the job with the board first.")
            return
        src = "%s:%s" % (kind, path)
        for k in [k for k in self._parsed if k[0] == src]:
            del self._parsed[k]
        n = 0
        for bl in bls:
            n = max(n, len(self.load_source(src, bl)))
            if n:
                lst = self.store.data["board_sources"].setdefault(self.board_key(bl), [])
                if src not in lst:
                    lst.append(src)
        if kind == "gerber" and n == 0:
            JOptionPane.showMessageDialog(self.frame, "No pin attributes found. Use a COPPER layer exported by KiCad\n"
                                          "with 'Use extended X2 format' and 'Include netlist attributes'.")
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
                ent = by_part.setdefault(str(part.getId()), (part, [], []))
                ent[1].append(str(pl.getId()))
                if str(pl.getId()) in cads[bk]:
                    ent[2].append(cads[bk][str(pl.getId())])
        for pid, (part, refs, infos) in sorted(by_part.items()):
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
                x["need"], x["status"] = need, note + st
                rows.append(x)
        shown = [x for x in rows if not self.only.isSelected() or x["matters"] is not False]
        self.model.rows = shown
        self.model.fireTableDataChanged()
        rel = [x for x in rows if x["matters"] is not False]
        ok = len([x for x in rel if x["status"].startswith("CORRECT")])
        bad = len([x for x in rel if "MISMATCH" in x["status"]])
        self.summary.setText("<html>%d part/feeder row(s) where orientation matters: <font color='green'>%d correct "
                             "(confirmed)</font>, <font color='red'>%d mismatch</font>, %d to check</html>" % (
                                 len(rel), ok, bad, len(rel) - ok - bad))
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

    def toggle(self):
        x = self.selected()
        if x is None:
            return
        p = self.store.part(x["part_id"])
        p["matters"] = not (x["matters"] is not False)
        self.store.save()
        self.refresh()


OrientationSetup()
