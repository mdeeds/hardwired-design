* Sawtooth Oscillator Core (External Antilog Drive)

* --- Power Rails ---
VCC vcc 0 15V
VEE vee 0 -15V

* --- 1. Linear Control Input ---
* Buffers external CV for injection into integrator
* U1: NTE987 Quad Op-Amp (Amp 1 used)
R1 lin_fm_in lin_sum 100k
R2 lin_out lin_sum 100k
U1 0 lin_sum lin_out vcc vee
* Pinout: in+ in- out v+ v-

* --- 2. Sawtooth Integrator ---
* Converts buffered control voltage into a rising ramp
* U2: NTE987 Quad Op-Amp (Amp 2 used)
R3 lin_out int_sum 100k
C1 core_saw int_sum 1n
U2 0 int_sum core_saw vcc vee

* --- 3. Reset Comparator ---
* Detects when ramp reaches +5V threshold
R4 vcc v_ref 10k
R5 v_ref 0 5k
* U3: NTE987 Quad Op-Amp (Amp 3 used)
* Pinout: in+ in- out v+ v-
U3 core_saw v_ref reset_pulse vcc vee
R6 reset_pulse core_saw 100k

* --- 4. Reset Switch ---
* Discharges C1 when reset_pulse goes high
* Note: Switch is across the capacitor (int_sum to core_saw)
* This avoids shorting the op-amp output directly to ground.
M1 core_saw reset_pulse int_sum 0 NMOS_SW
.model NMOS_SW NMOS(Vto=2V Kp=20u)

* --- 5. Output Buffer & Scaler ---
* U4: NTE987 Quad Op-Amp (Amp 4 used)
* Scales 0-5V ramp to 0-10V output
R7 saw_out_fb 0 10k
R8 saw_out saw_out_fb 10k
U4 core_saw saw_out_fb saw_out vcc vee
* Pinout: in+ in- out v+ v-

* --- Simulation Parameters ---
.tran 1u 10m
.end