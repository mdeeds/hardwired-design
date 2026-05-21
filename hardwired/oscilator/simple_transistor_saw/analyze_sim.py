import csv

csv_path = r"C:\Users\ADMIN\Documents\GitHub\hardwired-design\hardwired\oscilator\simple_transistor_saw\sim_output_0_Precision_Sawtooth_Oscillator_Core_with_Active_BJT_Reset.csv"

# Load the CSV
with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    headers = next(reader)
    
    time_idx = headers.index('time')
    v_ramp_idx = headers.index('v_ramp')
    v_comp_idx = headers.index('v_comp_out')
    
    times = []
    v_ramps = []
    v_comps = []
    
    for row in reader:
        if not row:
            continue
        times.append(float(row[time_idx]))
        v_ramps.append(float(row[v_ramp_idx]))
        v_comps.append(float(row[v_comp_idx]))

print(f"Total Rows: {len(v_ramps)}")
print(f"v_ramp Min: {min(v_ramps):.3f} V")
print(f"v_ramp Max: {max(v_ramps):.3f} V")

# Find peaks and troughs without tight voltage boundaries to see what bounds it reaches
peaks = []
troughs = []

for i in range(1, len(v_ramps) - 1):
    if v_ramps[i] > v_ramps[i-1] and v_ramps[i] > v_ramps[i+1]:
        peaks.append((times[i], v_ramps[i], i))
    elif v_ramps[i] < v_ramps[i-1] and v_ramps[i] < v_ramps[i+1]:
        troughs.append((times[i], v_ramps[i], i))

print(f"Unbounded Peaks: {len(peaks)}")
print(f"Unbounded Troughs: {len(troughs)}")

if peaks:
    print(f"First 5 Peak Voltages: {[p[1] for p in peaks[:5]]}")
if troughs:
    print(f"First 5 Trough Voltages: {[tr[1] for tr in troughs[:5]]}")
