# openpnp-lumen: LumenPnP tools inside OpenPnP

OpenPnP **scripts** (Jython 2.7, the interpreter bundled with OpenPnP 2.6), in the menu *Scripts > Lumen*. **OpenPnP itself and `machine.xml` are not modified**: the scripts use OpenPnP's public API, and feeder packets go through the existing `PhotonFeederData` actuator (`M485`), the same path OpenPnP's own Photon feeder support uses. Removing them (`./uninstall.sh`) restores the previous state exactly.

## Menu: Scripts > Lumen

| Script | Purpose | Study ref. | Touches the machine? |
|---|---|---|---|
| **Feeder Firmware Update** | Update Photon feeder firmware over the bus, feeders mounted, OpenPnP connected. Pick the binary, scan the bus, tick feeders (all / some / outdated), update with progress, log and result per feeder. | §7 | Feeder bus only |
| **Job Readiness** | View limited to the open job: only its parts and feeders, quantity / remaining, part height, and precisely why a feeder is not usable. Optional: job feeders shown on their LEDs (green = ready, red = issue, off = not used). | §5 | LEDs only (on request) |
| **Last Placements** | Newest placements first (placement journal). *Mark selected / last NOT placed* (the next run places it again), *Go to* (top camera over the part). | §6 | Camera move on *Go to* |
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
| `test_profiles.py` | `pnp-profile` on a **copy of the real `~/.openpnp2`**, judged by the real OpenPnP 2.6: byte-exact round trip; the lumen profile loads with the intended settings and nothing else changed; tuning in lumen + calibration edit → back to original equals the same edit in the original profile **byte for byte**; lumen tuning restored; hooks follow the profile; foreign hooks protected |
| `run_config_compat.sh` | Install into a **copy of the real `~/.openpnp2`**: no config file changed, OpenPnP loads it the same, the journal hook runs via OpenPnP's `Scripting.on()` and never raises, uninstall is clean |

Not covered without hardware or a display: real window layout and rendering, timing on the real Marlin bus, and the real camera move. These are checked on day 1.
