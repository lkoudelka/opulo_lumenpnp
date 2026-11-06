# Orientation detection: what to load, which Gerber, and what is checked

*For the operator of **Scripts > Lumen > Orientation Setup** and the desk check `tools/orientation_check.py`.*

## 1. Do I need the board file, the Gerber AND the library?

**No. One input is enough, and all of them are optional.**

Use **"Load CAD data (board / Gerber / library)..."**. It takes a file, a folder or a .zip and says what it found. Load the first one you have from this list:

| You have | Load | What you get |
|---|---|---|
| **KiCad board `.kicad_pcb`** (best) | the file, or the KiCad project folder | Pin 1 of every part, **verified** against the job: reference, footprint, rotation and position must match. |
| The board file, but of **another revision** | the same | Refused for the positions (with the reason). Pin 1 is still taken **by footprint name** from its footprints: a footprint's pin 1 is the same in every revision. Each part is shown as *auto*; confirm it once in *Check*. |
| Only **Gerbers** (e.g. from the fab package) | the **top copper Gerber X2**, or the folder / .zip with all Gerbers (the top copper is picked) | Pin 1 of every part, verified against the job. |
| Only the **`.pos`** and custom footprints | the **footprint library** (a `.pretty` folder, or a folder of them) | Pin 1 **by footprint name**. KiCad standard footprints come from KiCad's own library if it is installed on this PC. |
| Nothing | — | Click pin 1 by hand in *Check* (two squares). Confirmed footprints are remembered for every later job. |

You never need more than one of these. Extra inputs only add checks: if two sources disagree on pin 1, the part is flagged.

> A **BOM** or **position file** (`.pos`, `.csv`) is the job itself (*OpenPnP File > Import Board*). It has no pad data, so it cannot say where pin 1 is. A **schematic** has no pads either. Both are refused with that reason.

## 2. Which Gerber format?

- **Gerber X2** (RS-274X with X2 attributes), **top copper layer only** (`F.Cu`; file function `Copper,L1,Top`).
- It must contain the **netlist attributes**. Every pad then carries its reference and pin number (`%TO.P,U1,1*%`), and that is where pin 1 comes from.
- **KiCad:** *File > Plot*, format *Gerber*, layer *F.Cu*, tick ✅ **Use extended X2 format** and ✅ **Include netlist attributes**. Other EDA tools that write X2 netlist attributes also work.
- **Not usable** (refused, with the reason and what to do):

| File | Message |
|---|---|
| Silkscreen / legend, mask, paste | "not a copper layer (Legend,Top): use the top COPPER Gerber (F.Cu)" |
| Bottom copper | "not the TOP copper layer (Copper,L2,Bot): use F.Cu" |
| Old Gerber without X2 (RS-274X / "X1", e.g. many `.gtl` from older tools) | "Gerber without X2 attributes …: it has no pin numbers. Export the top copper again as Gerber X2 – KiCad: …" |
| X2 copper without netlist attributes | "X2 Gerber but no pin attributes: export again with 'Include netlist attributes' …" |
| Drill file (`.drl`) | "… is a drill file: no pads" |
| Folder with two top copper files | "2 top copper Gerbers … choose the one of this board" |

Your current files are fine as a format. `Panel-top_copper.gbr` is KiCad 9 X2 top copper with pin attributes.

## 3. Is there a check that detection could not be done? Yes, at three levels

1. **Whole file.** A file is used only if it is proven to belong to the job: at least half of the placements must be found at one common origin offset. Otherwise it is **refused as a whole**, for example "only 0 of 249 placements found in the board file: other design or revision?". This is shown in the load dialog and listed again in the report.
2. **Per part.** A part that cannot be verified or has no clear pin 1 says why in the *Status* column. Possible reasons:
   - not in the file;
   - position or rotation differs;
   - two copies at the same place;
   - pads differ from the other parts with the same footprint (a wrong rotation in the job);
   - no pad named 1;
   - ambiguous pin-1 position.
   
   Where CAD pin 1 is not known at all, the row shows **"CAD pin 1 NOT DETECTED: \<reason\> – \<what to load\>"**, and the summary line counts these parts in red.
3. **Detection report** (button). It covers every part where orientation matters:
   - **detected**: pin 1 corner, source file, confirmed or "auto, confirm in Check";
   - **NOT DETECTED**: the reason and what to load.

   It also lists refused files. It is saved as `~/.openpnp2/lumen/logs/orientation-report-<time>.txt`.

At the desk, before the job, the same check runs without OpenPnP:

```
~/claude/opulo/_tools/orientation-check.sh BOARD-top.pos --cad BOARD.kicad_pcb      # or --cad gerber-folder / fab.zip / my.pretty
```

| Exit code | Meaning |
|---|---|
| 0 | Every part where orientation matters is detected from verified files. |
| 3 | All detected, some only by footprint name (confirm those once). |
| 1 | NOT complete: listed with the reason. |
| 2 | No usable input. |

Detection never guesses: anything uncertain is reported, not filled in. Every mark is shown in the two squares, and nothing changes a feeder without *Confirm and apply*.

## 4. Result on your files (`~/claude/opulo/_testdata/wba65-panel`, checked 2026-11-06)

The three files are **different revisions**:
- `Panel.kicad_pcb`: one board, 108 parts on top;
- `Panel-top_copper.gbr`: a 21-up panel;
- `Panel-top.pos`: a 7-up panel, 249 placements.

| Input (only this one) | Result |
|---|---|
| nothing | exit 2, "no usable input" |
| `Panel.kicad_pcb` | **Refused for the positions** (0 of 249 found), but **all 6 relevant footprints by name** (42 placements: UFQFPN-48, QFN6L ECMF2, DFN4, ZDO 1610, crystal 2016, LED SK6805). Exit 3: confirm once each. |
| `Panel-top_copper.gbr` | **Refused** (7 of 249 found). Every relevant part: "NOT DETECTED: Gerber does not match the job". Exit 1. |
| `Panel-F_Silkscreen.gbr` | Every part: "NOT DETECTED: not a copper layer". Exit 1. |
| `bom.csv` / `Panel-top.pos` | Not loaded: "that is the job itself". |
| the whole folder | The board file is found and used as above. |
| a `.pretty` made from the board's footprints (KiCad: *File > Export > Export Footprints to New Library*) | All 6 relevant footprints by name. Exit 3. |
| `.pos` and `.kicad_pcb` of the **same** revision | 108 of 108 verified. Exit 0. |

**For this job:** load `Panel.kicad_pcb` (or the folder) and confirm the 6 footprints once in *Check*. For the real job, use the `.kicad_pcb` that matches the `.pos` revision: every part is then verified by position as well. As always, each mark is still confirmed in the two squares.

These cases run automatically:
- `tests/test_orientation.py`, section "inputs";
- `tests/run_orientation_headless.sh`: load dialog, refusals, detection report.
