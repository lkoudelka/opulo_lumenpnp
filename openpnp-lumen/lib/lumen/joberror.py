# -*- coding: utf-8 -*-
"""Job errors in words a person can act on (Jython in OpenPnP; events/Job.Error.py).

OpenPnP reports the low-level failure only.  Bench 2026-11-26: "Can't move y to -110.698mm, lower than soft limit
0.000mm" - the real cause was part C11 (package CAPC_2220) whose only compatible nozzle tip N24 was not loaded, so
the job tried an automatic tip change towards an unset changer location.  explain() names the part(s), the
package and the fix; on_error() logs it and shows it next to OpenPnP's own message.
"""
from __future__ import absolute_import, division, print_function

SEEN_KEY = "lumen.joberror.last"


def _log(text):
    try:
        from org.pmw.tinylog import Logger
        Logger.warn("Lumen job error: %s" % text)
    except Exception:
        print("Lumen job error: %s" % text)


def _trace(exception):
    """Message and stack text of the exception and its causes."""
    out, e, n = [], exception, 0
    while e is not None and n < 6:
        out.append(str(e))
        try:
            out.extend(str(x) for x in e.getStackTrace())
            e = e.getCause()
        except Exception:
            e = None
        n += 1
    return "\n".join(out)


def explain(job, machine, exception):
    """[lines] for a person, or [] when there is nothing to add to OpenPnP's message."""
    from lumen import jobinfo
    tr = _trace(exception)
    lines = []
    tips = jobinfo.tip_problems(job, machine) if job is not None else []
    if tips or "ChangeNozzleTips" in tr or "NozzleTip" in tr:
        if tips:
            lines.append("The job could not change the nozzle tip: no loaded tip suits these parts:")
            for pid, refs, issue in tips:
                lines.append("- %s (%s): %s" % (pid, ", ".join(refs[:8]) + (" ..." if len(refs) > 8 else ""), issue))
        elif "ChangeNozzleTips" in tr:
            lines.append("The job failed while changing the nozzle tip (no tip changer on this machine): check the "
                         "packages' Nozzle Tips of the next placements against the tips loaded now.")
    if "soft limit" in tr and not lines:
        lines.append("A move went outside the machine (soft limit). Check the next placement's board position "
                     "(Job tab) and its feeder's pick location (Job Readiness: Camera to feeder / next placement).")
    return lines


def on_error(job, machine, exception, show=None):
    """Log the explanation; show it once per distinct text (OpenPnP repeats the error on every retry)."""
    lines = explain(job, machine, exception)
    if not lines:
        return None
    text = "\n".join(lines)
    _log(text.replace("\n", " | "))
    from java.lang import System
    if System.getProperty(SEEN_KEY) == text:
        return text
    System.setProperty(SEEN_KEY, text)
    if show is None:
        from javax.swing import JOptionPane, SwingUtilities
        from java.lang import Runnable

        class _Show(Runnable):
            def run(self):
                from org.openpnp.gui import MainFrame
                JOptionPane.showMessageDialog(MainFrame.get(), "<html>%s<br><br><i>OpenPnP: %s</i></html>" % (
                    "<br>".join(l.replace("&", "&amp;").replace("<", "&lt;") for l in lines),
                    str(exception).replace("<", "&lt;")), "Lumen: why the job stopped", JOptionPane.WARNING_MESSAGE)
        SwingUtilities.invokeLater(_Show())
    else:
        show(text)
    return text
