# openpnp-lumen: LumenPnP tools inside OpenPnP

OpenPnP **scripts** (Jython 2.7, the interpreter bundled with OpenPnP 2.6), in the menu *Scripts > Lumen*. **OpenPnP itself and `machine.xml` are not modified**: the scripts use OpenPnP's public API, and feeder packets go through the existing `PhotonFeederData` actuator (`M485`), the same path OpenPnP's own Photon feeder support uses. Removing them (`./uninstall.sh`) restores the previous state exactly.

## Menu: Scripts > Lumen

| Script | Purpose | Study ref. | Touches the machine? |
|---|---|---|---|
| **Feeder Firmware Update** | Update Photon feeder firmware over the bus, feeders mounted, OpenPnP connected. Pick the binary, scan the bus, tick feeders (all / some / outdated), update with progress, log and result per feeder. | §7 | Feeder bus only |
| **Job Readiness** | View limited to the open job: only its parts and feeders, quantity / remaining, part height, and precisely why a feeder is not usable. Optional: job feeders shown on their LEDs (green = ready, red = issue, off = not used). | §5 | LEDs only (on request) |
| **Last Placements** | Newest placements first (placement journal). *Mark selected / last NOT placed* (the next run places it again), *Go to* (top camera over the part). | §6 | Camera move on *Go to* |
| **Orientation Setup** (optional) | For the job's parts where orientation matters, two squares: **PIN 1 of the part in the feeder** (as seen from above / in the top camera, which can be shown) and **PIN 1 in the CAD footprint at 0 deg**. Click the pin-1 corner (4 corners = the 4 possible rotations) in each and the rotation in the feeder is calculated; *Confirm*, or *Confirm and apply* to set the feeder rotation. Pin 1 in CAD is detected automatically from the **KiCad `.kicad_pcb`** or from **KiCad copper Gerbers with X2 attributes**, and still confirmed in the squares. **With only a `.pos` file**, it is found by footprint name: footprint libraries (`.pretty`), the OpenPnP package footprint, or the **footprint table**, which every import and confirmation fills, so each footprint is confirmed once for all boards. The list shows per part/feeder: auto / confirmed, CORRECT / MISMATCH / to check. Per-type hints (electrolytic: pin 1 = plus, the stripe marks minus; diode: cathode bar; IC: dot or notch). | §2 | Feeder rotation on *Apply* |
| **Pick Offset Learning** | Per feeder: systematic pick error learned from the bottom-vision offsets, damped suggestion, *Apply* / *Undo* for Photon feeders, "made it worse" detection, orientation hint (vision corrects ~90°). Data is recorded in the lumen profile only. | §3, §2 | Feeder offset on *Apply* |
| **Preflight** | One-click checklist from `~/.openpnp2/lumen/preflight.json`: machine enabled, job open, home (if needed), lights, nozzle tips, vacuum sensors, job readiness, job feeders answer on the bus (and minimum firmware). PASS / WARN / FAIL. | §4 | Homing (if enabled and needed), lights |

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
./install.sh              # menu scripts (links to this checkout)
./install.sh --journal    # + placement journal hook (Events/Job.Placement.Complete.py)
./uninstall.sh            # removes exactly these links (settings/logs in ~/.openpnp2/lumen stay)
```

Then use *Scripts > Refresh Scripts* in OpenPnP, or restart it. The installer never replaces a file it did not create.

### Orientation detection details
- **KiCad:** pad "1" of each footprint is taken relative to the centre of all numbered pads, in the footprint's 0° frame.
  - The conventions were validated against KiCad's own paste Gerber of a real board: 160/160 pads matched within 0.01 mm.
  - Note: KiCad's library draws some packages rotated compared with datasheets (SOT-23: pins 1/2 on the left). That is why the helper always shows the CAD footprint.
- **Gerber:** `%TO.P,<ref>,<pin>%` attributes on the copper layer, combined with the job's placement rotations. KiCad writes them with *Use extended X2 format* + *Include netlist attributes*; paste and mask layers do not carry them.
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

## Not covered (needs Java or the cameras)

| Study item | Why not here |
|---|---|
| §2 polarity (180°) by top-camera template match | Pipeline work with the real cameras |
| §3 layer B sprocket-hole vision for Photon feeders | Java change in `PhotonFeeder` (study §3.5 decision) |

## Layout

```
lib/lumen/photon.py     Photon bus + firmware update (CPython 3 and Jython 2.7)
lib/lumen/oppnp.py      OpenPnP glue: actuator transport, job-state guard, machine tasks, settings, logs
lib/lumen/jobinfo.py    what the open job needs, why a feeder is not usable
lib/lumen/journal.py    placement journal
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
| `run_config_compat.sh` | Install into a **copy of the real `~/.openpnp2`**: no config file changed, OpenPnP loads it the same, the journal hook runs via OpenPnP's `Scripting.on()` and never raises, uninstall is clean |

Not covered without hardware or a display: real window layout and rendering, timing on the real Marlin bus, and the real camera move. These are checked on day 1.
