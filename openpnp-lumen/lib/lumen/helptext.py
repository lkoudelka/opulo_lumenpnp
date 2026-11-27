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
<p><b>Tab Check</b></p>
<ol>
<li><b>Check now:</b> tick feeders, <i>Check selected</i>. Result per feeder: part at pick, how far the pick
location is from the pocket centre. A part already at pick sets OpenPnP's <i>Skip next feed</i>.</li>
<li><b>Correct:</b> <i>Apply offset to selected</i> moves the pick location onto the pocket centre (max 2 mm,
read back, logged).</li>
</ol>
<p><b>Tab Options per feeder</b> - what happens <b>during the job</b>, set <b>per feeder</b> (feeders behave differently
with different parts / tapes):</p>
<ol>
<li><b>Defaults</b> (top): used by every feeder that has no own value. <i>Save defaults</i> stores them.</li>
<li><b>Table</b>: one row per feeder with the values it really uses. <span style='color:gray'><i>Grey / italic</i></span>
= the default; black = the feeder's own value. Edit a cell to give the feeder its own value. Highlight several rows
(Shift / Ctrl + click) and edit one of them: the value is set for all highlighted rows.
<i>Reset highlighted to defaults</i> removes the own values (the <i>While feeding</i> tick stays).</li>
<li><b>While feeding</b>: every N-th feed of that feeder the camera checks it before it feeds: part at pick -> the
feed is skipped; pick off-centre by 0.05 mm ... max -> moved onto the centre (with a question if <i>Confirm</i>).</li>
<li><b>Vac check</b> (pick vacuum check, off by default): after each pick the vacuum is read with the part held.
An off-centre (edge) pick seals worse, so the level is closer to free air than this feeder's usual pick.
Then the feeder's <i>Edge pick action</i> runs.</li>
</ol>
<p><b>Edge pick actions:</b> <i>log only</i>; <i>re-centre at the next feed</i>;
<i>return to feeder + pick again</i> (the part goes back into its pocket, the pick location is
re-centred, the same part is picked again - nothing wasted); <i>discard + pick again</i> (part wasted).
Returning / discarding uses OpenPnP's retry: the part's <b>pick retry count must be 1 or more</b>, otherwise
only re-centring is done.</p>
<p>Options follow the <b>feeder</b> (its hardware id), not the slot or the part: after loading another reel, check
the feeder's row. Stored in ~/.openpnp2/lumen/settings.json (defaults: feedwatch, pickvac; own values: feeder_options).</p>
<p>Logs: ~/.openpnp2/lumen/logs/ (feeder-part-check-*, feedwatch-*). Images: ~/.openpnp2/lumen/feeder-check/.</p>
""" + MOVES % "Check, Go to and the checks while feeding move the <b>top camera</b> only (safe Z). Identify only blinks the LED. "
      "Return to feeder moves the nozzle back to the feeder and places the part. Editing options moves nothing.",
    "tabs": {
        "Check": "Check feeders now with the camera; apply the pick offset.",
        "Options per feeder": "What happens during the job, per feeder: centring while feeding, pick vacuum check, edge "
                              "pick action. Defaults on top, own values per feeder in the table.",
    },
    "tips": {
        "Tick feeders and press Check selected": "Status line: what is running and the last result.",
        "Defaults": "Values for feeders without an own value.",
        "While feeding: check every": "Default: every N-th feed of a feeder with 'While feeding' ticked, the camera checks it "
                                      "before the feed. 1 = every feed (slowest), 5 = default. Each check adds ~1-2 s. "
                                      "Own value per feeder: column 'Every N'.",
        "feeds;": "Number of feeds between two checks while feeding (default for all feeders).",
        "confirm moves": "Default. On: a question (Apply / Skip / Stop for this feeder) pauses the job before "
                         "the pick location is moved. Off: moved automatically within 'max correction'. Per feeder: column 'Confirm'.",
        "skip feed if part at pick": "Default. On: if the camera sees a part already in the pick pocket, OpenPnP's next feed is "
                                     "skipped (paper tape only; on clear/black tape presence is not detected). Per feeder: 'Skip if part'.",
        "max correction mm": "Default largest automatic move of the pick location while feeding (0.50 mm; 0.05 ... 2). Larger "
                             "offsets are only logged - check the feeder by hand. Per feeder: 'Max mm'.",
        "Pick vacuum check": "Default on/off (off by default): after each pick from a Photon feeder the vacuum is compared with "
                             "this feeder's usual good pick (median of its last 10). Clearly closer to free air = edge pick -> "
                             "the edge pick action. Per feeder: 'Vac check'.",
        "N045": "Threshold for the N045 tip in vacuum counts above the feeder's usual pick (bench: free air 233, covered 223 -> "
                "default 3 = 30 % of the span). Lower = more sensitive. Used by feeders whose 'Vac threshold' is 'per tip'.",
        "N08": "Threshold for the N08 tip (bench: free air 247, covered 224 -> default 7). Used by feeders whose 'Vac threshold' "
               "is 'per tip'.",
        "N14": "Threshold for the N14 tip in vacuum counts (no bench value yet: use ~30 % of free air minus covered).",
        "N24": "Threshold for the N24 tip in vacuum counts (no bench value yet: use ~30 % of free air minus covered).",
        "N40": "Threshold for the N40 tip in vacuum counts (no bench value yet).",
        "N75": "Threshold for the N75 tip in vacuum counts (no bench value yet).",
        "other tips": "Threshold for tips without their own value (default 3 counts).",
        "action:": "Default edge pick action: log only / re-centre at the next feed / return to feeder + pick again "
                   "(the part goes back into its pocket, re-centred, the same part picked again - nothing wasted) / discard + "
                   "pick again (part wasted). Return and discard need the part's pick retry count >= 1. Per feeder: "
                   "'Edge pick action'.",
        "return fails: feed next part": "Default, only for 'return to feeder': if the feeder cannot take the part back or the "
                                        "put-back fails, the part is discarded. On: the next part is fed and picked. Off "
                                        "(default): the next feed is refused, OpenPnP disables the feeder and stops the job - "
                                        "check the feeder (the part may lie loose on it). Per feeder: 'Return fails: feed next'.",
        "Save defaults": "Store the defaults (settings.json keys feedwatch, pickvac). Feeders with own values keep them.",
        "Pick retries...": "'Return' and 'discard' need the part's pick retry count >= 1. Sets 2 for the open "
                           "job's parts that have 0 (after confirmation; saved with the configuration).",
        "Edit a cell": "How to set options per feeder.",
        "Reset highlighted to defaults": "The highlighted feeders lose their own values and use the defaults again "
                                         "(the 'While feeding' tick is kept).",
        "Select all": "Tick all feeders in the list.",
        "Select none": "Untick all feeders.",
        "Check selected": "Camera to each ticked feeder's pick location: pocket centre, part at pick, offset. Part at pick -> "
                          "next feed skipped. No feed, no nozzle down.",
        "Apply offset to selected": "Move the pick location of the ticked, checked feeders onto the pocket centre "
                                    "(Photon feeder offset; max 2 mm; read back; logged).",
        "Go to pick location": "Top camera over the pick location of the clicked row (either tab), to look at it in the camera view.",
        "Set offset by hand": "For the clicked feeder - Photon, tray or strip, checked or not: the photo of its last "
                              "check opens (also when the pocket was NOT FOUND), otherwise the top camera goes to the "
                              "pick location and takes one (camera only, no feed). Zoom in with the mouse wheel and "
                              "click the centre of the pick pocket / part. Apply moves the pick location there (any "
                              "distance, after a confirmation; read back): Photon = feeder offset, tray = tray location "
                              "(every position moves with it), strip = both reference holes. Pocket outside the photo: "
                              "Camera here takes a new photo there. Photon only: Camera to slot location, and Camera to "
                              "feeder fiducial (round marks on the feeder nose, ~13 mm towards the nose; the centre mark "
                              "is found (green) and the pick location's distance from it is shown).",
        "only feeders of the open job": "Show only feeders whose part the open job places (both tabs). Hidden rows are "
                                        "unticked, so Check / Apply act only on the job's feeders.",
        "Identify (blink LED)": "The clicked feeder (either tab) blinks its LED white 3 times (Photon IDENTIFY command). No motion.",
        "Close": "Close the window (settings stay).",
    },
    "columns": {
        "Check": "Tick to include the feeder in Check selected / Apply offset.",
        "Feeder": "OpenPnP feeder name (hardware id and slot).",
        "Slot": "Slot address on the bus (sortable as a number).",
        "Part": "Part assigned to the feeder in OpenPnP.",
        "Tape": "How the pocket centre was found: sprocket holes, 8 / 12 mm tape.",
        "Part at pick": "YES / EMPTY on paper tape; ? on clear or black tape (not detected).",
        "Pick vs pocket mm": "Offset of the pocket centre from the current pick location (X / Y). Apply offset moves the "
                             "pick location by this.",
        "Result": "OK, or what needs attention (empty pocket, off-centre, not found).",
        "While feeding": "Tick = the camera checks this feeder during the job (every N feeds) and centres its pick location. "
                         "Always per feeder (off unless ticked).",
        "Every N": "Check every N-th feed of this feeder (1 = every feed). Grey = default.",
        "Confirm": "Ask before moving this feeder's pick location (pauses the job). Grey = default.",
        "Skip if part": "Skip the feed when a part is already in the pick pocket (paper tape). Grey = default.",
        "Max mm": "Largest automatic correction for this feeder (0.05 ... 2 mm); larger only logged. Grey = default.",
        "Vac check": "Pick vacuum check on for this feeder. Grey = default.",
        "Vac threshold": "Edge pick threshold in vacuum counts for this feeder, whatever tip picks. 'per tip' = the tip "
                         "thresholds of the defaults; type a number for an own value, clear the cell for 'per tip'.",
        "Edge pick action": "What happens after an edge pick from this feeder: log only / re-centre at next feed / return to "
                            "feeder + pick again / discard + pick again. Grey = default.",
        "Return fails: feed next": "For 'return to feeder': if the return fails, ticked = feed and pick the next part; unticked "
                                   "= refuse the next feed and stop the job for the operator. Grey = default.",
        "Own values": "Which options this feeder has its own value for ('defaults' = none).",
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
<p>The calibration runs at <b>50 % machine speed</b> (slower if OpenPnP's speed is set lower); the previous speed is
put back afterwards, also when the calibration stops.</p>
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
<li><b>Chip parts</b> (R / C / L 0201 .. 2512 by package name, size from the EIA code: 0603 = 1.6 x 0.8 mm): the two
bright <b>terminations</b> along the expected axis; a light ceramic body as bright as its tin is found as the
<b>whole part</b> instead. <b>Missing</b> = bare pads: between them the solder mask.</li>
<li><b>SMA / SMB / SMC diodes</b>: the two <b>lead tabs</b> with the black body between them.</li>
<li><b>Other parts:</b> the dark body (package body size, else the name, e.g. SOD-323) near the location.</li>
<li><b>Golden samples:</b> pictures of good parts of a package (<i>Make golden</i>, and every part you confirm:
<i>Set as OK</i> / <i>Draw where the part is</i>, up to 6 per package): the best match counts - score, offset, and
whether the part matches better <b>turned by 180 deg</b> (polarity).</li>
</ul>
<p>OK / CHECK / FAIL is an aid, not a sign-off - every image is kept
(~/.openpnp2/lumen/inspection/&lt;job&gt;-&lt;time&gt;/: <i>&lt;ref&gt;.png</i> with the result drawn in, <i>&lt;ref&gt;-raw.png</i>
as taken, <i>&lt;ref&gt;.json</i> what was used and found). Offset limits depend on the part: <b>along</b> it (towards one
pad) 15 % of its length, <b>across</b> 30 % of its width, never below 0.15 mm (0603: 0.24 / 0.24 mm, 0805: 0.30 / 0.38);
angle 8 deg (nearly square parts 15); golden score OK &ge; 0.70, FAIL &lt; 0.45.
<b>Limits...</b> sets the offset (along / across in % of the part, minimum in mm) and rotation limits between OK and
CHECK, with the allowed values shown for 0402 .. SOT-223 while you change them. They are saved
(inspection/limits.json), used by every next inspection and applied at once to the results in the table (your
<i>Set as OK / NOT OK</i> and drawn decisions are kept). <i>Defaults</i> restores the values above.</p>
<p><i>Show image</i> (or double-click a row): the picture, opened <b>zoomed on the part</b>; <b>&lt;&lt; Previous / Next
&gt;&gt;</b> (or the arrow keys) go through the results in the table's order, <i>only not OK</i> skips the good ones. In
the picture: <b>cyan dashed</b> = where the part should be, cross = placement location; the <b>box</b> = the part found
(green OK, orange CHECK, red FAIL); <b>magenta</b> = drawn by you. <i>Camera to part</i> puts the top camera over the
placement. <i>Set as OK</i>: you checked it and accept it (logged; parts of packages with golden samples are added as
samples: learning). <i>Set as NOT OK</i>: the reason (not assembled, bad rotation, shifted, wrong part, other); a not
assembled part can be marked <b>not placed</b> in the job so the next run places it again (for a placed part: remove
it from the board first).</p>
<p><b>Draw where the part is</b> - when the detection was wrong: drag a rectangle around the real part (its body with
the terminations / leads). The verdict then comes from where you drew it (OK within the limits, else CHECK offset),
the case is <b>saved for learning</b> (inspection/learning/: picture + your box, the test set the detection is tuned
on) and, for a package with golden samples, the part becomes one more golden sample centred where it really is.
<b>Keep the drawn size</b> (ticked when the placement is at 0 / 90 / 180 / 270 deg): the rectangle becomes the
package's <b>top-view size</b> for every next inspection, before the package body, the EIA code or the lead span.
The package footprint is not changed - bottom vision keeps its own size (for diodes the bottom camera sees only the
contacts, so its body size is smaller than the part seen from the top). <b>Drawn sizes...</b> lists them and forgets
the selected ones.</p>
""" + MOVES % "the <b>top camera</b> only (safe Z): Inspect selected, Camera to part.",
    "tips": {
        "only placed": "Show only placements marked as placed in the job (off: all placements).",
        "Select all": "Tick all listed placements.", "Select none": "Untick all placements.",
        "Select not OK": "Tick the placements whose last result is CHECK, FAIL or ERROR (to inspect them again).",
        "Inspect selected": "Camera over each ticked placement, analyse, save the image.",
        "Drawn sizes...": "Top-view sizes kept from 'Draw where the part is' (used instead of the package body); "
                          "forget selected ones.",
        "Limits...": "Offset and rotation limits between OK and CHECK (saved; applied to the shown results at once, "
                     "your decisions by hand kept).",
        "Make golden from selected": "Use the clicked, inspected placement (a GOOD part) as the golden sample of its package.",
        "Show image": "The saved image of the clicked row with the result drawn in, zoomed on the part; << Previous / Next >> "
                      "through the results, Set as OK / NOT OK and Draw where the part is there (double-click a row does the same).",
        "Camera to part": "Top camera over the clicked placement, part top in focus, to look at it in the camera view.",
        "Set as OK": "Accept the selected not-OK placement(s) as OK after your check (asks first; logged; image and CSV updated).",
        "Set as NOT OK...": "Your verdict for the selected placement(s): not assembled / bad rotation / shifted / wrong part / "
                            "other (logged; image and CSV updated). Optionally marks them NOT placed in the job, so the "
                            "next job run places them again (default for 'not assembled').",
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
cannot be used (no slot, no location, disabled, ...). Read-only towards the job; the configuration changes only by <i>Refill / set count</i> and a confirmed <i>Measure body size</i>.</p>
<p>A part whose package has <b>no compatible nozzle tip loaded</b> is an issue too: the job would try an automatic
tip change and stop with "Can't move ... soft limit" (no tip changer). Fix: tick a loaded tip in
<i>Packages &gt; Nozzle Tips</i>, or load the needed tip by hand.</p>
<p><b>Parts left</b>: tray and strip feeders count their picks, so the <i>Feeder(s)</i> column shows e.g.
<i>[3 of 5 left]</i>, and a part whose feeders hold fewer than the job still needs is an issue before the job runs.
When a tray runs empty, OpenPnP switches the feeder off and the job stops with "No compatible, enabled feeder found".
<b>Refill / set count</b> (also what <i>Go to problem</i> opens for it): enter how many parts are in the feeder now,
and switch it on again. Works with the job paused; then resume it. Photon feeders do not report a count.</p>
<p><b>Measure body size</b> (also what <i>Go to problem</i> opens for "no body size"): a package without body size
fails OpenPnP's bottom-vision size check on every part ("width too large: nominal 0.000"). After you confirm, one
part is fed and picked from its feeder, shown to the bottom camera 5 times (nozzle turned 0 / 90 / 180 / 270 / 0 deg,
OpenPnP's own pipeline - the size its check compares) and given back into the feeder. You see the 5 results; only
when they agree within 10 % is the median proposed, and it is applied as the package's body size only when you
confirm. Needs an empty nozzle with a fitting tip loaded and a usable feeder; also with the job paused.</p>
<p><b>Copy part ID</b>: for the search field of OpenPnP's <i>Feeders</i> tab (tray feeders are all called
"ReferenceTrayFeeder", the part finds them).</p>
<p><i>Show on feeder LEDs</i>: green = needed and ready, red = needed but has an issue, off = not used by the job.</p>
<p><b>Go to problem</b> opens where the selected line's problem is fixed, with the row already selected:
a feeder OpenPnP will not use -&gt; <i>Feeders</i> tab, that feeder (its settings below the table); no feeder has the
part -&gt; <i>Scripts &gt; Lumen &gt; Feeders</i>, tab <i>Assign feeders</i>, the part selected; nozzle tips or body
size -&gt; <i>Packages</i> tab, the package; part height -&gt; <i>Parts</i> tab, the part. <b>Next problem &gt;&gt;</b>
walks through all problems of the job one by one. Coming back to this window re-reads the job, so fixed lines turn
green.</p>
<p><i>Camera to feeder</i> (or double-click a line): the top camera goes over the pick location of the selected
part's feeder; press again for its next feeder. Also while the job is paused. <i>Camera to next placement</i>: over the part's placements on the
board, not yet placed ones first; each press goes to the next one. The status line says where the camera is.</p>
""" + MOVES % "top camera at safe Z (Camera to feeder / placement, also with the job paused); Measure body size: "
                "feed, pick, bottom camera, part back into its feeder (after you confirm); otherwise none.",
    "tips": {
        "Go to problem": "Open the OpenPnP tab (Feeders / Packages / Parts) or the Lumen Feeders window where the selected "
                         "line's problem is fixed, with that row selected. Several problems: you choose which.",
        "Refill / set count": "A tray / strip feeder of the selected part: how many parts are in it now (sets its pick "
                              "count) and switch it on again after OpenPnP switched it off as empty.",
        "Measure body size": "Package of the selected part has no body size: pick one part, 5 bottom-camera shots, "
                             "part back into the feeder; you confirm the measured size before it is applied.",
        "Copy part ID": "Copy the selected part id, to paste into the search field of OpenPnP's Feeders tab.",
        "Next problem >>": "Go to the next problem of the job (all lines, one problem at a time), the same way.",
        "Camera to feeder": "Top camera over the selected part's feeder (again: its next feeder). Double-click a line does the same.",
        "Camera to next placement": "Top camera over the selected part's next placement on the board (not yet placed first).",
        "Refresh": "Re-read the job and the feeders (also done when you come back to this window).",
        "Show on feeder LEDs": "Light the job's Photon feeders: green ready, red issue, others off.",
        "Feeder LEDs off": "Switch the feeder LEDs off again.",
        "Close": "Close the window.",
    },
    "columns": {
        "Part": "Part id.", "Package": "Package.", "Height mm": "Part height (needed for placing).",
        "Total": "Placements of this part in the job.", "Remaining": "Not yet placed.",
        "Feeder(s)": "Feeders holding the part; [n of m left] for trays and strips.", "Issues": "Why the part cannot be placed yet.",
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
HELP["feeder_assist"] = {
    "title": "Feeder Assistant - the job's feeders with the camera; feeders for a new board / panel",
    "html": """
<p><b>Tab Job feeders (camera)</b>: every feeder the open job uses, one line each, in slot order (front rail, then
rear), with its part, references, how many are left and whether it is ready. <b>Next &gt;&gt;</b> moves the top camera
to the next feeder's pick location (<i>&lt;&lt; Previous</i> back; double-click a line goes to that one).
<i>Identify</i> blinks the selected feeder's LED. Parts that no feeder holds are listed last.</p>
<p><b>Tab Assign feeders</b> (new board / panel): another project often names the same component differently (<i>C0402-0.1uF</i> vs <i>C_0402_1005Metric-100n</i>),
so OpenPnP sees a new part without a feeder. The assistant reads every part name of the open job - <b>kind</b>
(C, R, L, ferrite, LED, ...), <b>value</b> (100n = 100nF = 0.1uF, 4k7 = 4.7k, 0R1 = 0.1 ohm), <b>size</b> (0402, also from
1005Metric), voltage / dielectric / tolerance, LED colour, part number - and compares it with the parts of the
feeders you have already set up.</p>
<ol>
<li>Open the job with the new board / panel, then this tool. The list shows the parts without an enabled feeder
(untick the filter to see all).</li>
<li>Click a part: below, the <b>matching feeders are on top</b> (best first, green = strong, yellow = check the warning,
grey = weak), then all other feeders. Passives are proposed only with the <b>same kind, value and size</b>; a lower
voltage, other dielectric or worse tolerance is shown as a warning.</li>
<li><i>Identify</i> blinks the feeder's LED to find the reel. <i>Choose this feeder for the part</i> (also a
non-matching feeder, after a question). <i>Pre-select strong matches</i> fills only clear, warning-free proposals.</li>
<li><i>Apply choices</i>: a confirmation lists every change. Nothing changes before.</li>
</ol>
<p><b>Apply as:</b> <i>the job uses the feeder's part</i> (recommended): the board's placements take the feeder's part, so
its height, package, vision and nozzle tips stay as set up; the board / panel files are saved. <i>the feeder gets the job's
part</i>: the feeder's part is replaced in the machine configuration (the job's part then needs height etc.).</p>
<p>Your choices are remembered (~/.openpnp2/lumen/partmatch.json): the same part name in a later project is proposed
first ("confirmed by you before"). For parts where orientation matters and the package names differ, check the
rotation in Orientation Setup.</p>
""" + MOVES % ("top camera only, at safe Z (Job feeders: Next / Previous / Camera to feeder / double-click; Look at "
                "this feeder). Identify blinks the feeder's LED only."),
    "tips": {
        "<< Previous": "Top camera to the previous feeder of the job (wraps round).",
        "Camera to feeder": "Top camera to the selected feeder's pick location (double-click a line does the same).",
        "Next >>": "Top camera to the next feeder of the job, in slot order (wraps round).",
        "Refresh": "Re-read the open job and the feeders.",
        "only parts without an enabled feeder": "Hide parts that already have an enabled feeder holding exactly this part.",
        "Choose this feeder for the part": "Use the selected feeder (below) for the selected part (above). Not applied yet.",
        "Identify (blink LED)": "The selected feeder blinks its LED white 3 times (Photon IDENTIFY). No motion.",
        "Look at this feeder": "Top camera over the pick location of the selected feeder (or the part's chosen feeder) and a "
                               "zoomable picture next to the job part: is it the intended component? The yellow outline is "
                               "the job part's body size from its package. Camera move only.",
        "Pre-select strong matches": "Choose the best proposal for every part where it is strong (score >= 85), has no "
                                     "warning (also not: an IC with another package name) and no equal second. A disabled feeder is "
                                     "allowed (shown as a warning at Apply). "
                                     "Check them, then Apply.",
        "Clear choice": "Remove the choice of the selected part.",
        "Apply as:": "Recommended: the job's placements use the feeder's part (feeder and part settings unchanged, board / "
                     "panel files saved). Or: the feeder gets the job's part (machine configuration).",
        "Apply choices...": "Show every change with its warnings and apply after your OK. Choices are remembered for later projects.",
        "Close": "Close (choices not applied are lost).",
        "Select a part above": "Which part the feeder list is for, how its name was read, how many feeders match.",
    },
    "columns": {
        "Part": "Part id in the job (from the board import).", "Refs": "Placements of the part.", "Qty": "Number of placements.",
        "Read as": "What the name was read as: kind, value, size, voltage, dielectric, tolerance / LED colour / part number.",
        "Feeder now": "Feeders that already hold exactly this part.",
        "Best proposal": "Best matching feeder and why.", "Score": "Match score 0-100: 100 same part, 99 confirmed before, "
        ">= 85 strong, 40-84 check the warning, < 40 weak.",
        "Your choice": "Feeder you chose (applied only with Apply choices).",
        "Feeder": "Feeder name.", "Slot": "Photon slot address.", "Feeder part": "Part set up on the feeder.",
        "Why": "What matched.", "Warnings": "What to check before choosing (voltage, dielectric, size, keywords only).",
        "Enabled": "Whether the feeder is enabled.",
        "#": "Position in the camera round.", "References (not placed first)": "Placements of the part, not placed first.",
        "Left": "Placements of the part not placed yet.",
        "Status": "ready, or why the feeder / part cannot be used yet (disabled, no location, no loaded nozzle tip, ...).",
    },
}
# Feeders = Feeder Part Check + Feeder Assistant in one window (2026-11-26: "shall be merged")
HELP["feeders"] = {
    "title": "Feeders - the job's feeders with the camera, pick location check, options while feeding, assign feeders",
    "html": """
<p><b>Job feeders</b>: the feeders of the open job (untick <i>only feeders of the open job</i> for every Photon feeder),
with the references they serve, how many are left and the job status. <b>Next &gt;&gt;</b> moves the top camera to the
next feeder, <i>&lt;&lt; Previous</i> back, double-click a row goes to that one; the line on top says where the camera is.
Feeders that are not Photon feeders (tray, strip) are listed for the camera round only.</p>
""" + HELP["part_check"]["html"] + """
<p><b>Assign feeders (new board)</b>: """ + HELP["feeder_assist"]["html"].split("<p><b>Tab Assign feeders</b> (new board / panel): ", 1)[-1],
    "tips": {},
    "columns": {},
    "tabs": {
        "Job feeders": "The open job's feeders: camera round (Next / Previous), check them now with the camera, apply the "
                       "pick offset, set it by hand.",
        "Options per feeder": HELP["part_check"]["tabs"]["Options per feeder"],
        "Assign feeders (new board)": "A new board / panel: which set-up feeder holds each part (name matching), applied "
                                      "after your confirmation.",
    },
}
for _k in ("part_check", "feeder_assist"):
    HELP["feeders"]["tips"].update(HELP[_k]["tips"])
    HELP["feeders"]["columns"].update(HELP[_k].get("columns", {}))
HELP["feeders"]["tips"].update({
    "Camera to feeder": "Top camera to the clicked feeder's pick location (any tab; double-click a row in Job feeders).",
    "<< Previous": "Top camera to the previous feeder of the Job feeders list (wraps round).",
    "Next >>": "Top camera to the next feeder of the Job feeders list, in slot order (wraps round).",
    "Identify (blink LED)": "The clicked Photon feeder (Job feeders / Options, or the lower list in Assign feeders) blinks "
                            "its LED white 3 times. No motion.",
    "only feeders of the open job": "Job feeders / Options: only the feeders whose part the open job places (default). "
                                    "Untick: every Photon feeder. Hidden rows are unticked.",
})
HELP["feeders"]["columns"].update({
    "References": "Placements of the job this feeder serves (not placed first).",
    "Left": "Placements of its part not placed yet.",
    "Result": "Check result, or before a check the job status (ready, or why the feeder / part cannot be used yet).",
    "Tape": "Tape found by the check (sprocket holes), or 'not a Photon feeder: no automatic check, offset by hand' (tray / strip: camera, Set offset by hand).",
})


HELP["pick_safety"] = {
    "title": "Pick safety - notice an empty nozzle or a part left on the nozzle, from measured values",
    "html": """
<p>Bench 2026-11-26: the nozzle came down on the cover foil, nothing was picked, and the part was "placed": the vacuum
read 232 with the part-on range ending at 232 (free air 233), bottom vision accepted a 1 x 0 px "part" (no body size,
size check off), and nothing checked after the place. Typing sizes and levels by hand for every part is not practical,
so this window <b>learns them</b> and proposes; only ticked rows change, after a confirmation.</p>
<p><b>Body sizes</b>: bottom vision measures every good pick very consistently (RES_0603: 1.45 x 0.80 mm every time,
an empty nozzle 0.04 mm). The median of the good picks in OpenPnP's log becomes the package body size, in the
orientation OpenPnP's size check compares. With the <b>size check</b> on (BodySize, generous tolerance) an empty
nozzle fails bottom vision and OpenPnP picks again. Note: the size is what the bottom camera sees (e.g. only the leads
of a SOD-323), which is right for this check.</p>
<p><b>Vacuum</b>: <i>Measure free air</i> turns the vacuum on for 1.5 s per nozzle (empty, no motion). The part-on
high limit goes halfway between the highest good pick and free air. The <b>part-off check</b> (OpenPnP turns the vacuum
on for the probing time after a place: a part still on the nozzle seals it) is proposed only where free air and a
part on the nozzle are clearly apart; it adds that time to every placement, so it is not ticked by default.</p>
<p>Data source: the current OpenPnP log (picks after the last nozzle tip change). Changes are saved with OpenPnP's
configuration.</p>
""" + MOVES % "none; <i>Measure free air</i> switches the vacuum on for 1.5 s per nozzle (no motion).",
    "tips": {
        "Measure free air...": "Vacuum on for 1.5 s per nozzle with the EMPTY nozzle, no motion: the free-air level and its "
                               "build-up (for the part-on and part-off proposals).",
        "Apply ticked...": "Lists every change, applies after your OK, logs old and new values.",
        "Close": "Close the window (nothing changes).",
        "size check on": "Switch OpenPnP's bottom-vision size check to BodySize with a generous tolerance in the vision "
                         "settings the job's parts use.",
    },
    "columns": {
        "Apply": "Tick to set this package's body size to the measured one.", "Package": "Package id.",
        "Job parts": "Parts of the open job with this package.",
        "Measured W x H mm": "Median bottom-vision size of the good picks (OpenPnP's orientation).",
        "Good picks": "Picks used for the median.", "Empty picks": "Picks where bottom vision saw nothing (accepted!).",
        "Now W x H mm": "Current footprint body size.", "Note": "How the value was found, or why there is none.",
        "Part-on": "Tick to set the proposed part-on high limit.", "Nozzle / tip": "Nozzle and its loaded tip.",
        "Free air": "Measured with the empty nozzle (Measure free air).", "Part-on now": "Current part-on range.",
        "Proposed high": "New high limit, or why none.", "Part-off": "Tick to switch the part-off check on.",
        "Part-off proposal": "Probing time and limit, or why none.",
    },
}


HELP["orientation"] = {
    "title": "Orientation Setup - pin 1 in the feeder vs. in the CAD footprint",
    "html": """
<p>For parts where orientation matters: pin 1 <b>in the feeder</b> (seen from above) and <b>in the CAD footprint</b>
at 0 deg. From the two the rotation in the feeder follows (4 corners = 0/90/180/270).</p>
<p><b>What to load (one is enough, all are optional):</b></p>
<table cellpadding='2'>
<tr><td valign='top'><b>KiCad board .kicad_pcb</b></td><td>Best. Pin 1 of every footprint, verified against the job
(reference, footprint, rotation, position). Another revision is refused for the positions, but still gives pin 1
<b>by footprint name</b> (confirm once per part).</td></tr>
<tr><td valign='top'><b>Top copper Gerber X2</b></td><td>When the board file is not available. Only the <b>F.Cu</b> layer
in <b>Gerber X2 with netlist attributes</b> (KiCad Plot: tick <i>Use extended X2 format</i> and
<i>Include netlist attributes</i>). Silkscreen, mask, paste, drill, and old Gerbers (RS-274X / X1, no attributes) have no pin
numbers and are refused with the reason. A folder or .zip with all Gerbers is fine: the top copper is picked.</td></tr>
<tr><td valign='top'><b>Footprint library .pretty</b></td><td>Only for footprints that are not in the board file and not in
the KiCad standard library (custom footprints), when the job came from a .pos file. A folder of .pretty folders is fine.</td></tr>
<tr><td valign='top'><b>Nothing</b></td><td>Set pin 1 by hand in <i>Check selected</i> (two squares). Confirmed
footprints are remembered for later jobs.</td></tr>
</table>
<p><b>Checks:</b> a file that does not match the job is refused as a whole with the reason (e.g. "only 0 of 249 placements
found: other design or revision?"); single parts that cannot be verified say why in Status. Parts whose CAD pin 1 is
unknown show <b>CAD pin 1 NOT DETECTED</b> with what to load. <i>Detection report</i> lists every part (detected from
which source / not detected and why) and saves it to ~/.openpnp2/lumen/logs/.</p>
<p>Every mark is confirmed in the two squares (<i>Check selected</i>). Nothing is changed on the feeder without
<i>Confirm and apply</i>.</p>
<p><b>Still in doubt?</b> <i>Test placement on the PCB</i> puts one part on its real pads (board without paste), you mark
pin 1 in the photo, and the part goes back into its feeder (nothing wasted). Meant for the bigger, polarised parts (ICs,
diodes, LEDs, electrolytics); parts marked "orientation not relevant" are skipped.</p>
""" + MOVES % ("<i>Show top camera at the feeder</i> moves the camera; <i>Test placement on the PCB</i> feeds, picks, "
                "places and picks up again (only after its own confirmation)."),
    "tips": {
        "Load CAD data (board / Gerber / library)": "Choose a KiCad board (.kicad_pcb), the top copper Gerber X2, a folder or "
                                                    ".zip with the Gerbers / the KiCad project, or a footprint library folder. "
                                                    "The tool says what it found; a wrong file (silkscreen, drill, .pos, old "
                                                    "Gerber without X2) is refused with the reason. One input is enough.",
        "Detection report": "List every part where orientation matters: pin 1 detected (from which file, confirmed or not) or "
                            "NOT DETECTED with the reason and what to load. Saved to ~/.openpnp2/lumen/logs/.",
        "only parts where orientation matters": "Hide resistors, capacitors and other parts whose orientation does not matter.",
        "Check selected (two squares)": "Open the two squares for the selected row: click pin 1 in the feeder and in CAD.",
        "Test placement on the PCB": "For the selected row(s) you are not sure about: place one part on its real pads (board "
                                     "WITHOUT solder paste), photograph it, mark pin 1 in the photo, then the part is picked up "
                                     "again and recycled into its feeder. Several rows: one window after the other. Rows marked "
                                     "'orientation not relevant' are skipped.",
        "Toggle 'orientation matters'": "Override the automatic decision for the selected part.",
        "Refresh": "Re-read the job, feeders and sources.",
        "Close": "Close the window.",
    },
    "columns": {
        "Part": "Part id.", "Footprint": "Footprint name.", "Refs": "Placements of the part.",
        "Orientation": "matters / not relevant.",
        "CAD pin 1": "Pin-1 corner in the footprint at 0 deg: auto (from which file) or confirmed; '-' = not detected.",
        "Feeder": "Feeder holding the part.", "Feeder mark": "Pin-1 corner seen in the feeder.",
        "Needs": "Rotation the feeder needs (deg).", "Feeder now": "Current feeder rotation (deg).",
        "Status": "CORRECT / MISMATCH / to check / CAD pin 1 NOT DETECTED (with the reason and what to load).",
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

HELP["orientation_test"] = {
    "title": "Test placement - the part on its real pads, pin 1 marked in the photo, then recycled",
    "html": """
<p>For a part you are not sure about (mostly bigger, polarised parts: ICs, diodes, LEDs, electrolytics): <b>one</b> part is fed, picked, aligned (bottom vision, as in the job) and placed on
its real pads, then photographed with the top camera. <b>The board must have NO solder paste</b> on these pads (bare or test
board): the part is picked up again afterwards.</p>
<p>At the first trial with a nozzle / tip after OpenPnP started, OpenPnP's <b>nozzle tip calibration</b> (runout and
rotation offset, over the bottom camera) runs for that nozzle - also N2 - even if an older result is stored. Later
trials in the same session use it. If calibration is switched off for the tip, the photo panel says so in red.</p>
<p>In the photo: the <b>red dot</b> = pin 1 of the <b>part</b> (click it; preset only when a golden sample of the package
recognises the turn), the <b>green ring</b> = pin 1 of the <b>board</b> (from CAD; switch the click mode and move it if the
silkscreen / pad 1 says otherwise). Light pads = CAD pads at the placement rotation (red = pad 1).
Same corners -> CORRECT. Different -> the feeder rotation that would have been right is shown.</p>
<p><b>Zoom the photo like OpenPnP's camera view:</b> mouse wheel = zoom in / out at the pointer, drag = move the zoomed
photo, right click = fit again. Zooming out below the fit shows the whole camera frame around the part. The photo starts
at about one screen pixel per camera pixel (as sharp as the camera view); further in, the camera's pixels are
interpolated. Clicks set the marks at the zoomed position.</p>
<p><b>Finish</b> picks the part up from the board in the same grip (corrected by where the camera found it) and, by
<i>After the decision</i>, returns it to its feeder with OpenPnP's take-back: <b>Photon: back into its pocket, the next feed
is skipped</b> (the tape does not move, the job picks this same part); strip / tray feeders: back into its pocket, feed count
- 1. If the feeder cannot take it back it is discarded and that is reported. A corrected rotation is applied only
<b>after</b> the part is back (you are asked), and the marks are stored as confirmed for Orientation Setup. Closing the window
with the part on the board asks what to do with it.</p>
<p>Not used: the Lumen while-feeding camera check and the pick vacuum check (they belong to job feeds); the job's placed
status is not changed.</p>
""" + MOVES % "<i>Start test placement</i>: feed, pick, bottom vision, place, top camera; <i>Retake photo</i>: camera; "
                 "<i>Finish</i>: pick up from the board, take back into the feeder (or discard). Each after confirmation.",
    "tips": {
        "Placement": "Which placement of this part is used (the first one not placed yet is preselected). The part goes on "
                     "these pads.",
        "Nozzle": "Empty nozzles whose loaded tip suits the package. No automatic tip change: load the tip first.",
        "After the decision": "What Finish does with the part: back into its feeder (recommended, nothing wasted), to the "
                              "discard location, or leave it on the board.",
        "The pads of this placement have NO solder paste": "Required: the part is put on the bare pads and picked up again. "
                                                           "With paste the part and the pads would be smeared.",
        "Bottom vision alignment as in the job": "Align the part with the bottom camera before placing, exactly like the job "
                                                 "(recommended: the test then shows what the job would place).",
        "Click marks pin 1 of the PART": "A click in the photo sets the red dot: the corner where the part's own pin-1 mark is.",
        "Click marks pin 1 of the BOARD": "A click in the photo moves the green ring: the corner where the board's pin-1 "
                                          "marking (silkscreen dot, pad 1 shape) is.",
        "Save as golden sample": "Only for a CORRECT part: Placement Inspection compares later placements of this "
                                           "package with this photo, and the next test placement can preset the part mark.",
        "Start test placement": "Feed, pick, align, place on the selected placement, photograph. Asks first.",
        "Retake photo": "Photograph the placed part again (camera only).",
        "Finish": "Pick the part up from the board and recycle it (After the decision); store the result; set the corrected "
                  "feeder rotation if you agree.",
        "Close": "Close; if the part is still on the board you are asked whether to return it to the feeder first.",
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
machine enabled, job open (and no board still at X 0 / Y 0, i.e. added again without its position), home if needed, lights, nozzle tips, vacuum sensors, job readiness, feeder bus,
orientation confirmations, pick checks (part-on / part-off vacuum checks of the loaded tips and the bottom-vision
part size check: what would notice an empty pick or a part left on the nozzle), scripting engines (pooled automatically while a job runs, fresh code when stopped / paused;
without it every Lumen job hook loads a new Python engine: ~0.6 s per feed / pick / placement), optional board Z. Steps added in a newer version run
also when your preflight.json is older. Result PASS / WARN / FAIL; it does not start or block the job.</p>
""" + MOVES % "only <i>home</i> (if the step is on and the machine is not homed).",
    "tips": {
        "checklist:": "The checklist file in use.",
        "Run checks": "Run all enabled steps in order.",
        "Edit checklist": "Open preflight.json in the editor.",
        "Pick safety...": "Learned from the machine's own measurements: body sizes from bottom vision (+ size check), "
                          "vacuum part-on high limit and part-off check. Proposals only; ticked rows change after your OK.",
        "Close": "Close the window.",
    },
    "columns": {"Step": "Check name.", "Result": "PASS / WARN / FAIL / SKIP.", "Detail": "What was found."},
}

# ---------------------------------------------------------------------------------------
HELP["machine_cal"] = {
    "title": "Machine Calibration - the Opulo V4.1 calibration guide, automated",
    "html": """
<p>All <b>fundamental</b> and <b>optional</b> calibration steps of the Opulo LumenPnP V4.1 guide
(Issues &amp; Solutions), in the guide's order. Each calibration is done by <b>OpenPnP's own routine</b> (the same as
its <i>Accept</i> button); this window does what the guide asks you to do by hand: moves the camera / nozzle to the
fiducial, measures the touching Z, sets the feature diameter and checks the detection, changes nozzle tips with you,
carries the calibration target, and checks every result.</p>
<ol>
<li><b>Safety check, backup, homing</b>: backup of machine.xml, nozzles to safe Z, visual home free of the target.</li>
<li>Primary and secondary <b>fiducial</b> (camera only).</li>
<li><b>Nozzle offsets</b> N1 primary / secondary, N2 primary: the touching Z by <b>vacuum contact</b> (slow 0.05 mm
steps, stops at the first contact, max 2.5 mm) or jogged by you.</li>
<li><b>Bottom camera</b> with the tip on N1 ("use nozzle Z", never auto focus), then homing method + homing fiducial.
The Opulo guide swaps to N08 first; tick <i>swap</i> for that, otherwise no tip is changed.</li>
<li>Tips back, <b>precise offsets</b> with the calibration target, <b>camera settling</b>, optional <b>backlash</b> X/Y.</li>
<li><b>Prepare for homing</b> (runout calibration on tip change), <b>home and verify</b>, save (you confirm).</li>
</ol>
<p>Where your hands are needed (tip change, nothing homed yet, a detection that does not match), the run stops and
the right side shows what to do with pictures. <b>Never home while the calibration target lies on the visual
home</b>; the tool checks it with the camera before every homing. The backup is in
~/.openpnp2/lumen/calibration/. At the end the machine is ready for File &gt; New Job / Import Board.</p>
<p>The run goes at <b>50 % machine speed</b> (slower if OpenPnP's speed is set lower); the previous speed is put back
when the run ends or stops.</p>
""" + MOVES % "homing; camera to the fiducials; nozzles <b>down slowly onto the fiducials</b> (contact probe); N1 over the "
              "bottom camera; tip change position; <b>pick and place of the calibration target</b>; backlash test moves.",
    "tips": {
        "Fiducial Z:": "How the touching Z on the fiducials is found: vacuum contact (the nozzle goes down in 0.05 mm steps "
                       "and stops when the open tip is sealed) or jogged by you, as in the Opulo guide.",
        "optional steps": "Also run the optional backlash calibration for X and Y (OpenPnP, up to 15 minutes each).",
        "pause for my check": "Stop before every OpenPnP Accept so you can check the camera view or the nozzle by eye.",
        "swap N1 tip": "Off (default): the bottom camera step uses the tip that is on N1, no tip change. On: N1 gets this "
                       "tip first (Opulo guide: N08), by hand with a picture, and the tips from before are loaded again "
                       "after the step.",
        "Target park X/Y:": "Where the calibration target normally lies (mm). It is taken from here and always returned here.",
        "Run all from the selected step": "Run the selected step and all after it, in the guide's order.",
        "Run the selected step only": "Run only the selected step (for example to repeat one).",
        "Stop after this step": "Stop after the step that is running now. For an emergency use OpenPnP's stop / disable.",
        "Clear status": "Forget the done / failed marks (nothing in the machine changes).",
        "Open the Opulo guide page": "Open the matching page of the Opulo V4.1 guide in the browser (photos of each step).",
        "Close": "Close the window (a running step is stopped after it ends).",
    },
    "columns": {"#": "Order in the Opulo guide.", "Step": "Calibration step.",
                "Type": "fundamental / optional (Opulo guide) or setup (safety, tips, verification).",
                "Status": "done / failed / skipped / running (kept between runs).",
                "Result": "What was measured or changed."},
}
