# Module Design: Simple Transistor Sawtooth Core (V-to-I Stage)

This is the first phase of the **Simple Transistor Sawtooth Oscillator** module. It implements a precision Voltage-to-Current (V-to-I) converter (Voltage-Controlled Current Source / VCCS).

## 1. Theory of Operation

The circuit converts a control voltage input ($V_{in}$) linearly into an output sink current ($I_{out}$) using an active feedback loop consisting of an operational amplifier and a Bipolar Junction Transistor (BJT).

```
          +12V
            |
         [R_LOAD] (10 ohms)
            |
         v_coll
          /
  +-----+|  Q1 (BC337 NPN)
  |      \>
  |        |
  |      v_emit <----------+
  |        |               |
[LM358]----+             [R_SET] (50 ohms)
  |                        |
 vin_ctrl                 GND
```

### feedback Loop Mechanics
1. **Input Stage**: The control voltage $V_{in}$ (from $0\text{V}$ to $5\text{V}$) is applied directly to the non-inverting input ($IN+$) of the op-amp section (`LM358N_SEC`).
2. **Error Amplification**: The op-amp output drives the base of the NPN transistor `BC337`.
3. **Negative Feedback**: The emitter of `BC337` is connected back to the inverting input ($IN-$) of the op-amp, closing the feedback loop. This forces the emitter voltage $V_{emit}$ to match $V_{in}$ exactly:
   $$V_{emit} = V_{in}$$
4. **Current Generation**: Because $V_{emit}$ is clamped to $V_{in}$, the current through the emitter resistor $R_{set}$ is:
   $$I_e = \frac{V_{emit}}{R_{set}} = \frac{V_{in}}{50\Omega}$$
5. **Output Sink Current**: The collector current $I_c$ (sunk from the load at the collector) is:
   $$I_{out} = I_c = \alpha \cdot I_e \approx I_e$$
   With $\beta \approx 400$ for the `BC337`, the current gain $\alpha = \frac{\beta}{\beta + 1} \approx 0.9975$, meaning the output current is $99.75\%$ of the theoretical current, providing outstanding linearity.

For $V_{in} = 5\text{V}$, the output current is:
$$I_{out} = \frac{5\text{V}}{50\Omega} = 100\text{mA}$$

---

## 2. Technical Specifications

*   **Input Control Voltage**: $0\text{V}$ to $5\text{V}$ (linear scale)
*   **Output Current Range**: $0$ to $100\text{mA}$ (sinking)
*   **Power Rails**: $\pm12\text{V}$ DC and $\text{GND}$
*   **Linearity Deviation**: $< 0.3\%$ over full scale
*   **Output Node Voltage Range**: $+1\text{V}$ to $+12\text{V}$ (dependent on load impedance)

---

## 3. Sourcing Audit (BOM)

The components listed below are selected from the Vetco Sourcing Library for maximum breadboard compatibility, DIP footprints, and robust operation on $\pm12\text{V}$ rails.

| Component | Part Number | Quantity | Unit Cost | Purpose |
| :--- | :--- | :---: | :--- | :--- |
| **Dual Op-Amp** | LM358N | 1 | $2.06 | Active feedback and error amplifier |
| **NPN Transistor** | BC337 | 1 | $0.25 | Active current pass BJT (sinking current) |
| **PNP Transistor** | BC327 | 1 | $0.25 | Optional sourcing current pass BJT |
| **Emitter Resistor** | 50 Ohm, 1W | 1 | $0.45 | Current set resistor $R_{set}$ (metal oxide power resistor) |
| **Load Resistor** | 10 Ohm, 1/4W | 1 | $0.15 | Dummy collector load for simulation verification |

**Estimated Component Cost: ~$3.16**

---

## 4. SPICE Simulation

The simulation netlist is defined in the companion netlist file:
👉 [simple_transistor_saw.net](file:///c:/Users/ADMIN/Documents/GitHub/hardwired-design/hardwired/oscilator/simple_transistor_saw/simple_transistor_saw.net)

It sweeps $V_{in}$ from $0\text{V}$ to $5\text{V}$ and runs a DC operating point sweep to measure:
*   The voltage tracking accuracy at the emitter node: $V(v\_emit) \text{ vs } V(vin\_ctrl)$
*   The output collector sink current: $I(R\_SET)$ or $I(R\_LOAD)$
*   The base control voltage: $V(v\_base)$
*   Transistor power dissipation: $I_c \cdot (V_c - V_e)$
