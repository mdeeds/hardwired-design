# Exponential Converter Design (Matched BJT Pair)

## Overview
This skill documents the design and simulation of an exponential voltage-to-current converter using a matched pair of NPN transistors. The circuit implements octave-scaled control: the output current doubles approximately once per volt of input control voltage.

**Use case:** VCO exponential controllers, pitch CV-to-frequency converters, and other exponential modulation circuits in Eurorack modules.

## Design Principles

### Exponential Behavior
BJTs in the active region follow the Shockley equation:
$$I_C = I_S \cdot e^{V_{BE}/V_T}$$

where:
- $I_S$ = reverse saturation current (transistor-specific)
- $V_{BE}$ = base-emitter voltage
- $V_T$ = thermal voltage ≈ 26 mV at room temperature

### Matched Pair Advantage
When two transistors from the same matched package are used:
- Q1 acts as a reference current source (fixed bias)
- Q2 converts control voltage to exponential current
- The $I_S$ parameters are nearly identical → they cancel in the current ratio
- Result: $I_{out} / I_{ref} = e^{(\Delta V_{BE})/V_T}$

**Key point:** Without matched pairs or on-die transistors (like LM394), temperature drift causes unacceptable linearity errors.

## Circuit Architecture

### Block Diagram
```
Input CV (-5V to +5V)
    |
    ├─ Resistor divider (voltage conditioning)
    |
    ├─ Op-amp buffer (unity-gain follower)
    |  ↓
    Q2 base (exponential converter)
    |
Reference bias ─→ Q1 base (current reference)
    |
±12V supplies
    |
Collector loads (10kΩ)
    ↓
Output currents
```

### Component Selection

**Transistors:**
- Use matched NPN pair (e.g., 2N2222 from same package)
- Avoid single transistors or mismatched pairs
- For precision: consider on-die matched pairs (CA3086, LM394)

**Op-Amp:**
- Unity-gain follower configuration
- Purpose: Prevent transistor base impedance from loading the voltage divider
- In simulation, use ideal behavioral source: `B_buffer out 0 V=V(in)`
- In PCB: Use op-amp like TL071, LM358, or OPA2134 (rail-to-rail preferred)

**Resistors (Voltage Divider):**
- $R_{in}$ = 47kΩ (from control input)
- $R_{bias}$ = 1kΩ (from bias voltage)
- $R_{load}$ = 10kΩ (collector loads)
- Creates input slope: ~20.8 mV/V for octave scaling

**Bias Voltage Source:**
- $V_{BIAS}$ = 0.7V (targets mid-range base voltage)
- Adjust if different input range or doubling rate needed

**Power Supplies:**
- ±12V (Eurorack standard)
- Alternatively: ±15V for more headroom
- Reference bias: VBB = -11.4V (for ±12V) or -14.3V (for ±15V)

## Tuning for Octave Scaling

To achieve approximately 2× current doubling per volt of input CV:

**Math:**
The base voltage should swing ~18-21 mV/V input. This gives:

$$\text{Current ratio per volt} = e^{(20 \text{ mV/V} \times 1 \text{ V}) / 26 \text{ mV}} \approx 2.15×$$

**Resistor divider equation:**
$$V_{base}(V_{in}) = \frac{V_{in} \cdot R_{bias} + V_{BIAS} \cdot R_{in}}{R_{in} + R_{bias}}$$

**Derivation:**
- For -5V to +5V input with ±12V supplies:
- Desired base range: ~0.58V to 0.79V (208 mV swing)
- Using R_in=47kΩ, R_bias=1kΩ, V_BIAS=0.7V:
  - At -5V: $V_{base} \approx 0.581V$
  - At +5V: $V_{base} \approx 0.790V$
  - Slope: 20.8 mV/V ✓

**Fine-tuning:** Adjust R_in or R_bias to shift slope. For different ranges, scale both resistors proportionally.

## SPICE Netlist Template

```spice
* Exponential Converter - Octave Scaling

.title Exponential Converter with Matched BJT Pair

* Power supplies
VCC 1 0 DC 12V
VEE 2 0 DC -12V

* Input CV (-5V to +5V)
VIN 10 0 DC 0V

* Bias voltage
VBIAS 30 0 DC 0.7V

* Reference current bias
VBB 11 0 DC -11.4V
RBB 11 12 100k

* Input conditioning: voltage divider
R_in 10 32 47k
R_bias 30 32 1k

* Op-amp buffer (ideal behavioral source)
B_buffer 33 0 V=V(32)

* Q1: Reference current source
Q1 20 12 0 Q2N2222

* Q2: Exponential converter (control input)
Q2 21 33 0 Q2N2222

* Collector loads
RC1 1 20 10k
RC2 1 21 10k

* BJT model (2N2222 NPN)
.model Q2N2222 NPN(IS=14.34E-15 BF=255.9 NF=1.307 VAF=74.03
+ IKF=0.2847 ISE=14.34E-15 NE=1.307 BR=6.092 NR=1 VAR=24
+ RB=1 IRB=0.1 RBM=0.1 RE=0.1 RC=0.1 CJE=26.08E-12 VJE=0.75
+ MJE=0.33 CJC=7.306E-12 VJC=0.75 MJC=0.3 XCJC=1 CJS=0
+ VJS=0.75 MJS=0.5 XTB=1.5 EG=1.11 XTI=3 FC=0.5)

* DC sweep: -5V to +5V, 0.1V steps
.dc VIN -5 5 0.1

.save all
.end
```

## Simulation & Validation

### Key Measurements
Use DC sweep analysis. Calculate collector currents from voltages:
$$I_C = \frac{V_{CC} - V_C}{R_{load}}$$

**Expected results (±12V, 10kΩ loads):**
- Output current range: ~0.5 µA to ~200 µA
- Current doubling per volt: 1.75× to 2.2×
- Buffer effectiveness: base_div shows loading, cv_buffered shows isolation
- Slope: ~18-20 mV/V for octave scaling

### Simulation Analysis Workflow
**Best practice:** Create standalone Python scripts for analysis instead of inlining large code blocks.

**Workflow:**
1. Run SPICE simulation: `python scripts/run_spice.py exponential_converter.cir`
2. Generate plots: `python plot_exponential_results.py`
3. Adjust netlist if needed (e.g., R_in, bias voltage)
4. Repeat step 1-2 without rewriting analysis code

**Example script:** See `plot_exponential_results.py` in the simple_vpo folder for a full implementation including:
- CSV data loading and parsing
- Current calculations from collector voltages
- Doubling factor analysis
- Multi-panel visualization (buffer isolation, linear/log response, octave validation)
- Summary statistics output

### Creating Your Own Analysis Script
Use this template for new analysis scripts:
```python
#!/usr/bin/env python3
"""Analyze exponential converter simulation results."""

import csv
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

def find_latest_csv():
    """Find most recent sim_output_*.csv file."""
    files = sorted(Path('.').glob('sim_output_*.csv'), 
                   key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None

def load_data(csv_file):
    """Load SPICE CSV output."""
    with open(csv_file) as f:
        return list(csv.DictReader(f))

def main():
    csv_file = find_latest_csv()
    data = load_data(csv_file)
    
    # Extract and analyze data
    # ... your analysis code here ...
    
    # Save plots
    plt.savefig('output.png', dpi=150, bbox_inches='tight')
    print("Results saved")

if __name__ == '__main__':
    main()
```

**Why scripts over inline code:**
- Reusable across multiple iterations
- Easier to modify parameters (slopes, voltage ranges)
- Version-controllable and documentable
- Faster to execute after netlist changes
- Scalable to batch analysis of multiple circuits

## PCB Implementation Considerations

### Layout
1. **Transistor matching:** Place Q1 and Q2 adjacent, same orientation
2. **Thermal coupling:** Ensure same copper plane temperature
3. **Op-amp:** Place close to divider network
4. **Bias network:** Use precision resistors (1% or better)

### Component Notes
- **Op-amp rail-to-rail:** Simplifies biasing; use TL071, OPA2134, or LM358
- **Collector loads:** Can be active loads (current mirrors) for higher output impedance
- **Emitter resistors:** Add small resistor (~100Ω) to improve matching if needed

### Temperature Stability
- Budget ~0.3%/°C drift without compensation
- For audio VCOs, consider thermistor in bias network or on-die matched pairs

## Common Pitfalls

### Issue: Voltage divider loads
**Symptom:** Output nonlinearity, especially at negative inputs.
**Cause:** Transistor base impedance (~1-10kΩ) loads the divider.
**Solution:** Add op-amp buffer (this skill's approach).

### Issue: Limited exponential range
**Symptom:** Output saturates or cuts off over input range.
**Cause:** Base voltage swing too large or too small.
**Solution:** Adjust R_in, R_bias, V_BIAS per tuning section above.

### Issue: Temperature drift
**Symptom:** CV scale drifts with temperature.
**Cause:** Transistor IS varies ~0.7%/°C; $V_T$ varies ~-2mV/°C.
**Solution:** Use matched pair package or add compensation network.

### Issue: Asymmetry between positive/negative CV
**Symptom:** Doubling factor differs for ±CV.
**Cause:** Transistor saturation at extreme inputs.
**Solution:** Reduce input range or add emitter degeneration (trade-off: nonlinearity).

## Design Variants

### With Emitter Degeneration
Add small resistor (50-200Ω) to improve linearity at cost of reduced slope:
```spice
RE1 0_temp 0 100
RE2 0_temp 0 100
Q1 20 12 0_temp Q2N2222
Q2 21 33 0_temp Q2N2222
```

### With Active Loads
Replace 10kΩ resistors with current mirrors for higher output impedance and more constant current over load changes.

### Dual Output (Complementary)
Add Q3 (PNP) with inverse bias to produce complementary exponential current output.

## References
- **Shockley BJT Equation:** $I_C = I_S(e^{V_{BE}/V_T} - 1)$
- **Thermal voltage:** $V_T = k \cdot T / q \approx 26 \text{ mV @ 25°C}$
- **Matched pair transistors:** CA3086, LM394, Intersil ISL93xx series
- **Op-amps for audio:** TL071, OPA2134, NE5532
- **Eurorack VCO references:** Moog ladder filter exponential converter, ARP 2600 design

## Implementation Checklist
- [ ] Select matched transistor pair (same package or on-die)
- [ ] Design voltage divider for target octave scaling (~20 mV/V)
- [ ] Simulate with SPICE to verify doubling factor
- [ ] Add op-amp buffer to protect divider
- [ ] Validate output range over ±12V supplies
- [ ] Layout with thermal coupling of Q1/Q2
- [ ] Test frequency accuracy if used in VCO
- [ ] Temperature test across -10°C to +50°C if needed

---

**Last updated:** 2026-06-16  
**Created from:** Exponential converter design session (simple_vpo project)
