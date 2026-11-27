# openpnp-lumen: LumenPnP tools inside OpenPnP

OpenPnP **scripts** (Jython 2.7, the interpreter bundled with OpenPnP 2.6), in the menu *Scripts > Lumen*. **OpenPnP itself and `machine.xml` are not modified**: the scripts use OpenPnP's public API, and feeder packets go through the existing `PhotonFeederData` actuator (`M485`), the same path OpenPnP's own Photon feeder support uses. Removing them (`./uninstall.sh`) restores the previous state exactly.

## Menu: Scripts > Lumen

| Script | Purpose | Study ref. | Touches the machine? |
|---|---|---|---|
| **Board Z Probe** | Board surface Z on the job's board fiducials by gentle vacuum contact. Shows Z per fiducial, the mean and the tilt (warning above 0.2 mm); *Apply* sets the board location Z. | §1 | **Moves**: nozzle down slowly onto the fiducials |
| **Feeders** (Feeder Part Check + Feeder Assistant, merged) | One window, three tabs. **Job feeders**: the open job's feeders (untick the filter for every Photon feeder; the job's tray / strip feeders are listed too: camera and *Set offset by hand*, no automatic check) with references, how many are left and the job status; **Next >>** / *<< Previous* / double-click: the top camera goes to that feeder's pick location; *Identify* blinks its LED. Tick feeders and *Check selected*: pocket centre from the sprocket holes (any tape), part at pick (paper tape), *Apply offset*; a part at pick sets OpenPnP's `SkipNext`. When the pocket is NOT FOUND (or looks wrong): *Set offset by hand* opens the check photo (zoomable), you click the pocket centre, *Apply* moves the pick location there (any distance, after a confirmation); a pocket outside the photo is found with *Camera here* / *Camera to slot location* (new photo there); *Camera to feeder fiducial* looks at the round marks on the feeder nose (position from the Photon feeder CAD, ~13 mm past the pick location), finds the centre mark (only with its two side marks) and shows the pick location relative to it. **Options per feeder**: "While feeding" centring and pick vacuum check during the job (`Feeder.BeforeFeed`, `Nozzle.AfterPick`). **Assign feeders (new board)**: which **already set-up feeder** holds each part, although the project names it differently. Reads kind, value (100n = 0.1uF, 4k7, 0R1), size (0402 / 1005Metric), voltage / dielectric / tolerance, LED colour, part number; per part the **matching feeders on top** (why, warnings), then all others. **You choose**, *Apply* after a confirmation: the job uses the feeder's part (board file saved), or the feeder gets the job's part. Choices are remembered for later projects. *Look at this feeder (camera)* shows a zoomable picture of the feeder's pick pocket next to the job part. Details: [matching rules](#feeders-assign-feeders-matching-rules). | §2/§3/§5 | Camera only; LED blink on *Identify*; pick location on *Apply offset* / while feeding; board file / feeder part on *Apply choices* |
| **Feeder Firmware Update** | Update Photon feeder firmware over the bus, feeders mounted, OpenPnP connected. Pick the binary, scan the bus, tick feeders (all / some / outdated), update with progress, log and result per feeder. | §7 | Feeder bus only |
| **Job Readiness** | View limited to the open job: only its parts and feeders, quantity / remaining, part height, and precisely why a feeder is not usable. Optional: job feeders shown on their LEDs (green = ready, red = issue, off = not used). *Camera to feeder* (or double-click a line) / *Camera to next placement*: the top camera goes over the selected part's feeder or its placements on the board (not yet placed first; each press: the next one; also with the job paused). *Go to problem* / *Next problem*: the OpenPnP tab or Lumen window where the problem is fixed, row selected. Tray / strip feeders show *[n of m left]*; too few parts for the job is an issue, *Refill / set count* sets the count and switches an emptied feeder on again. *Measure body size*: a package without body size (OpenPnP's size check would reject every part) is measured with the bottom camera, 5 shots of one picked part that then goes back into its feeder; applied only after you confirm. *Copy part ID* for the Feeders tab search. | §5 | LEDs (on request); top camera at safe Z on *Camera to ...* (homed machine only); feeder count / package body size only on your confirmation; Measure body size: feed, pick, bottom camera, part back into its feeder |
| **Last Placements** | Newest placements first (placement journal). *Mark selected / last NOT placed* (the next run places it again), *Go to* (top camera over the part). | §6 | Camera move on *Go to* |
| **Machine Calibration** | The **Opulo LumenPnP V4.1 calibration guide, automated**: all fundamental and optional Issues & Solutions steps in the guide's order (fiducials, nozzle offsets, bottom camera, precise offsets, camera settling, backlash X/Y, homing preparation), each done by **OpenPnP's own routine**. The tool positions camera / nozzles, measures the touching Z by vacuum contact, changes tips with you only if you choose to, carries the calibration target, checks every result, then homes, verifies and saves. Manual actions are shown with pictures. Details: [Machine Calibration](#machine-calibration-details). | — | **Moves**: homing, nozzles down slowly onto the fiducials, N1 over the bottom camera, **picks** the target; changes calibration settings |
| **Nozzle Offset Calibration** | Carries the calibration target from its park spot onto the visual home (OpenPnP pick/place), runs **OpenPnP's own** nozzle offset calibration for the ticked nozzles, carries the target back and checks it. GUI only. | — | **Moves and picks** the target; sets nozzle head offsets |
| **Orientation Setup** (optional) | For the job's parts where orientation matters, two squares: **PIN 1 of the part in the feeder** (as seen from above / in the top camera, which can be shown) and **PIN 1 in the CAD footprint at 0 deg**. Click the pin-1 corner (4 corners = the 4 possible rotations) in each and the rotation in the feeder is calculated; *Confirm*, or *Confirm and apply* to set the feeder rotation. Pin 1 in CAD is detected automatically from **one** of: the **KiCad `.kicad_pcb`**, the **top copper Gerber X2** (netlist attributes), or a footprint library, all via one *Load CAD data* button (file, folder or .zip), and still confirmed in the squares. **What to load, which Gerber, what is checked: [docs/orientation-inputs.md](docs/orientation-inputs.md).** Parts whose CAD pin 1 cannot be detected show "NOT DETECTED" with the reason; *Detection report* lists every part. **With only a `.pos` file**, it is found by footprint name: footprint libraries (`.pretty`), the OpenPnP package footprint, or the **footprint table**, which every import and confirmation fills, so each footprint is confirmed once for all boards. The list shows per part/feeder: auto / confirmed, CORRECT / MISMATCH / to check. Per-type hints (electrolytic: pin 1 = plus, the stripe marks minus; diode: cathode bar; IC: dot or notch). **Still in doubt: *Test placement on the PCB*** places one part on its real pads (board without paste), you mark pin 1 in the photo (zoom in / out to the whole camera frame / pan like OpenPnP's camera view: wheel, drag, right click = fit), and the part is picked up again and recycled into its feeder (Photon: SkipNext; strip / tray: feed count - 1). Meant for bigger, polarised parts; rows marked 'not relevant' are skipped: [docs/test-placement.md](docs/test-placement.md). | §2 | Feeder rotation on *Apply*; test placement: feed / pick / place / pick up / take back, each after confirmation |
| **Pick Offset Learning** | Per feeder: systematic pick error learned from the bottom-vision offsets, damped suggestion, *Apply* / *Undo* for Photon feeders, "made it worse" detection, orientation hint (vision corrects ~90°). Data is recorded in the lumen profile only. | §3, §2 | Feeder offset on *Apply* |
| **Placement Inspection** | Top camera over the job's placed parts. Chip parts (R / C / L 0201..2512, size from the EIA code) by their two terminations along the expected axis, light ceramic bodies as the whole part, missing = solder mask between the pads; SMA/SMB/SMC diodes by their lead tabs; other parts by the dark body; golden samples (up to 6 per package, the best match counts) incl. 180° polarity check. Offset limits per part (along 15 % of the length, across 30 % of the width, min 0.15 mm). Images per run with the result drawn in + `<ref>.json`, CSV report. *Show image*: zoomed on the part, *<< Previous / Next >>* (arrow keys, "only not OK"), *Camera to part*, *Set as OK* (adds golden samples: learning) / *Set as NOT OK...*, **Draw where the part is** when the detection was wrong: verdict from the drawn box, case saved for learning (`inspection/learning/`), optional golden sample. Tuned on a test set of 7 bench runs: `tests/run_inspection_eval.sh` (95 % of present parts OK, missing and shifted parts all caught). *Limits...*: the offset (along / across in % of the part, minimum mm) and rotation limits between OK and CHECK, with the allowed values for 0402..SOT-223 shown live; saved (inspection/limits.json), applied at once to the shown results (drawn parts judged again, *Set as OK / NOT OK* kept). | §2 | Camera only |
| **Preflight** | One-click checklist from `~/.openpnp2/lumen/preflight.json`: machine enabled, job open, home (if needed), lights, nozzle tips, vacuum sensors, job readiness, job feeders answer on the bus (and minimum firmware). PASS / WARN / FAIL. **Pick safety...**: learns from the machine's own measurements and proposes, you tick: package body sizes from bottom vision (median of the good picks in OpenPnP's log, e.g. RES_0603 1.45 x 0.80 mm) plus OpenPnP's size check (BodySize, 40 %) so an empty nozzle fails bottom vision; vacuum part-on high limit between good picks and free air (*Measure free air*: vacuum on, no motion); part-off check after place where empty and part-on build-ups are clearly apart (adds its probing time per placement, not ticked by default). | §4 | Homing (if enabled and needed), lights |

**Help inside every tool:**
- **"▸ Help" at the top of each window** unfolds a short description: what the tool does, the steps, what moves the machine, and every option and column.
- **Tooltips:** every option, button and input field has one (one or two concrete sentences, with defaults and units); table column headers have tooltips too.
- **Source:** all texts are in `lib/lumen/helptext.py` (one place, easy to correct).
- **Test:** `tests/run_help_offline.sh` opens every tool and fails if any control or column has no description.

**Feeder Firmware Update details:**
- **Guards:**
  - The machine must be enabled.
  - No job may be running; if the job state cannot be read, you are asked.
  - The binary is checked: size ≤ 31,744 B, vectors, version and bus-update entry.
  - The confirmation lists every selected feeder.
- **Feeder states:**
  - Feeders without the bus loader (old firmware) are listed but cannot be ticked. They need the one-time dongle flash of the `*-factory.bin`.
  - A feeder that was interrupted (magenta LED) is listed as "in bus loader" and can be ticked to finish the update.
- **Cancel** skips the remaining feeders. A feeder that has already been erased is always completed.
- **Logs:** `~/.openpnp2/lumen/logs/feeder-update-*.log`, plus INFO lines in `OpenPnP.log`.

**Placement journal:**
- It is an event hook, installed only with `--journal`.
- It writes `~/.openpnp2/lumen/placement-journal.jsonl`, one line per placement.
- It never raises into the job.
- Without it, *Last Placements* lists the job's placed placements without order.

**Safe homing** (`Events/Startup.py`, installed by `./install.sh`):
- OpenPnP's *Home* (Machine Controls button, *Machine > Home*, hotkey) sends G28 at once, also with a nozzle down. On the bench, N1 was left at Z 3.2 and Marlin stopped with "Homing Failed" and a kill.
- With the hook, *Home* first checks:
  - **homed** (heights known): every nozzle goes to safe Z, and the visual home is checked free of the calibration target. Then it homes. The log names any nozzle that was lowered.
  - **not homed** (heights unknown: power-up, after a kill or E-stop): a dialog with pictures asks you to confirm by eye that both nozzles are up and level and the target is parked.
- OpenPnP's button, menu item and hotkey keep their look and enabled state; only what a press does changes. `machine.xml` is not changed. Remove the `Events/Startup.py` link (or `./uninstall.sh`) to go back to plain *Home*. Takes effect at the next OpenPnP start.
- Why not in G-code: OpenPnP only fills home coordinates into the home command. A `G1 Z..` before `G28` is wrong after a controller reset, when Marlin takes the current position as 0.

**Board positions live in the job** (`Events/Startup.py`, `lib/lumen/lastjob.py`):
- OpenPnP starts with an empty job. Adding the board file again (*Add Board*) creates a new board at X 0 / Y 0 / Z 0 / 0 deg. The position set before is in the saved `.job.xml`.
- At start-up, if the job is empty and the last job file (*File > Open Recent*) exists, a question offers to reopen it. *Yes* opens it as *File > Open Job* would.
- Preflight (*job open*) fails, and Job Readiness shows a red line, when an enabled board is still at X 0 / Y 0.

**Scripting engines pooled while a job runs** (`Events/Startup.py`, `lib/lumen/enginepool.py`):
- Without pooling OpenPnP loads a new Python engine for every event script: ~0.6 s per Lumen hook call, ~1.9 s per part with the three job hooks (bench 2026-11-26). With pooling, changed Lumen code reaches the hooks only after a restart.
- So, when *Pool scripting engines?* is off in the configuration, a 1 s timer follows the job: **Running** (also Pausing / Stopping) -> pooled; **Paused / Stopped** -> not pooled and the pool emptied, the next run loads the current code. With the setting on, OpenPnP pools permanently and the automatic mode stays out of the way. A configuration saved during a job (pooling on) is put back at the next start. Preflight *script_engines* says which mode is active.

**Job errors in words** (`Events/Job.Error.py`, `lib/lumen/joberror.py`):
- OpenPnP reports only the low-level failure. Example (bench 2026-11-26): "Can't move y to -110.698mm, lower than soft limit". The cause was part C11 (package CAPC_2220), whose only compatible nozzle tip N24 was not loaded. The job tried an automatic tip change, and the changer location is not set on a Lumen.
- On a job error, a second message names the parts and references, the package, the tips needed and the fix (tick a loaded tip in *Packages > Nozzle Tips*, or load the tip by hand). It is shown once per distinct text, because OpenPnP repeats the error on every retry. Other soft-limit errors point to the board position and the pick location.
- Before the run: Job Readiness and Preflight (*job readiness*) show the same nozzle-tip issue for every part still to place.

## Install / uninstall

```
./install.sh              # menu scripts + the inert hooks Feeder.BeforeFeed, Nozzle.AfterPick + safe homing Startup (links)
./install.sh --journal    # + placement journal hook (Events/Job.Placement.Complete.py)
./uninstall.sh            # removes exactly these links (settings/logs in ~/.openpnp2/lumen stay)
```

Then use *Scripts > Refresh Scripts* in OpenPnP, or restart it. The installer never replaces a file it did not create.

### Orientation detection details
- **Verified import (`.kicad_pcb` or top copper Gerber):** a file is used for a placement only when it is proven to belong to the job. Nothing is guessed; every refusal says why (load dialog, list status `NOT VERIFIED ...` / `CAD pin 1 NOT DETECTED: ...`, *Detection report*, `orientation-check.sh`). Operator summary: [docs/orientation-inputs.md](docs/orientation-inputs.md).

  | | `.kicad_pcb` | top copper Gerber (`F_Cu`, KiCad X2) |
  |---|---|---|
  | Needs | the board file | *Use extended X2 format* + *Include netlist attributes* (both on in your files). Silkscreen, paste and mask have no pin data and are refused. |
  | Pin 1 from | footprint-local pads (exact) | pads of the part on the board, turned back by the job's rotation |
  | Proof it is the same board as the job | per placement: same reference, footprint name, side, rotation (0.01°), position within 0.01 mm at one common origin offset | per placement: same reference, exactly one copy of the part at the position (one common origin offset), and every part of a footprint shows the same pad pattern (catches a single wrong rotation in the job) |
  | Whole file refused when | fewer than half of the placements are found (other design / revision) | same, or not KiCad top copper with pin attributes |
  | Panels with repeated references | matched by position | the copies are split only if all references give the same copy count AND the split is unchanged with twice the link distance (clear gap); else that reference is refused |

  - **Pin-1 corner rule:** pin 1 relative to the pads' bounding box, normalised per axis. At least 0.6 of the half size on both axes gives a corner. At least 0.6 on one axis and no more than 0.25 on the other gives an end (the corner clockwise of it). Anything in between, no pad "1"/"A1", or pin 1 in the centre is refused, and you set it in *Check*. Pin headers and connectors give the corner a person sees.
  - **Validated on real KiCad 9.0.0 files** (`~/claude/opulo/_testdata/wba65-panel`, outside the repo):
    - `.kicad_pcb`: 108/108 placements verified; a 180° rotation or a 0.02 mm shift of one placement is refused.
    - The 21-up panel Gerber splits into 21 copies of 37 references; only J1 is refused (copies 2.3 mm apart).
    - Gerber pin 1 = `.kicad_pcb` pin 1 for 35/35 parts, including the custom ST footprints.
    - The antenna (origin off its pads) is refused.
    - A `.pos` of another revision is refused by both files.
  - **Before the job, at the desk:** `~/claude/opulo/_tools/orientation-check.sh BOARD-top.pos --cad BOARD.kicad_pcb` (`--cad` also takes the top copper Gerber, a Gerber folder / .zip, a `.pretty`; `--lib DIR`; `--pcb` / `--gerber` still work). Exit 0 = every relevant part verified, 3 = all detected but some only by footprint name (confirm once), 1 = some NOT detected (reason per part), 2 = no usable input.
  - KiCad's library draws some packages rotated compared with datasheets (SOT-23: pins 1/2 on the left). That is why the helper always shows the CAD footprint.
  - A `.kicad_pcb` also fills the footprint table with all its footprints (exact footprint-local data, marked auto), even when the board is another revision. Gerber data is learned only where verified.
- **Position file only (`.pos`, also what assembly partners get with the BOM):**
  - The `.pos` file has no pad data, only footprint name + rotation, and the BOM / CPL add nothing about pin 1 (LCSC numbers point to EasyEDA footprints, whose 0° differs from KiCad's).
  - Pin 1 in the footprint's 0° frame is a property of the **footprint**, the same on every board, so it is looked up by the name OpenPnP's KiCad importer gives the package (= `Package` column). Order: confirmed footprint-table entry, OpenPnP package footprint (pads named, e.g. from *Import KiCad .kicad_mod*), footprint library, auto entry learned from an earlier board/Gerber.
  - Sources that disagree are shown in the list; a confirmed entry is never overwritten automatically.
  - Library dirs: added with *Load CAD data* (a `.pretty` folder or a folder of them), plus the KiCad stock library if installed (`/usr/share/kicad/footprints`, `KICADn_FOOTPRINT_DIR`). Checked: library pin 1 = placed footprint for all 84 uses on the Opulo boards.
  - Without pad data, R/C/L/fiducials are "not relevant" and U/Q/D/LED/CR/J "matter" by reference prefix.
- **Board binding:** a `.kicad_pcb` / Gerber is bound to the OpenPnP board it was imported for, so U1 of another board never takes its pin 1. Older global entries still apply.
- **Schematic:** a KiCad *schematic* (`.kicad_sch`) contains no pad geometry. Pin 1 position needs the board file or the copper Gerber.
- **Marks:** **4 corner marks**, one per possible rotation (0/90/180/270).
  - For 2-terminal polarized parts, pin 1 is an end. Click the corner on the clockwise side of that end (pin 1 left → top-left, bottom → bottom-left).
  - The feeder square draws the footprint's pads (light) as they would sit in the feeder for the chosen corner, to compare with the real part or the camera image.
  - 2-pin parts with R/C/L/FB designators are "not relevant", except electrolytic/tantalum footprints.
- **Overrides:** "Toggle orientation matters" overrides the classification.
- **Storage:** `~/.openpnp2/lumen/orientation.json` holds the sources per board, the footprint table, confirmations and applied rotations. Copy it to another machine to take the confirmed footprints along.
- **Preflight:** the `orientation` step warns about mismatches and unconfirmed parts; it is skipped if the helper was never used.
- **Test placement on the PCB** (rows you select, one window each; [docs/test-placement.md](docs/test-placement.md)):
  - feed, pick, bottom vision and place exactly like the job (`ReferencePnpJobProcessor` steps, OpenPnP 2.6), on a board **without solder paste**; top-camera photo with the CAD pads at true scale;
  - you click pin 1 of the part (red dot) and, if CAD does not know it, of the board (green ring); a golden sample of the package presets the part mark when it clearly recognises the turn;
  - *Finish* picks the part up in the same grip (corrected by the body found in the photo) and recycles it with OpenPnP's `takeBackPart()`; a corrected feeder rotation is applied only afterwards, and the marks are stored as confirmed;
  - the Lumen pick vacuum hook and the while-feeding check are not used for test picks; the job's placed status is not touched.

### Feeders: pick location check and centring while feeding (`Scripts > Lumen > Feeders`, `Events/Feeder.BeforeFeed.py`)
- **Pocket centre from the sprocket holes**, using the EIA-481 tape geometry: holes 1.5 mm every 4 mm; pocket centre F from the hole line (3.5 / 5.5 / 7.5 / 11.5 mm for 8 / 12 / 16 / 24 mm tape, recognised automatically); 2.0 mm along the tape from a hole. Candidate pockets are spaced min(pitch, 4) mm, and the one nearest the current pick location is used.
  - It works on paper, clear and black tape, and for any part size.
  - Checked: it matches the directly detected pocket within 0.08 mm on 5 calibrated feeders.
- **Part at pick** is detected on paper tape only (bright band); on clear or black tape it shows "?".
- **Part already at pick** sets OpenPnP's feed option `SkipNext`, so the next feed is skipped (also in the menu Check).
- **Columns sort** by clicking the header. *Apply offset* moves the pick location onto the pocket centre (read back, max 2 mm).
- **Go to pick location / Identify (blink LED):** for the clicked row, the top camera moves over the feeder's pick location, or the feeder blinks its LED white 3 times (Photon `IDENTIFY_FEEDER` 0xC1 + UUID, every firmware, no motion).
- **Pick vacuum check** (`Events/Nozzle.AfterPick.py`, off by default):
  - Right after each pick the vacuum level is read with the part held. An edge pick seals worse, so the level is closer to free air.
  - Each feeder is compared with **its own typical good pick** (median of the last 10 good picks, after 3 learning picks).
  - A level more than the threshold above it is logged (`PICKVAC` in the feedwatch log). Then, depending on the **action**:
    - **log only**;
    - **re-centre at the next feed** (default): the next feed of that feeder runs the camera re-centring check (also for feeders not ticked "While feeding"; with confirmation if set);
    - **return to feeder, synchronise and pick again (recycle, nothing wasted):**
      1. OpenPnP's `Feeder.takeBackPart()` puts the part back into its pocket. For Photon: nozzle back to the pick location, place, part-off check, and the feeder is set to `SkipNext`.
      2. Re-centring is requested and the hook makes the pick fail on purpose.
      3. OpenPnP's job processor then "discards" an empty nozzle (does nothing), feeds again (the feed hook re-centres = synchronise; the Photon feed is skipped, the tape does not move) and picks **the same part** again at the corrected location.
      4. If the feeder cannot take the part back, or the put-back fails, the part is discarded (logged). Then the checkbox **"if the return fails: discard and feed the next part"** decides:
         - **off (default):** the next feed of that feeder is refused. OpenPnP makes its 1 + feed-retry-count attempts (all refused, no tape movement), then disables the feeder and stops the job with the Lumen message. The part may lie loose on the feeder: check it, re-enable the feeder, continue. The refusal covers exactly those attempts and expires after 60 s, so it never refuses a feed after you continue.
         - **on:** the next part is fed, re-centred and picked.
    - **discard, synchronise and pick again (part wasted):** the part goes to the discard location, OpenPnP feeds the next part, re-centres and picks.
  - "Return" and "discard" use OpenPnP's retry loop, so they need the **part's pick retry count ≥ 1**. With 0, OpenPnP would stop the job instead, so then only re-centring is done and the log says why.
  - *Pick retries for the job's parts...* sets the retry count to 2 for the open job's parts that have 0, after confirmation (`parts.xml` on save).
  - On/off, threshold, action and the return-fails choice can be set per feeder (see Options per feeder).
  - Thresholds are in vacuum counts per nozzle tip. Default about 30 % of the free-air / covered span measured on the bench: **N045 3** (233 / 223), **N08 7** (247 / 224), other tips 3.
  - The feed hook remembers which feeder supplied each nozzle; picks without a feed on that nozzle within 60 s (manual picks) are not judged.
  - Offline-tested through OpenPnP's `Scripting.on()`; **not yet on the machine**.
- **Options per feeder** (tab *Options per feeder*): feeders behave differently with different parts and tapes, so every option for the job can be set **per feeder**:
  - While feeding (on/off), Every N feeds, Confirm, Skip if part, Max mm, Vac check (on/off), Vac threshold (counts, any tip; "per tip" = the tip thresholds), Edge pick action, Return fails: feed next.
  - **Defaults** on top (*Save defaults*, `settings.json` → `feedwatch`, `pickvac`) are used by every feeder without its own value.
  - The table shows each feeder's effective values: **grey / italic = default**, black = the feeder's own value (`settings.json` → `feeder_options`, keyed by the feeder's hardware id). Edit a cell to set an own value. With several rows highlighted (Shift / Ctrl + click), the edit applies to all of them. *Reset highlighted to defaults* removes the own values; the While feeding tick stays.
  - Options follow the physical feeder (hardware id), not the slot or the part. After loading another reel, check that feeder's row.
  - The older single list `feedwatch.feeders` still works: a feeder in it counts as "While feeding" on until it gets an own value.
  - Code: `lib/lumen/feederopts.py` (pure Python; `tests/test_feederopts.py`).
- **While feeding:** tick the feeder's "While feeding" cell. The `Feeder.BeforeFeed` hook (linked by `install.sh`, inert for unticked feeders) then checks every N-th feed of that feeder, with that feeder's options.
  - It moves only the camera. It sets `SkipNext` if a part is at pick, and centres the pick location for offsets between 0.05 mm and the feeder's max (with a dialog Apply / Skip / Stop for this feeder if Confirm is set; Stop = the feeder's own While feeding off). Larger offsets are only logged.
  - Log: `~/.openpnp2/lumen/logs/feedwatch-<date>.log`. The hook never raises into the job.

### Feeders, Assign feeders: matching rules
- **Reading a part name** (`lib/lumen/partmatch.py`, part id + name + package id, plus the job's references):
  - **Kind:** C, R, L, FB (ferrite; also `100R@100MHz`), LED, D, Y, other. Taken from the references (C12 → C; D1 with "LED" in the name → LED), else from the name (`C_`, `CAPC_0402`, `RES_`, `R0603`, `L_`, `COIL`, `FB_`, `LED`, `DIODE`, `Crystal`). A single letter counts only at the start of a name part, so `QFN6L_…` and `L7983` are not inductors.
  - **Size:** 01005 … 2818, also from `1005Metric` → 0402. A name that contradicts its package (named 1210, package 1206) gives "size unknown" plus a warning.
  - **Value:**
    - capacitors: 100n = 100nF = 0.1uF = 0.1µF, 4n7, 1n0;
    - resistors: 4k7 = 4.7k = 4K7, 7k5, 100R = 100 = 100Ω, 0R1 = 0.1R, 1M65, 10m = 10 mΩ;
    - inductors: 2.2_uH = 2u2, 2.5n.
  - **Ratings:** voltage (25V, 1kV; `10u25V` is split), tolerance, dielectric (C0G = NP0 = COG).
  - **Ignored when reading the value:** current (0A5, 5A), frequency, dimensions.
- **Proposals:**
  - **Passives** need the same kind, value and size; a different value or size is never proposed.
    - Score 85 base, +5 voltage ≥ needed, +4 same dielectric, +3 tolerance as good.
    - Lower voltage −30, other dielectric −15, worse tolerance −15, each with a warning. A needed voltage the feeder part does not state gives −10 and a warning.
    - A size missing from one name gives 50 and a warning. An unreadable value with the same kind and size gives 20, "check by hand".
  - **LEDs:** same colour (or the same part number). Never a colour versus no colour.
  - **Other parts:** the same part number gives 95, also with an order-code suffix (`STM32WBA65CI` ~ `STM32WBA65CIx`, ≥ 7 characters). Otherwise shared keywords give 40–90, "keywords only", plus a warning.
    - Package names (QFN, SOT, DFN …) never count as a part number or as the only common keyword.
  - **Never proposed:** fiducials.
  - **Remembered choices:** a confirmed choice (`~/.openpnp2/lumen/partmatch.json`) gives 99, "confirmed by you before".
- **Checked against the real configuration:** 98 feeder parts read correctly, including `CAPC_1206-10u25V`, `RES_0603-100R@100MHz, 0,5A` (ferrite), `RES_2818_Sense-10m` (10 mΩ). Of the 58 parts without a feeder, the proposals were sensible: `RES_0402-100` → `RES_0402-100R`, `CAPC_0805_4u7_16` → `CAPC_0805_4u7_25V`, and no fiducials.
- **Apply:**
  - The window shows every change with its warnings first.
  - *The job uses the feeder's part* (recommended): the board's / panel's placements take the feeder's part, so the tuned height, package, vision and nozzle tips are kept. The board / panel file is saved, and the file names are in the confirmation.
  - *The feeder gets the job's part*: changes the machine configuration (OpenPnP saves it).
  - An IC whose package name differs from the feeder part's warns "check the orientation (Orientation Setup)".
  - *Pre-select strong matches* fills only proposals with score ≥ 85 that have no warning, no equal second, and no package-name difference on an IC. A disabled feeder is allowed and shown as a warning.

### Board Z Probe details (vacuum contact, safety rules)
- **Principle:** with the vacuum on, the open nozzle reads about 233 (N045); when the tip touches a flat surface the opening closes and the level drops (about 223 when covered). The first step with a drop of more than 5 counts (or 6 × noise) is the surface.
- **Rules:**
  - The free-air level is read at **safe Z** (a baseline taken near the board was already "covered" on the bench and the nozzle was driven into the board; that version is gone).
  - The probe aborts if the start height is already covered.
  - 0.05 mm steps at 5 % speed; never more than 2 mm below the start.
  - Vacuum off and safe Z on every exit.
- **Start height:** board Z + 1.5 mm, or `probe_start_z` (default 6.0) while the board Z is 0.
- **Not for light objects:** the calibration target disc moves with the nozzle, so it is handled by OpenPnP's pick/place at the configured calibration Z instead.
- **Bench 2026-11-06 (WBA panel):** REF_1..4 at 4.45–4.50 / 4.25 / 4.10 / 4.40 → mean 4.31, tilt 0.35–0.40 mm, repeatable within one step.

### Machine Calibration details
- **Source:** the Opulo V4.1 guide, from https://docs.opulo.io/openpnp/v4-1/issues-solutions/fundamental/primary-cal-fid-pos/ to *Prepare for homing*. Each row in the window links its Opulo page (photos).
- **Steps** (`lib/lumen/machinecal.py`, one engine method per step; the status is kept between runs):

  | # | Step | Opulo | What the tool does instead of your hands | Your hands |
  |---|---|---|---|---|
  | 1 | Safety check, backup, homing | preflight | backup `~/.openpnp2/lumen/calibration/machine-before-*.xml`; nozzles to safe Z; camera checks the visual home is free of the target; homes if needed | not homed: confirm nozzles up / target parked (pictures) |
  | 2-3 | Primary / secondary fiducial | fundamental | camera over the stored fiducial, feature diameter from the known size, checked with OpenPnP's own detection (±30 %, near the centre), Accept | detection off: adjust the diameter while watching the camera view |
  | 4-6 | Nozzle N1 primary / secondary, N2 primary | fundamental | touching Z by **vacuum contact** (start stored Z + 1.5 mm, 0.05 mm steps, slow, max 2.5 mm), nozzle to that Z (last 0.5 mm slow), Accept (OpenPnP keeps good X/Y offsets and takes the Z); a Z change > 1 mm is asked | option *jog by hand*: you jog down until it touches (Opulo way) |
  | 7 | Bottom camera | fundamental | N1 **with the tip it has** (default; option *swap*: N08 first, as in the Opulo guide, by OpenPnP's manual tip change), over the bottom camera at the primary fiducial Z, choice **"use nozzle Z" (never auto focus)**, tip opening checked against the tip's vision diameter, Accept; then homing method ResetToFiducialLocation, homing fiducial = primary X/Y | only with *swap*: swap the tip (picture) |
  | 8 | Tips back | setup | loads the tips that were on the nozzles before (runout calibration if set); nothing to do without *swap* | only with *swap* |
  | 9 | Precise offsets N1 + N2 | fundamental (2 pages) | target from its park spot onto the primary fiducial, OpenPnP's precise routine per nozzle, target back and checked | only if the target is not at its park spot |
  | 10-11 | Camera settling top / bottom | fundamental | Accept if OpenPnP offers it (only for *FixedTime*), else nothing to do | — |
  | 12-13 | Backlash X / Y | optional | Accept (up to 15 min each); option to skip | — |
  | 14 | Prepare for homing | setup | homing method / fiducial, runout calibration *NozzleTipChange* for every tip with calibration enabled | — |
  | 15 | Home, verify, save | setup | safe Z, visual home free, homing, primary fiducial within 0.1 mm of the camera centre, before / after table, save after your OK | confirm saving |
- **Safety rules:** every move at safe Z; Z goes down only by the contact probe, to a measured contact (last 0.5 mm slow), over the bottom camera to the fiducial Z, or inside OpenPnP's routines; before **every** homing all nozzles go to safe Z and the camera checks the visual home for the target (not homed: you confirm with pictures); the target is never probed by vacuum (OpenPnP's calibration Z only) and never left on the visual home; *Cancel* stops with nothing else moving; afterwards all nozzles go to safe Z.
- **Why the issue texts:** the steps find OpenPnP's issues by their exact texts; checked against the installed OpenPnP jar's constant pool. A missing issue stops the step and lists the issues OpenPnP offers.
- **Pictures:** `lib/lumen/pictures/cal-*.png` (`tools/make_cal_pictures.py`; camera pictures from the bench, 2026-11-06).
- **Tests:** `tests/test_machinecal.py` (order, checks, probe window, OpenPnP texts), `tests/run_machinecal_sim.sh` (OpenPnP's simulated machine: all 15 steps, Accept/wait like OpenPnP, manual tip change via `ManualLoadException`, homing safety, motion limits, cancel, override), window + tooltips in `run_help_offline.sh`. **Not yet run on the real machine.**

### Nozzle Offset Calibration details
- **Sequence:**
  1. Camera finds the target (head setting *calibration test object diameter*) at its park spot (saved in `settings.json` → `target_park`).
  2. OpenPnP pick/place moves it onto the *calibration primary fiducial* (visual home).
  3. `CalibrationSolutions.calibrateNozzleOffsets` (the Issues & Solutions routine) runs for each ticked nozzle.
  4. The target goes back, and the camera checks it.
- **Needs the GUI:** OpenPnP's vision centring draws into the camera view.
- **Never home while the target lies on the visual home:** visual homing then locks onto the target and the coordinates are off by about 2 mm (seen on the bench).
- **Bench 2026-11-06:** N1 offsets −0.019 / −0.012 mm, N2 −0.004 / +0.011 mm; the target was returned 0.08 mm from its park spot. *File > Save Configuration* keeps the offsets.

### Placement Inspection details
- **Location:** board location + placement (`Utils2D`), camera view plane = board Z + part height.
- **Size method:** body length/width from the package footprint body, else footprint pads, else the KiCad name (`…_1005Metric`, `0402`). The blob of that size nearest the location (Otsu / adaptive, bright and dark) gives found / offset / angle (mod 180, mod 90 for square bodies).
- **Golden sample:** *Make golden from selected* on a good, inspected part stores a crop per package (`~/.openpnp2/lumen/inspection/golden/`). Later inspections rotate it to the placement and match (normalised correlation) in a ±0.6 mm window: score, offset, and a check whether the part matches better turned by 180° (polarity).
- **Limits** (`lib/lumen/inspect.py` `LIMITS`): offset 0.15 mm, angle 8°, golden score OK ≥ 0.70, FAIL < 0.45.
- **Verdict:** OK / CHECK / FAIL is an aid, not a sign-off. Each image is kept in `inspection/<job>-<time>/`; *Export CSV* writes the report.
- **Status 2026-11-06:** offline tests pass on semi-synthetic images (a real 0402 cut from a tape image on real soldermask): offset to 0.02 mm, rotation, missing, golden, polarity. **Not yet run on real placed parts**; for that: `tests/run_bench_real_ui.sh exec tests/bench/inspect_placements.py` (camera only).

## Configuration profiles: "original" and "lumen" (`profile/pnp_profile.py`)

§1–§3 need configuration changes, so they live in a second profile you can switch to and back. Close OpenPnP first.

```
pnp-profile status
pnp-profile diff            # show what the switch would change, nothing written
pnp-profile use lumen
pnp-profile use original
```

| | original (Opulo V4.1, as delivered) | lumen |
|---|---|---|
| Nozzles N1/N2 | `ReferenceNozzle` | `ContactProbeNozzle`, VacuumSense with the existing VAC1/VAC2 sensors; feeder Z probed `AfterHoming`, unknown part heights probed `Once` (§1) |
| Bottom vision `BVS_Default` | size check `Disabled`, 300 % | size check `BodySize`, 25 %: catches 90° errors of non-square parts (§2) |
| Event hooks | none | `Feeder.AfterFeed` + `Vision.PartAlignment.After` record the feeder and vision offset of each pick for Pick Offset Learning (§3, §2 hints) |
| Preflight `board_z` (§1) | skipped | contact-probes configured bare points on each board: Z, tilt |
| Job Readiness | unknown height = issue; package without body size = issue when its bottom vision checks the body size | unknown height = probed; package without body size = issue (size check) |

What the switch changes is defined in `profile/lumen-profile.json`.

**How the switch behaves:**
- It is a minimal text edit of exactly these elements.
- **Switching back gives a `machine.xml` byte-identical to making the same changes in the original profile.** Calibration done in either profile is kept in both.
- Lumen tuning (probe depth, size tolerance, probed heights) is stored when you switch to original and restored on the next switch to lumen.
- Each switch backs up both files to `~/.openpnp2/lumen/profile-backups/`.
- It never replaces an event script it did not create.

**To set on day 1** (in the lumen profile, using OpenPnP's normal settings; they are kept across switches):
- probe start offset, depth, speed, sniffle step;
- the vacuum levels for VacuumSense;
- the size-check tolerance;
- board-Z probe points in `preflight.json`;
- the first learning correction, to confirm the correction direction: the residual must shrink, otherwise the dialog says "undo".

## Planned (documented, not implemented)
- **Laser Z measurement** without contact: board Z map, pick Z of every feeder, part presence on clear and black tape, placed part height. Proposal: a line laser + the existing top camera, ≈ €10–25, used as OpenPnP's Z probe through a `ScriptActuator`.
  - [docs/laser-z-proposal.md](docs/laser-z-proposal.md): bill of materials, wiring to the AUX header, software, calibration, limits.
  - [docs/z-measurement-options.md](docs/z-measurement-options.md): market check, needle tip vs switch probe vs laser.

## Not covered yet

| Study item | Status |
|---|---|
| §2 polarity (180°) by top-camera template match | Post-placement: Placement Inspection golden sample (offline-tested). Before picking: not yet. |
| §3 layer B sprocket-hole vision for Photon feeders | Done as a script (Feeder Part Check / "While feeding"), no Java change; not yet run in a real job. |
| Part presence on clear / black tape | Not detected ("?"): only paper tape. |

## Layout

```
lib/lumen/photon.py     Photon bus + firmware update (CPython 3 and Jython 2.7)
lib/lumen/oppnp.py      OpenPnP glue: actuator transport, job-state guard, machine tasks, settings, logs
lib/lumen/jobinfo.py    what the open job needs, why a feeder is not usable
lib/lumen/journal.py    placement journal
lib/lumen/orientation.py  pin-1 marks, verified .kicad_pcb / Gerber import, footprint table
lib/lumen/testplace.py  test placement: marks vs. board, place / photo / pick up / take back
lib/lumen/tapevision.py tape analysis: sprocket holes, EIA pocket centre, pockets / parts (paper)
lib/lumen/feedercheck.py, feedwatch.py   Feeders (pick location check) and the Feeder.BeforeFeed centring
lib/lumen/feederassign.py   Feeders, tab Assign feeders (was Feeder Assistant)
lib/lumen/helptext.py, uihelp.py   in-tool help texts, folding help panel, tooltips
lib/lumen/pickvac.py    pick vacuum check (edge pick -> re-centre), Nozzle.AfterPick
lib/lumen/zprobe.py     vacuum contact probing (Board Z Probe)
lib/lumen/nozzlecal.py  target carry + OpenPnP nozzle offset calibration
lib/lumen/zoomview.py   zoom in / out / pan for pictures (wheel, drag, right click = fit), like OpenPnP's camera view
lib/lumen/homeguard.py  safe homing: guard in front of OpenPnP's Home (events/Startup.py)
lib/lumen/lastjob.py    start-up offer to reopen the last job; boards still at X 0 / Y 0
lib/lumen/picksafety.py, picksafetyui.py   Preflight > Pick safety: learned body sizes / vacuum limits
lib/lumen/enginepool.py scripting engines pooled only while a job runs (events/Startup.py)
lib/lumen/joberror.py   job errors in words (events/Job.Error.py): e.g. no loaded nozzle tip for a part
lib/lumen/machinecal.py Machine Calibration: Opulo V4.1 steps via OpenPnP's Issues & Solutions, safety rules
lib/lumen/pictures/     pictures for the manual calibration steps (tools/make_cal_pictures.py)
lib/lumen/inspect.py    placement inspection (size + golden sample)
tools/orientation_check.py  desk check of a .pos: pin 1 from board / Gerber / folder / zip / library, reason when not
scripts/Lumen/*.py      menu scripts
events/                 optional event hooks
tests/                  see below
```

## Tests (`tests/run_all.sh photon-lumenpnp-v1.0.7.bin`)

| Suite | What |
|---|---|
| `test_photon_sim.py` | Library in CPython against the Marlin + feeder-bus simulator with the **real PBL core**: scan, update, progress, cancel, old firmware refused, 10 % lost replies, power cut → recovery |
| `run_jython_smoke.sh` | The same library in **OpenPnP's own Jython 2.7.1** against the simulator |
| `run_openpnp_headless.sh` | Library against the **real OpenPnP 2.6 classes** (stock simulated config): job analysis, Photon "not usable" reasons, journal, placed flags, go-to coordinates, machine tasks, exception carry-back |
| `run_openpnp_ui_headless.sh` | The **menu scripts' own code** (Swing models, buttons' handlers), with only the window and message boxes faked: update dialog end to end via machine tasks and the simulator; Job Readiness + LEDs; Last Placements + mark not placed; Preflight |
| `test_learning.py` | Learning statistics: systematic vs scatter, frame transform, step limit, epochs after correction / undo, "worse" detection, orientation hint |
| `test_orientation.py` | Real Opulo boards: LQFP-48, SOIC-8, SOT-23 (KiCad orientation), diodes/LEDs, passives not relevant (145 footprint types); Gerber X2 detection == KiCad on all 81 parts of the ftp board; rotation arithmetic over all marks and rotations; inputs: old Gerber without X2, X2 without netlist attributes, bottom copper, silkscreen, drill, .pos refused with the reason; Gerber folder / .zip picks the top copper; desk checker exit codes on the real files |
| `run_orientation_headless.sh` | Orientation Setup with real OpenPnP classes and the real feeder mainboard: import, auto marks, two-square check by clicking, apply sets the Photon pick rotation, CORRECT status, store and reopen; **renders the dialogs to PNG** for review; NOT DETECTED reasons, Load CAD data (.pos refused, project folder), detection report with refused files |
| `test_profiles.py` | `pnp-profile` on a **copy of the real `~/.openpnp2`**, judged by the real OpenPnP 2.6: byte-exact round trip; the lumen profile loads with the intended settings and nothing else changed; tuning in lumen + calibration edit → back to original equals the same edit in the original profile **byte for byte**; lumen tuning restored; hooks follow the profile; foreign hooks protected |
| `test_tapevision.py` | Real top-camera images (white, clear, black tape): hole-geometry pocket within 0.08 mm of the detected pocket, 12 mm tape recognised, 8 mm pitch parity, presence "?" without paper; hole lines: the tape's own line chosen when a neighbouring tape is in view, circles on the ribbed feeder housing (no tape loaded) rejected by hole contrast; raw bench images 2026-11-09 |
| `run_tapevision_offline.sh` | The same hole geometry through OpenPnP's OpenCV (the Java path Feeder Part Check runs on the machine) on the raw bench images: empty feeders → "no tape", own hole line, pocket offsets as measured on the machine |
| `run_inspect_offline.sh` | Placement inspection with OpenPnP's OpenCV on semi-synthetic images (offset, rotation, missing, golden, polarity) + the menu script on the real job with the camera replaced (table, sort, golden, CSV) |
| `test_partmatch.py` | Part name reading on real feeder names; other projects' names → feeders (0.1uF → 100n, 7.5k → 7k5, 0.1R → 0R1, ferrite, LED colours, part-number suffix, alias); never a different value / size; voltage / dielectric warnings; µ / Ω |
| `run_feeder_assist_offline.sh` | Feeder Assistant on copies of the real configuration, test job and board file (no machine): renamed parts get the right feeder on top, all other feeders below, nothing changes before Apply / on Cancel, pre-select only strong warning-free proposals, Apply saves the board COPY (real file untouched), aliases remembered (99 next time), "feeder gets the job's part" mode, non-ASCII part names |
| `test_testplace.py` | Test placement arithmetic: board mark from CAD at every placement rotation, part turn, corrected feeder rotation for every CAD mark x true x set x placement rotation (and Orientation Setup reads it back), golden-score proposal, pick-back correction orbiting the part centre, recycling per feeder type, rows marked 'not relevant' skipped, camera-view warning for parts as big as the photo |
| `run_testplace_sim.sh` | Test placement on **OpenPnP's simulated machine** (stock config, NullDriver, simulated cameras): refusals (no paste ticked, cancel = nothing moves, row marked 'not relevant' skipped), Photon feeder: feed consumes SkipNext, placed at the board placement, photo, marks by clicking, WRONG 180 → part taken back (SkipNext) and only then the rotation set, store + list CORRECT; again: same part picked, CORRECT, golden saved; tray feeder: feed count 1 → back to 0 on close, discard keeps it used; with simulated bottom vision; every control described |
| `test_feederopts.py` | Options per feeder: defaults, own values, older feeders list, validation, reset |
| `test_pickvac.py`, `run_pickvac_offline.sh` | Pick vacuum decision (learning, edge pick, per-tip thresholds, own typical per feeder); the hooks through OpenPnP's `Scripting.on()` on a copy of the real config without a machine (re-centre request, forced check once, disabled, manual picks ignored; return to feeder with Photon SkipNext, fallbacks to discard when the take-back is impossible or fails, "feed the next part" off = exactly 1 + feed-retry-count refused feeds (also through `Scripting.on`), then clear, stale block ignored, discard, retry count 0 = re-centre only; the exception reaches OpenPnP as `ScriptException`); per-feeder options (own on/off, threshold, action, return-fails, Every N, While feeding vs the older list, Stop for this feeder); identify packet byte by byte |
| `run_help_offline.sh` | Every tool opened on a copy of the real config with the test job, no machine: every button / checkbox / input / column has a description, the help panel opens and closes, windows rendered to PNG; Feeder Part Check options tab: edit with several rows highlighted, invalid value refused, reset, Save defaults |
| `run_config_compat.sh` | Install into a **copy of the real `~/.openpnp2`**: no config file changed, OpenPnP loads it the same, the journal hook runs via OpenPnP's `Scripting.on()` and never raises, uninstall is clean |

### Real machine (manual, `tests/run_bench_real_ui.sh`)
Runs on a **copy** of `~/.openpnp2` (the real configuration is never written), with a TRACE log of every serial line in `~/claude/opulo/_logs/`. OpenPnP must be closed.

| Mode | Motion |
|---|---|
| `scan [LAST]`, `update IMAGE ADDR` | none: HOME and MOVE replaced by an `M118` echo |
| `preflight ADDR UUID` | homing only |
| `verify ADDR` | homing, camera images, one 4 mm feed |
| `exec SNIPPET.py` | homing + the reviewed snippet (`tests/bench/*.py`) |

`BENCH_HOME_FID=x,y` homes on another fiducial, used when the target covers the visual home.

**Verified on the machine 2026-11-06:**
- bus scan and firmware update through OpenPnP;
- Preflight; feeder 50 setup; Feeder Part Check on 7 feeders;
- `Feeder.BeforeFeed` via `Scripting.on()`;
- Board Z Probe;
- target carry and the OpenPnP nozzle calibration (GUI).

**Not yet on the machine:** Placement Inspection on real parts; "While feeding" inside a real job and its confirmation dialog; pick vacuum check; Go to / Identify buttons.
