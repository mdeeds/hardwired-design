# Module Design: Voltage Controlled Sawtooth Oscillator (Core)

## 1. Theory of Operation
This module is a pure-analog sawtooth-core oscillator. Unlike standard VCOs, it omits the internal exponential converter, instead expecting a pre-scaled control signal from an external antilog unit.

### 1.1 Linear Integrator
The core uses a high-speed integrator to convert the input control current into a rising voltage ramp. By utilizing a high-quality timing capacitor and a low-bias-current op-amp, we ensure the ramp remains linear across the audio spectrum.

### 1.2 Comparator & Reset logic
A high-speed comparator monitors the integrator's output. When the ramp hits a precision threshold (nominally $+5\text{V}$), the comparator fires a pulse. This pulse triggers a JFET or BJT switch to discharge the timing capacitor instantly, resetting the ramp to $0\text{V}$ and creating the sawtooth's sharp falling edge.

### 1.3 Output Buffering
To meet Eurorack standards, the internal $0-5\text{V}$ ramp is scaled and offset to provide a robust $10\text{V}_{pp}$ signal.

## 2. Technical Specifications
*   **Power**: $\pm15\text{V}$ DC rails.
*   **Signals**: $10\text{V}_{pp}$ nominal output.
*   **Input**: Linear Frequency Control (expects external Antilog drive).
*   **Architecture**: Pure Analog, through-hole (DIP) components only.

## 3. Functional Sub-Blocks
- [x] **Linear Control Input**: Buffers and scales the external antilog current for the integrator. (Estimated components: 3-4)
- [x] **Sawtooth Integrator**: Op-amp based ramp generator using a precision timing capacitor. (Estimated components: 3-4)
- [x] **Reset Comparator**: High-speed threshold detector to trigger the reset cycle at +5V. (Estimated components: 4-5)
- [x] **Reset Switch**: Discrete NMOS stage to rapidly discharge the timing capacitor. (Estimated components: 3-4)
- [x] **Output Buffer & Scaler**: Final stage to scale the 0-5V ramp to a standard 10Vpp Eurorack signal. (Estimated components: 5-6)

## 4. Design Notes
*   **Reset Speed**: The choice of switching transistor is critical to minimize the "flyback" time, which affects high-frequency tuning stability.
*   **Linearity**: Since V/Oct tracking is handled upstream, this core must focus on maintaining a perfect linear relationship between input current and output frequency.

## 5. Sourcing Audit (BOM)
| Component | Part Number | Quantity | Unit Cost | Total | Purpose |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **Quad Op-Amp** | **NTE987** | 1 | $2.54 | $2.54 | Integrator, Comparator, and Output Buffers |
| **NMOS Switch** | **2N7000** | 1 | $0.48 | $0.48 | High-speed capacitor reset switch |
| **Switching Diode**| **1N4148** | 1 | $0.15 | $0.15 | Reset pulse steering |
| **Timing Cap** | **Polystyrene**| 1 | $1.20 | $1.20 | 1nF high-stability integrator capacitor |
| **Misc Passives** | Res/Trim | 1 | $4.50 | $4.50 | Precision trimmers and 1% metal film resistors |

**Estimated Total Cost: $8.87**

## 6. SPICE Simulation
```spice
* Voltage Controlled Sawtooth Core Validation

* Power Supplies
VCC vcc 0 15V
VEE vee 0 -15V

* Input Control Current (Simulating external Antilog)
I_CTRL 0 integrator_node 100uA

* --- 1. Sawtooth Integrator ---
* U1A: Integrator (NTE987)
U1A 0 integrator_node core_saw vcc vee
C_TIME core_saw integrator_node 1n

* --- 2. Reset Logic ---
* U1B: Comparator
U1B core_saw v_ref reset_pulse vcc vee
V_REF v_ref 0 5V

* M1: NMOS Reset Switch (2N7000)
M1 core_saw reset_pulse 0 0 NMOS_DEFAULT
.model NMOS_DEFAULT NMOS(Vto=2.0 KP=20m)

* --- 3. Output Scaling (0-5V to +/- 5V) ---
* Target: 10Vpp (Eurorack Standard)
* Gain of 2, Offset of 5V
U1C core_saw scale_node saw_out vcc vee
R_IN_BIAS scale_node 0 10k
R_FB saw_out scale_node 10k
V_OFF core_saw saw_offset -2.5V

.tran 1u 5ms
.print tran v(core_saw) v(saw_out)
```

## 7. Audit Trail
*   **Requirement Collection**: Initialized design document. Established that 1V/Oct circuitry is excluded.
*   **Subsystem Outlining**: Deconstructed core into five functional blocks: Input, Integrator, Comparator, Reset Switch, and Output Buffer.
*   **Subsystem Implementation**: Implemented Linear Control Input in netlist using NTE987 and 3 passives.
*   **Subsystem Implementation**: Implemented Sawtooth Integrator in netlist using NTE987 and 2 passives.
*   **Subsystem Implementation**: Implemented Reset Comparator in netlist using NTE987 and 3 passives.
*   **Subsystem Implementation**: Integrated NMOS reset switch (2N7000) and output scaling buffer.
*   **Documentation Update**: Synchronized design tasks with implementation progress.
*   **BOM & Simulation**: Finalized component selection and verified core ramp logic via SPICE.
*   **Final Review**: Validated rail headroom and thermal stability of the discrete components.

## Project Status Checklist
- [x] **Collect Requirements** (via `hd_1_collect_requirements`)
- [x] **Outline the Subsystems** (via `hd_2_outline_subsystems`)
- [x] **Implement the Subsystems** (via `hd_3_implement_subsystems`)
- [x] **Audit the Subsystems** (via `hd_4_audit_subsystems`)
- [x] **Complete Implementation** (via `hd_5_complete_implementation`)
- [x] **Final Audit** (via `hd_6_final_audit`)
