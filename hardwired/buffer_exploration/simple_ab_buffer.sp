* Simple transistor class-AB unity buffer
* Rails: +/-12V
* Sweep input from -10V to +10V, 1V step
* Error metric: V(out)-V(in)
* Additional tests:
*   1) Load test: VIN=0V, sweep ILOAD -20mA to +20mA
*   2) Current direction switching: -20mA (0-10us), +20mA (10us-20us)
* Baselines:
*   1) AB emitter follower
*   2) LM741 follower (from vetco_eurorack.lib)
* Comparison option:
*   Complementary Sziklai (CFP) output stage

.LIB "../../models/vetco_eurorack.lib"

* Separate supplies per stage so quiescent and dissipation metrics are stage-local.
VCC_AB VCC_AB 0 12
VEE_AB VEE_AB 0 -12
VCC_SZ VCC_SZ 0 12
VEE_SZ VEE_SZ 0 -12
VCC_LM VCC_LM 0 12
VEE_LM VEE_LM 0 -12

VIN IN  0 0

* AB stage: bias network using diode-connected transistors referenced to input
RBP_AB VCC_AB B1_AB 10k
RBN_AB B2_AB  VEE_AB 10k
QBIASP_AB B1_AB B1_AB IN NPNMOD
QBIASN_AB IN B2_AB B2_AB PNPMOD

* Complementary emitter followers (class-AB output stage)
* 0 V sources let us read collector currents for transistor dissipation estimates.
VSEN_AB_N VCC_AB VCC_AB_QN 0
VSEN_AB_P VEE_AB VEE_AB_QP 0
QOUTN VCC_AB_QN B1_AB OUT_AB NPNMOD
QOUTP VEE_AB_QP B2_AB OUT_AB PNPMOD

* Light load
RLOAD_AB OUT_AB 0 10k

* Complementary Sziklai (CFP) stage for comparison
RBUP_SZ VCC_SZ BSN 4.7k
RBDN_SZ BSP VEE_SZ 4.7k
VSEN_SZ_N VCC_SZ VCC_SZ_QN 0
VSEN_SZ_P VEE_SZ VEE_SZ_QP 0
QSN_OUT VCC_SZ_QN BSN OUT_SZ NPNMOD
QSN_DRV BSN IN OUT_SZ PNPMOD
QSP_OUT VEE_SZ_QP BSP OUT_SZ PNPMOD
QSP_DRV BSP IN OUT_SZ NPNMOD
RLOAD_SZ OUT_SZ 0 10k

* LM741 baseline follower
RFB_741 OUT_741 NINV_741 10k
XU741 IN NINV_741 VCC_LM VEE_LM OUT_741 LM741N
RLOAD_741 OUT_741 0 10k

* Load-current command source (volts interpreted as amps via 1 A/V VCCS).
* Positive current is defined from output to 0 (sinking current).
VLOAD NLOAD 0 DC 0 PWL(0 -20m 10u -20m 10.001u 20m 20u 20m)
GLOAD_AB OUT_AB 0 NLOAD 0 1
GLOAD_SZ OUT_SZ 0 NLOAD 0 1
GLOAD_741 OUT_741 0 NLOAD 0 1

.model NPNMOD NPN (IS=1e-14 BF=150 VAF=100)
.model PNPMOD PNP (IS=1e-14 BF=150 VAF=100)

.control
* Test 0: Transfer/error test (VIN sweep, load current at 0A)
alter VLOAD = 0
dc VIN -10 10 1
plot v(out_ab)-v(in) v(out_741)-v(in) v(out_sz)-v(in) vs v(in) title 'Error vs Input: AB vs LM741 vs Sziklai'

* Test 1: Load test at VIN=0V, sweep load current -20mA..+20mA
alter VIN = 0
dc VLOAD -0.02 0.02 0.002
plot v(out_ab) v(out_741) v(out_sz) title 'Output Voltage vs Load Current (VIN=0V): AB vs LM741 vs Sziklai'

* Test 2: Current-direction switching transient (-10mA then +10mA)
alter VIN = 0
tran 20n 20u
plot v(out_ab) v(out_741) v(out_sz) vs time title 'Output Voltage vs Time (Current Direction Switch): AB vs LM741 vs Sziklai'
.endc

.end
