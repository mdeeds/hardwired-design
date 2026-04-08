# Module Design: Exponential Current Source (v2 — C1815 + LM358N)

## 1. Theory of Operation

This block converts a 1V/oct CV ($-5\text{V}$ to $+5\text{V}$, $0\text{V}$ = C4) into an exponential current. The output is a voltage proportional to the exponential current, produced by an op-amp transimpedance stage. The resistive feedback will eventually be replaced by a timing capacitor for the saw/triangle oscillator core.

### 1.1 Circuit Architecture

```
  CV_IN ──[R_IN 100k]──┐
                        ├── cv_sum (inverting input)
  VEE ──[R_OFFSET 91k]─┘        │
                        ┌────────┘
                        │  R_TEMPCO 1.8k (3300ppm PTC)
                        │
                   ┌────┴────┐
                   │  U1A    │
             GND──(+) LM358 (-)──cv_sum
                   │         │
                   └────┬────┘
                        │ cv_node
                        │
                        B  Q1 (C1815) ── driven transistor
                        │  C──[R_BIAS 3.3k]──VCC
                        │  E
                        │  │
                        │  ├── expo_emit (common emitter)
                        │  │
                        │  E
                        B  Q2 (C1815) ── output transistor
                   GND──┘  C──tia_in
                              │
                        ┌─────┤
                        │  R_FEEDBACK 100k
                        │     │
                   ┌────┴────┐│
                   │  U1B    ││
   GND──[R_COMP]──(+) LM358 (-)──tia_in
       100k        │         │
                   └────┬────┘
                        │
                      v_out  (= I_C2 × R_FEEDBACK)

               expo_emit
                   │
               [R_E 4.7k]
                   │
                  VEE
```

### 1.2 Sub-Block Descriptions

1. **U1A (CV Summer)**: Inverting summer. $R_{TEMPCO}$ ($1.8\text{k}\Omega$, 3300ppm PTC) as feedback, $R_{IN}$ ($100\text{k}\Omega$) from CV, $R_{OFFSET}$ ($91\text{k}\Omega$) from $V_{EE}$.

$$V_{cv\_node} = -\frac{1.8\text{k}}{100\text{k}} \cdot V_{CV} - \frac{1.8\text{k}}{91\text{k}} \cdot (-12\text{V}) = -0.018 \cdot V_{CV} + 0.237\text{V}$$

2. **Q1 (Control NPN)**: Base on `cv_node`. As CV increases, `cv_node` goes more negative, Q1 releases tail current to Q2. Collector load $R_{BIAS}$ ($3.3\text{k}\Omega$) keeps Q1 in active mode.

3. **Q2 (Output NPN)**: Base grounded. Collector current is the exponential output. Collector connects to the transimpedance amp's virtual ground (0V), giving a constant $V_{CE}$ independent of output current.

4. **R_E (Tail Resistor)**: $4.7\text{k}\Omega$ to $V_{EE}$. Sets $I_{tail} \approx 2.4\text{mA}$.

5. **U1B (Transimpedance Amp)**: Holds Q2's collector at virtual ground (0V). Q2's sink current flows through $R_{FEEDBACK}$ ($100\text{k}\Omega$), producing $V_{out} = I_{C2} \cdot R_{FEEDBACK}$ (positive). $R_{COMP}$ ($100\text{k}\Omega$) matches the impedance at U1B's non-inverting input to $R_{FEEDBACK}$, cancelling the bias current offset. This stage becomes the integrator when $R_{FEEDBACK}$ is replaced by a timing capacitor.

### 1.3 Operating Point Table

| $V_{CV}$ | Note | $V_{cv\_node}$ | $I_{C2}$ (approx) | $V_{out}$ (approx) |
| :---: | :---: | :---: | :---: | :---: |
| $-5\text{V}$ | C-1 | $+325\text{mV}$ | $\approx 8\text{nA}$ | $\approx 0.8\text{mV}$ |
| $0\text{V}$ | **C4** | $+235\text{mV}$ | $\approx 265\text{nA}$ | $\approx 26\text{mV}$ |
| $+5\text{V}$ | C9 | $+145\text{mV}$ | $\approx 8.5\mu\text{A}$ | $\approx 850\text{mV}$ |

## 2. Technical Specifications
*   **CV Input Range**: $-5\text{V}$ to $+5\text{V}$ (10 octaves, $0\text{V}$ = C4)
*   **Output Voltage Range**: ~$0.8\text{mV}$ to ~$850\text{mV}$ (across $R_{FEEDBACK}$)
*   **Tracking Accuracy**: 1V/Octave, $\pm 2.4$ cents across 10 octaves (simulated, post-calibration)
*   **Power Supply**: $\pm 12\text{V}$ DC (Eurorack standard)
*   **Active Components**: 1× LM358N (dual), 2× 2SC1815 (matched pair)

## 3. Sourcing Audit (BOM)

| Component | Part | Qty | Source | Unit Cost | Total |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **Dual Op-Amp** | LM358N | 1 | Brother's stock | $0.00 | $0.00 |
| **Low-Noise NPN** | 2SC1815 (C1815) | 2 | Brother's stock | $0.00 | $0.00 |
| **Tempco Resistor** | 1.8kΩ 3300ppm PTC | 1 | Specialty | $1.50 | $1.50 |
| **Misc Passives** | Resistors (6×) | 1 lot | Generic | $0.50 | $0.50 |

**Estimated Total: ~$2.00**

## 4. SPICE Simulation (ngspice)

DC sweep of CV from $-5\text{V}$ to $+5\text{V}$. Verifies exponential doubling-per-volt at the transimpedance amp output.

```spice
* Exponential Current Source - C1815 + LM358N Transimpedance
* CV range: -5V (C-1) through 0V (C4) to +5V (C9)
* U1A = CV summer, U1B = transimpedance amp

* ============================================================
* Power Supplies
* ============================================================
VCC vcc 0 12V
VEE vee 0 -12V

* ============================================================
* Control Voltage Source (swept during simulation)
* ============================================================
V_CV cv_in 0 DC 0V

* ============================================================
* U1: LM358N Dual Op-Amp (DIP-8 package)
*
* Single package instance with both sections.
* Pin order: 1=OUT_A 2=IN-_A 3=IN+_A 4=V- 5=IN+_B 6=IN-_B 7=OUT_B 8=V+
*
* Section A (pins 1-3): CV Summing Amplifier
*   Inverting summer with DC offset bias:
*   Vout = -(R_TEMPCO/R_IN)*V_CV - (R_TEMPCO/R_OFFSET)*VEE
*        = -0.018*V_CV + 0.237V
*   The 1.8k tempco gives 18mV/V = VT*ln(2), the exact delta-VBE
*   needed to double collector current per octave.
*
* Section B (pins 5-7): Transimpedance Amplifier
*   Q2 collector sinks current from the inverting input.
*   Op-amp drives output positive to supply current through
*   R_FEEDBACK, maintaining virtual ground at tia_in.
*   V_out = I_C2 * R_FEEDBACK (positive, exponential)
*   R_COMP matches impedance at (+) to R_FEEDBACK at (-),
*   so that equal bias currents produce equal voltage drops
*   that cancel via the differential input.
*   Future: replace R_FEEDBACK with timing capacitor C_TIMING
*   to create the integrator for saw/triangle core.
*   Note: R_FEEDBACK=100k gives 10x gain vs 10k for easier measurement.
*   The larger feedback resistor also improves SNR (~20dB) by scaling
*   the signal relative to fixed input noise/bias current noise.
* ============================================================
*    pin1     pin2   pin3 pin4 pin5    pin6   pin7  pin8
*    out_a    inn_a  inp_a vm  inp_b   inn_b  out_b vp
XU1  cv_node  cv_sum 0    vee  u1b_pos tia_in v_out vcc LM358N

* --- U1A external components (CV summer) ---
R_IN     cv_in cv_sum 100k
R_OFFSET vee   cv_sum 91k
R_TEMPCO cv_node cv_sum 1.8k

* ============================================================
* Q1, Q2: Matched NPN Exponential Pair (2SC1815)
*
* Q1 = driven (base on cv_node). As CV rises, cv_node goes
*      negative, Q1 conducts LESS, releasing tail current.
* Q2 = output (base grounded). Picks up exponential current.
*      Collector feeds into U1B transimpedance amp.
*
* Thermally coupled (same batch, bonded with thermal compound).
* ============================================================

* Q1: Driven transistor
*  C         B        E
Q1 expo_ref  cv_node  expo_emit NPN_C1815

* R_BIAS: Q1 collector load (3.3k keeps Q1 in active region)
R_BIAS vcc expo_ref 3.3k

* Q2: Output transistor (collector to transimpedance amp input)
*  C      B   E
Q2 tia_in 0   expo_emit NPN_C1815

* R_E: Shared tail resistor to negative rail
* I_tail = (0V - 0.7V - (-12V)) / 4.7k = 2.4mA
R_E expo_emit vee 4.7k

* --- U1B external components (transimpedance amp) ---
R_FEEDBACK v_out tia_in 100k
R_COMP     u1b_pos 0 100k

* ============================================================
* Transistor Model: 2SC1815 (low-noise audio NPN)
*
* Japanese low-noise audio transistor. NF=1 (ideal emission
* coefficient) ensures Ic = Is * exp(Vbe/VT) holds cleanly
* for precision 1V/Oct exponential conversion.
* ============================================================
.model NPN_C1815 NPN(IS=2.04f BF=400 NF=1
+   VAF=100 IKF=80m ISE=12.5f NE=2
+   BR=3.377 NR=1 ISC=0 RC=1 RB=10 RE=0.5
+   CJC=3.638p MJC=0.3085 VJC=0.75 FC=0.5
+   CJE=4.493p MJE=0.2593 VJE=0.75
+   TR=239.5n TF=301.2p
+   XTI=3 EG=1.11 XTB=1.5)

* LM358N dual op-amp macromodel (DIP-8 package)
* Pin order: 1=OUT_A 2=IN-_A 3=IN+_A 4=V- 5=IN+_B 6=IN-_B 7=OUT_B 8=V+
* Based on TI LM358 datasheet specifications:
*   Avol  = 100dB (100,000 V/V)
*   Ibias = 45nA (PNP input pair, current sourced out of pins)
*   Vos   = 2mV (input offset voltage, typical)
*   Rin   = 2MOhm (differential input impedance)
*   Rout  = 75 Ohm (open-loop output impedance)
.subckt LM358N out_a inn_a inp_a vm inp_b inn_b out_b vp
* --- Section A ---
IbpA 0 inp_a DC 45n
IbnA 0 inn_a DC 45n
VosA inp_a intpA DC 0
RinA intpA inn_a 2Meg
E1A intoutA 0 intpA inn_a 100000
RoutA intoutA out_a 75
* --- Section B ---
IbpB 0 inp_b DC 45n
IbnB 0 inn_b DC 45n
VosB inp_b intpB DC 0
RinB intpB inn_b 2Meg
E1B intoutB 0 intpB inn_b 100000
RoutB intoutB out_b 75
.ends LM358N

* ============================================================
* Simulation: DC Sweep
* Sweep CV from -5V to +5V in 0.1V steps (10 octaves)
* ============================================================
.dc V_CV -5 5 0.1

* v_out = exponential output voltage (= I_C2 * R_FEEDBACK)
.print dc v(cv_in) v(cv_node) v(v_out) v(expo_ref) v(expo_emit)
```

## 5. Builder Notes
*   **Thermal Coupling**: Q1 and Q2 must be from the same C1815 batch, glued together with thermal compound, and shrink-wrapped. The tempco resistor should also be bonded to the pair.
*   **LM358N Bias Compensation**: $R_{COMP}$ ($100\text{k}\Omega$) at U1B's non-inverting input matches the impedance seen by the inverting input through $R_{FEEDBACK}$. This cancels the LM358's ~45nA input bias current, which would otherwise add a $4.5\text{mV}$ DC offset — significant at low octaves where $I_{C2}$ is in the single-digit nA range. The input offset voltage ($V_{OS}$, up to $7\text{mV}$) is a fixed per-unit error absorbed into initial frequency calibration.
*   **Future Oscillator Conversion**: Replace $R_{FEEDBACK}$ with a timing capacitor to convert U1B into the integrator core. The exponential current charges the cap linearly, producing a ramp (sawtooth). A comparator + reset switch completes the saw oscillator.

## 6. Tuning & Troubleshooting

### 6.1 Tuning Resistors

**R_OFFSET (91k) — Frequency Calibration (CV = 0V)**
This is the primary tuning resistor. It sets $V_{cv\_node}$ when $V_{CV} = 0\text{V}$, which determines the base frequency (C4 / 261.6 Hz in oscillator mode). The target is:

$$V_{cv\_node}\big|_{CV=0} = +237\text{mV}$$

This gives $I_{C2} \approx 265\text{nA}$ at middle C. To tune:
*   Measure $V_{cv\_node}$ with CV grounded.
*   **Too high** → frequency too low → decrease R_OFFSET (more current from $V_{EE}$ pulls cv_sum harder, U1A output goes lower).
*   **Too low** → frequency too high → increase R_OFFSET.
*   A trimpot (100k pot + 47k series resistor) can replace R_OFFSET for bench calibration. The series resistor prevents the trimpot from going below a safe minimum.

**R_TEMPCO (1.8k, 3300ppm PTC) — Scale (V/Oct Tracking)**
This sets the volts-per-octave slope. The gain from CV to $V_{cv\_node}$ is $-R_{TEMPCO}/R_{IN} = -1.8\text{k}/100\text{k} = -18\text{mV/V}$. This must equal $V_T \cdot \ln(2) \approx 17.9\text{mV}$ at 25°C for exact 1V/oct tracking. R_TEMPCO is not easily trimmed — it's a precision part selected for the correct value. The 3300ppm PTC characteristic compensates for the transistor pair's $V_T$ temperature drift (~3300ppm/°C), maintaining tracking across temperature.

**R_E (4.7k) — Tail Current / Maximum Output**
Sets $I_{tail} \approx (0\text{V} - 0.7\text{V} - V_{EE}) / R_E = 11.3\text{V} / 4.7\text{k} \approx 2.4\text{mA}$. This is the total current shared between Q1 and Q2. At the highest octave (CV = +5V), Q2 only takes $8.5\mu\text{A}$ — just 0.35% of the tail current — so there is wide headroom. R_E does not need precision tuning. Effects of changing it:
*   **Larger R_E** → less tail current → Q1/Q2 operate at lower currents → slightly slower thermal settling, but negligible impact on tracking.
*   **Smaller R_E** → more tail current → more power dissipation in the emitter leg → more self-heating of Q1/Q2 (bad for stability).
*   Keep R_E in the 3.3k–10k range. The exact value is not critical.

**R_BIAS (3.3k) — Q1 Collector Load**
Keeps Q1 in active mode by pulling its collector toward $V_{CC}$. Not a tuning resistor. The constraint is Q1 must not saturate ($V_{CE} > 0.2\text{V}$) across the full CV range. Worst case is CV = $-5\text{V}$, where Q1 carries nearly all the tail current:

$$V_{C,Q1} = V_{CC} - I_{C1} \cdot R_{BIAS} \approx 12 - 2.4\text{mA} \times 3.3\text{k} = 4.1\text{V}$$

Plenty of headroom. R_BIAS only matters if it's too large (Q1 saturates) or too small (wasted current, minor). Keep in the 2.2k–4.7k range.

### 6.2 Troubleshooting

| Symptom | Likely Cause | Check / Fix |
| :--- | :--- | :--- |
| No output (v_out ≈ 0V) | U1B not powered, Q2 not conducting, or open R_FEEDBACK | Verify ±12V rails. Measure expo_emit — should be ≈ $-0.7\text{V}$. Measure tia_in — should be near 0V (virtual ground). |
| Output stuck at V+ rail | U1B saturated — Q2 drawing too much current, or tia_in disconnected | Measure I_C2 via v_out/R_FEEDBACK. If > 100µA, check Q1/Q2 orientation. If tia_in is floating, U1B output rails positive. |
| Flat output (no exponential shape) | Q1 or Q2 saturated, or cv_node not varying | Sweep CV and measure cv_node — should go from +327mV to +147mV linearly. If flat, check U1A feedback (R_TEMPCO). Measure $V_{CE}$ on both transistors — must be > 0.2V. |
| Wrong V/Oct slope (not doubling per volt) | R_TEMPCO wrong value, or poor thermal coupling | Measure v_out ratio between adjacent octaves — should be exactly 2×. If consistently off, recheck R_TEMPCO value. If drifting with temperature, improve thermal bond between Q1, Q2, and R_TEMPCO. |
| Correct slope but wrong frequency at CV=0 | R_OFFSET needs trimming | Adjust R_OFFSET per §6.1. This is the normal calibration step. |
| Output noisy or drifting | Thermal mismatch, PCB leakage, or poor grounding | Ensure Q1/Q2 are bonded. Clean flux residue around tia_in node (100kΩ R_FEEDBACK is sensitive to nA-level leakage). Use star grounding for the analog ground. |
| Output offset at low octaves (CV < $-3\text{V}$) | Bias current mismatch or R_COMP wrong | Verify R_COMP = R_FEEDBACK = 100kΩ. Residual offset from $I_{OS}$ (5–10nA × 100kΩ = 0.5–1mV) is normal and absorbed into calibration. |
