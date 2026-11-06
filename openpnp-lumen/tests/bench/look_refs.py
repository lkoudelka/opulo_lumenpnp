# camera only: calibrated back-rail slots as references for the pick-pocket geometry, then slot 50 again
import re
xml = open(os.path.expanduser("~/.openpnp2/machine.xml")).read()
for a in (44, 45, 46, 47, 48):
    m = re.search(r'<slot address="%d">\s*<location units="Millimeters" x="([-\d.]+)" y="([-\d.]+)" z="([-\d.]+)"' % a, xml)
    look("slot%d-ref" % a, float(m.group(1)), float(m.group(2)), float(m.group(3)))
look("slot50-est", 29.33, 411.2, 3.3)
