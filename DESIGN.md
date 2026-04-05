# Module Design: Analog Sample and Hold (S&H)

## 1. Theory of Operation
The Sample and Hold module captures the instantaneous voltage of an input signal at the moment a trigger is received. This design utilizes a JFET-based switching architecture to balance fast acquisition time with minimal voltage droop.

### Signal Path
*   **Input Stage**: A high-impedance buffer receives the "Source" signal.
*   **Sampling Core**: An N-Channel JFET acts as the gate between the input buffer and the storage capacitor.
*   **Storage**: A low-leakage film capacitor holds the sampled potential.
*   **Output Stage**: A dedicated high-input-impedance JFET op-amp buffers the capacitor's voltage to the output jack.

### Control Path
*   **Trigger Input**: A comparator converts any incoming signal above a threshold into a logic-high state.
*   **Pulse Shaper**: A passive RC differentiator converts the gate into a narrow pulse, ensuring the JFET only conducts for a fraction of a millisecond. This minimizes "feedthrough" (where the input signal leaks into the output during the sample phase).

## 2. Technical Specifications
*   **Input Impedance**: $100\text{k}\Omega$
*   **Output Impedance**: $<1\text{k}\Omega$ (Short-circuit protected)
*   **Power Consumption**: Approx. $\pm20\text{mA}$
*   **Signal Range**: $\pm10\text{V}$ (Full Eurorack swing)

## 3. Calibration Notes
*   **Offset**: The output buffer may require a small offset trim if using the module for precise 1V/Oct pitch tracking.
*   **Pulse Width**: The RC network in the pulse shaper can be adjusted to balance sampling reliability against signal bleed.

## 4. Sourcing Audit (BOM)
The following components have been selected from the Vetco Sourcing Library to ensure compatibility with DIP-based breadboarding and the Eurorack $\pm12\text{V}$ standard.

| Component | Part Number | Quantity | Unit Cost | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Dual Op-Amp** | LM358N | 1 | $2.06 | Input Signal Buffer & Trigger Comparator |
| **Precision Op-Amp** | NTE976 | 1 | $11.60 | Ultra-high impedance Hold Buffer (Low Droop) |
| **Switching JFET** | NTE467 | 1 | $1.10 | Low "on" resistance sampling switch |
| **NPN Transistor** | VET123AP | 1 | $1.69 | Trigger pulse shaper/level shifter |
| **Misc Passives** | Res/Cap/Diode | 1 | ~$2.50 | Film hold cap, protection diodes, resistors |

**Estimated Total Cost: ~$18.95**

### Sourcing Justification:
*   **NTE976**: While expensive, this single op-amp is critical for S&H modules. Its extremely low input bias current ensures that the charge stored on the hold capacitor doesn't leak away through the op-amp input, preventing "pitch drift."
*   **NTE467**: Specifically selected for its performance as an analog switch, providing a clean path for the signal during the sampling window.
*   **LM358N**: Used for non-audio tasks (buffering the input and comparing the trigger) where its slight crossover distortion is irrelevant.

---
*Status: Complete.*

## 5. SPICE Simulation (ngspice)
This netlist simulates a $23\text{Hz}$ sine wave being sampled at $10\text{Hz}$ to demonstrate hold stability and signal capture.

```spice
* Sample and Hold Circuit Validation

* Power Supplies
VCC vcc 0 12V
VEE vee 0 -12V

* Signal Sources
V_SOURCE source 0 SINE(0 5 23)         ; 23Hz 5V Peak Sine
V_TRIG trig_in 0 PULSE(0 5 0 1u 1u 1m 100m) ; 10Hz Trigger Pulse

* Input Stage (U1A: LM358N)
R1 source 0 100k
* in+ in- out v+ v-
U1A source buf_out buf_out vcc vee

* Trigger & Pulse Shaper (U1B: LM358N + Q1: VET123AP)
R2 vcc v_ref 10k
R3 v_ref 0 2.2k
* in+ in- out v+ v-
U1B trig_in v_ref comp_out vcc vee
C1 comp_out q1_b 10n
R4 q1_b 0 47k
* C B E
Q1 gate_ctrl q1_b vee VET123AP
R5 vcc gate_ctrl 10k
D1 gate_ctrl buf_out 1N4148 ; Clamp gate to signal during ON phase

* Sampling Core (Q2: NTE467 + C2: Hold Cap)
* D G S
Q2 buf_out gate_ctrl hold_node NTE467
C2 hold_node 0 100n ; Low-leakage film capacitor

* Output Stage (U2: NTE976)
* in+ in- out v+ v-
U2 hold_node out_sh out_sh vcc vee
R6 out_sh out_final 1k ; Short-circuit protection

.tran 100u 300m
.print tran v(source) v(out_final) v(trig_in)
```
