# -*- coding: utf-8 -*-
"""Board positions live in the JOB file, not in the board file (Jython in OpenPnP).

OpenPnP starts with an empty job.  Adding the board again (Add Board) creates a NEW board location at
X 0 / Y 0 / Z 0 / 0 deg - the position set and saved before is in the .job.xml (bench 2026-11-25: after every
restart the GAN board showed all zeros while GAN_power_suply.board.job.xml held 318.66 / 145.14 / Z 4.5).
- offer(gui): at start-up, empty job and the last job file exists -> ask to reopen it (OpenPnP's own load).
- unplaced_boards(job): enabled boards still at X 0 / Y 0 (position never set) - for Preflight / Job Readiness.
"""
from __future__ import absolute_import, division, print_function

import os

RECENT_KEY = "JobPanel.recentFiles_0"          # OpenPnP's File > Open Recent, newest first (node org/openpnp/gui)


def _log(text):
    try:
        from org.pmw.tinylog import Logger
        Logger.info("Lumen last-job: %s" % text)
    except Exception:
        print("Lumen last-job: %s" % text)


def last_job_file(prefs=None):
    """Path of OpenPnP's most recent job (File > Open Recent), or None."""
    if prefs is None:
        from java.util.prefs import Preferences
        prefs = Preferences.userRoot().node("org/openpnp/gui")
    p = prefs.get(RECENT_KEY, None)
    return str(p) if p else None


def job_is_empty(job):
    return job is None or len(list(job.getBoardLocations())) == 0


def board_xy(bl):
    from org.openpnp.model import LengthUnit
    loc = bl.getLocation().convertToUnits(LengthUnit.Millimeters)
    return loc.getX(), loc.getY()


def unplaced_boards(job):
    """[board location id / name] of the enabled boards whose position is still X 0 / Y 0 (never set: a board
    added with Add Board starts there; no real board lies at the machine origin)."""
    out = []
    if job is None:
        return out
    for bl in job.getBoardLocations():
        try:
            if not bl.isEnabled():
                continue
        except Exception:
            pass
        x, y = board_xy(bl)
        if abs(x) < 1e-6 and abs(y) < 1e-6:
            name = bl.getBoard().getName() if bl.getBoard() is not None else "board"
            out.append("%s (%s)" % (bl.getId(), name))
    return out


def open_job(gui, path):
    """Like OpenPnP's File > Open Job: load, show, feeders view updated."""
    from java.io import File
    from org.openpnp.model import Configuration
    job = Configuration.get().loadJob(File(path))
    gui.getJobTab().setJob(job)
    try:
        gui.getFeedersTab().updateView()
    except Exception:
        pass
    return job


def offer(gui, ask=None, prefs=None):
    """Start-up: OpenPnP shows an empty job and the last job file exists -> ask to reopen it.  Returns the opened
    path or None."""
    job = gui.getJobTab().getJob()
    path = last_job_file(prefs)
    if not job_is_empty(job) or not path or not os.path.isfile(path):
        return None
    if ask is None:
        from javax.swing import JOptionPane

        def ask(text):
            return JOptionPane.showConfirmDialog(gui, text, "Open the last job?",
                                                 JOptionPane.YES_NO_OPTION) == JOptionPane.YES_OPTION
    text = ("<html>OpenPnP started with an empty job. Open the last job<br><b>%s</b>?<br><br>"
            "The board positions (X / Y / Z / rotation) are stored in the <b>job</b>. Adding the board file again "
            "(Add Board) starts it at X 0 / Y 0.</html>" % path)
    if not ask(text):
        _log("not reopened: %s" % path)
        return None
    job = open_job(gui, path)
    _log("reopened %s (%s)" % (path, ", ".join("%s at %.2f / %.2f" % ((bl.getId(),) + board_xy(bl))
                                               for bl in job.getBoardLocations())))
    return path


def offer_later(gui):
    """offer() after OpenPnP has finished starting (the Startup event runs inside its start-up code)."""
    from javax.swing import SwingUtilities
    from java.lang import Runnable

    class _R(Runnable):
        def run(self):
            try:
                offer(gui)
            except:                                  # bare: also Java exceptions (Jython)
                import sys
                _log("offer failed: %s" % (sys.exc_info()[1],))
    SwingUtilities.invokeLater(_R())
