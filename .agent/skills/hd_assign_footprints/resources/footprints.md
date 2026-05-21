# Standard Eurorack Footprint Reference Catalog

This resource contains a curated list of approved footprints. When mapping a netlist to physical packages, prioritize these footprints as standard fallbacks if a component is not covered explicitly in the main skill instructions.

---

## 1. Approved Footprints Catalog

### 1.1 Polarized Radial Capacitor
*   **Footprint**: `Capacitor_THT:CP_Radial_D10.0mm_P5.00mm`
*   **Description**: Through-hole radial electrolytic capacitor, 10.0mm diameter, 5.00mm pin pitch.
*   **Intended Use**: Primary power rail bulk decoupling (typically 47µF, 100µF, or 220µF electrolytic capacitors).

### 1.2 Indicator LED
*   **Footprint**: `LED_THT:LED_D5.0mm_Clear`
*   **Description**: Through-hole 5.0mm diameter LED, clear package style.
*   **Intended Use**: Front panel indicator lights, trigger/gate monitors, and LFO rate indicators.

### 1.3 Power Supply Input Header
*   **Footprint**: `Connector_IDC:IDC-Header_2x05_P2.54mm_Vertical`
*   **Description**: Dual-row 10-pin vertical shrouded/unshrouded header, 2.54mm pitch.
*   **Intended Use**: Standard 10-pin Eurorack power supply bus cable input.

### 1.4 Axial Metal-Film Resistor
*   **Footprint**: `Resistor_THT:R_Axial_DIN0309_L9.0mm_D3.2mm_P2.54mm_Vertical`
*   **Description**: Through-hole axial resistor, DIN0309 body size, mounted vertically with 2.54mm pitch.
*   **Intended Use**: Standard signal-path and feedback-loop 1/4W resistors in dense layouts.

### 1.5 Audio/CV Jack Interface
*   **Footprint**: `Connector_Audio:Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical_CircularHoles`
*   **Description**: Mono 3.5mm switched vertical jack with circular PCB routing holes (QingPu manufacturer).
*   **Intended Use**: Panel inputs (1V/Oct, Trigger, Source) and outputs (Audio, CV).

### 1.6 Configuration Pin Header
*   **Footprint**: `Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical`
*   **Description**: Single-row 3-pin vertical header, 2.54mm pin pitch.
*   **Intended Use**: Jumpers for range/mode selection, hardware bypass routing, or three-terminal trimming/potentiometer interfaces.

### 1.7 Integrated Circuit Package
*   **Footprint**: `Package_DIP:DIP-8_W7.62mm`
*   **Description**: Through-hole 8-pin Dual In-line Package (DIP), 7.62mm width between rows.
*   **Intended Use**: Dual operational amplifiers (LM358N, NE5532, NTE983, LMC6492), single high-impedance op-amps (NTE976), and audio power amplifiers (LM386).
