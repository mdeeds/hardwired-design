# Buffer Exploration Workflow

This folder contains a repeatable SPICE simulation pipeline for comparing buffer topologies.

The workflow is centered on one master deck:

- `simple_ab_buffer.sp`

and two helper scripts:

- `run.ps1` (run all simulations and generate plots)
- `clean.ps1` (remove generated artifacts)

## What `run.ps1` does

Run from this folder:

```powershell
.\run.ps1
```

`run.ps1` performs two steps:

1. Runs `run_spice.py` on `simple_ab_buffer.sp`.
2. Runs `generate_plots.py` to build comparison plots.

Generated artifacts include:

- Raw simulation output:
	- `sim_output_*.txt`
	- `sim_output_*.csv`
- Plot overlays:
	- `compare_error_vs_input.svg`
	- `compare_vout_vs_load_current.svg`
	- `compare_vout_vs_time.svg`
	- `compare_error_vs_input.png`
	- `compare_vout_vs_load_current.png`
	- `compare_vout_vs_time.png`

## What `clean.ps1` does

Run from this folder:

```powershell
.\clean.ps1
```

`clean.ps1` deletes generated files so you can rerun from a clean state:

- `sim_output_*.txt`
- `sim_output_*.csv`
- `compare_*.sp`
- `compare_*.svg`
- `compare_*.png`

## How to try other circuits

Edit `simple_ab_buffer.sp` and rerun the pipeline.

Typical loop:

1. Modify the circuit in `simple_ab_buffer.sp`.
2. Keep node names used by plotting logic consistent where possible (for example output and current-sense nodes) so comparisons continue to work.
3. Run `.\run.ps1`.
4. Inspect updated SVG/PNG plots.
5. Optional: run `.\clean.ps1` before your next major variant.

### Practical tips while editing the `.sp` deck

- Keep this file as the single source of truth for your variant.
- Preserve `.control` sections expected by the plotting script unless you also update `generate_plots.py`.
- If adding/removing topologies, ensure each compared topology still has the vectors that `generate_plots.py` reads.
- If you change sweep ranges (input, load, time), rerun and verify axis units/labels in the generated plots.

## Related files

- `generate_plots.py`: builds comparison plot overlays and summary tables.
- `run_spice.py`: ngspice shared-library runner used by `run.ps1`.
- `simple_ab_buffer.sp`: master simulation deck to edit for new circuit variants.
