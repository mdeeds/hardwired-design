#!/usr/bin/env python3
"""
model_fit.py — Config-driven multi-circuit BJT model fitter.

Reads a TOML configuration file that specifies:
  [model]          — current parameter values (starting point + write-back target)
  [param_catalog]  — physical bounds and log/linear optimizer space per parameter
  [optimizer]      — method, iteration limits, sensitivity thresholds
  [[circuit]]      — one or more circuits, each linking a .cir file to a
                     digitised datasheet CSV with column-mapping metadata

Workflow
--------
  Step 1  Sensitivity pre-sweep
          Run nominal simulation for every circuit, then re-run with each
          catalog parameter multiplied by sensitivity_factor (default 2x).
          Any parameter that changes any circuit output by less than
          sensitivity_threshold (default 5% of mean |nominal output|) is
          frozen.

  Step 2  Joint optimisation
          A single shared parameter vector (the sensitive params) is
          optimised by L-BFGS-B.  Every optimizer iteration runs ALL
          circuits, computes each circuit's weighted error, and returns a
          single scalar loss.

  Step 3  Write-back
          Best-fit parameter values are written into the [model] section of
          the TOML file and patched into every .cir file.

Usage
-----
    python scripts/model_fit.py path/to/fit_config.toml [options]

    --sensitivity-only   Only run Step 1 (useful for exploration)
    --plot-only          Skip fitting; regenerate plots with current [model]
    --no-write           Don't write results back to any file
    --maxiter N          Override optimizer max iterations
    --threshold T        Override sensitivity threshold (default 0.05)

Example
-------
    python scripts/model_fit.py \
        hardwired/component_test/C1815_model_itteration/fit_config.toml

    python scripts/model_fit.py \\
        hardwired/component_test/C1815_model_itteration/ic_vs_vbe.cir \\
        "hardwired/component_test/C1815_model_itteration/KSC1815 Ic vs Vbe at Vce_6v.csv"

The script:
  1. Reads the .cir file and parses the inline .model parameters.
  2. Loads the datasheet CSV (x=Vbe, y=Ic in mA).
  3. Runs ngspice for each candidate parameter set (via run_spice.py).
  4. Minimises RMS log10(Ic_sim / Ic_ds) using L-BFGS-B.
  5. Writes the best-fit parameters back into the .cir file.
  6. Saves a comparison PNG plot and a CSV of the best-fit simulation.

Requirements:
    pip install scipy matplotlib pandas
    Python >= 3.11 (uses stdlib tomllib; or pip install tomli for older Python)
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib          # type: ignore
    except ImportError:
        sys.exit("Python >=3.11 required, or:  pip install tomli")

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_spice


# ══════════════════════════════════════════════════════════════════════
# SPICE value helpers
# ══════════════════════════════════════════════════════════════════════

_SPICE_SUFFIXES = {
    't': 1e12, 'g': 1e9, 'meg': 1e6, 'k': 1e3,
    'm': 1e-3, 'u': 1e-6, 'n': 1e-9, 'p': 1e-12, 'f': 1e-15,
}


def _parse_spice_val(s: str) -> float:
    s = s.strip()
    m = re.match(r'^([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)(meg|[tgkmunpf])?',
                 s, re.IGNORECASE)
    if not m:
        raise ValueError(f"Cannot parse SPICE value: {s!r}")
    val = float(m.group(1))
    suf = (m.group(2) or '').lower()
    return val * _SPICE_SUFFIXES.get(suf, 1.0)


def _fmt_spice_val(val: float) -> str:
    if val == 0:
        return '0'
    abs_v = abs(val)
    for divisor, suffix in [(1e12,'T'),(1e9,'G'),(1e6,'Meg'),(1e3,'k'),
                             (1.0,''),(1e-3,'m'),(1e-6,'u'),(1e-9,'n'),
                             (1e-12,'p'),(1e-15,'f')]:
        if 1.0 <= abs_v / divisor < 1000.0:
            return f'{val/divisor:.6g}{suffix}'
    return f'{val:.6e}'


def write_model_params(cir_text: str, updates: dict) -> str:
    """Return cir_text with .model parameter values replaced."""
    up = {k.upper(): v for k, v in updates.items()}

    def _replace_kv(m):
        key = m.group(1).upper()
        return f'{m.group(1)}={_fmt_spice_val(up[key])}' if key in up else m.group(0)

    def _patch_model(mm):
        return re.sub(r'(\w+)\s*=\s*([^\s,)]+)', _replace_kv, mm.group(0))

    return re.sub(r'\.model\s+\S+\s+\w+\(.*?\)', _patch_model,
                  cir_text, flags=re.DOTALL | re.IGNORECASE)


# ══════════════════════════════════════════════════════════════════════
# Config loading
# ══════════════════════════════════════════════════════════════════════

def load_config(toml_path: str) -> dict:
    with open(toml_path, 'rb') as f:
        cfg = tomllib.load(f)
    cfg['model'] = {k.upper(): float(v) for k, v in cfg.get('model', {}).items()}
    cfg['param_catalog'] = {k.upper(): v for k, v in cfg.get('param_catalog', {}).items()}
    return cfg


# ══════════════════════════════════════════════════════════════════════
# Datasheet CSV loading
# ══════════════════════════════════════════════════════════════════════

def load_circuit_data(circuit_cfg: dict, config_dir: str) -> list:
    """Returns flat list of (ds_x, ds_y) arrays matching run_and_extract order."""
    data = []
    for trace in circuit_cfg.get('trace', []):
        # Per-trace CSV override; fall back to circuit-level CSV.
        csv_file = trace.get('trace_csv', circuit_cfg['csv'])
        df = pd.read_csv(os.path.join(config_dir, csv_file))
        if 'ib_steps' in trace:
            for ib in trace['ib_steps']:
                xc = trace['x_col_template'].replace('{ib}', str(ib))
                yc = trace['y_col_template'].replace('{ib}', str(ib))
                xs = df[xc].dropna().to_numpy(float)
                ys = df[yc].dropna().to_numpy(float)
                n = min(len(xs), len(ys))
                mask = (ys[:n] > 0) & (xs[:n] >= 0)
                data.append((xs[:n][mask], ys[:n][mask]))
        else:
            xs = df[trace['x_col']].dropna().to_numpy(float)
            ys = df[trace['y_col']].dropna().to_numpy(float)
            n = min(len(xs), len(ys))
            mask = np.isfinite(xs[:n]) & np.isfinite(ys[:n]) & (ys[:n] > 0)
            data.append((xs[:n][mask], ys[:n][mask]))
    return data


# ══════════════════════════════════════════════════════════════════════
# Simulation runner
# ══════════════════════════════════════════════════════════════════════

def run_and_extract(circuit_cfg: dict, model_params: dict,
                    dll_path: str, lib_dirs: list,
                    config_dir: str):
    """Patch .cir, run ngspice, return flat list of (sim_x, sim_y).
    Returns None on failure."""
    cir_path = os.path.join(config_dir, circuit_cfg['cir'])
    patched = write_model_params(
        Path(cir_path).read_text(encoding='utf-8'), model_params)
    _text, vectors = run_spice.run_netlist(
        dll_path, patched, lib_dirs, source_dir=config_dir)
    if not vectors:
        return None
    results = []
    for trace in circuit_cfg.get('trace', []):
        xv, yv = trace['sim_x_vec'], trace['sim_y_vec']
        sx_scale = float(trace.get('sim_x_scale', 1.0))
        sy_scale = float(trace.get('sim_y_scale', 1.0))
        if xv not in vectors or yv not in vectors:
            return None
        sim_x = np.array(vectors[xv]) * sx_scale
        sim_y = np.array(vectors[yv]) * sy_scale
        if 'sim_y_divisor_vec' in trace:
            dv = trace['sim_y_divisor_vec']
            if dv not in vectors:
                return None
            divisor = np.array(vectors[dv])
            with np.errstate(invalid='ignore', divide='ignore'):
                sim_y = np.where(np.abs(divisor) > 1e-30, sim_y / divisor, np.nan)
        if 'ib_steps' in trace:
            n = trace['n_pts_per_step']
            for i in range(len(trace['ib_steps'])):
                results.append((sim_x[i*n:(i+1)*n], sim_y[i*n:(i+1)*n]))
        else:
            # Clean NaN/inf and ensure ascending x for np.interp
            valid = np.isfinite(sim_x) & np.isfinite(sim_y)
            sx, sy = sim_x[valid], sim_y[valid]
            order = np.argsort(sx)
            results.append((sx[order], sy[order]))
    return results


# ══════════════════════════════════════════════════════════════════════
# Error computation
# ══════════════════════════════════════════════════════════════════════

def _trace_error(sim_x, sim_y, ds_x, ds_y, error_space: str):
    if len(sim_x) < 2 or len(ds_x) < 2:
        return None
    interp = np.interp(ds_x, sim_x, sim_y, left=np.nan, right=np.nan)
    if error_space == 'log':
        mask = (ds_y > 0) & (interp > 0) & np.isfinite(interp)
        if mask.sum() < 2:
            return None
        return float(np.sqrt(np.mean(
            (np.log10(interp[mask]) - np.log10(ds_y[mask])) ** 2)))
    else:
        mask = np.isfinite(interp)
        if mask.sum() < 2:
            return None
        norm = float(np.mean(np.abs(ds_y[mask]))) or 1.0
        return float(np.sqrt(np.mean(((interp[mask] - ds_y[mask]) / norm) ** 2)))


def compute_circuit_error(circuit_cfg: dict, trace_results: list,
                          circuit_data: list) -> float:
    errors, idx = [], 0
    for trace in circuit_cfg.get('trace', []):
        esp = trace.get('error_space', 'linear')
        if 'ib_steps' in trace:
            step_errs = []
            for _ in trace['ib_steps']:
                e = _trace_error(*trace_results[idx], *circuit_data[idx], esp)
                if e is not None:
                    step_errs.append(e)
                idx += 1
            if step_errs:
                errors.append(float(np.mean(step_errs)))
        else:
            e = _trace_error(*trace_results[idx], *circuit_data[idx], esp)
            if e is not None:
                errors.append(e)
            idx += 1
    return float(np.mean(errors)) if errors else 1e6


# ══════════════════════════════════════════════════════════════════════
# Step 1 — Sensitivity pre-sweep
# ══════════════════════════════════════════════════════════════════════

def sensitivity_sweep(config: dict, circuits_data: list,
                      dll_path: str, lib_dirs: list, config_dir: str,
                      threshold: float, factor: float) -> list:
    model_params  = dict(config['model'])
    param_catalog = config['param_catalog']
    circuits      = config['circuit']

    print(f"══ Step 1: Sensitivity pre-sweep  "
          f"(factor={factor}x, threshold={threshold:.0%}) ══\n")

    print("  Running nominal simulations...")
    nominal = {}
    for circ in circuits:
        res = run_and_extract(circ, model_params, dll_path, lib_dirs, config_dir)
        nominal[circ['name']] = res
        print(f"    {circ['name']}: {'OK' if res else 'FAILED'}")
    print()

    params_to_test = [p for p in param_catalog
                      if p in model_params and model_params[p] != 0]

    sensitivities = {}
    for param in params_to_test:
        perturbed = dict(model_params)
        pdef = param_catalog[param]
        new_val = model_params[param] * factor
        new_val = max(float(pdef.get('lo', 0)),
                      min(float(pdef.get('hi', 1e30)), new_val))
        perturbed[param] = new_val

        sens_per_circ = {}
        for circ in circuits:
            pert_res = run_and_extract(circ, perturbed, dll_path, lib_dirs, config_dir)
            nom_res  = nominal[circ['name']]
            if pert_res is None or nom_res is None:
                sens_per_circ[circ['name']] = 0.0
                continue
            rms_list = []
            for (sx_n, sy_n), (sx_p, sy_p) in zip(nom_res, pert_res):
                if len(sx_n) < 2:
                    continue
                sy_p_at_n = np.interp(sx_n, sx_p, sy_p)
                norm = float(np.mean(np.abs(sy_n))) or 1.0
                rms_list.append(
                    float(np.sqrt(np.mean((sy_p_at_n - sy_n) ** 2))) / norm)
            sens_per_circ[circ['name']] = float(np.mean(rms_list)) if rms_list else 0.0
        sensitivities[param] = sens_per_circ

    # Print table
    circ_names = [c['name'] for c in circuits]
    col_w = max(max(len(n) for n in circ_names) + 2, 12)
    hdr = (f"  {'Param':<10}"
           + "".join(f"{n[:col_w-1]:>{col_w}}" for n in circ_names)
           + f"  {'Max':>8}  Status")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    force_params = [p.upper() for p in config.get('optimizer', {}).get('force_params', [])]

    sensitive_params = []
    for param in params_to_test:
        vals   = sensitivities.get(param, {})
        per    = [vals.get(n, 0.0) for n in circ_names]
        max_s  = max(per) if per else 0.0
        forced = param in force_params
        if max_s >= threshold:
            status = "SENSITIVE"
        elif forced:
            status = "FORCED"
        else:
            status = "frozen"
        print(f"  {param:<10}"
              + "".join(f"{v:>{col_w}.4f}" for v in per)
              + f"  {max_s:>8.4f}  {status}")
        if max_s >= threshold or forced:
            sensitive_params.append(param)

    frozen = [p for p in params_to_test if p not in sensitive_params]
    print(f"\n  -> {len(sensitive_params)}/{len(params_to_test)} selected: "
          f"{', '.join(sensitive_params)}")
    if frozen:
        print(f"  -> Frozen: {', '.join(frozen)}")
    print()
    return sensitive_params


# ══════════════════════════════════════════════════════════════════════
# Step 2 — Joint optimisation
# ══════════════════════════════════════════════════════════════════════

def run_joint_optimizer(config: dict, circuits_data: list,
                        sensitive_params: list,
                        dll_path: str, lib_dirs: list, config_dir: str,
                        maxiter: int, tol: float) -> dict:
    import math as _math
    model_params  = dict(config['model'])
    param_catalog = config['param_catalog']
    circuits      = config['circuit']

    print(f"══ Step 2: Joint optimisation  "
          f"({len(sensitive_params)} params x {len(circuits)} circuits) ══\n")
    print(f"  Method: L-BFGS-B  maxiter={maxiter}  tol={tol:.1e}")
    print(f"  Parameters: {', '.join(sensitive_params)}\n")

    x0, bounds = [], []
    for pname in sensitive_params:
        pdef = param_catalog.get(pname, {})
        val  = model_params[pname]
        lo   = float(pdef.get('lo', 1e-30))
        hi   = float(pdef.get('hi', 1e30))
        if pdef.get('log', False):
            x0.append(_math.log10(max(val, lo)))
            bounds.append((_math.log10(lo), _math.log10(hi)))
        else:
            x0.append(val)
            bounds.append((lo, hi))

    call_count = [0]
    best = [np.inf, None]
    checkpoint_path = os.path.join(config_dir, 'fit_checkpoint.json')

    def _save_checkpoint(params: dict, loss: float, calls: int):
        import json
        data = {'loss': loss, 'calls': calls, 'params': params}
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    def objective(x):
        current = dict(model_params)
        for i, pname in enumerate(sensitive_params):
            pdef = param_catalog.get(pname, {})
            current[pname] = 10 ** x[i] if pdef.get('log', False) else x[i]
        total = 0.0
        for circ, circ_data in zip(circuits, circuits_data):
            res = run_and_extract(circ, current, dll_path, lib_dirs, config_dir)
            total += (10.0 if res is None
                      else compute_circuit_error(circ, res, circ_data)
                           * float(circ.get('weight', 1.0)))
        loss = total / len(circuits)
        call_count[0] += 1
        if loss < best[0]:
            best[0] = loss
            best[1] = dict(current)
            show = sensitive_params[:5]
            pstr = '  '.join(f'{p}={current[p]:.4g}' for p in show)
            more = (f'  (+{len(sensitive_params)-5} more)'
                    if len(sensitive_params) > 5 else '')
            print(f'  [{call_count[0]:4d}]  loss={loss:.5f}  {pstr}{more}')
            _save_checkpoint(current, loss, call_count[0])
        return loss

    t0 = time.time()
    result = minimize(objective, np.array(x0, dtype=float),
                      method='L-BFGS-B', bounds=bounds,
                      options={'maxiter': maxiter, 'ftol': tol**2,
                               'gtol': tol*0.1, 'eps': 1e-4})
    elapsed = time.time() - t0
    print(f'\n  {result.message}')
    print(f'  Calls: {call_count[0]}  |  Elapsed: {elapsed:.1f}s')
    print(f'  Final loss: {result.fun:.6f}\n')
    return best[1] if best[1] is not None else model_params


# ══════════════════════════════════════════════════════════════════════
# Step 3 — Write-back
# ══════════════════════════════════════════════════════════════════════

def write_back(config_path: str, config: dict, best_params: dict):
    config_dir = os.path.dirname(os.path.abspath(config_path))
    # Update [model] section of TOML
    lines, in_model, result = Path(config_path).read_text(encoding='utf-8').split('\n'), False, []
    for line in lines:
        stripped = line.strip()
        if re.match(r'^\[model\]', stripped):
            in_model = True
        elif re.match(r'^\[', stripped):
            in_model = False
        if in_model and '=' in line and not stripped.startswith('#'):
            key = stripped.split('=')[0].strip().upper()
            if key in best_params:
                indent = len(line) - len(line.lstrip())
                line = ' ' * indent + f'{key}  = {best_params[key]:.8g}'
        result.append(line)
    Path(config_path).write_text('\n'.join(result), encoding='utf-8')
    print(f"  Updated TOML: {config_path}")
    # Patch every .cir
    for circ in config['circuit']:
        cir_path = os.path.join(config_dir, circ['cir'])
        if os.path.isfile(cir_path):
            Path(cir_path).write_text(
                write_model_params(Path(cir_path).read_text(encoding='utf-8'), best_params),
                encoding='utf-8')
            print(f"  Updated .cir: {cir_path}")


# ══════════════════════════════════════════════════════════════════════
# Plotting
# ══════════════════════════════════════════════════════════════════════

def _plot_single_trace(ax_main, ax_err, trace, final_results, nom_results,
                       circuit_data, idx):
    """Plot one non-stepped trace onto the given axes. Returns updated idx."""
    esp = trace.get('error_space', 'linear')
    ds_x, ds_y = circuit_data[idx]
    sx_f, sy_f = final_results[idx]

    y_label = trace.get('y_col', '')
    x_label = trace.get('x_col', '')

    if esp == 'log':
        ax_main.semilogy(ds_x, ds_y, 'ko', ms=5, label='Datasheet', zorder=5)
        ax_main.semilogy(sx_f, np.maximum(sy_f, 1e-30),
                         color='#e05c5c', lw=2, label='Sim')
        if nom_results:
            ax_main.semilogy(nom_results[idx][0],
                             np.maximum(nom_results[idx][1], 1e-30),
                             color='#aaa', lw=1.5, ls='--', alpha=0.6, label='Initial')
    else:
        ax_main.plot(ds_x, ds_y, 'ko', ms=5, label='Datasheet', zorder=5)
        ax_main.plot(sx_f, sy_f, color='#e05c5c', lw=2, label='Sim')
        if nom_results:
            ax_main.plot(*nom_results[idx], color='#aaa', lw=1.5, ls='--',
                         alpha=0.6, label='Initial')

    ax_main.set_xlabel(x_label)
    ax_main.set_ylabel(y_label)
    ax_main.legend(fontsize=8)
    ax_main.grid(True, alpha=0.3)

    # Error subplot
    interp = np.interp(ds_x, sx_f, sy_f, left=np.nan, right=np.nan)
    mask = np.isfinite(interp) & np.isfinite(ds_y) & (ds_y != 0)
    if mask.sum() >= 2:
        if esp == 'log' and (ds_y[mask] > 0).all() and (interp[mask] > 0).all():
            err = np.log10(interp[mask]) - np.log10(ds_y[mask])
            ax_err.set_ylabel('log\u2081\u2080(sim/ds) [decades]')
        else:
            norm = float(np.mean(np.abs(ds_y[mask]))) or 1.0
            err  = (interp[mask] - ds_y[mask]) / norm
            ax_err.set_ylabel('(sim \u2212 ds) / mean|ds|')
        ax_err.plot(ds_x[mask], err, 'o-', color='#e05c5c', ms=4, lw=1.2)
        ax_err.axhline(0, color='k', lw=0.7, ls='--')
        rms = float(np.sqrt(np.mean(err ** 2)))
        ax_err.set_title(f'RMS = {rms:.4f}', fontsize=9)
    ax_err.set_xlabel(x_label)
    ax_err.grid(True, alpha=0.3)
    return idx + 1


def plot_circuit(circuit_cfg: dict, nom_results, final_results,
                 circuit_data: list, config_dir: str, open_file: bool = True):
    traces = circuit_cfg.get('trace', [])
    colors = plt.cm.plasma(np.linspace(0.1, 0.9, 8))

    # Count rows: one row per non-stepped trace, one row for all stepped traces
    has_stepped = any('ib_steps' in t for t in traces)
    non_stepped = [t for t in traces if 'ib_steps' not in t]
    n_rows = len(non_stepped) + (1 if has_stepped else 0)
    if n_rows == 0:
        return

    fig, axes = plt.subplots(n_rows, 2,
                             figsize=(13, 5 * n_rows),
                             squeeze=False)
    fig.suptitle(circuit_cfg['name'], fontsize=13, fontweight='bold')

    row = 0
    idx = 0

    for trace in traces:
        esp = trace.get('error_space', 'linear')
        ax_main, ax_err = axes[row]

        if 'ib_steps' in trace:
            rms_labels, rms_vals = [], []
            for i, ib in enumerate(trace['ib_steps']):
                c = colors[i % len(colors)]
                ds_x, ds_y = circuit_data[idx]
                sx_f, sy_f = final_results[idx]
                ax_main.plot(sx_f, sy_f, color=c, lw=1.5, label=f'IB={ib}\u03bcA')
                ax_main.scatter(ds_x, ds_y, color=c, s=18, zorder=5, linewidths=0)
                if nom_results:
                    ax_main.plot(*nom_results[idx], color=c, lw=1, ls='--', alpha=0.35)
                e = _trace_error(sx_f, sy_f, ds_x, ds_y, esp)
                if e is not None:
                    rms_labels.append(f'{ib}\u03bcA')
                    rms_vals.append(e)
                idx += 1
            ax_main.set_xlabel('VCE (V)')
            ax_main.set_ylabel('IC (mA)')
            ax_main.legend(fontsize=7, loc='lower right')
            ax_main.set_xlim(left=0)
            ax_main.set_ylim(bottom=0)
            ax_main.grid(True, alpha=0.3)
            if rms_labels:
                xp = np.arange(len(rms_labels))
                ax_err.bar(xp, rms_vals, color='#e05c5c', alpha=0.8, width=0.6)
                ax_err.set_xticks(xp)
                ax_err.set_xticklabels(rms_labels, rotation=45, fontsize=8)
                ax_err.set_ylabel('Normalised RMS error per IB step')
                ax_err.set_title(f'Mean RMS = {np.mean(rms_vals):.4f}', fontsize=9)
            ax_err.grid(True, alpha=0.3)
            row += 1
        else:
            idx = _plot_single_trace(ax_main, ax_err, trace,
                                     final_results, nom_results, circuit_data, idx)
            row += 1

    plt.tight_layout()
    safe = re.sub(r'[^\w]', '_', circuit_cfg['name'])[:40]
    out  = os.path.join(config_dir, f'fit_{safe}.png')
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  Plot: {out}")
    if open_file:
        try:
            os.startfile(out)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(description='Config-driven multi-circuit BJT fitter.')
    p.add_argument('config', help='Path to fit_config.toml')
    p.add_argument('--sensitivity-only', action='store_true')
    p.add_argument('--plot-only',        action='store_true')
    p.add_argument('--no-write',         action='store_true')
    p.add_argument('--maxiter',  type=int,   default=None)
    p.add_argument('--threshold', type=float, default=None)
    return p.parse_args()


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def main():
    # Ensure UTF-8 output on Windows (needed for box-drawing characters).
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    args = parse_args()
    if not os.path.isfile(args.config):
        sys.exit(f"Error: config not found: {args.config}")

    config     = load_config(args.config)
    config_dir = os.path.dirname(os.path.abspath(args.config))
    opt_cfg    = config.get('optimizer', {})

    threshold = args.threshold or float(opt_cfg.get('sensitivity_threshold', 0.05))
    factor    = float(opt_cfg.get('sensitivity_factor', 2.0))
    maxiter   = args.maxiter   or int(opt_cfg.get('maxiter', 300))
    tol       = float(opt_cfg.get('tol', 1e-5))

    print(f"\nmodel_fit.py -- {args.config}")
    print(f"Circuits : {len(config['circuit'])}")
    for circ in config['circuit']:
        print(f"  * {circ['name']}")
    print(f"Catalog  : {len(config['param_catalog'])} parameters\n")

    dll_path, lib_dirs = run_spice.setup_ngspice()
    if config_dir not in lib_dirs:
        lib_dirs.insert(0, config_dir)
    print(f"ngspice: {dll_path}\n")

    circuits_data = [load_circuit_data(c, config_dir) for c in config['circuit']]

    if args.plot_only:
        print("Plot-only mode\n")
        for circ, cdata in zip(config['circuit'], circuits_data):
            res = run_and_extract(circ, config['model'], dll_path, lib_dirs, config_dir)
            if res:
                plot_circuit(circ, None, res, cdata, config_dir, open_file=True)
            else:
                print(f"  FAILED to simulate: {circ['name']}")
        return

    # Step 1
    sensitive_params = sensitivity_sweep(
        config, circuits_data, dll_path, lib_dirs, config_dir,
        threshold=threshold, factor=factor)

    if args.sensitivity_only or not sensitive_params:
        if not sensitive_params:
            print("No sensitive parameters found.")
        return

    # Capture nominal results for comparison plots
    initial_results = {
        circ['name']: run_and_extract(circ, config['model'], dll_path, lib_dirs, config_dir)
        for circ in config['circuit']
    }

    # Step 2
    best_params = run_joint_optimizer(
        config, circuits_data, sensitive_params,
        dll_path, lib_dirs, config_dir, maxiter=maxiter, tol=tol)

    # Change table
    print("══ Parameter changes ══\n")
    print(f"  {'Param':<10} {'Original':>14} {'Best-fit':>14}  {'Delta%':>8}")
    print("  " + "-" * 52)
    for k in sensitive_params:
        v_old = config['model'].get(k, float('nan'))
        v_new = best_params.get(k, v_old)
        pct   = (v_new - v_old) / v_old * 100 if v_old else float('nan')
        print(f"  {k:<10} {v_old:>14.6g} {v_new:>14.6g}  {pct:>+7.1f}%")
    print()

    # Step 3
    if not args.no_write:
        print("══ Writing results ══\n")
        write_back(args.config, config, best_params)
        print()

    # Plots
    print("══ Plots ══\n")
    for circ, cdata in zip(config['circuit'], circuits_data):
        res = run_and_extract(circ, best_params, dll_path, lib_dirs, config_dir)
        if res:
            plot_circuit(circ, initial_results.get(circ['name']), res, cdata,
                         config_dir, open_file=True)


if __name__ == '__main__':
    main()