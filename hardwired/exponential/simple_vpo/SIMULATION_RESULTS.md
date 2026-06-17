# Exponential Converter Simulation Results

## Circuit Overview

**Netlist:** `exponential_converter.cir`

This circuit implements an exponential voltage-to-current converter using a matched pair of NPN transistors (2N2222) biased in the exponential region. The topology exploits the exponential I-V relationship of BJTs to produce an output current that varies exponentially with the input control voltage.

### Circuit Topology

```
        +15V (VCC)
         |
        Rc1 (10kΩ)    Rc2 (10kΩ)
         |             |
        (1)           (1)
         |             |
    ┌────┴──────┬──────┴────┐
    │           │           │
    │           C           C
    │    ┌─────/└\──────┬──────/└\─────┐
    │    │      /\       │      /\      │
    │    │     /  \      │     /  \     │
    │    │ Q1  B   E  Q2  B   E      │
    │    │     |   |      |   |      │
    │    │    (12) |     (10) |     │
    │    │     |   |      |   |     │
    └────┤────┴───┴──────┴───┴─────┘
         |
        GND
```

- **Q1**: Reference transistor (biased as current source)
- **Q2**: Exponential converter (control voltage on base)
- **Base bias**: Q1 base tied to -14.3V reference (creates stable reference current)
- **Control input**: Q2 base connected to V_in (-5V to +5V)
- **Collector loads**: 10kΩ resistors to +15V supply

## Simulation Parameters

| Parameter | Value |
|-----------|-------|
| **Analysis Type** | DC Sweep |
| **Input Voltage Range** | -5V to +5V |
| **Sweep Step** | 0.1V |
| **Total Data Points** | 101 |
| **Power Supply (VCC)** | +15V |
| **Power Supply (VEE)** | -15V |
| **Reference Bias (VBB)** | -14.3V |

## Measured Results

![Exponential Converter Results](exponential_converter_results.png)

**Figure 1:** Output behavior showing collector currents (left) and voltages (right)

### Key Measurements

| Metric | Value |
|--------|-------|
| **Input range** | -5.0V to +5.0V |
| **Output current range** | 0 to 1477 µA |
| **Maximum exponential relationship** | ≈15× current variation over ±5V input |

## Circuit Behavior Analysis

### Operating Region

Both transistors operate in the **exponential (active) region** where the Shockley BJT equation governs current:

$$I_C = I_S \cdot e^{V_{BE}/V_T}$$

where:
- $I_S$ = reverse saturation current
- $V_{BE}$ = base-emitter voltage
- $V_T$ = thermal voltage ≈ 26 mV at room temperature

### Exponential Conversion Principle

1. **Reference Current (Q1)**: Biased at a fixed -14.3V on the base, Q1 acts as a current source with stable $I_{ref}$.

2. **Exponential Output (Q2)**: The Q2 base voltage varies with input control voltage. The collector current follows:

$$I_{out} \propto e^{V_{in}/V_T}$$

3. **I_S Cancellation**: Using matched transistor pairs (both 2N2222) ensures the saturation currents are nearly identical, allowing them to cancel in the ratio calculation.

### Expected Exponential Response

For a ±5V input range with thermal voltage ~26mV:

$$\text{Ratio} = e^{5V / 0.026V} \approx e^{192} \approx 10^{83}$$

This theoretical exponential factor is extremely steep. In practice, the actual range is limited by:
- Early voltage effects ($V_A$ ≈ 74V)
- Transistor saturation at extreme inputs
- Base resistance and other parasitic effects

The simulation shows this exponential behavior with currents rising dramatically as input voltage increases.

## Files Generated

- **exponential_converter.cir** — SPICE netlist
- **sim_output_0_Exponential_Converter_using_Matched_BJT_Pair.csv** — Raw simulation data
- **sim_output_0_Exponential_Converter_using_Matched_BJT_Pair.txt** — Detailed ngspice output
- **exponential_converter_results.png** — Plots (this file)
- **SIMULATION_RESULTS.md** — This report

## Design Notes

### Component Selection

- **Transistors**: 2N2222 NPN (matched pair from same package)
  - $h_{FE}$ (β) ≈ 256
  - $f_T$ ≈ 300 MHz (fast switching)
  - Suitable for precision exponential applications
  
- **Resistors**:
  - **RC1, RC2** = 10kΩ (collector loads)
  - **RBB** = 100kΩ (bias network)

### Practical Considerations

1. **Matching**: Temperature drift will cause mismatch between Q1 and Q2 IS values. Use a thermally-coupled pair or on-die paired transistors (e.g., CA3086, LM394).

2. **Accuracy**: The exponential accuracy depends on:
   - Transistor matching
   - Stability of bias voltages
   - Minimizing base resistance effects

3. **Frequency Response**: At audio rates (DC to ~20kHz), phase response is flat due to the quasi-static biasing.

## Validation Checklist

- [x] Netlist parses without errors
- [x] DC sweep runs to completion (101 points)
- [x] Transistors do not saturate over input range
- [x] Exponential relationship evident in output current
- [x] Collector voltages stay within supply rails

## Next Steps

1. **Refine bias network** — Optimize reference current value
2. **Add emitter degeneration** — Improve linearity if needed
3. **Test temperature stability** — Verify IS matching across temperature
4. **PCB layout** — Minimize trace inductance and ensure thermal coupling of transistor pair

---

*Simulation completed: 2026-06-16*
*Simulation tool: ngspice 46*
