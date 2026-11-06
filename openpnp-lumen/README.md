# openpnp-lumen: LumenPnP tools inside OpenPnP

OpenPnP **scripts** (Jython 2.7, the interpreter bundled with OpenPnP 2.6), in the menu *Scripts > Lumen*. **OpenPnP itself and `machine.xml` are not modified**: the scripts use OpenPnP's public API, and feeder packets go through the existing `PhotonFeederData` actuator (`M485`), the same path OpenPnP's own Photon feeder support uses. Removing them (`./uninstall.sh`) restores the previous state exactly.

## Menu: Scripts > Lumen

| Script | Purpose | Study ref. | Touches the machine? |
|---|---|---|---|
| **Board Z Probe** | Board surface Z on the job's board fiducials by gentle vacuum contact. Shows Z per fiducial, the mean and the tilt (warning above 0.2 mm); *Apply* sets the board location Z. | §1 | **Moves**: nozzle down slowly onto the fiducials |
| **Feeder Firmware Update** | Update Photon feeder firmware over the bus, feeders mounted, OpenPnP connected. Pick the binary, scan the bus, tick feeders (all / some / outdated), update with progress, log and result per feeder. | §7 | Feeder bus only |
| **Feeder Part Check** | Camera over the pick location of the ticked feeders. Pocket centre from the sprocket holes (any tape), part at pick (paper tape), *Apply offset*; a part at pick sets OpenPnP's `SkipNext`. Optional "While feeding" centring and pick vacuum check during the job, **options per feeder** (`Feeder.BeforeFeed`, `Nozzle.AfterPick`). Sortable. | §2/§3 | Camera only; pick location on *Apply* / while feeding |
| **Job Readiness** | View limited to the open job: only its parts and feeders, quantity / remaining, part height, and precisely why a feeder is not usable. Optional: job feeders shown on their LEDs (green = ready, red = issue, off = not used). | §5 | LEDs only (on request) |
| **Last Placements** | Newest placements first (placement journal). *Mark selected / last NOT placed* (the next run places it again), *Go to* (top camera over the part). | §6 | Camera move on *Go to* |
| **Nozzle Offset Calibration** | Carries the calibration target from its park spot onto the visual home (OpenPnP pick/place), runs **OpenPnP's own** nozzle offset calibration for the ticked nozzles, carries the target back and checks it. GUI only. | — | **Moves and picks** the target; sets nozzle head offsets |
| **Orientation Setup** (optional) | For the job's parts where orientation matters, two squares: **PIN 1 of the part in the feeder** (as seen from above / in the top camera, which can be shown) and **PIN 1 in the CAD footprint at 0 deg**. Click the pin-1 corner (4 corners = the 4 possible rotations) in each and the rotation in the feeder is calculated; *Confirm*, or *Confirm and apply* to set the feeder rotation. Pin 1 in CAD is detected automatically from the **KiCad `.kicad_pcb`** or from **KiCad copper Gerbers with X2 attributes**, and still confirmed in the squares. **With only a `.pos` file**, it is found by footprint name: footprint libraries (`.pretty`), the OpenPnP package footprint, or the **footprint table**, which every import and confirmation fills, so each footprint is confirmed once for all boards. The list shows per part/feeder: auto / confirmed, CORRECT / MISMATCH / to check. Per-type hints (electrolytic: pin 1 = plus, the stripe marks minus; diode: cathode bar; IC: dot or notch). | §2 | Feeder rotation on *Apply* |
| **Pick Offset Learning** | Per feeder: systematic pick error learned from the bottom-vision offsets, damped suggestion, *Apply* / *Undo* for Photon feeders, "made it worse" detection, orientation hint (vision corrects ~90°). Data is recorded in the lumen profile only. | §3, §2 | Feeder offset on *Apply* |
| **Placement Inspection** | Top camera over the job's placed parts: body found / offset / rotation (size from the package), golden-sample comparison incl. 180° (polarity) check; images per run, CSV report. Sortable. | §2 | Camera only |
| **Preflight** | One-click checklist from `~/.openpnp2/lumen/preflight.json`: machine enabled, job open, home (if needed), lights, nozzle tips, vacuum sensors, job readiness, job feeders answer on the bus (and minimum firmware). PASS / WARN / FAIL. | §4 | Homing (if enabled and needed), lights |

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

## Install / uninstall

```
./install.sh              # menu scripts + the inert hooks Feeder.BeforeFeed, Nozzle.AfterPick (links to this checkout)
./install.sh --journal    # + placement journal hook (Events/Job.Placement.Complete.py)
./uninstall.sh            # removes exactly these links (settings/logs in ~/.openpnp2/lumen stay)
```

Then use *Scripts > Refresh Scripts* in OpenPnP, or restart it. The installer never replaces a file it did not create.

### Orientation detection details
- **Verified import (`.kicad_pcb` or top copper Gerber):** a file is used for a placement only when it is proven to belong to the job. Nothing is guessed; every refusal says why (import dialog, list status `NOT VERIFIED ...`, `orientation-check.sh`).

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
  - **Before the job, at the desk:** `~/claude/opulo/_tools/orientation-check.sh BOARD-top.pos --pcb BOARD.kicad_pcb --gerber BOARD-F_Cu.gbr`. Exit 0 = every relevant part verified, 1 = some need manual confirmation, 2 = a file was refused.
  - KiCad's library draws some packages rotated compared with datasheets (SOT-23: pins 1/2 on the left). That is why the helper always shows the CAD footprint.
  - A `.kicad_pcb` also fills the footprint table with all its footprints (exact footprint-local data, marked auto), even when the board is another revision. Gerber data is learned only where verified.
- **Position file only (`.pos`, also what assembly partners get with the BOM):**
  - The `.pos` file has no pad data, only footprint name + rotation, and the BOM / CPL add nothing about pin 1 (LCSC numbers point to EasyEDA footprints, whose 0° differs from KiCad's).
  - Pin 1 in the footprint's 0° frame is a property of the **footprint**, the same on every board, so it is looked up by the name OpenPnP's KiCad importer gives the package (= `Package` column). Order: confirmed footprint-table entry, OpenPnP package footprint (pads named, e.g. from *Import KiCad .kicad_mod*), footprint library, auto entry learned from an earlier board/Gerber.
  - Sources that disagree are shown in the list; a confirmed entry is never overwritten automatically.
  - Library dirs: added with *Footprint library (.pretty)...*, plus the KiCad stock library if installed (`/usr/share/kicad/footprints`, `KICADn_FOOTPRINT_DIR`). Checked: library pin 1 = placed footprint for all 84 uses on the Opulo boards.
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

### Feeder Part Check and centring while feeding (`Scripts > Lumen > Feeder Part Check`, `Events/Feeder.BeforeFeed.py`)
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
| Job Readiness | unknown height = issue | unknown height = probed; package without body size = issue (size check) |

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
lib/lumen/tapevision.py tape analysis: sprocket holes, EIA pocket centre, pockets / parts (paper)
lib/lumen/feedercheck.py, feedwatch.py   Feeder Part Check and the Feeder.BeforeFeed centring
lib/lumen/helptext.py, uihelp.py   in-tool help texts, folding help panel, tooltips
lib/lumen/pickvac.py    pick vacuum check (edge pick -> re-centre), Nozzle.AfterPick
lib/lumen/zprobe.py     vacuum contact probing (Board Z Probe)
lib/lumen/nozzlecal.py  target carry + OpenPnP nozzle offset calibration
lib/lumen/inspect.py    placement inspection (size + golden sample)
tools/orientation_check.py  desk check of a .pos against .kicad_pcb / Gerber
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
| `test_orientation.py` | Real Opulo boards: LQFP-48, SOIC-8, SOT-23 (KiCad orientation), diodes/LEDs, passives not relevant (145 footprint types); Gerber X2 detection == KiCad on all 81 parts of the ftp board; rotation arithmetic over all marks and rotations |
| `run_orientation_headless.sh` | Orientation Setup with real OpenPnP classes and the real feeder mainboard: import, auto marks, two-square check by clicking, apply sets the Photon pick rotation, CORRECT status, store and reopen; **renders the dialogs to PNG** for review |
| `test_profiles.py` | `pnp-profile` on a **copy of the real `~/.openpnp2`**, judged by the real OpenPnP 2.6: byte-exact round trip; the lumen profile loads with the intended settings and nothing else changed; tuning in lumen + calibration edit → back to original equals the same edit in the original profile **byte for byte**; lumen tuning restored; hooks follow the profile; foreign hooks protected |
| `test_tapevision.py` | Real top-camera images (white, clear, black tape): hole-geometry pocket within 0.08 mm of the detected pocket, 12 mm tape recognised, 8 mm pitch parity, presence "?" without paper |
| `run_inspect_offline.sh` | Placement inspection with OpenPnP's OpenCV on semi-synthetic images (offset, rotation, missing, golden, polarity) + the menu script on the real job with the camera replaced (table, sort, golden, CSV) |
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
