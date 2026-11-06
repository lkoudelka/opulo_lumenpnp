# Z measurement of the board and of parts in feeders: what exists (market check 2026-11-06)

**Question:** can the nozzle be replaced by a "needle" nozzle to measure Z, not only on the board but on all parts in the feeders?

**Short answer:**
- A needle *tip* alone cannot measure: there is nothing to tell the machine when it touches.
- The LumenPnP senses contact through the **vacuum** of a normal tip; OpenPnP calls this "sniffle" contact probing. The smallest tip in the Opulo set, **N045**, is already the practical "needle". This is what Board Z Probe uses.
- To measure **all parts in feeders without touching them**, the established option is a **laser triangulation (displacement) sensor on the head**, used as OpenPnP's *Z probe*.

## 1. Options

| Option | What it is | Board | Parts in feeders | Cost | Effort / risk |
|---|---|---|---|---|---|
| **A. Vacuum contact with the existing tips** (now) | Nozzle goes down in small steps with vacuum on; seal = contact. Board Z Probe (Lumen script) or OpenPnP's *ContactProbeNozzle* (Vacuum Sense, "sniffle"). | yes (done: 4 fiducials, ±0.05 mm) | Only by picking. OpenPnP's ContactProbeNozzle can learn the feeder pick Z on the first pick and remember it. Light parts are lifted, which is fine because they are being picked anyway. | 0 | ContactProbeNozzle changes the nozzle class: config change, needs your confirmation (profile "lumen"). |
| **B. "Needle" tip** (closed / pin) | A CP40-style tip with a pin end. | – | – | low | **Cannot sense contact** (no vacuum seal, no switch). Not found as a product for probing. Opulo's CP40 set goes N045 … N75; N045 is the smallest. |
| **C. Switch probe** (BLTouch-like deployable pin, or a nozzle with a contact switch) | Pin deployed beside the nozzles, Hall/switch trigger; OpenPnP "Z probe" actuator. | yes | Poorly: a ~1–2 mm pin cannot hit 0402/0201 parts and pushes light parts in their pockets. | 30–50 € | Needs free controller pins and Marlin support on the Lumen board; pre-travel offset; contact force. |
| **D. Laser displacement sensor on the head** (recommended for parts in feeders) | Triangulation sensor, e.g. Panasonic HG-C1030 (centre 30 mm, ±5 mm range, µm-class resolution), read as OpenPnP *Z probe* actuator. | yes, without contact | **yes, without contact**: tape surface, part tops, pocket depth, also fragile or light parts. The OpenPnP wiki names this use (measuring delicate surfaces / loose parts in feeders). | about 350–500 € (HG-C1030) | Mounting bracket + offset calibration; dark / shiny / transparent surfaces need care; 12–24 V supply. |

## 2. How option D fits this machine without firmware changes
- OpenPnP *Z Probing*: an Actuator that returns a number in mm, assigned as the head's **Z Probe actuator**. Probing with it is meant for setup (boards, feeders), not inside every pick.
- **Reading the sensor:** use its **analog output** (check the exact variant: listings disagree on which HG-C1030 variant has the 0–5 V / 4–20 mA output; confirm with the Panasonic datasheet before buying).
  - Feed it into a small **I2C ADC (e.g. ADS1115)**.
  - Connect that to the **I2C multiplexer already on the head (address 112)**. The config uses channels 1 (VAC1) and 2 (VAC2), so the other channels look free; check the connector on your Lumen REV5 board.
  - OpenPnP then reads it with the same `M260` / `M261` commands as the vacuum sensors. **No Marlin rebuild.**
- **Calibration:** measure one known surface, e.g. the Board Z Probe result 4.31 mm, to get the sensor offset; then every reading converts to machine Z.
- **What it would enable** (scripts, like the existing Lumen tools):
  - board Z map without contact (tilt: we measured 0.35–0.40 mm);
  - pick Z of every feeder (tape top or part top);
  - part presence in the pocket on any tape, from height, including the clear / black tapes where the camera says "?";
  - after placement, a coplanarity / tombstone check (part height on the board).

**Concrete proposal: [laser-z-proposal.md](laser-z-proposal.md) (line laser + top camera, ≈ €10–25).**

## 3. Recommendation
1. **Now (free):**
   - Keep vacuum contact (Board Z Probe) for the board and other fixed surfaces.
   - For feeder pick heights, OpenPnP's ContactProbeNozzle "feeder height probing on first pick" is available. It is a configuration change; your confirmation is needed, and the "lumen" profile is prepared for it.
2. **If non-contact height of all parts in feeders is wanted:** a laser displacement sensor (option D) on the head, read through an I2C ADC on the existing vacuum-sensor I2C mux. Before buying:
   - confirm which variant has the analog output;
   - confirm a free multiplexer channel and connector on the head;
   - design the bracket (sensor centre distance 30 mm, the head's travel and safe Z).
3. **Not recommended:** needle-only tips (no sensing) and a BLTouch-style pin for parts in feeders (pin too big for small parts, pushes light parts).

## Sources
- Opulo: [nozzle prep, LumenPnP uses CP40-style tips](https://docs.opulo.io/openpnp/v4-1/preflight/nozzle-prep/), [CP40 nozzle tip set](https://www.opulo.io/products/cp40-pnp-nozzle), [setting pick position (manual Z by jogging)](https://docs.opulo.io/feeders/7-setting-pick-position/setting-pick-position/)
- OpenPnP: [Contact Probing Nozzle](https://github.com/openpnp/openpnp/wiki/Contact-Probing-Nozzle), [Z Probing (laser displacement sensors, nozzle switches, deployable sensors)](https://github.com/openpnp/openpnp/wiki/Z-Probing), [Z calibration / contact probing / height sensing announcement](https://groups.google.com/g/openpnp/c/CIj9T9TjFBY), [Z probe ideas](https://groups.google.com/g/openpnp/c/S7pDpZGIjmk), [Z-probe with touch plate / pin probe](https://groups.google.com/g/openpnp/c/4Vzs3Rxt3Nw), [PR #1164 part height / feeder / placement probing](https://github.com/openpnp/openpnp/pull/1164)
- Sensor: [Panasonic HG-C1030 (Bürklin)](https://buerklin.com/en/p/panasonic/optical-sensors/hg-c1030/28G1550), [HG-C1030 (DigiKey)](https://www.digikey.at/en/products/detail/panasonic-industrial-automation-sales/HG-C1030/5215054), [HG-C1030-P analog output listing (Applied Automation)](https://appliedautomation.com/part/panasonic/hg-c1030-p/2773402)
- Third-party CP40 tips: [Printables custom CP40 nozzles for Lumen PnP](https://www.printables.com/model/795539-custom-cp40-capable-smt-nozzles-for-lumen-pnp)
