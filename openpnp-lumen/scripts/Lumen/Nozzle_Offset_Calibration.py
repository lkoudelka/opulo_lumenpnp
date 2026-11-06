# Scripts > Lumen > Nozzle Offset Calibration (OpenPnP, with the calibration target)
#
# 1. the top camera finds the calibration target (round disc, head setting "test object diameter")
#    at its park spot;  2. it is carried onto the visual home (calibration primary fiducial) with
#    OpenPnP's normal pick and place at the calibration Z;  3. OpenPnP's own nozzle offset
#    calibration (Issues & Solutions > Calibration) runs for every ticked nozzle and sets the new head
#    offsets;  4. the target is carried back to its park spot and checked by the camera.
# Do NOT home the machine while the target lies on the visual home (visual homing would use it).
# Save the configuration afterwards to keep the new offsets (OpenPnP also saves on exit).
from __future__ import absolute_import, division, print_function

import os
import sys

_LIB = os.path.join(str(scripting.getScriptsDirectory().getParent()), "lumen", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
import lumen.oppnp
import lumen.helptext
import lumen.uihelp
import lumen.zprobe
import lumen.tapevision
import lumen.nozzlecal
reload(lumen.oppnp)
reload(lumen.helptext)
reload(lumen.uihelp)
reload(lumen.zprobe)
reload(lumen.tapevision)
reload(lumen.nozzlecal)
from lumen import nozzlecal, oppnp
from lumen.oppnp import JavaException

from java.awt import BorderLayout, Dimension, FlowLayout
from javax.swing import (BorderFactory, JButton, JCheckBox, JFrame, JLabel, JOptionPane, JPanel, JScrollPane,
                         JTextArea, JTextField, WindowConstants)

DEFAULT_PARK = (240.624, 189.420)


class NozzleCal(object):
    def __init__(self):
        self.settings = oppnp.Settings(scripting)
        self.log = oppnp.FileLog(scripting, "nozzle-offset-calibration")
        self.busy = False
        self.result = None
        park = self.settings.get("target_park", list(DEFAULT_PARK))
        f = self.frame = JFrame("Nozzle offset calibration (OpenPnP) with the target")
        f.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE)
        root = JPanel(BorderLayout(6, 6))
        root.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8))
        top = JPanel(FlowLayout(FlowLayout.LEFT))
        top.add(JLabel("Target park spot X/Y:"))
        self.px = JTextField("%.3f" % park[0], 8)
        self.py = JTextField("%.3f" % park[1], 8)
        top.add(self.px)
        top.add(self.py)
        self.boxes = []
        for n in machine.getDefaultHead().getNozzles():
            cb = JCheckBox(n.getName(), True)
            self.boxes.append((cb, n))
            top.add(cb)
        root.add(top, BorderLayout.NORTH)
        self.text = JTextArea(16, 90)
        self.text.setEditable(False)
        self.text.setText("The target is carried from its park spot to the visual home, OpenPnP calibrates the ticked\n"
                          "nozzles, then the target goes back. Do not home the machine while the target is on the visual home.\n")
        root.add(JScrollPane(self.text), BorderLayout.CENTER)
        b = JPanel(FlowLayout(FlowLayout.RIGHT))
        self.run_btn = JButton("Run calibration", actionPerformed=lambda e: self.run())
        b.add(self.run_btn)
        b.add(JButton("Close", actionPerformed=lambda e: f.dispose()))
        root.add(b, BorderLayout.SOUTH)
        f.setContentPane(lumen.uihelp.wrap(root, "nozzle_cal"))
        f.pack()
        f.setLocationRelativeTo(gui)
        f.setVisible(True)

    def say(self, s):
        self.log(s)
        oppnp.on_ui(lambda: self.text.append(s + "\n"))

    def run(self):
        nozzles = [n for cb, n in self.boxes if cb.isSelected()]
        if not nozzles:
            JOptionPane.showMessageDialog(self.frame, "Tick at least one nozzle.")
            return
        try:
            park = (float(self.px.getText()), float(self.py.getText()))
        except ValueError:
            JOptionPane.showMessageDialog(self.frame, "Park spot X/Y must be numbers.")
            return
        if not machine.isHomed():
            JOptionPane.showMessageDialog(self.frame, "Home the machine first (with the target at its park spot).")
            return
        if not oppnp.confirm_ready(machine, gui, self.frame, "Cannot calibrate"):
            return
        self.settings.set("target_park", list(park))
        self.busy = True
        self.run_btn.setEnabled(False)

        def work():
            try:
                carrier = machine.getDefaultHead().getNozzles()[0]
                self.result = oppnp.run_machine_task(machine, lambda: nozzlecal.calibrate_openpnp(
                    machine, nozzles, park, carrier, log=self.say))
                for k, (o, n) in sorted(self.result["offsets"].items()):
                    self.say("RESULT %s: head offsets %s -> %s" % (k, o, n))
                self.say("Done. Save the configuration (File > Save Configuration) to keep the new offsets.")
            except (Exception, JavaException) as e:
                self.say("STOPPED: %s" % e)
            finally:
                self.busy = False
                oppnp.on_ui(lambda: self.run_btn.setEnabled(True))
        oppnp.in_background(work)


NozzleCal()
