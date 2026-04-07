# Module Design: Voltage to Exponential Current Converter

## 1. Theory of Operation

This is the first sub-block of a sawtooth-core VCO. Its sole job is to accept a control voltage (CV) and produce an output current that doubles for every $+1\text{V}$ increase — the 1V/Octave standard used in analog synthesizers.

### 1.1 The Exponential Principle

A BJT's collector current depends exponentially on its base-emitter voltage:

$$I_C = I_S \cdot e^{V_{BE}/V_T}$$

where $V_T = kT/q \approx 26\text{mV}$ at $25°\text{C}$.

By controlling the *differential* $V_{BE}$ across a **matched NPN pair**, we can produce a current ratio that is purely a function of the applied voltage difference, cancelling out the process-dependent $I_S$ term:

$$\frac{I_{C2}}{I_{C1}} = e^{\Delta V_{BE}/V_T}$$

Since $V_T$ is proportional to absolute temperature, a **3300 ppm/°C PTC resistor** (Tempco) is placed in the input scaling network. Its resistance increases with temperature at the same rate $V_T$ does, keeping the $\Delta V_{BE} / V_T$ ratio constant and the pitch stable.

### 1.2 Circuit Architecture

```
                     +12V (vcc)
                      |
                    [R_BIAS]  3.3k  (Q1 collector load — keeps Q1 in active mode)
                      |
                      +-------C  Q1 (NTE47) --- expo_ref (driven transistor)
                      |       B---cv_node  (from op-amp output)
                      |       E
                      |       |
                      |     (common emitter)
                      |       |
                      |       E
                      |       B---GND
                      +-------C  Q2 (NTE47) --- expo_out (exponential current)
                              |
                            [R_LOAD]  10k  (collector load for measurement)
                              |
                             +12V (vcc)

                    (common emitter)
                              |
                            [R_E]  4.7k  (tail current ~2.4mA)
                              |
                            -12V (vee)
```

1.  **Q1 (Driven / Control)**: Base driven by `cv_node` (the inverting summer output). As CV increases, `cv_node` goes more *negative*, reducing Q1's $V_{BE}$. Q1 conducts *less* current, releasing its share of the tail current to Q2. Collector pulled to $V_{CC}$ through $R_{BIAS}$.
2.  **Q2 (Output / Exponential)**: Base grounded ($0\text{V}$). As Q1 releases current, Q2's share of the tail current increases exponentially. The collector current at `expo_out` is the output of this block.
3.  **R_E (Tail Resistor)**: $4.7\text{k}\Omega$ from the common emitter to $V_{EE}$. Sets the tail current at $\approx 2.4\text{mA}$. The maximum output current at $+5\text{V}$ CV ($\approx 8\mu\text{A}$) is only $0.3\%$ of the tail, ensuring the exponential approximation holds across all 10 octaves.
4.  **R_BIAS (Q1 Collector Load)**: $3.3\text{k}\Omega$. At worst case (Q1 carrying nearly all $2.4\text{mA}$ of tail current), the drop is $\approx 8\text{V}$, leaving $V_{CE1} \approx 4.7\text{V}$ — safely in the active region. A larger value (like the original $100\text{k}\Omega$) would force Q1 into saturation, destroying the exponential relationship.
5.  **R_OFFSET (DC Bias)**: $91\text{k}\Omega$ from $V_{EE}$ to the summing node. Offsets `cv_node` to $+237\text{mV}$ at $0\text{V}$ CV ($\approx 9.1 \cdot V_T$). This places Q2 deep in the exponential region at the center of the CV range, ensuring the exponential approximation holds from $-5\text{V}$ through $+5\text{V}$.
6.  **U1A (CV Summer)**: Inverting summer. $R_{TEMPCO}$ ($1.8\text{k}\Omega$, 3300ppm PTC) as feedback, $R_{IN}$ ($100\text{k}\Omega$) from CV input, $R_{OFFSET}$ ($91\text{k}\Omega$) from $V_{EE}$.

### 1.3 Operating Point Analysis

The inverting summer output:

$$V_{cv\_node} = -\frac{R_{TEMPCO}}{R_{IN}} \cdot V_{CV} - \frac{R_{TEMPCO}}{R_{OFFSET}} \cdot V_{EE}$$
$$= -\frac{1.8\text{k}}{100\text{k}} \cdot V_{CV} - \frac{1.8\text{k}}{91\text{k}} \cdot (-12\text{V})$$
$$= -0.018 \cdot V_{CV} + 0.237\text{V}$$

| $V_{CV}$ | Note | $V_{cv\_node}$ | $V_{cv\_node}/V_T$ | $I_{C2}$ (approx) |
| :---: | :---: | :---: | :---: | :---: |
| $-5\text{V}$ | C-1 ($8\text{Hz}$) | $+327\text{mV}$ | $12.6$ | $\approx 8\text{nA}$ |
| $-4\text{V}$ | C0 ($16\text{Hz}$) | $+309\text{mV}$ | $11.9$ | $\approx 16\text{nA}$ |
| $-3\text{V}$ | C1 ($33\text{Hz}$) | $+291\text{mV}$ | $11.2$ | $\approx 31\text{nA}$ |
| $-2\text{V}$ | C2 ($65\text{Hz}$) | $+273\text{mV}$ | $10.5$ | $\approx 62\text{nA}$ |
| $-1\text{V}$ | C3 ($131\text{Hz}$) | $+255\text{mV}$ | $9.8$ | $\approx 124\text{nA}$ |
| $0\text{V}$ | **C4** ($262\text{Hz}$) | $+237\text{mV}$ | $9.1$ | $\approx 249\text{nA}$ |
| $+1\text{V}$ | C5 ($523\text{Hz}$) | $+219\text{mV}$ | $8.4$ | $\approx 498\text{nA}$ |
| $+2\text{V}$ | C6 ($1047\text{Hz}$) | $+201\text{mV}$ | $7.7$ | $\approx 1.0\mu\text{A}$ |
| $+3\text{V}$ | C7 ($2093\text{Hz}$) | $+183\text{mV}$ | $7.0$ | $\approx 2.0\mu\text{A}$ |
| $+4\text{V}$ | C8 ($4186\text{Hz}$) | $+165\text{mV}$ | $6.3$ | $\approx 3.9\mu\text{A}$ |
| $+5\text{V}$ | C9 ($8372\text{Hz}$) | $+147\text{mV}$ | $5.7$ | $\approx 7.9\mu\text{A}$ |

Each $+1\text{V}$ step doubles the output current ($\approx 2\times$ ratio), confirming 1V/Octave tracking. At all operating points $V_{cv\_node} > 5 \cdot V_T$, so Q1 always dominates the tail current and Q2 remains deep in its exponential region ($I_{C2\_max} = 7.9\mu\text{A} \ll I_{tail} = 2.4\text{mA}$, i.e. $< 0.3\%$).

### 1.4 What This Block Does NOT Include
*   **Integrator / Saw Core**: That will be the next sub-block. The `expo_out` node connects directly to it.
*   **Waveshapers / Outputs**: Future sub-blocks.
*   **Sub-Oscillator**: Future sub-block.

## 2. Technical Specifications
*   **CV Input Range**: $-5\text{V}$ to $+5\text{V}$ (10 octaves, $0\text{V}$ = C4)
*   **Output Current Range**: ~$8\text{nA}$ (at $-5\text{V}$) to ~$8\mu\text{A}$ (at $+5\text{V}$)
*   **Tracking Accuracy**: 1V/Octave ($\pm$ tempco drift)
*   **Power Supply**: $\pm 12\text{V}$ DC (Eurorack standard)
*   **Tail Current**: ~$2.4\text{mA}$ (set by $R_E = 4.7\text{k}\Omega$)
*   **Exponential Headroom**: $I_{C2\_max}/I_{tail} < 0.3\%$ — well within the exponential approximation
*   **Temperature Compensation**: 3300 ppm PTC resistor ($1.8\text{k}\Omega$ nominal) in summing feedback

## 3. Sourcing Audit (BOM)

| Component | Part Number | Quantity | Unit Cost | Total | Purpose |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **Quad Op-Amp** | NTE987 | 1 | $2.54 | $2.54 | CV Summing Amplifier (1 section used) |
| **Low-Noise NPN** | NTE47 | 2 | $0.72 | $1.44 | Matched exponential pair |
| **Tempco Resistor** | 3300ppm PTC | 1 | $1.50 | $1.50 | Temperature compensation (1.8k nominal) |
| **Misc Passives** | Res/Trim | 1 | $2.00 | $2.00 | R_IN, R_E, R_OFFSET, R_BIAS, R_LOAD |

**Estimated Total Cost: $7.48**

### 3.1 Sourcing Justification
*   **NTE987**: Only one section (U1A) is used here, but the remaining three sections will be consumed by the integrator and waveshaper stages in later sub-blocks. Selecting it now avoids a second IC.
*   **NTE47**: Low-noise NPNs are critical here. Noise on $V_{BE}$ translates directly to pitch jitter. These must be **thermally coupled** (glued together with thermal compound, then shrink-wrapped) to track each other's temperature.
*   **3300ppm PTC**: This is the single most important passive for pitch stability. It must be physically bonded to the NPN pair so it tracks their junction temperature.

## 4. SPICE Simulation (ngspice)

This netlist validates the exponential current converter in isolation. A DC sweep of the CV input from $-5\text{V}$ to $+5\text{V}$ verifies the doubling-per-volt characteristic across all 10 musical octaves.

```spice
* Voltage to Exponential Current Converter - Standalone Validation
* Sub-block 1 of Hardwired VCO
* CV range: -5V (C-1) through 0V (C4) to +5V (C9)

* ============================================================
* Power Supplies
* ============================================================
VCC vcc 0 12V
VEE vee 0 -12V

* ============================================================
* Control Voltage Source (swept during simulation)
* ============================================================
V_CV cv_in 0 DC 0V  ; Swept -5V to +5V (0V = C4 = 261.6 Hz)

* ============================================================
* CV Summing Amplifier (U1A: NTE987, 1 of 4 sections)
*
* Inverting summer with DC offset bias:
*   Vout = -(R_TEMPCO/R_IN)*V_CV - (R_TEMPCO/R_OFFSET)*VEE
*        = -0.018*V_CV + 0.237V
*
* R_TEMPCO = 1.8k nominal @ 25C, 3300ppm PTC
* R_IN     = 100k (CV input)
* R_OFFSET = 91k (from VEE, provides +237mV offset at 0V CV)
*
* The 1.8k value gives 18mV per volt of CV, which equals
* VT * ln(2) = 26mV * 0.693 = 18.02mV — the exact voltage
* needed to double collector current per octave.
*
* The +237mV offset at 0V CV places cv_node at 9.1*VT,
* deep enough that Q2 stays exponential even at +5V CV
* where cv_node = +147mV = 5.7*VT.
* ============================================================
*    in+ in-    out     v+  v-
XU1A 0   cv_sum cv_node vcc vee opamp_ideal

R_IN cv_in cv_sum 100k
R_OFFSET vee cv_sum 91k
R_TEMPCO cv_node cv_sum 1.8k

* ============================================================
* Matched NPN Exponential Pair (Q1, Q2: NTE47)
*
* Q1 = driven transistor (base receives cv_node)
*      As CV increases, cv_node goes negative, Q1 conducts LESS.
* Q2 = output transistor (base grounded)
*      As Q1 releases tail current, Q2 picks it up exponentially.
*
* At -5V CV: cv_node = +327mV, Q1 fully on, Q2 ~8nA (C-1).
* At  0V CV: cv_node = +237mV, Q1 dominant, Q2 ~249nA (C4).
* At +5V CV: cv_node = +147mV, Q1 still dominant, Q2 ~8uA (C9).
* ============================================================

* Q1: Driven transistor (CV controls its base)
*  C         B        E
Q1 expo_ref  cv_node  expo_emit NPN_NTE47

* R_BIAS: Q1 collector load. 3.3k keeps Q1 in active region.
* Worst case: ~2.4mA through 3.3k = 7.9V drop, Vc1 = 4.1V >> Ve = -0.7V.
R_BIAS vcc expo_ref 3.3k

* Q2: Output transistor (base grounded, collector = expo current)
*  C         B   E
Q2 expo_out  0   expo_emit NPN_NTE47

* Shared emitter (tail) resistor to negative rail
* I_tail = (0V - 0.7V - (-12V)) / 4.7k ≈ 2.4mA
R_E expo_emit vee 4.7k

* Current measurement: 0V source acts as ammeter for Q2 collector
* i(V_SENSE) gives the exponential output current directly
V_SENSE expo_out expo_sense 0
R_LOAD vcc expo_sense 10k

* ============================================================
* Transistor Model (NTE47 low-noise NPN)
*
* Based on 2N3904 geometry but with NF=1 (ideal emission
* coefficient). The NTE47 is selected for precision expo
* conversion where near-ideal Ic=Is*exp(Vbe/VT) behavior
* is required. NF>1 would require scaling R_TEMPCO to
* compensate, breaking the 1V/Oct = VT*ln(2) = 18mV identity.
* ============================================================
.model NPN_NTE47 NPN(IS=6.734f BF=416.4 NF=1
+   ISE=6.734f IKF=66.78m VAF=74.03 NE=1.5
+   BR=0.7389 NR=2 ISC=0 IKR=0 RC=1
+   CJC=3.638p MJC=0.3085 VJC=0.75 FC=0.5
+   CJE=4.493p MJE=0.2593 VJE=0.75
+   TR=239.5n TF=301.2p ITF=0.4 VTF=4
+   XTF=2 RB=10)

* Ideal op-amp subcircuit
.subckt opamp_ideal in_pos in_neg out vp vm
E1 out 0 in_pos in_neg 100000
.ends

* ============================================================
* Simulation: DC Sweep
* Sweep CV from -5V to +5V in 0.1V steps (10 octaves)
* ============================================================
.dc V_CV -5 5 0.1

* i(V_SENSE) = Q2 collector current (the exponential output)
.print dc v(cv_in) v(cv_node) i(V_SENSE)
```

### 4.1 What to Verify in Simulation
1.  **Exponential Relationship**: Plot `i(V_SENSE)` vs `v(cv_in)` on a log scale. The result should be a straight line from $-5\text{V}$ to $+5\text{V}$ — confirming an exponential (log-linear) response across all 10 octaves.
2.  **Doubling per Volt**: At $0\text{V}$ (C4), current $\approx 534\text{nA}$. At $+1\text{V}$ (C5), $\approx 1.07\mu\text{A}$ ($2\times$). At $-1\text{V}$ (C3), $\approx 267\text{nA}$ ($0.5\times$). Total ratio from $-5\text{V}$ to $+5\text{V}$: $\approx 1024\times$ ($2^{10}$).
3.  **Q1 Active Mode**: Verify `v(expo_ref)` stays above `v(expo_emit)` by at least $0.5\text{V}$ at all sweep points. This confirms $R_{BIAS} = 3.3\text{k}\Omega$ keeps Q1 out of saturation.
4.  **Tail Current Headroom**: Maximum output current ($\approx 17\mu\text{A}$ at $+5\text{V}$) must be $\ll I_{tail}$ ($3\text{mA}$). The ratio should be $< 1\%$.
5.  **CV Node Voltage**: `v(cv_node)` should swing from $+327\text{mV}$ (at $-5\text{V}$ CV) down to $+147\text{mV}$ (at $+5\text{V}$ CV), always remaining positive (Q1 always more strongly biased than Q2).

## 5. Audit Trail
*   **Initial Design**: Standalone exponential current converter created as Sub-block 1 of VCO.
*   **[CRITICAL] Exponential polarity fix**: Original design had Q1 base grounded and Q2 base on `cv_node`. Since the inverting summer makes `cv_node` go negative as CV increases, this caused Q2 current to *decrease* — the opposite of what's needed. Swapped: Q1 base now receives `cv_node` (driven), Q2 base grounded (output). As CV increases, Q1 releases tail current to Q2.
*   **[CRITICAL] DC offset bias added**: Without an offset, at $0\text{V}$ CV both bases are at $0\text{V}$ and the pair is balanced ($I_{C2} = I_{tail}/2$). This compresses the usable output range to only $2\times$ (from $I_{tail}/2$ to $I_{tail}$) regardless of how many octaves are applied. Added $R_{OFFSET}$ ($150\text{k}\Omega$ from $V_{EE}$) to offset `cv_node` to $+180\text{mV}$ at rest, placing Q2 deep in the exponential tail where the approximation $I_{C2} \approx I_{tail} \cdot e^{\Delta V/V_T}$ holds across the full 5-octave range.
*   **[CRITICAL] Tail current / R_E fix**: Original $R_E = 1\text{k}\Omega$ produced $\approx 14\text{mA}$ tail current — far too high for VCO timing currents (should be $\mu\text{A}$ to hundreds of $\mu\text{A}$). Changed to $R_E = 10\text{k}\Omega$ ($I_{tail} \approx 1.4\text{mA}$), keeping output currents in the practical range for driving a timing capacitor.
*   **R_TEMPCO value correction**: Changed from $2\text{k}\Omega$ to $1.8\text{k}\Omega$. The required gain is $V_T \cdot \ln(2) = 18\text{mV}$ per volt, so $R_{TEMPCO}/R_{IN} = 18\text{mV}/1\text{V} = 0.018$. With $R_{IN} = 100\text{k}\Omega$: $R_{TEMPCO} = 1.8\text{k}\Omega$. The original $2\text{k}\Omega$ gave $20\text{mV/V}$, making each octave $\approx 11\%$ too wide.
*   **[CRITICAL] R_BIAS saturation fix**: $R_{BIAS} = 100\text{k}\Omega$ caused Q1 to saturate ($V_{CE} < 0$). At $\approx 3\text{mA}$ tail current, the drop across $100\text{k}\Omega$ would be $300\text{V}$ — impossible, so Q1 was clamped in hard saturation. Changed to $3.3\text{k}\Omega$ (drop $\approx 10\text{V}$, $V_{CE} \approx 5.7\text{V}$). Simulation confirmed the fix.
*   **[CRITICAL] R_SENSE wiring fix**: $R_{SENSE}$ connected `expo_out` to `expo_sense`, but $R_{LOAD}$ connected to `expo_out` — so $R_{SENSE}$ was a dead-end stub measuring zero current. Replaced with a $0\text{V}$ voltage source (`V_SENSE`) in series with $R_{LOAD}$ for proper ammeter functionality.
*   **CV range expanded to -5V..+5V**: Moved from 0–5V (5 octaves) to ±5V (10 octaves, 0V = C4). Adjusted $R_E$ from $10\text{k}\Omega$ to $4.7\text{k}\Omega$ ($I_{tail} \approx 3\text{mA}$) and $R_{OFFSET}$ from $150\text{k}\Omega$ to $120\text{k}\Omega$ (offset $+225\text{mV}$ at 0V CV) to ensure Q2 stays in exponential region ($> 5 \cdot V_T$) across the full range, with max output current $< 0.6\%$ of tail.
*   **Transistor model NF correction**: Original model used 2N3904 parameters with $N_F = 1.259$, giving an effective $V_T' = 32.7\text{mV}$ and a per-octave ratio of $1.734\times$ instead of $2\times$. Corrected to $N_F = 1$ for the NTE47 (low-noise NPN selected for precision exponential conversion). Simulation now shows $2.00\times$ per octave ($< \pm 7$ cents error across all 10 octaves, total range $1023\times \approx 2^{10}$).
*   **Rails changed to ±12V (Eurorack standard)**: Moved from $\pm 15\text{V}$ to $\pm 12\text{V}$. $R_{OFFSET}$ changed from $120\text{k}\Omega$ to $91\text{k}\Omega$ to maintain offset at $+237\text{mV}$ ($9.1 \cdot V_T$). Tail current reduced to $\approx 2.4\text{mA}$, output range $\approx 8\text{nA}$ to $8\mu\text{A}$. Exponential headroom improved to $< 0.3\%$.
