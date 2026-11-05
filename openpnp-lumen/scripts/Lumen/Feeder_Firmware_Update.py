# Scripts > Lumen > Feeder Firmware Update
#
# Update Photon feeder firmware over the machine's RS-485 bus (Marlin M485), with the
# feeders mounted and OpenPnP connected.  Pick the firmware binary, scan the bus, tick
# the feeders (all / some), update.  Needs feeders that already have the bus loader
# (one-time dongle flash of the *-factory.bin); others are listed but cannot be ticked.
from __future__ import absolute_import, division, print_function

import os
import sys

_LIB = os.path.join(str(scripting.getScriptsDirectory().getParent()), "lumen", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
import lumen.photon
import lumen.oppnp
reload(lumen.photon)
reload(lumen.oppnp)
from lumen import photon, oppnp
from lumen.oppnp import JavaException

from java.awt import BorderLayout, Dimension, FlowLayout, Font
from java.io import File
from java.lang import Boolean, String
from javax.swing import (BorderFactory, BoxLayout, JButton, JFileChooser, JFrame, JLabel,
                         JOptionPane, JPanel, JProgressBar, JScrollPane, JSpinner, JTable,
                         JTextArea, JTextField, SpinnerNumberModel, WindowConstants)
from javax.swing.filechooser import FileNameExtensionFilter
from javax.swing.table import AbstractTableModel

COLS = ["Update", "Address", "OpenPnP feeder", "UUID", "Firmware", "Bus update", "Result"]


class FeederModel(AbstractTableModel):
    def __init__(self):
        AbstractTableModel.__init__(self)
        self.rows = []          # dicts
        self.locked = False

    def getRowCount(self):
        return len(self.rows)

    def getColumnCount(self):
        return len(COLS)

    def getColumnName(self, c):
        return COLS[c]

    def getColumnClass(self, c):
        return Boolean if c == 0 else String

    def isCellEditable(self, r, c):
        return c == 0 and not self.locked and self.rows[r]["info"].updatable

    def getValueAt(self, r, c):
        row = self.rows[r]
        info = row["info"]
        return [Boolean(row["sel"]), str(info.addr), row["name"], info.uuid_hex or "-",
                info.version or ("(bus loader)" if info.mode == "pbl" else "?"),
                info.update_status(), row["result"]][c]

    def setValueAt(self, v, r, c):
        if c == 0:
            self.rows[r]["sel"] = bool(v)
            self.fireTableCellUpdated(r, c)

    def set_all(self, pred):
        for row in self.rows:
            row["sel"] = bool(row["info"].updatable and pred(row))
        self.fireTableDataChanged()


class UpdateDialog(object):
    def __init__(self):
        self.settings = oppnp.Settings(scripting)
        self.log = oppnp.FileLog(scripting, "feeder-update")
        self.image = None
        self.cancel = False
        self.busy = False
        self.model = FeederModel()

        f = self.frame = JFrame("Photon feeder firmware update (bus)")
        f.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8))

        top = JPanel()
        top.setLayout(BoxLayout(top, BoxLayout.Y_AXIS))
        row = JPanel(FlowLayout(FlowLayout.LEFT))
        row.add(JLabel("Firmware binary:"))
        self.path_field = JTextField(42)
        self.path_field.setEditable(False)
        row.add(self.path_field)
        self.browse_btn = JButton("Choose...", actionPerformed=lambda e: self.choose_image())
        row.add(self.browse_btn)
        top.add(row)
        self.image_label = JLabel("no binary selected")
        lrow = JPanel(FlowLayout(FlowLayout.LEFT))
        lrow.add(self.image_label)
        top.add(lrow)
        srow = JPanel(FlowLayout(FlowLayout.LEFT))
        srow.add(JLabel("Scan addresses 1 to"))
        self.last_addr = JSpinner(SpinnerNumberModel(int(self.settings.get("scan_last", 50)), 1, 254, 1))
        srow.add(self.last_addr)
        self.scan_btn = JButton("Scan bus", actionPerformed=lambda e: self.scan())
        srow.add(self.scan_btn)
        self.all_btn = JButton("Select all", actionPerformed=lambda e: self.model.set_all(lambda r: True))
        self.none_btn = JButton("Select none", actionPerformed=lambda e: self.model.set_all(lambda r: False))
        self.outdated_btn = JButton("Select outdated", actionPerformed=lambda e: self.select_outdated())
        for b in (self.all_btn, self.none_btn, self.outdated_btn):
            srow.add(b)
        top.add(srow)
        root.add(top, BorderLayout.NORTH)

        table = JTable(self.model)
        table.setFillsViewportHeight(True)
        for i, w in enumerate((60, 60, 160, 210, 130, 230, 260)):
            table.getColumnModel().getColumn(i).setPreferredWidth(w)
        sp = JScrollPane(table)
        sp.setPreferredSize(Dimension(1100, 260))
        root.add(sp, BorderLayout.CENTER)

        bottom = JPanel(BorderLayout(4, 4))
        self.progress = JProgressBar(0, 1000)
        self.progress.setStringPainted(True)
        self.progress.setString("")
        bottom.add(self.progress, BorderLayout.NORTH)
        self.text = JTextArea(10, 100)
        self.text.setEditable(False)
        self.text.setFont(Font(Font.MONOSPACED, Font.PLAIN, 12))
        bottom.add(JScrollPane(self.text), BorderLayout.CENTER)
        brow = JPanel(FlowLayout(FlowLayout.RIGHT))
        self.update_btn = JButton("Update selected feeders", actionPerformed=lambda e: self.update())
        self.cancel_btn = JButton("Cancel", actionPerformed=lambda e: self.request_cancel())
        self.cancel_btn.setEnabled(False)
        brow.add(self.update_btn)
        brow.add(self.cancel_btn)
        brow.add(JButton("Close", actionPerformed=lambda e: self.close()))
        bottom.add(brow, BorderLayout.SOUTH)
        root.add(bottom, BorderLayout.SOUTH)

        f.setContentPane(root)
        f.pack()
        f.setLocationRelativeTo(gui)
        f.setVisible(True)

        last = self.settings.get("last_image")
        if last and os.path.isfile(last):
            self.set_image(last)
        self.say("log file: %s" % self.log.path)

    # -- helpers -------------------------------------------------------------------------
    def say(self, text):
        line = self.log(text)
        oppnp.on_ui(lambda: self.text.append(line + "\n"))

    def set_progress(self, frac, text):
        oppnp.on_ui(lambda: (self.progress.setValue(int(frac * 1000)), self.progress.setString(text)))

    def set_busy(self, busy):
        self.busy = busy
        self.model.locked = busy

        def ui():
            for b in (self.browse_btn, self.scan_btn, self.all_btn, self.none_btn,
                      self.outdated_btn, self.update_btn):
                b.setEnabled(not busy)
            self.cancel_btn.setEnabled(busy)
        oppnp.on_ui(ui)

    def close(self):
        if self.busy:
            JOptionPane.showMessageDialog(self.frame, "An operation is running - wait for it or press Cancel.")
            return
        self.frame.dispose()

    # -- image ---------------------------------------------------------------------------
    def choose_image(self):
        start = self.settings.get("image_dir") or os.path.expanduser("~/claude/opulo/_dev/photon/artifacts")
        ch = JFileChooser(start if os.path.isdir(start) else os.path.expanduser("~"))
        ch.setFileFilter(FileNameExtensionFilter("Photon firmware (*.bin)", ["bin"]))
        if ch.showOpenDialog(self.frame) == JFileChooser.APPROVE_OPTION:
            p = str(ch.getSelectedFile().getAbsolutePath())
            self.settings.set("image_dir", os.path.dirname(p))
            self.set_image(p)

    def set_image(self, path):
        try:
            img = photon.Image.load(path)
        except IOError as e:
            JOptionPane.showMessageDialog(self.frame, "Cannot read %s: %s" % (path, e))
            return
        self.image = img
        self.path_field.setText(path)
        if img.problems:
            self.image_label.setText("<html><font color='red'>NOT USABLE: %s</font></html>" % "; ".join(img.problems))
        elif not img.has_entry:
            self.image_label.setText("<html>%s<br><font color='#b06000'>No bus-update entry: after this update the "
                                     "feeders can only be updated with the dongle again.</font></html>" % img.describe())
        else:
            self.image_label.setText(img.describe())
        self.settings.set("last_image", path)
        self.say("binary: %s (%s)" % (path, img.describe()))

    # -- scan ----------------------------------------------------------------------------
    def scan(self):
        if not oppnp.confirm_ready(machine, gui, self.frame, "Cannot scan"):
            return
        last = int(self.last_addr.getValue())
        self.settings.set("scan_last", last)
        self.set_busy(True)

        def work():
            try:
                configured = oppnp.photon_feeders(machine)
                addrs = sorted(set(range(1, last + 1)) | set(configured))
                bus = photon.Bus(oppnp.ActuatorTransport(machine))
                self.say("scanning addresses %d..%d" % (addrs[0], addrs[-1]))
                found = oppnp.run_machine_task(machine, lambda: photon.scan(
                    bus, addrs, lambda s, fr, t: self.set_progress(fr, "scan " + t)))
                rows = []
                for a in sorted(found):
                    f = configured.get(a)
                    rows.append({"info": found[a], "sel": False, "result": "",
                                 "name": f.getName() if f else "(not in OpenPnP)"})
                    self.say("  addr %3d  %-14s %-34s %s" % (a, found[a].version or "-", found[a].uuid_hex,
                                                            found[a].update_status()))
                for a in sorted(set(configured) - set(found)):
                    self.say("  addr %3d  OpenPnP feeder '%s' did not answer" % (a, configured[a].getName()))

                def ui():
                    self.model.rows = rows
                    self.model.fireTableDataChanged()
                oppnp.on_ui(ui)
                self.say("scan done: %d feeder(s) found, %d updatable" %
                         (len(rows), len([r for r in rows if r["info"].updatable])))
                self.set_progress(1.0, "scan done")
            except (Exception, JavaException) as e:
                self.say("scan FAILED: %s" % e)
            finally:
                self.set_busy(False)
        oppnp.in_background(work)

    def select_outdated(self):
        if not self.image:
            JOptionPane.showMessageDialog(self.frame, "Choose the firmware binary first.")
            return
        self.model.set_all(lambda r: r["info"].mode == "pbl" or r["info"].version != self.image.version)

    # -- update --------------------------------------------------------------------------
    def request_cancel(self):
        self.cancel = True
        self.say("cancel requested: the running feeder finishes if it is already erased; the rest are skipped")

    def update(self):
        rows = [r for r in self.model.rows if r["sel"]]
        if not self.image or self.image.problems:
            JOptionPane.showMessageDialog(self.frame, "Choose a usable firmware binary first.")
            return
        if not rows:
            JOptionPane.showMessageDialog(self.frame, "No feeder selected (scan the bus and tick feeders).")
            return
        if not oppnp.confirm_ready(machine, gui, self.frame, "Cannot update"):
            return
        allow_no_entry = False
        if not self.image.has_entry:
            if JOptionPane.showConfirmDialog(self.frame, "This binary has no bus-update entry.\nAfter the update these "
                                             "feeders can only be updated with the dongle.\nContinue?", "Warning",
                                             JOptionPane.YES_NO_OPTION) != JOptionPane.YES_OPTION:
                return
            allow_no_entry = True
        msg = "Update %d feeder(s) to %s?\n\n%s\n\nDo not power off the machine during the update.\n" \
              "A feeder that is interrupted waits in the bus loader (magenta LED);\nrun the update again for it." % (
                  len(rows), self.image.version or "?",
                  "\n".join("  address %d  %s  (%s)" % (r["info"].addr, r["name"], r["info"].version or "bus loader")
                            for r in rows))
        if JOptionPane.showConfirmDialog(self.frame, msg, "Confirm feeder update",
                                         JOptionPane.OK_CANCEL_OPTION) != JOptionPane.OK_OPTION:
            return
        self.cancel = False
        self.set_busy(True)
        img = self.image

        def work():
            ok = failed = skipped = 0
            bus = photon.Bus(oppnp.ActuatorTransport(machine))
            self.say("update to %s (%s), %d feeder(s)" % (img.version, img.path, len(rows)))
            for i, r in enumerate(rows):
                a = r["info"].addr
                if self.cancel:
                    r["result"] = "skipped (cancel)"
                    skipped += 1
                    continue
                r["result"] = "updating..."
                oppnp.on_ui(self.model.fireTableDataChanged)

                def prog(stage, frac, text, i=i, a=a):
                    self.set_progress((i + frac) / len(rows), "feeder %d (%d/%d): %s" % (a, i + 1, len(rows), text))
                    if stage in ("enter", "commit", "done"):
                        self.say("  addr %d: %s" % (a, text))
                try:
                    after = oppnp.run_machine_task(machine, lambda: photon.flash_one(
                        bus, a, img, progress=prog, cancelled=lambda: self.cancel, allow_no_entry=allow_no_entry))
                    r["info"] = after
                    r["result"] = "OK -> %s" % after.version
                    ok += 1
                except photon.Cancelled as e:
                    r["result"] = "skipped (cancel)"
                    skipped += 1
                    self.say("  addr %d: %s" % (a, e))
                except (Exception, JavaException) as e:
                    r["result"] = "FAILED: %s" % e
                    failed += 1
                    self.say("  addr %d: FAILED: %s" % (a, e))
                r["sel"] = False
                oppnp.on_ui(self.model.fireTableDataChanged)
            self.say("finished: %d OK, %d failed, %d skipped; %d packets, %d retries"
                     % (ok, failed, skipped, bus.packets, bus.retries))
            self.set_progress(1.0, "finished: %d OK, %d failed, %d skipped" % (ok, failed, skipped))
            self.set_busy(False)
            if failed:
                oppnp.on_ui(lambda: JOptionPane.showMessageDialog(
                    self.frame, "%d feeder(s) failed - see the Result column and the log.\nA feeder with a magenta "
                    "LED waits in the bus loader: scan and update it again." % failed))
        oppnp.in_background(work)


UpdateDialog()
