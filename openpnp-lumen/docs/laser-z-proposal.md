# Laser Z measurement: concrete proposal (2026-11-06)

**Goal:** measure Z without contact on the board (any point, tilt map) and on **every part in every feeder** (tape top, part top, part present on clear/black tape), and later placed parts (height, tombstone). The budget is well below €300.

**Proposal:**
- **A (recommended): laser line + the existing top camera (triangulation), about €10–30.**
- B: a ready-made laser displacement sensor, only if A turns out too noisy on shiny parts.

---

## A. Line laser + top camera (laser triangulation)

### Principle
A red laser line is mounted on the head beside the top camera and tilted by θ ≈ 45° to the camera axis. It shines a thin line across the spot under the camera:
- On a higher surface the line appears shifted in the image; with θ = 45° the shift equals the height difference.
- The camera is already calibrated at 0.011 mm/px, so **1 px ≈ 0.011 mm of Z**. With sub-pixel line centring, a realistic **±0.02–0.03 mm** on matte surfaces.
- **Range:** the line must stay inside the image: ±5.9 mm in image Y at 45°, which covers the board (Z 4.3), tapes (Z 3–4) and tall parts.

### Bill of materials

| Item | Example | Typical price* |
|---|---|---|
| Line laser module 650 nm, **≤ 1 mW (class 2)**, 5 V, focusable, Ø 9–12 mm | generic "650nm line laser module 5V 1mW" | €3–10 |
| Logic-level switch for the laser (3.3 V input) | small N-MOSFET module (AO3400 / 2N7002 class) or a module with EN input | €1–3 |
| Bracket | 3D-printed (PETG), M3 screws, head-mounted next to the top camera, adjustable tilt 35–50° | €1–2 |
| Cable | 3-wire (5 V, GND, EN) along the head cable chain | €2–5 |
| **Total** | | **≈ €10–25** |

\*Typical online prices for these generic parts; not quoted from a specific shop, check before ordering.

### Wiring (Lumen motherboard REV05, from the Opulo schematic)
- **Laser power:** 5 V from the board.
- **Switching:** one of the AUX header outputs `LUMEN_AUX_PWM1..3` (3.3 V logic) drives the MOSFET/EN, so the laser is **on only during a measurement**.
- **OpenPnP:** a Boolean actuator `LASER` with `ACTUATE_BOOLEAN_COMMAND` = `M42 P<pin> S255` / `M42 P<pin> S0`.
  - The Marlin pin number comes from the Lumen pins file for that AUX signal. **To verify before wiring.**
  - The `FAN` MOSFET output is the alternative if it is free on your machine.

### Software (prepared once you order; it uses the same building blocks as the existing tools)
1. **`LaserZ` = OpenPnP `ScriptActuator`** (driverless; its read runs a Lumen script), set as the **head's Z Probe actuator** in Machine Setup > Heads. OpenPnP's own Z-probe functions then use it.
2. **Measurement**, about 0.5 s:
   1. Top camera to the point (safe Z), ring light low.
   2. Image with the laser off, laser **on**, image, laser off.
   3. The difference image isolates the line (ambient light cancels).
   4. Line centroid per column near the centre (sub-pixel).
   5. `Z = Z_ref + (y_px − y_ref) × k`.
3. **Calibration:** two known heights. Either the vacuum-probed board fiducial (4.31) and the calibration plate (4.55), or better a 1.00 mm feeler-gauge stack on the plate, giving the reference row and k (mm/px). It is saved in `settings.json`, re-checkable in 10 s, and the Board Z Probe can serve as the contact reference.
4. **Tools on top:**
   - *Board Z map* without contact (the bench tilt was 0.35–0.40 mm);
   - *Feeder pick Z* for all feeders in one run (tape top + part top → also part present on clear / black tape where the camera says "?");
   - *Placement Inspection* add-on: placed part height (tombstone, missing).

### Limits / risks
- **Shiny surfaces** (solder, metal lids) reflect specularly and the line can vanish or double. Mitigation: measure on the part body or tape, use exposure control, or take 2 measurements.
- **Transparent tape:** the line may show on the tape and on the part below. Take the higher, brighter peak, with a plausibility check.
- **Black parts** reflect little: longer exposure (the camera supports it).
- **Laser safety:** class 2 (≤ 1 mW); on only during the measurement (software interlock); never look into the beam; label the head.
- **Mechanical:** the bracket must be rigid. Calibration drift is caught by re-checking against a contact-probed reference.

---

## B. Ready-made laser displacement sensor (only if A is not enough)

| Option | Range / resolution | Interface | Price |
|---|---|---|---|
| Panasonic HG-C1030 (new) | 30 ± 5 mm, µm-class | analog (variant!) / NPN | €350–500 (Bürklin ~€500, DigiKey ~€350 net) |
| Chinese 30 ± 5 mm triangulation sensors (e.g. Dadi GFL-Z30, Delta LD-E 30±5) | 10 µm class | RS-485 Modbus / 4–20 mA | not listed: quotation only; ATO 30-200 mm model $307 |
| Used HG-C1030 / Keyence IL | – | – | variable (used market) |

**Integration without firmware changes:**
- **RS-485 Modbus:** a USB-RS485 adapter (€5–10) on the PC, read by the `LaserZ` ScriptActuator (OpenPnP bundles jSerialComm).
- **Analog output:** an ADS1115 I2C ADC (€3–5) on a free channel of the head-board I2C switch (PCA9545A, channels 3/4 look free), read with `M260` / `M261` like the vacuum sensors.

---

## Recommendation and next steps
1. Order the **line laser (class 2, 5 V) + MOSFET module** (≈ €10–25) and print the bracket. I prepare:
   - the bracket model;
   - the `LASER` actuator and `LaserZ` ScriptActuator script, with calibration;
   - the tools listed above.
2. **Verify on your board:** the free AUX PWM pin and its Marlin pin number, and 5 V on the AUX header (from the REV05 schematic and the Marlin pins file).
3. **Bench test, when allowed:**
   - calibrate on two heights;
   - compare with the vacuum-probed fiducials (4.45 / 4.25 / 4.10 / 4.40);
   - measure feeders 48 (paper), 27 (clear) and 3 (black).

## Sources
- OpenPnP: [Z Probing (actuator returning mm, laser displacement sensors)](https://github.com/openpnp/openpnp/wiki/Z-Probing), [Contact Probing Nozzle](https://github.com/openpnp/openpnp/wiki/Contact-Probing-Nozzle)
- Sensors: [Panasonic HG-C1030 (Bürklin)](https://buerklin.com/en/p/panasonic/optical-sensors/hg-c1030/28G1550), [HG-C1030 (DigiKey)](https://www.digikey.at/en/products/detail/panasonic-industrial-automation-sales/HG-C1030/5215054), [Delta LD-E 30±5 mm, RS-485 Modbus](https://www.delta-emea.com/en-gb/products/Smart-Sensor/3668), [Dadi GFL-Z (datasheet)](https://ja.dadisick.com/file/GFL-Zシリーズ_8116136.pdf), [ATO 30 mm sensor ($1,110)](https://ato.com/laser-distance-sensor-30mm), [ATO digital displacement sensor 30-200 mm ($307)](https://www.ato.com/digital-displacement-sensor)
- Triangulation accuracy factors (line thickness, exposure vs reflectivity, dark objects): [Hackster low-cost high-accuracy scanner](https://hackster.io/news/building-a-low-resolution-high-accuracy-3d-scanner-ee6d78ace491), [Makezine scanner guide](https://makezine.com/article/digital-fabrication/3d-printing-workshop/buyers-guide-3d-scanners/)
- Board: Opulo `opulo_lumenpnp/src/PCB/mobo` REV05 schematic (AUX header `LUMEN_AUX_PWM1..3`, `LUMEN_AUX_A1`, MOSFETs `MOS1..4` + `FAN`, PCA9545A I2C switch)
