#!/usr/bin/env python3
"""
Generate plots from exponential converter SPICE simulation results.

Usage:
    python plot_exponential_results.py [csv_file]

If no CSV file specified, looks for the most recent sim_output_*.csv file.
"""

import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def find_latest_csv():
    """Find the most recent sim_output CSV file in current directory."""
    csv_files = sorted(Path('.').glob('sim_output_*.csv'), key=lambda p: p.stat().st_mtime)
    if csv_files:
        return csv_files[-1]
    raise FileNotFoundError("No sim_output_*.csv files found in current directory")


def load_simulation_data(csv_path):
    """Load SPICE CSV output and extract relevant data."""
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        data = list(reader)

    v_in = np.array([float(row['v-sweep']) for row in data])
    v_base_div = np.array([float(row['base_div']) for row in data])
    v_cv_buffered = np.array([float(row['cv_buffered']) for row in data])
    v_c_ref = np.array([float(row['c_ref']) for row in data])
    v_c_exp = np.array([float(row['c_exp']) for row in data])

    return v_in, v_base_div, v_cv_buffered, v_c_ref, v_c_exp


def calculate_collector_currents(v_c_ref, v_c_exp, vcc=12.0, r_load=10000.0):
    """Calculate collector currents from voltages."""
    i_ref = (vcc - v_c_ref) / r_load * 1e6  # in microamps
    i_out = (vcc - v_c_exp) / r_load * 1e6  # in microamps
    return i_ref, i_out


def calculate_doubling_factors(v_in, i_out, step_size=10):
    """Calculate current doubling factor per 1V increment."""
    doubling_factors = []
    test_voltages = np.arange(-4.5, 4.5, 0.5)

    for v in test_voltages:
        idx = np.argmin(np.abs(v_in - v))
        if idx + step_size < len(i_out):
            i_at_v = i_out[idx]
            i_at_v_plus_1 = i_out[idx + step_size]
            if i_at_v > 0:
                factor = i_at_v_plus_1 / i_at_v
                doubling_factors.append(factor)

    return doubling_factors, test_voltages[: len(doubling_factors)]


def create_plots(v_in, v_base_div, v_cv_buffered, v_c_ref, v_c_exp, i_ref, i_out):
    """Create the 4-panel plot."""
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))

    # Plot 1: Buffer isolation effect
    ax1.plot(v_in, v_base_div, 'r--', linewidth=2, label='base_div - Before buffer (loaded)', alpha=0.7)
    ax1.plot(v_in, v_cv_buffered, 'g-', linewidth=2.5, label='cv_buffered - After buffer (isolated)')
    ax1.set_xlabel('Control Input (V)', fontsize=11)
    ax1.set_ylabel('Base Voltage (V)', fontsize=11)
    ax1.set_title('Op-Amp Buffer Isolation Effect', fontsize=12)
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=10)

    # Calculate and display slope
    slope = (v_cv_buffered[-1] - v_cv_buffered[0]) / (v_in[-1] - v_in[0]) * 1000  # in mV/V
    ax1.text(0.5, 0.95, f'Slope: {slope:.1f} mV/V (≈ octave scaling)',
             transform=ax1.transAxes, fontsize=10, bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

    # Plot 2: Exponential current response (linear scale)
    ax2.plot(v_in, i_out, 'b-', linewidth=2.5, label='I_out')
    ax2.plot(v_in, i_ref, 'r--', linewidth=2, label='I_ref', alpha=0.7)
    ax2.set_xlabel('Control Input (V)', fontsize=11)
    ax2.set_ylabel('Collector Current (µA)', fontsize=11)
    ax2.set_title('Output Current vs Control Voltage', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend(fontsize=10)

    # Plot 3: Exponential current response (log scale)
    ax3.semilogy(v_in, i_out, 'b-', linewidth=2.5, label='I_out')
    ax3.semilogy(v_in, i_ref, 'r--', linewidth=2, label='I_ref', alpha=0.7)
    ax3.set_xlabel('Control Input (V)', fontsize=11)
    ax3.set_ylabel('Collector Current (µA, log scale)', fontsize=11)
    ax3.set_title('Exponential Response (Log Scale)', fontsize=12)
    ax3.grid(True, alpha=0.3, which='both')
    ax3.legend(fontsize=10)

    # Plot 4: Current doubling per volt
    doubling_factors, test_voltages = calculate_doubling_factors(v_in, i_out)

    ax4.bar(np.arange(len(doubling_factors)), doubling_factors, color='skyblue', edgecolor='navy', alpha=0.7)
    ax4.axhline(y=2.0, color='r', linestyle='--', linewidth=2, label='Ideal (2× per volt)')
    ax4.set_ylabel('Current Ratio (I(V+1V) / I(V))', fontsize=11)
    ax4.set_xlabel('Test Voltage Point', fontsize=11)
    ax4.set_title('Current Doubling per Volt', fontsize=12)
    ax4.set_ylim([0, 2.5])
    ax4.grid(True, alpha=0.3, axis='y')
    ax4.legend(fontsize=10)
    ax4.set_xticks(range(len(doubling_factors)))
    ax4.set_xticklabels([f'{v:.1f}V' for v in test_voltages], fontsize=9, rotation=45)

    plt.tight_layout()
    return fig, doubling_factors, slope


def main():
    """Main entry point."""
    # Determine CSV file
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        csv_path = find_latest_csv()

    print(f"Loading data from: {csv_path}")

    # Load and process data
    v_in, v_base_div, v_cv_buffered, v_c_ref, v_c_exp = load_simulation_data(csv_path)
    i_ref, i_out = calculate_collector_currents(v_c_ref, v_c_exp)

    # Create plots
    fig, doubling_factors, slope = create_plots(v_in, v_base_div, v_cv_buffered, v_c_ref, v_c_exp, i_ref, i_out)

    # Save figure
    output_file = 'exponential_converter_results.png'
    fig.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"Graph saved as: {output_file}")

    # Print measurements
    print()
    print('=== PERFORMANCE SUMMARY ===')
    print(f'Input voltage range: {v_in.min():.1f}V to {v_in.max():.1f}V')
    print(f'Buffered base voltage range: {v_cv_buffered.min():.4f}V to {v_cv_buffered.max():.4f}V')
    print(f'Base voltage swing: {(v_cv_buffered.max() - v_cv_buffered.min())*1000:.1f} mV')
    print(f'Slope (octave scaling): {slope:.1f} mV/V')
    print(f'I_out range: {i_out.min():.3f} to {i_out.max():.3f} µA')
    print(f'Exponential current ratio (I_max/I_min): {i_out.max() / (i_out.min() + 1e-10):.1f}×')
    print(f'Average doubling per volt: {np.mean(doubling_factors):.2f}×')


if __name__ == '__main__':
    main()
