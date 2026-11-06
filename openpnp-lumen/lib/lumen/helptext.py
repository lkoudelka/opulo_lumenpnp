# -*- coding: utf-8 -*-
"""Help texts of the Lumen tools: one place, short and concrete.

HELP[tool] = {"title": shown on the Help button,
              "html":  folding help text (what the tool does, steps, what moves the machine),
              "tips":  {visible text of a control (or its beginning): tooltip},
              "columns": {column name: description}}
A label's tooltip is also given to the input field right after it.
"""
from __future__ import absolute_import, division, print_function

MOVES = "<p><b>Machine motion:</b> %s</p>"

HELP = {}

# ---------------------------------------------------------------------------------------
HELP["part_check"] = {
    "title": "Feeder Part Check - pick location centring, part at pick, centring while feeding, pick vacuum check",
    "html": """
<p>Checks Photon feeders with the <b>top camera</b>. The pocket centre comes from the tape's
<b>sprocket holes</b> (EIA tape geometry), so it works on paper, clear and black tape and for any part.
Whether a part sits in the pick pocket is detected on <b>white paper tape</b> only ("?" otherwise).</p>
<ol>
<li><b>Check now:</b> tick feeders, <i>Check selected</i>. Result per feeder: part at pick, how far the pick
location is from the pocket centre. A part already at pick sets OpenPnP's <i>Skip next feed</i>.</li>
<li><b>Correct:</b> <i>Apply offset to selected</i> moves the pick location onto the pocket centre (max 2 mm,
read back, logged).</li>
<li><b>While feeding</b> (during the job): tick the column, set the options of the first row, <i>Save options</i>.
Every N-th feed the camera checks the feeder before it feeds: part at pick -> the feed is skipped;
pick off-centre by 0.05 mm ... max -> moved onto the centre (with a question if <i>confirm</i> is ticked).</li>
<li><b>Pick vacuum check</b> (during the job, off by default): after each pick the vacuum is read with the part held.
An off-centre (edge) pick seals worse, so the level is closer to free air than this feeder's usual pick.
Then the chosen action runs (see the drop-down).</li>
</ol>
<p><b>Actions after an edge pick:</b> <i>log only</i>; <i>re-centre at the next feed</i>;
<i>return to feeder, synchronise and pick again</i> (the part goes back into its pocket, the pick location is
re-centred, the same part is picked again - nothing wasted); <i>discard, synchronise and pick again</i> (part wasted).
Returning / discarding uses OpenPnP's retry: the part's <b>pick retry count must be 1 or more</b>, otherwise
only re-centring is done.</p>
<p>Logs: ~/.openpnp2/lumen/logs/ (feeder-part-check-*, feedwatch-*). Images: ~/.openpnp2/lumen/feeder-check/.</p>
""" + MOVES % "Check, Go to and the checks while feeding move the <b>top camera</b> only (safe Z). Identify only blinks the LED. "
      "Return to feeder moves the nozzle back to the feeder and places the part.",
    "tips": {
        "Tick feeders and press Check selected": "Status line: what is running and the last result.",
        "While feeding: check every": "Every N-th feed of a feeder ticked 'While feeding' the camera checks it "
                                                     "before the feed. 1 = every feed (slowest), 5 = default. Each check adds ~1-2 s.",
        "feeds;": "Number of feeds between two checks while feeding.",
        "confirm moves": "On: a question (Apply / Skip / Stop for this feeder) pauses the job before "
                                                   "the pick location is moved. Off: moved automatically within 'max correction'.",
        "skip feed if part at pick": "On: if the camera sees a part already in the pick pocket, OpenPnP's next feed is "
                                              "skipped (paper tape only; on clear/black tape presence is not detected).",
        "max correction mm": "Largest automatic move of the pick location while feeding (default 0.50 mm). Larger offsets are "
                             "only logged - check the feeder by hand.",
        "Save options": "Store the 'while feeding' options and the ticked feeders (settings.json, key feedwatch).",
        "Pick vacuum check": "On (off by default): after each pick from a Photon feeder the vacuum is compared with this feeder's usual good pick "
                             "(median of its last 10). Clearly closer to free air = edge pick -> the action from the drop-down.",
        "N045": "Threshold for the N045 tip in vacuum counts above the feeder's usual pick (bench: free air 233, covered 223 -> "
                "default 3 = 30 % of the span). Lower = more sensitive.",
        "N08": "Threshold for the N08 tip (bench: free air 247, covered 224 -> default 7).",
        "N14": "Threshold for the N14 tip in vacuum counts (no bench value yet: use ~30 % of free air minus covered).",
        "N24": "Threshold for the N24 tip in vacuum counts (no bench value yet: use ~30 % of free air minus covered).",
        "N40": "Threshold for the N40 tip in vacuum counts (no bench value yet).",
        "N75": "Threshold for the N75 tip in vacuum counts (no bench value yet).",
        "other tips": "Threshold for tips without their own value (default 3 counts).",
        "action:": "What happens after an edge pick: log only / re-centre at the next feed / return to feeder + pick again "
                   "(the part goes back into its pocket, re-centred, the same part picked again - nothing wasted) / discard + "
                   "pick again (part wasted). Return and discard need the part's pick retry count >= 1.",
        "return fails: feed next part": "Only for 'return to feeder': if the feeder cannot take the part back or the put-back fails, the "
                               "part is discarded. On: the next part is fed and picked. Off (default): the next feed is refused, "
                               "OpenPnP disables the feeder and stops the job - check the feeder (the part may lie loose on it).",
        "Save": "Store the pick vacuum options (settings.json, key pickvac).",
        "Pick retries...": "'Return' and 'discard' need the part's pick retry count >= 1. Sets 2 for the open "
                                            "job's parts that have 0 (after confirmation; saved with the configuration).",
        "Select all": "Tick all feeders in the list.",
        "Select none": "Untick all feeders.",
        "Check selected": "Camera to each ticked feeder's pick location: pocket centre, part at pick, offset. Part at pick -> "
                          "next feed skipped. No feed, no nozzle down.",
        "Apply offset to selected": "Move the pick location of the ticked, checked feeders onto the pocket centre "
                                    "(Photon feeder offset; max 2 mm; read back; logged).",
        "Go to pick location": "Top camera over the pick location of the clicked row (to look at it in the camera view).",
        "Identify (blink LED)": "The clicked feeder blinks its LED white 3 times (Photon IDENTIFY command). No motion.",
        "Close": "Close the window (settings stay).",
    },
    "columns": {
        "Check": "Tick to include the feeder in Check selected / Apply offset.",
        "While feeding": "Tick to check this feeder during the job (every N feeds, options in the first row).",
        "Feeder": "OpenPnP feeder name (hardware id and slot).",
        "Slot": "Slot address on the bus (sortable as a number).",
        "Part": "Part assigned to the feeder in OpenPnP.",
        "Tape": "How the pocket centre was found: sprocket holes, 8 / 12 mm tape.",
        "Part at pick": "YES / EMPTY on paper tape; ? on clear or black tape (not detected).",
        "Pick vs pocket mm": "Offset of the pocket centre from the current pick location (X / Y). Apply offset moves the "
                             "pick location by this.",
        "Result": "OK, or what needs attention (empty pocket, off-centre, not found).",
    },
}

# ---------------------------------------------------------------------------------------
HELP["board_z"] = {
    "title": "Board Z Probe - board surface height on the fiducials",
    "html": """
<p>Measures the board surface Z on the <b>board fiducials</b> of the open job by gentle <b>vacuum contact</b>:
the nozzle goes down in 0.05 mm steps at 5 % speed with the vacuum on and stops at the first drop of the
vacuum level (the tip is covered by the board).</p>
<p>Safety: the free-air level is read high above the board; the probe stops if the tip is already covered at the
start height; never more than 2 mm below the start (board Z + 1.5 mm, or 6.0 mm while the board Z is 0).</p>
<p>The result shows Z per fiducial, the mean and the tilt (warning above 0.2 mm). <i>Apply</i> sets the board
location Z to the mean - then save the job.</p>
<p>Not for light objects (they move with the nozzle) - e.g. the calibration disc.</p>
""" + MOVES % "the <b>nozzle goes down</b> onto each fiducial (slowly, vacuum contact).",
    "tips": {
        "Nozzle:": "Nozzle used for probing (a small tip such as N045 gives the most local measurement).",
        "Probe fiducials": "Probe every enabled fiducial of the job's boards with the chosen nozzle.",
        "Apply mean Z to board(s)": "Set the board location Z to the measured mean (after confirmation). Save the job afterwards.",
        "Close": "Close the window.",
    },
    "columns": {
        "Board": "Board of the job.", "Fiducial": "Fiducial placement id.",
        "X": "Machine X of the fiducial (mm).", "Y": "Machine Y of the fiducial (mm).",
        "Surface Z": "Measured surface Z at the fiducial (mm).",
        "Result": "contact / STOPPED with the reason (no contact, covered at start, ...).",
    },
}

# ---------------------------------------------------------------------------------------
HELP["nozzle_cal"] = {
    "title": "Nozzle Offset Calibration - OpenPnP's calibration with the target disc",
    "html": """
<ol>
<li>The top camera finds the calibration target (disc, head setting <i>test object diameter</i>) at its park spot.</li>
<li>It is carried onto the <b>visual home</b> (calibration primary fiducial) with OpenPnP's normal pick and place.</li>
<li><b>OpenPnP's own nozzle offset calibration</b> runs for every ticked nozzle and sets the new head offsets.</li>
<li>The target is carried back to its park spot and checked by the camera.</li>
</ol>
<p><b>Never home the machine while the target lies on the visual home</b> - visual homing would use it (coordinates
~2 mm off). Save the configuration afterwards to keep the new offsets.</p>
""" + MOVES % "the nozzles <b>pick and place the target</b>; OpenPnP's routine picks / places it several times.",
    "tips": {
        "Target park spot X/Y:": "Where the target disc normally lies (camera position of its centre, mm). It is always returned here.",
        "N1": "Calibrate nozzle N1.", "N2": "Calibrate nozzle N2.",
        "Run calibration": "Carry the target to the visual home, run OpenPnP's nozzle offset calibration for the ticked nozzles, "
                           "carry it back. Needs a homed machine with the target at its park spot.",
        "Close": "Close the window.",
    },
    "columns": {},
}

# ---------------------------------------------------------------------------------------
HELP["inspection"] = {
    "title": "Placement Inspection - check placed parts with the top camera",
    "html": """
<p>For the ticked placements the top camera looks at each part (camera only):</p>
<ul>
<li><b>Size method:</b> the part body (size from the package footprint, its pads or the KiCad name such as
C_0402_1005Metric) near the location: found / offset / rotation.</li>
<li><b>Golden sample:</b> after you mark one good part of a package as golden, later parts of that package are
compared with it: match score, offset, and whether the part matches better <b>turned by 180 deg</b> (polarity).</li>
</ul>
<p>OK / CHECK / FAIL is an aid, not a sign-off - every image is kept
(~/.openpnp2/lumen/inspection/&lt;job&gt;-&lt;time&gt;/). Limits: offset 0.15 mm, angle 8 deg, golden score OK &ge; 0.70,
FAIL &lt; 0.45.</p>
""" + MOVES % "the <b>top camera</b> only (safe Z).",
    "tips": {
        "only placed": "Show only placements marked as placed in the job (off: all placements).",
        "Select all": "Tick all listed placements.", "Select none": "Untick all placements.",
        "Select not OK": "Tick the placements whose last result is CHECK, FAIL or ERROR (to inspect them again).",
        "Inspect selected": "Camera over each ticked placement, analyse, save the image.",
        "Make golden from selected": "Use the clicked, inspected placement (a GOOD part) as the golden sample of its package.",
        "Open image": "Open the saved image of the clicked row.",
        "Export CSV": "Write the report (inspection.csv) into this run's folder.",
        "Close": "Close the window.",
    },
    "columns": {
        "Check": "Tick to inspect.", "Board": "Board of the job.", "Ref": "Placement id (reference designator).",
        "Part": "Part id.", "Package": "Package (footprint) - golden samples are per package.",
        "Placed": "The job's placed flag.", "Result": "OK / CHECK / FAIL with the reason.",
        "Offset mm": "Distance of the found body from the expected location.",
        "Angle err": "Rotation error of the body (deg, CCW).",
        "Golden score": "Match with the package's golden sample (1.0 = identical).",
        "Body size from": "Where the expected body size came from (package body, pads, KiCad name).",
    },
}

# ---------------------------------------------------------------------------------------
HELP["firmware_update"] = {
    "title": "Feeder Firmware Update - Photon firmware over the RS-485 bus",
    "html": """
<ol><li><i>Choose...</i> the firmware binary (application .bin with bus-update entry, max 31,744 B; not *-factory.bin).</li>
<li><i>Scan bus</i>: lists every answering feeder with its firmware.</li>
<li>Tick feeders (only ones with the bus loader can be ticked), <i>Update selected feeders</i>.</li></ol>
<p>Feeders with old firmware need the one-time dongle flash of the *-factory.bin first. An interrupted feeder
(magenta LED) is listed as "in bus loader" and can be finished. Logs: ~/.openpnp2/lumen/logs/feeder-update-*.</p>
""" + MOVES % "none (bus messages only). No job may be running.",
    "tips": {
        "Firmware binary:": "The firmware file to install (application .bin).",
        "Choose...": "Pick the firmware binary; size, vectors, version and bus-update entry are checked.",
        "no binary selected": "Version and size of the chosen binary.",
        "Scan addresses 1 to": "Highest bus address to scan (50 slots on the LumenPnP).",
        "Scan bus": "Ask every address for its feeder id, firmware and bus-update capability.",
        "Select all": "Tick all updatable feeders.", "Select none": "Untick all.",
        "Select outdated": "Tick the updatable feeders whose firmware differs from the chosen binary.",
        "Update selected feeders": "Install the binary on the ticked feeders (confirmation lists them).",
        "Cancel": "Stop after the current feeder (a feeder already erased is always completed).",
        "Close": "Close the window.",
    },
    "columns": {
        "Update": "Tick to update.", "Address": "Bus address (slot).", "OpenPnP feeder": "Matching OpenPnP feeder, if configured.",
        "UUID": "Feeder hardware id.", "Firmware": "Firmware version reported by the feeder.",
        "Bus update": "ready / old firmware (dongle once) / in bus loader.", "Result": "Update result.",
    },
}

# ---------------------------------------------------------------------------------------
HELP["job_readiness"] = {
    "title": "Job Readiness - only what the open job needs",
    "html": """
<p>Parts of the open job with quantity, remaining, part height and feeders, and precisely why a feeder
cannot be used (no slot, no location, disabled, ...). Read-only.</p>
<p><i>Show on feeder LEDs</i>: green = needed and ready, red = needed but has an issue, off = not used by the job.</p>
""" + MOVES % "none (LEDs only).",
    "tips": {
        "Refresh": "Re-read the job and the feeders.",
        "Show on feeder LEDs": "Light the job's Photon feeders: green ready, red issue, others off.",
        "Feeder LEDs off": "Switch the feeder LEDs off again.",
        "Close": "Close the window.",
    },
    "columns": {
        "Part": "Part id.", "Package": "Package.", "Height mm": "Part height (needed for placing).",
        "Total": "Placements of this part in the job.", "Remaining": "Not yet placed.",
        "Feeder(s)": "Feeders holding the part.", "Issues": "Why the part cannot be placed yet.",
    },
}

# ---------------------------------------------------------------------------------------
HELP["last_placements"] = {
    "title": "Last Placements - newest placements first, mark not placed",
    "html": """
<p>Newest placements of the open job first (placement journal, installed with --journal). <i>Mark ... NOT
placed</i> clears OpenPnP's Placed flag so the next run places the part again (same as unticking Placed in the
job table). Without the journal the placed placements are listed without order.</p>
""" + MOVES % "<i>Go to</i> moves the top camera.",
    "tips": {
        "Refresh": "Re-read the journal and the job.",
        "Mark LAST NOT placed": "Clear the Placed flag of the newest placement.",
        "Mark selected NOT placed": "Clear the Placed flag of the selected rows.",
        "Go to (camera)": "Top camera over the selected placement.",
        "Close": "Close the window.",
    },
    "columns": {
        "Time": "When it was placed.", "Board": "Board.", "Placement": "Placement id.", "Part": "Part id.",
        "Nozzle": "Nozzle that placed it.", "Placed now": "The job's current Placed flag.",
    },
}

# ---------------------------------------------------------------------------------------
HELP["orientation"] = {
    "title": "Orientation Setup - pin 1 in the feeder vs. in the CAD footprint",
    "html": """
<p>For parts where orientation matters: pin 1 <b>in the feeder</b> (seen from above) and <b>in the CAD footprint</b>
at 0 deg. From the two the rotation in the feeder follows (4 corners = 0/90/180/270).</p>
<p>CAD pin 1 comes from a verified KiCad board or copper Gerber, or by footprint name (library, OpenPnP package,
earlier confirmations). Every mark is confirmed in the two squares (<i>Check selected</i>).</p>
""" + MOVES % "<i>Show top camera at the feeder</i> moves the camera.",
    "tips": {
        "Import KiCad board (.kicad_pcb)": "Pin 1 of every footprint from the board file - used only where it matches the job "
                                           "(reference, footprint, rotation, position).",
        "Import copper Gerber (X2)": "Pin 1 from the top copper Gerber with pin attributes (KiCad X2 + netlist attributes).",
        "Footprint library (.pretty)": "Folder with KiCad footprints: pin 1 by footprint name for jobs from a .pos file.",
        "only parts where orientation matters": "Hide resistors, capacitors and other parts whose orientation does not matter.",
        "Check selected (two squares)": "Open the two squares for the selected row: click pin 1 in the feeder and in CAD.",
        "Toggle 'orientation matters'": "Override the automatic decision for the selected part.",
        "Refresh": "Re-read the job, feeders and sources.",
        "Close": "Close the window.",
    },
    "columns": {
        "Part": "Part id.", "Footprint": "Footprint name.", "Refs": "Placements of the part.",
        "Orientation": "matters / not relevant.", "CAD pin 1": "Pin-1 corner in the footprint at 0 deg (auto / confirmed).",
        "Feeder": "Feeder holding the part.", "Feeder mark": "Pin-1 corner seen in the feeder.",
        "Needs": "Rotation the feeder needs (deg).", "Feeder now": "Current feeder rotation (deg).",
        "Status": "CORRECT / MISMATCH / to check.",
    },
}
HELP["orientation_check"] = {
    "title": "Pin 1 in the feeder and in CAD",
    "html": "<p>Click the corner where pin 1 is: left = the part in the feeder (seen from above, like the top camera), "
            "right = the footprint at 0 deg. The rotation in the feeder is calculated from the two.</p>"
            + MOVES % "<i>Show top camera at the feeder</i> moves the camera.",
    "tips": {
        "Show top camera at the feeder": "Move the top camera to the feeder's pick location and show the image in the left square.",
        "Confirm and apply rotation to feeder": "Store both marks and set the feeder rotation (after confirmation).",
        "Confirm": "Store both marks without changing the feeder.",
        "Cancel": "Close without storing.",
    },
    "columns": {},
}

# ---------------------------------------------------------------------------------------
HELP["pick_learning"] = {
    "title": "Pick Offset Learning - systematic pick error per feeder",
    "html": """
<p>From the bottom-vision offsets recorded during jobs (lumen profile) a systematic pick error per feeder is
learned. Nothing changes automatically: select a feeder with a suggestion and <i>Apply</i> (damped, limited
step, logged, undoable). After a correction only newer samples count; if they get worse the row says "undo".</p>
""" + MOVES % "none.",
    "tips": {
        "Refresh": "Re-read the recorded samples.",
        "Apply suggestion to selected feeder": "Move the selected Photon feeder's pick location by the suggestion.",
        "Undo last correction of selected": "Restore the pick location before the last correction.",
        "Close": "Close the window.",
    },
    "columns": {
        "Feeder": "Feeder.", "Parts": "Parts picked from it.", "Samples": "Bottom-vision samples used.",
        "Mean X mm": "Mean pick error X.", "Mean Y mm": "Mean pick error Y.", "Scatter mm": "Spread of the error.",
        "Rot deg": "Mean rotation error.", "Status / hint": "Suggestion, collecting, undo, orientation hint.",
    },
}

# ---------------------------------------------------------------------------------------
HELP["preflight"] = {
    "title": "Preflight - checklist before a job",
    "html": """
<p>Runs the checks of ~/.openpnp2/lumen/preflight.json (edit to switch steps on/off or change severity):
machine enabled, job open, home if needed, lights, nozzle tips, vacuum sensors, job readiness, feeder bus,
orientation confirmations, optional board Z. Result PASS / WARN / FAIL; it does not start or block the job.</p>
""" + MOVES % "only <i>home</i> (if the step is on and the machine is not homed).",
    "tips": {
        "checklist:": "The checklist file in use.",
        "Run checks": "Run all enabled steps in order.",
        "Edit checklist": "Open preflight.json in the editor.",
        "Close": "Close the window.",
    },
    "columns": {"Step": "Check name.", "Result": "PASS / WARN / FAIL / SKIP.", "Detail": "What was found."},
}
