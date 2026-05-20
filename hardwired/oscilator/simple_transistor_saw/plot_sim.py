import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Set paths
base_dir = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.join(base_dir, "sim_output_0_Precision_Sawtooth_Oscillator_Core_with_Active_BJT_Reset.csv")
output_img = os.path.join(base_dir, "oscillation_waveforms.png")

if not os.path.exists(csv_path):
    print(f"Error: Simulation CSV file not found at {csv_path}")
    exit(1)

# Load data
print("Loading simulation CSV data...")
df = pd.read_csv(csv_path)

# Extract signals
t_ms = df['time'].values * 1000  # Convert to ms
v_ramp = df['v_ramp'].values
v_comp = df['v_comp_out'].values
v_th = df['v_comp_in+'].values

# Calculate stats
peaks = []
troughs = []
window = 15

for i in range(window, len(v_ramp) - window):
    val = v_ramp[i]
    if all(v_ramp[j] <= val for j in range(i - window, i + window + 1)):
        peaks.append((t_ms[i], val))
    elif all(v_ramp[j] >= val for j in range(i - window, i + window + 1)):
        troughs.append((t_ms[i], val))

# Filter duplicates/noise (at least 0.1ms apart)
clean_peaks = []
for p in peaks:
    if not clean_peaks or (p[0] - clean_peaks[-1][0] > 0.1):
        clean_peaks.append(p)

clean_troughs = []
for tr in troughs:
    if not clean_troughs or (tr[0] - clean_troughs[-1][0] > 0.1):
        clean_troughs.append(tr)

avg_peak = np.mean([p[1] for p in clean_peaks]) if clean_peaks else np.nan
avg_trough = np.mean([tr[1] for tr in clean_troughs]) if clean_troughs else np.nan

print("\n--- Simulation Analysis ---")
print(f"Total simulated time: {t_ms[-1]:.2f} ms")
print(f"Average Peak Voltage (High Threshold):  {avg_peak:.4f} V")
print(f"Average Trough Voltage (Low Threshold): {avg_trough:.4f} V")
print(f"Peak-to-Peak Voltage Range:             {avg_peak - avg_trough:.4f} V")

if len(clean_peaks) > 1:
    periods = [clean_peaks[i][0] - clean_peaks[i-1][0] for i in range(1, len(clean_peaks))]
    avg_period = np.mean(periods)
    avg_freq = 1000.0 / avg_period
    print(f"Average Period:                         {avg_period:.4f} ms")
    print(f"Oscillation Frequency:                  {avg_freq:.2f} Hz")

# --- Beautiful Plotting with Matplotlib ---
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
fig, ax1 = plt.subplots(figsize=(11, 6), dpi=150)

# Set dark background theme aesthetics manually for premium look
fig.patch.set_facecolor('#1a1a24')
ax1.set_facecolor('#14141c')
ax1.grid(color='#2d2d3a', linestyle='--', linewidth=0.5)

# Plot ramp and threshold
line_ramp, = ax1.plot(t_ms, v_ramp, color='#00ffcc', linewidth=2, label='Capacitor Voltage (v_ramp)')
line_th, = ax1.plot(t_ms, v_th, color='#ff007f', linewidth=1.5, linestyle=':', label='Threshold (v_comp_in+)')

ax1.set_xlabel('Time (ms)', color='#a0a0c0', fontsize=11, fontweight='bold')
ax1.set_ylabel('Capacitor / Threshold Voltage (V)', color='#00ffcc', fontsize=11, fontweight='bold')
ax1.tick_params(colors='#a0a0c0')

# Create a second y-axis for comparator output
ax2 = ax1.twinx()
ax2.grid(False) # Turn off grid for the secondary axis
line_comp, = ax2.plot(t_ms, v_comp, color='#ffd700', linewidth=1.2, alpha=0.8, linestyle='--', label='Comparator Output (v_comp_out)')
ax2.set_ylabel('Comparator Output (V)', color='#ffd700', fontsize=11, fontweight='bold')
ax2.tick_params(colors='#a0a0c0')

# Combine legends
lines = [line_ramp, line_th, line_comp]
labels = [l.get_label() for l in lines]
leg = ax1.legend(lines, labels, loc='upper right', facecolor='#1e1e28', edgecolor='#2d2d3a')
for text in leg.get_texts():
    text.set_color('#e0e0ed')

# Zoom in on first few cycles for high detail
ax1.set_xlim(0, 3.0)

# Add title and annotations
plt.title('Precision Sawtooth Core Oscillation Waveforms', color='#ffffff', fontsize=14, fontweight='bold', pad=15)

# Annotation for levels
ax1.axhline(y=avg_peak, color='#00ffcc', linestyle='--', alpha=0.3)
ax1.axhline(y=avg_trough, color='#00ffcc', linestyle='--', alpha=0.3)

ax1.text(0.1, avg_peak + 0.3, f'Peak: {avg_peak:.2f}V', color='#00ffcc', fontweight='bold', fontsize=9, bbox=dict(facecolor='#14141c', alpha=0.8, boxstyle='round,pad=0.3'))
ax1.text(0.1, avg_trough - 0.7, f'Trough: {avg_trough:.2f}V', color='#00ffcc', fontweight='bold', fontsize=9, bbox=dict(facecolor='#14141c', alpha=0.8, boxstyle='round,pad=0.3'))

# Add explanations of dynamic threshold pull-down
explanation_text = (
    "Schmitt Trigger targeted +/-6V.\n"
    "• Negative threshold reaches -5.96V.\n"
    "• Positive threshold is pulled down to\n"
    "  ~4.45V due to base loading of Q_RESET\n"
    "  on the comparator open-collector output."
)
ax1.text(1.5, -2.5, explanation_text, color='#e0e0ed', fontsize=9.5,
         bbox=dict(facecolor='#1e1e28', edgecolor='#ff007f', alpha=0.8, boxstyle='round,pad=0.5'))

plt.tight_layout()
plt.savefig(output_img, facecolor=fig.get_facecolor(), edgecolor='none')
print(f"Beautiful waveform visualization saved to: {output_img}")
