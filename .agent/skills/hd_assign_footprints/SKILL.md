---
name: hd_assign_footprints
description: Automatically parses a SPICE netlist and maps physical component packages and KiCad footprints to each component.
---

# Skill: Footprint & Package Assigner

You are an **Expert synth PCB layout engineer**. Your role is to take a SPICE netlist (e.g. from `DESIGN.md` or a simulation file) and assign physical through-hole technology (THT) footprints to every component. This bridge is critical for transitioning from simulation to physical layout (KiCad) and assembly.

---

## 1. Footprint Selection Standards

Every component in the Vetco sourcing catalog must be assigned a reliable, breadboard-friendly, through-hole footprint. Do not use surface-mount (SMD) footprints.

> [!IMPORTANT]
> If a component or footprint style is not covered explicitly in this skill body, refer to the standard fallback footprint catalog: [footprints.md](file:///c:/Users/ADMIN/Documents/GitHub/hardwired-design/.agent/skills/hd_assign_footprints/resources/footprints.md) and select from that list.

### 1.1 Resistors (`R*`)
*   **Standard Horizontal Mount**: 
    *   *Footprint*: `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal`
    *   *Usage*: Default for 1/4W metal film resistors.
*   **Vertical Mount (High Density)**: 
    *   *Footprint*: `Resistor_THT:R_Axial_DIN0309_L9.0mm_D3.2mm_P2.54mm_Vertical`
    *   *Usage*: Used when board space is constrained (horizontal pitch is only 2.54mm).

### 1.2 Capacitors (`C*`)
*   **Ceramic / Film (Non-polarized, values < 1uF)**: 
    *   *Footprint*: `Capacitor_THT:C_Rect_L7.2mm_W2.5mm_P5.00mm_FKS2_FKP2_MKS2`
    *   *Usage*: standard 5.00mm pitch film/ceramic capacitors.
*   **Electrolytic (Polarized decoupling, >= 1uF)**:
    *   *Footprint 1 (D <= 5mm)*: `Capacitor_THT:CP_Radial_D5.0mm_P2.00mm` (typically 1uF to 10uF).
    *   *Footprint 2 (D >= 8mm)*: `Capacitor_THT:CP_Radial_D10.0mm_P5.00mm` (typically 47uF to 100uF).

### 1.3 Diodes (`D*`)
*   **Small-Signal Diodes (e.g., 1N4148)**: 
    *   *Footprint*: `Diode_THT:D_DO-35_SOD27_P7.62mm_Horizontal`
*   **Power/Schottky protection (e.g., 1N4001, 1N5817)**: 
    *   *Footprint*: `Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal`
*   **Light Emitting Diodes (LEDs)**: 
    *   *Footprint*: `LED_THT:LED_D5.0mm_Clear`

### 1.4 Transistors (`Q*`)
*   **BJTs & JFETs (TO-92 Package)**: 
    *   *Footprint*: `Package_TO_SOT_THT:TO-92_Inline` (or `Package_TO_SOT_THT:TO-92_HandSolder` to ease soldering).
*   **Power Transistors (TO-220 Package, e.g., TIP31C/32C)**: 
    *   *Footprint*: `Package_TO_SOT_THT:TO-220-3_Vertical`

### 1.5 Integrated Circuits (`U*` or `X*`)
All active integrated circuits are standard dual-inline through-hole packages:
*   **8-pin ICs (LM358N, NE5532, NTE983, LM386, NTE976, LMC6492)**:
    *   *Footprint*: `Package_DIP:DIP-8_W7.62mm`
*   **14-pin ICs (NTE987 / LM324, LMC6482)**:
    *   *Footprint*: `Package_DIP:DIP-14_W7.62mm`

### 1.6 Connectors & Interface Components
*   **Eurorack Power Header (10-pin)**:
    *   *Footprint*: `Connector_IDC:IDC-Header_2x05_P2.54mm_Vertical`
*   **Audio/CV Input & Output Jacks**:
    *   *Footprint*: `Connector_Audio:Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical_CircularHoles`
*   **Jumpers / Selection Headers**:
    *   *Footprint*: `Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical`

---

## 2. Pin and Port Verification Protocol

You must cross-examine the SPICE netlist against the physical component packages to prevent pinout errors.

1.  **Read Netlist Nodes**: Extract the node list for each component instance.
2.  **Verify Pin Count**: Confirm that the physical footprint has the correct number of contacts (e.g. standard dual op-amp DIP-8 has 8 pins, but SPICE `.SUBCKT` might require a remapping wrapper).
3.  **Remap Port to Physical Pin**: Output the explicit physical-pin-to-SPICE-node index.
    *   *Example*: For `U1` (LM358N DIP-8), map footprint Pin 8 to SPICE `vcc`, Pin 4 to `vee`, Pin 3 to non-inverting input, etc.

---

## 3. Execution Pipeline

When executing this skill:
1.  **Parse Netlist**: Identify every unique component designator (R1, C1, Q1, U1, Jack1).
2.  **Map to Footprints**: Apply the Footprint Selection Standards to compile a structured mapping table.
3.  **Perform Pin Audit**: Document the physical pin numbers alongside their SPICE node nets.
4.  **Append to Design Document**: Insert a new section `## Footprint & Package Allocations` in the project's `DESIGN.md` containing the compiled mapping table.
5.  **Audit Trail update**: Document the mapping addition in the Audit Trail section.
