# Transistor Matching Fixture for Exponential Converter

## 1. Purpose

Match 2SC1815 (C1815) NPN transistors for the exponential current source (expo_converter_v2). Two parameters are critical:

- **IS (saturation current) matching** — Transistors with identical IS will have the same VBE at any given IC. Matching IS confirms both devices came from the same wafer/process and will track together thermally. A VBE mismatch can be calibrated out as a fixed offset, but unmatched IS temperature coefficients cause drift that *cannot* be calibrated away.
- **Ideality factor (NF = 1)** — The exponential law $I_C = I_S \cdot e^{V_{BE}/V_T}$ requires NF = 1. If NF ≠ 1, the 1V/oct scaling breaks regardless of how well the pair is matched.

hFE (beta) matching is *not* critical for this circuit — the exponential relationship is set entirely by IS and NF. Gross beta mismatch (>3:1) can cause minor base current errors but is unlikely within the same batch.

## 1.1 Tip: Identifying Transistor Type and Pinout with a DMM

A bipolar transistor is two back-to-back diodes sharing a common pin (the base). Set your DMM to **diode test mode** and measure the forward voltage between every pair of pins. Record the results in a 3×3 table (red lead = row, black lead = column).

### How to read the table

- **Find the base**: it's the pin that shows a forward diode drop to *both* other pins (in one lead polarity).
- **NPN vs PNP**: In an NPN, the two diodes point *away* from the base — you see forward drops with red on the base. In a PNP, the diodes point *toward* the base — you see forward drops with black on the base (red on E or C).
- **Collector vs Emitter**: The B–E junction has a **lower** forward voltage than the B–C junction because the emitter is more heavily doped. If both drops are identical, you can test hFE (current gain) in each orientation — the direction with higher gain is the correct C–E assignment.

### Example: NPN transistor (e.g. 2SC1815)

| Red \\ Black | **E** | **B** | **C** |
| :----------- | :---: | :---: | :---: |
| **E**        |   —   |  OL   |  OL   |
| **B**        | 0.58V |   —   | 0.62V |
| **C**        |  OL   |  OL   |   —   |

Reading the table:
- Row **B** has two forward drops → B is the base.
- Red on B shows diode drops → diodes point away from base → **NPN**.
- B→E = 0.58V < B→C = 0.62V → the lower drop identifies the **emitter**.

### Example: PNP transistor (e.g. 2SA1015)

| Red \\ Black | **E** | **B** | **C** |
| :----------- | :---: | :---: | :---: |
| **E**        |   —   | 0.58V |  OL   |
| **B**        |  OL   |   —   |  OL   |
| **C**        |  OL   | 0.62V |   —   |

Reading the table:
- Column **B** has two forward drops → B is the base.
- Black on B shows diode drops → diodes point toward base → **PNP**.
- E→B = 0.58V < C→B = 0.62V → the lower drop identifies the **emitter**.

### Quick summary

| Clue                           | NPN                      | PNP                      |
| :----------------------------- | :----------------------- | :----------------------- |
| Two diode drops appear when…   | Red is on the base       | Black is on the base     |
| Diodes point…                  | Away from base           | Toward base              |
| Lower forward voltage junction | B→E (identifies emitter) | E→B (identifies emitter) |

> **Note:** Exact voltages vary by transistor type — the absolute values don't matter. What matters is which pin shows drops to both others (base) and which junction has the lower drop (emitter).

## 2. Test Fixture

### 2.1 Design Philosophy

A 30V bench supply and high-value series resistors form two **fixed** current sources (100µA and 10µA). Because $V^+ \gg V_{BE}$, Ohm's law sets the current: swapping transistors changes VBE by a few millivolts against ~29V of headroom, shifting the current by less than 0.02%. The resistor network behaves like an ideal current source — no adjustment needed when switching DUTs.

Two independent sources eliminate pot-fiddling between Test 1 (matching at 100µA) and Test 2 (ideality check at 10µA). Calibrate both trim pots once at the start of the session, then perform every measurement by moving a single jumper wire.

### 2.2 Schematic

```
     100µA SOURCE                         10µA SOURCE

     V+ (30V)                             V+ (30V)
      │                                    │
    [R1  270kΩ]                          [R2  2.7MΩ]
      │                                    │
    [RV1  50kΩ trim]  ← set once         [RV2  500kΩ trim]  ← set once
      │                                    │
 A1 ●─┤  calibration test point       A2 ●─┤  calibration test point
      │                                    │
    [RS1  10kΩ ±1%]                      [RS2  10kΩ ±1%]
      │                                    │
 B1 ●─┤  100µA output                 B2 ●─┤  10µA output
      │                                    │
      └─── jumper wire to DUT              └─── jumper wire to DUT


     DUT (any one transistor at a time):

            B1 or B2
              │
              C ─── B   (collector-base short, permanent jumper per DUT)
              │
             DUT       2SC1815 under test
              │
              E
              │
             GND
```

Diode-connecting (C tied to B) forces the transistor into active mode with $V_{CE} = V_{BE}$.

#### Current source quality

| Parameter             | 100µA source  | 10µA source    |
| :-------------------- | :------------ | :------------- |
| Total series R        | ~294kΩ        | ~2.94MΩ        |
| Headroom (V+ − VBE)   | ~29.4V        | ~29.4V         |
| ΔI for 5mV VBE change | 17nA (0.017%) | 1.7nA (0.017%) |

For comparison, the old 9V/93kΩ design had 0.054% sensitivity — the 30V design is 3× more stable.

### 2.3 Breadboard Layout

Build both current sources and pre-install all candidate transistors **before** starting measurements. Each source ends at an output node (B1 or B2). A single jumper wire from that node reaches to whichever DUT is under test.

```
  ┌─── 100µA SOURCE ───┐      ┌─── 10µA SOURCE ────┐
  │                     │      │                     │
  │ V+ ─[R1 270k]──┐   │      │ V+ ─[R2 2.7M]──┐   │
  │          [RV1 50k]  │      │          [RV2 500k] │
  │              │      │      │              │      │
  │       (A1)───┤      │      │       (A2)───┤      │
  │          [RS1 10k]  │      │          [RS2 10k]  │
  │              │      │      │              │      │
  │       (B1) output   │      │       (B2) output   │
  └─────────────────────┘      └─────────────────────┘

  Pre-installed DUTs (all sitting in the breadboard, only one connected at a time):

     DUT1          DUT2          DUT3          DUT4          DUT5          DUT6
   E  C  B       E  C  B       E  C  B       E  C  B       E  C  B       E  C  B
   │  └──┘       │  └──┘       │  └──┘       │  └──┘       │  └──┘       │  └──┘
   │  (C-B       │  (C-B       │  (C-B       │  (C-B       │  (C-B       │  (C-B
   │  jumper)    │  jumper)    │  jumper)    │  jumper)    │  jumper)    │  jumper)
  GND           GND           GND           GND           GND           GND
  (bus)         (bus)         (bus)         (bus)         (bus)         (bus)
```

Each DUT has a permanent C-to-B jumper and its emitter on the GND bus. To test a transistor, plug one jumper wire from B1 (or B2) to that DUT's collector/base junction — that's the only wire that moves.

**Never connect both sources to the same DUT simultaneously** (currents would add, giving a wrong reading).

### 2.4 BOM

| Component | Value            | Notes                                                                |
| :-------- | :--------------- | :------------------------------------------------------------------- |
| V+        | 30V bench supply | Higher voltage = better current source. Any supply 20–35V works.     |
| R1        | 270kΩ            | Metal film preferred. Tolerance not critical (trim pot compensates). |
| RV1       | 50kΩ trim pot    | 100µA source adjustment. Bourns 3362 or similar.                     |
| RS1       | 10kΩ ±1%         | Sense resistor for 100µA calibration.                                |
| R2        | 2.7MΩ            | If unavailable: 2.2MΩ + 470kΩ in series.                             |
| RV2       | 500kΩ trim pot   | 10µA source adjustment.                                              |
| RS2       | 10kΩ ±1%         | Sense resistor for 10µA calibration.                                 |
| DUT       | 2SC1815          | Transistor under test (ECB pinout, TO-92). 4–6 per session.          |
| Jumpers   | —                | Short wires: one C-B jumper per DUT, one output wire per source.     |

#### Trim pot ranges

| Source | R at trim = 0     | R at trim = max        | Current range |
| :----- | :---------------- | :--------------------- | :------------ |
| 100µA  | 280kΩ (270k+10k)  | 330kΩ (270k+50k+10k)   | 105 – 89 µA   |
| 10µA   | 2.71MΩ (2.7M+10k) | 3.21MΩ (2.7M+500k+10k) | 10.9 – 9.2 µA |

### 2.5 Measurement Formulas

**Before building the circuit**, measure the actual resistance of RS1 and RS2 with your DMM and record them. Nominal 10kΩ ±1% resistors can be anywhere from 9.9kΩ to 10.1kΩ — use the measured values in all calculations.

All voltages are measured with respect to GND (black lead clipped to GND bus).

$$V_{BE} = V(B_n) \quad \text{(emitter is at GND)}$$

$$I_C = \frac{V(A_n) - V(B_n)}{R_{SENSE,measured}}$$

The calibration targets depend on your measured sense resistor values:

$$V_{SENSE} = I_C \times R_{SENSE,measured}$$

| Source | Target IC | If RS = 10.00kΩ | If RS = 9.95kΩ | If RS = 10.05kΩ |
| :----- | :-------- | :--------------- | :------------- | :-------------- |
| 100µA  | 100µA     | 1.000V           | 0.995V         | 1.005V          |
| 10µA   | 10µA      | 100.0mV          | 99.5mV         | 100.5mV         |

## 3. Test Procedures

### Calibration (one time, before all tests)

1. Measure the resistance of RS1 and RS2 with your DMM. Record the values.
2. Compute calibration targets: $V_{CAL} = I_{TARGET} \times R_{SENSE,measured}$.
3. Power on the 30V supply. Connect the 100µA source (B1) to any DUT.
4. Measure $V(A_1)$ and $V(B_1)$. Adjust RV1 until $V(A_1) - V(B_1) = 100\mu\text{A} \times R_{S1,measured}$.
   For example, if RS1 = 9.97kΩ, set the voltage difference to 0.997V.
5. Disconnect B1. Connect the 10µA source (B2) to the same (or any) DUT.
6. Measure $V(A_2)$ and $V(B_2)$. Adjust RV2 until $V(A_2) - V(B_2) = 10\mu\text{A} \times R_{S2,measured}$.
   For example, if RS2 = 10.03kΩ, set the voltage difference to 100.3mV.
5. **Lock both trim pots.** Optionally seal with a drop of nail polish or hot glue. Do not touch the pots again for the rest of the session.

### Test 1: VBE Matching (Critical)

This is the primary go/no-go test. It verifies IS matching between two transistors.

**Procedure:**

Clip the DMM black lead to GND and leave it there. All readings are taken with the red lead only.

1. Pre-install all candidate DUTs into the breadboard with C-B jumpers and emitters on the GND bus (see §2.3). **Wait 2 minutes** for all transistors to reach ambient temperature.
2. Plug the 100µA source jumper (from B1) into DUT #1's collector/base.
3. Measure $V(B_1)$ with the DMM. Record $V_{BE,1} = V(B_1)$.
4. Move the B1 jumper to DUT #2. Measure $V(B_1)$. Record $V_{BE,2}$.
5. Repeat for all remaining DUTs. **Do not adjust anything** — just move the one wire.
6. Pair the two transistors with the closest $V_{BE}$ readings.

*Why no re-calibration is needed:* A 5mV VBE difference between transistors changes IC by 5mV / 294kΩ = 17nA (0.017%), shifting VBE by only 0.01mV — far below your measurement threshold.

**Accept/Reject Criteria:**

| ΔVBE  | Grade     | Frequency Impact                                         |
| :---- | :-------- | :------------------------------------------------------- |
| < 1mV | Excellent | < 66 cents (absorbed by R_OFFSET cal)                    |
| 1–2mV | Good      | 66–133 cents (calibrate-able)                            |
| 2–5mV | Marginal  | Use only if no better pair available                     |
| > 5mV | Reject    | Different process characteristics, won't track thermally |

*Why these numbers:* A ΔVBE of 1mV at $V_T = 25.85\text{mV}$ gives a current ratio of $e^{1/25.85} = 1.039$, or 3.9% frequency error. This is 66 cents — well within the range of R_OFFSET calibration. The real concern is thermal tracking: a matched pair (ΔVBE < 2mV) will drift together with temperature, while a mismatched pair will not.

**Tip:** Test 4–6 transistors from the same batch. Since they're all pre-installed, you can cycle through them multiple times to check repeatability.

### Test 2: Ideality Factor (NF Check)

Verifies that the transistor follows the ideal exponential law. Both transistors in the pair should pass independently.

**Procedure:**

1. Plug the 100µA source jumper (from B1) into the DUT. Measure $V(B_1)$. Record $V_{BE,100}$.
2. Remove the B1 jumper. Plug the 10µA source jumper (from B2) into the **same** DUT. Measure $V(B_2)$. Record $V_{BE,10}$.
3. Compute $\Delta V_{BE} = V_{BE,100} - V_{BE,10}$.
4. Repeat for the other transistor in the pair.

No pots are adjusted. You are literally swapping one jumper wire for another.

**Expected value at 25°C:**

$$\Delta V_{BE} = V_T \times \ln(10) = 25.85\text{mV} \times 2.3026 = 59.5\text{mV}$$

This is the voltage change per decade of collector current for an ideal transistor (NF = 1).

| ΔVBE (per decade)  | NF             | Verdict                         |
| :----------------- | :------------- | :------------------------------ |
| 58–61mV            | ≈ 1.00         | Pass — ideal exponential        |
| 55–58mV or 61–65mV | ≈ 0.95 or 1.05 | Marginal — slight V/oct error   |
| < 55mV or > 65mV   | ≠ 1            | Reject — exponential law broken |

**Note:** Ambient temperature affects VT. At 20°C: 59.1mV. At 30°C: 59.9mV. Perform this test in a stable environment and don't touch the transistor (body heat changes VBE by ~2mV/°C).

### Test 3: Quick Sort (Batch Screening)

Test 1 screens all pre-installed transistors in one pass. For larger batches (>6 transistors), install them in groups of 6, run Test 1 on each group, then move the best candidates from each group to a single breadboard for a final comparison.

Once you have a matched pair, run Test 2 (NF check) on each transistor individually to confirm ideality.

## 4. SPICE Validation

Reference simulation of the dual-source fixture with resistor-based current sources from 30V. Runs a DC operating-point analysis at both 100µA and 10µA to validate expected VBE values.

```spice
* Transistor Matching Fixture - Dual Fixed Current Source
* 30V supply with resistor-chain current sources.
* Validates VBE at both operating points.

* ============================================================
* Supply
* ============================================================
V1 vcc 0 30

* ============================================================
* 100µA current source
* R1 (270k) + RV1 (trim, modeled at 13.6k) + RS1 (10k) = 293.6k
* I = (30 - VBE) / 293.6k ≈ 100µA
* ============================================================
R1   vcc  n1   270k
RV1  n1   a1   13.6k
RS1  a1   b1   10k
Q1   b1   b1   0   NPN_C1815

* ============================================================
* 10µA current source
* R2 (2.7M) + RV2 (trim, modeled at 232k) + RS2 (10k) = 2.942M
* I = (30 - VBE) / 2.942M ≈ 10µA
* ============================================================
R2   vcc  n2   2.7MEG
RV2  n2   a2   232k
RS2  a2   b2   10k
Q2   b2   b2   0   NPN_C1815

* ============================================================
* 2SC1815 NPN model (same as expo_converter_v2)
* ============================================================
.model NPN_C1815 NPN(IS=2.04f BF=400 NF=1
+   VAF=100 IKF=80m ISE=12.5f NE=2
+   BR=3.377 NR=1 ISC=0 RC=1 RB=10 RE=0.5
+   CJC=3.638p MJC=0.3085 VJC=0.75 FC=0.5
+   CJE=4.493p MJE=0.2593 VJE=0.75
+   TR=239.5n TF=301.2p
+   XTI=3 EG=1.11 XTB=1.5)

* ============================================================
* DC operating point — reports VBE and IC at both sources
* ============================================================
.op

.print dc v(b1) v(b2) v(a1) v(a2)
+ i(RS1) i(RS2)

* Expected results at 25°C:
*   v(b1) ≈ 637mV   (VBE at 100µA)
*   v(b2) ≈ 577mV   (VBE at 10µA)
*   i(RS1) ≈ 100µA
*   i(RS2) ≈ 10µA
*   v(b1) - v(b2) ≈ 59.5mV  (confirms NF = 1)
```

## 5. Expected Results

At 25°C (VT = 25.85mV) with IS = 2.04fA:

| Source | IC    | Expected VBE | Used in                                      |
| :----- | :---- | :----------- | :------------------------------------------- |
| 100µA  | 100µA | ≈ 637mV      | **Test 1 matching point**, Test 2 high point |
| 10µA   | 10µA  | ≈ 577mV      | Test 2 low point                             |

VBE difference between decades (10µA → 100µA): $59.6\text{mV}$ (confirms NF = 1).

Your DMM readings should be within ±10mV of these values (exact IS varies unit-to-unit). What matters is: (a) the *difference* between two transistors at the same current (Test 1), and (b) the *slope* per decade (Test 2) — not the absolute VBE.

## 6. Builder Notes

- **Calibrate once, then hands off**: After setting RV1 and RV2 during calibration, seal them (nail polish, hot glue, or just discipline). Every subsequent measurement is just moving one jumper wire.
- **Pre-install, don't swap**: Install all transistors before starting. Moving a jumper wire introduces zero thermal disturbance. Pulling and re-inserting a transistor adds a 30+ second wait while it re-equilibrates.
- **No gloves needed**: Briefly touching a TO-92 to insert it transfers negligible heat. The 2-minute thermal soak after installation handles it. Self-heating at 100µA: $P_{diss} = 0.637\text{V} \times 100\mu\text{A} = 64\mu\text{W}$, raising $T_J$ by only 0.013°C ($\theta_{JA} \approx 200\text{°C/W}$ for TO-92).
- **Don't hover over the DUTs**: Body heat radiating from your hand at close range can warm a TO-92 by 1–2°C. Keep hands away from the breadboard during measurements.
- **Trim pot wiring**: Wire the trim pot as a variable resistor — connect one end pin to the wiper pin so that if the wiper ever loses contact, the resistance goes to maximum (minimum current) rather than open circuit.
- **DMM resolution**: A 4½-digit DMM (10µV resolution) is ideal. A 3½-digit DMM (100µV) works for Test 1 (matching to 1mV) but is borderline for the 10µA calibration (100.0mV target has only 3 significant digits).
- **Supply voltage**: The exact voltage doesn't matter much — anything from 20V to 35V works. Higher voltage means even better current-source behavior. Just re-calibrate the trim pots if V+ changes.
- **One source per DUT**: Never connect both sources to the same transistor simultaneously. The currents add, giving 110µA instead of the expected single-source value.
- **Same session**: Always compare transistors in the same measurement session. VBE drifts with ambient temperature, so a reading from Monday cannot be compared to one from Tuesday.
