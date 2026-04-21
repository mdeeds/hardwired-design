# Various Designs for Transistor Antilog

## 1. Core Principle
The antilog (exponential) function in analog circuitry relies on the fundamental Shockley diode equation for a Bipolar Junction Transistor (BJT):

$$I_C = I_S \cdot (e^{\frac{V_{BE}}{V_T}} - 1) \approx I_S \cdot e^{\frac{V_{BE}}{V_T}}$$

Where:
- $V_T$ is the thermal voltage ($\approx 26mV$ at room temperature).
- $I_S$ is the saturation current (highly temperature dependent).

## 2. Basic Op-Amp Antilog Configuration
In this design, the transistor is placed in the feedback path of an Op-Amp, or the input is fed into the base to control collector current.

### 2.1 Basic Uncompensated Circuit
- **Input:** Voltage $V_{in}$ to the base of a BJT.
- **Load Resistor ($R_L$):** Converts the collector current $I_C$ into a measurable voltage drop.
- **Output:** $V_{out} = -R_L \cdot I_C = -R_L \cdot I_S \cdot e^{\frac{V_{in}}{V_T}}$ (when used with an inverting op-amp stage).
- **Limitation:** Extremely sensitive to temperature changes due to $I_S$ and $V_T$.

## 3. Precision Temperature-Compensated Design
To create a stable synthesizer or signal processor, temperature compensation is mandatory.

### 3.1 The Differential Pair (Matched Pair)
Using a matched transistor pair (e.g., LM394 or THAT300) allows the $I_S$ terms to cancel out when the ratio of collector currents is taken.

### 3.2 Tempco Resistor Feedback
Utilizing a PTAT (Proportional To Absolute Temperature) compensation resistor (typically +3300 ppm/°C or +3500 ppm/°C) in the input attenuator helps cancel the $V_T$ drift.

## 4. Implementation Strategies

### 4.1 Log-Antilog Pair
Used for multiplication/division of signals.
1. Convert $V_1$ and $V_2$ to log form.
2. Sum the voltages (Addition in log domain = Multiplication in linear domain).
3. Pass the result through an Antilog stage.

### 4.2 Current Output vs. Voltage Output
- **Current Output:** Ideal for OTA-based filters (Operational Transconductance Amplifiers).
- **Voltage Output:** Requires an I-to-V converter stage (Transimpedance amplifier).

## 5. Design Considerations

| Feature | Requirement | Reason |
| :--- | :--- | :--- |
| **Matching** | High | Transistors must be at the same temperature and have identical $I_S$. |
| **Op-Amp Bias** | Low | Input bias current must be significantly lower than the minimum $I_C$. |
| **Stability** | High | High-gain exponential feedback can cause oscillation; compensation caps required. |

## 6. Recommended Components
- **Matched Pairs:** DMMT3904, BC847BS, or specialized ICs like the THAT340.
- **Op-Amps:** Precision, low-offset parts like the OPA2172 or TL072H (for high impedance inputs).
- **Tempcos:** 1k Ohm 3500ppm wire-wound or metal film resistors.

## 7. Mathematical Model for SPICE
```spice
* Basic Antilog Test Bench
Q1 C B E 0 Q2N3904
R1 IN B 10k
RL C VCC 1k    ; Load resistor to measure current as a voltage drop (V = Ic * RL)
Rf C OUT 10k   ; Feedback resistor for transimpedance configuration
Vcc VCC 0 15
Vee VEE 0 -15
* Note: Requires thermal coupling in simulation
```
