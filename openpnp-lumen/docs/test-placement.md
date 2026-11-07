# Test placement: settle an orientation doubt on the real board

*Orientation Setup > select the row(s) > Test placement on the PCB...*

When you are not sure whether a part will be placed the right way round, for example:
- a custom footprint;
- a pin-1 mark that is hard to see in the tape;
- a CAD pin 1 detected only by footprint name.

Place **one** part on its real pads, look at the photo, and get the part back into its feeder.

## What happens

| Step | Machine | Notes |
|---|---|---|
| Start | feed 1 part, pick, bottom vision (optional, as in the job), place on the chosen placement, top-camera photo | asks first; the job must be stopped and the machine homed; no automatic nozzle tip change |
| You decide | none | the part lies on the board while you look; *Retake photo* moves the camera only |
| Finish | pick the part up from the board, give it back to the feeder (or discard / leave it, as chosen) | a corrected feeder rotation is set **after** the part is back, if you agree |

**The board must have no solder paste on these pads** (a bare or test board). The tool refuses to start until you tick that.

## The photo

- **Red dot:** pin 1 of the **part**, which you click. It is preset only when a golden sample of the package clearly recognises the turn (make one in Placement Inspection, or tick *Save as golden sample* after a correct test).
- **Green ring:** pin 1 of the **board**. It is preset from CAD (pin 1 at the placement rotation). If you see from the silkscreen dot or the pad-1 shape that CAD is wrong, switch the click mode and move it. Without CAD data, click it yourself.
- **Light pads:** the CAD pads at the placement rotation, true scale; red = pad 1.
- **Same corner** → CORRECT. **Different corner** → the part is turned by 90 / 180 / 270 deg, and the window shows the feeder rotation that would have been right.

The result is stored in `~/.openpnp2/lumen/orientation.json` as confirmed marks, the same as a confirmation in *Check*. The list then shows CORRECT or MISMATCH, and every test is recorded under the part's `tests`. Photos are saved to `~/.openpnp2/lumen/testplace/`.

## Recycling: nothing wasted

The pick-up from the board uses the nozzle position of the place. It is corrected by where the camera found the body: up to 0.4 mm and 10 deg, turning about the part centre. The part therefore sits on the nozzle as it did when it was picked from the feeder. The part then goes back through OpenPnP's own `Feeder.takeBackPart()`:

| Feeder | What happens |
|---|---|
| Photon, push-pull | back into its pocket; the **next feed is skipped** (SkipNext): the tape does not move, and the job picks this same part |
| Strip, tray, rotated tray, blinds | back into its pocket; **feed count - 1** |
| Auto feeder | only with "recycle support" on |
| Feeders that cannot take it back | **discarded** at the discard location, and the window says so |

Failures are reported with where the part is:
- not picked up from the board: it is still there, remove it by hand;
- take-back failed after the part was put down: check the pocket and the nozzle tip before the next feed.

If you close the window while the part is on the board, it asks: return it now, or leave it there.

## What it does not do

- It does not run the Lumen while-feeding camera check or the pick vacuum check. Those belong to job feeds, and the test clears the pick vacuum hook's feed record so the test picks are not judged.
- It does not change the job's placed status, or any file except `orientation.json`, the photos, and, only on your Yes, the feeder rotation.
- Bottom side boards are not supported.
