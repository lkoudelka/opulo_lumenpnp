# OpenPnP menu script: Scripts > Session > Mark
# Writes a "USER-MARK: <text>" line into OpenPnP.log, right between the G-code
# trace lines, so pnp-session can put your note on the timeline.
# Menu only: no event hooks, does not touch the machine.
from javax.swing import JOptionPane
from org.pmw.tinylog import Logger

text = JOptionPane.showInputDialog(gui, "What did you just do / notice?", "Session mark", JOptionPane.PLAIN_MESSAGE)
if text:
    Logger.info("USER-MARK: " + text)
