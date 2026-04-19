"""
wc_analysis.py — Worst-case analysis tool for SPICE netlists in DESIGN.md files.

Extracts the SPICE netlist from a markdown file, parses all tunable
parameters (R, C, V values), and prepares to run exhaustive ±tolerance
sweeps.

Usage:
    python wc_analysis.py path/to/DESIGN.md [--tol 5]
"""

import argparse
import os
import re
import sys

# Allow importing run_spice from the same directory
sys.path.insert(0, os.path.dirname(__file__))
import run_spice


# ── SPICE engineering notation ──────────────────────────────────────
# Order matters: 'meg' before 'm' so regex matches greedily.
ENG_SUFFIXES = {
    "t":   1e12,
    "g":   1e9,
    "meg": 1e6,
    "k":   1e3,
    "m":   1e-3,
    "u":   1e-6,
    "n":   1e-9,
    "p":   1e-12,
    "f":   1e-15,
}

# Matches a number with optional engineering suffix and optional unit.
# Groups: (number) (eng_suffix|"") (unit|"")
# Examples: "100k" → ("100","k",""), "12V" → ("12","","V"), "2.04f" → ("2.04","f","")
_SUFFIX_PAT = "|".join(re.escape(s) for s in ENG_SUFFIXES)
VALUE_RE = re.compile(
    rf"^([+-]?\d+\.?\d*(?:e[+-]?\d+)?)"   # numeric part
    rf"({_SUFFIX_PAT})?"                    # optional eng suffix
    rf"([a-zA-Z]*)$",                       # optional unit (V, ohm, etc.)
    re.IGNORECASE,
)


def parse_eng_value(token: str) -> float | None:
    """Parse a SPICE value token into a float.  Returns None if not numeric."""
    m = VALUE_RE.match(token)
    if not m:
        return None
    num = float(m.group(1))
    suffix = (m.group(2) or "").lower()
    if suffix:
        num *= ENG_SUFFIXES[suffix]
    return num


def format_eng_value(value: float, orig_token: str) -> str:
    """Format *value* using the same suffix/unit style as *orig_token*."""
    m = VALUE_RE.match(orig_token)
    if not m:
        return str(value)
    suffix = (m.group(2) or "").lower()
    unit = m.group(3) or ""
    divisor = ENG_SUFFIXES.get(suffix, 1.0)
    scaled = value / divisor
    # Preserve original suffix casing
    orig_suffix = m.group(2) or ""
    # Use enough precision to avoid rounding artefacts, but trim trailing zeros
    formatted = f"{scaled:.6g}{orig_suffix}{unit}"
    return formatted


# ── Netlist pre-processing ──────────────────────────────────────────

def preprocess_netlist(raw: str) -> list[tuple[str, list[int]]]:
    """Join continuation lines and strip comments.

    Returns a list of (logical_line, [original_line_indices]).
    Line indices are 0-based into the raw text split.
    """
    raw_lines = raw.split("\n")
    logical: list[tuple[str, list[int]]] = []

    for i, line in enumerate(raw_lines):
        stripped = line.strip()

        # Skip blank lines
        if not stripped:
            continue

        # Skip comments
        if stripped.startswith("*"):
            continue

        # Continuation line — append to previous logical line
        if stripped.startswith("+"):
            if logical:
                prev_text, prev_indices = logical[-1]
                logical[-1] = (prev_text + " " + stripped[1:].strip(), prev_indices + [i])
            continue

        # New logical line
        logical.append((stripped, [i]))

    return logical


# ── Parameter extraction ────────────────────────────────────────────

# Component prefixes whose last token is a value we want to sweep.
# R=resistor, C=capacitor, V=voltage src, I=current src,
# E=VCVS, F=CCCS, G=VCCS, H=CCVS, L=inductor
BASIC_PREFIXES = {"r", "c", "v", "i", "l", "e", "f", "g", "h"}


def find_print_vectors(netlist: str) -> list[str]:
    """Parse .print directives and return the requested vector names.

    e.g. '.print dc v(cv_in) v(cv_node) v(v_out)' → ['cv_in', 'cv_node', 'v_out']
    """
    vectors = []
    for line, _ids in preprocess_netlist(netlist):
        if line.lower().startswith(".print"):
            # Extract v(...) and i(...) references
            for m in re.finditer(r'[vi]\(([^)]+)\)', line, re.IGNORECASE):
                vectors.append(m.group(1))
    return vectors


def find_parameters(netlist: str) -> list[dict]:
    """Find all tunable numeric parameters in a SPICE netlist.

    Returns a list of dicts:
        name:       component name (e.g. "R_IN")
        type:       component type letter ("R", "C", "V")
        value:      numeric value as float
        token:      original value token string (e.g. "100k")
        line:       the full logical line
        line_ids:   original line indices (0-based)
    """
    logical_lines = preprocess_netlist(netlist)
    params = []

    for line, line_ids in logical_lines:
        tokens = line.split()
        if not tokens:
            continue

        first = tokens[0]
        prefix = first[0].lower()

        if prefix not in BASIC_PREFIXES:
            continue

        # For V sources, skip the swept source (the one referenced by .dc)
        # We'll detect .dc later; for now just find all V sources.

        # Find the value token — last token that parses as a number.
        # For "V_CV cv_in 0 DC 0V" we want "0V"; for "VCC vcc 0 12V" we want "12V".
        # For "R_IN cv_in cv_sum 100k" we want "100k".
        # Skip keywords like "DC", "AC", "PULSE", etc.
        KEYWORDS = {"dc", "ac", "pulse", "sin", "pwl", "exp", "sffm"}

        value_token = None
        value_idx = None
        for j in range(len(tokens) - 1, 0, -1):
            t = tokens[j]
            if t.lower() in KEYWORDS:
                continue
            val = parse_eng_value(t)
            if val is not None:
                value_token = t
                value_idx = j
                break

        if value_token is None:
            continue

        params.append({
            "name": first,
            "type": prefix.upper(),
            "value": parse_eng_value(value_token),
            "token": value_token,
            "line": line,
            "line_ids": line_ids,
            "token_idx": value_idx,
            "kind": "component",
        })

    return params


def find_model_parameters(netlist: str) -> list[dict]:
    """Find tunable parameters inside .model directives.

    Returns a list of dicts with the same shape as find_parameters(),
    plus 'param_key' (e.g. 'IS', 'BF') and kind='model'.
    """
    logical_lines = preprocess_netlist(netlist)
    params = []

    for line, line_ids in logical_lines:
        if not line.lower().startswith(".model"):
            continue

        # .model NAME TYPE(params...)
        tokens = line.split(None, 2)
        if len(tokens) < 3:
            continue
        model_name = tokens[1]  # e.g. "NPN_C1815"

        # Extract KEY=VALUE pairs
        for m in re.finditer(r'(\w+)=([^\s)]+)', line):
            key = m.group(1)
            val_token = m.group(2)

            val = parse_eng_value(val_token)
            if val is None:
                continue

            params.append({
                "name": f"{model_name}.{key}",
                "type": "M",
                "value": val,
                "token": val_token,
                "line": line,
                "line_ids": line_ids,
                "param_key": key,
                "kind": "model",
            })

    return params


def apply_parameter(netlist: str, param: dict, new_value: float) -> str:
    """Return a copy of *netlist* with one parameter's value replaced."""
    raw_lines = netlist.split("\n")
    new_token = format_eng_value(new_value, param["token"])
    line_ids = param["line_ids"]
    result_lines = list(raw_lines)

    if param.get("kind") == "model":
        # Replace KEY=old_token with KEY=new_token inside the .model line
        key = param["param_key"]
        new_logical = re.sub(
            rf'\b{re.escape(key)}={re.escape(param["token"])}',
            f'{key}={new_token}',
            param["line"],
            count=1,
        )
    else:
        # Component: replace the value token by position
        tokens = param["line"].split()
        tokens[param["token_idx"]] = new_token
        new_logical = " ".join(tokens)

    # The logical line may span multiple raw lines (via + continuations).
    # Replace them all with a single line.
    result_lines[line_ids[0]] = new_logical
    # Blank out any continuation lines
    for lid in line_ids[1:]:
        result_lines[lid] = ""

    return "\n".join(result_lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Worst-case analysis of SPICE netlists from DESIGN.md files.",
    )
    parser.add_argument(
        "md_path",
        help="Path to the DESIGN.md file containing a ```spice block.",
    )
    parser.add_argument(
        "--tol",
        type=float,
        default=5.0,
        help="Tolerance percentage for worst-case analysis (default: 5).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    md_path = args.md_path
    tol = args.tol / 100.0

    if not os.path.isfile(md_path):
        print(f"Error: '{md_path}' not found.", file=sys.stderr)
        sys.exit(1)

    print(f"Worst-case analysis: {md_path}  (±{args.tol:.1f}% tolerance)")
    print()

    # Step 1: Extract netlist
    blocks = run_spice.extract_spice_blocks(md_path)
    if not blocks:
        print("No ```spice blocks found.", file=sys.stderr)
        sys.exit(1)

    label, netlist = blocks[0]

    # Step 2: Parse parameters, drop zero-valued ones (no effect from ±%)
    all_params = find_parameters(netlist) + find_model_parameters(netlist)
    params = [p for p in all_params if p["value"] != 0]

    print(f"Block: {label}")
    print(f"Found {len(params)} tunable parameters ({len(all_params) - len(params)} zero-valued skipped):\n")
    print(f"  {'Name':<16} {'Type':>4} {'Value':>14} {'Token':>10}   ±{args.tol:.0f}% range")
    print(f"  {'─'*16} {'─'*4} {'─'*14} {'─'*10}   {'─'*20}")
    for p in params:
        lo = p["value"] * (1 - tol)
        hi = p["value"] * (1 + tol)
        lo_s = format_eng_value(lo, p["token"])
        hi_s = format_eng_value(hi, p["token"])
        print(f"  {p['name']:<16} {p['type']:>4} {p['value']:>14.6g} {p['token']:>10}   {lo_s} … {hi_s}")

    n_runs = 2 * len(params) + 1  # +1 for nominal
    print(f"\n  Sensitivity sweep: {n_runs} runs (1 nominal + 2 × {len(params)} params)")

    # Step 3: Setup ngspice
    dll_path, lib_dirs = run_spice.setup_ngspice()
    print(f"\nUsing ngspice: {dll_path}")

    # Step 4: Determine output vectors from .print directive
    print_vectors = find_print_vectors(netlist)
    if print_vectors:
        print(f"Output vectors (from .print): {', '.join(print_vectors)}")
    else:
        print("No .print directive found — will track all voltage vectors.")

    # Step 5: Run nominal
    print("Running nominal...", end="", flush=True)
    _text, nominal_vectors = run_spice.run_netlist(dll_path, netlist, lib_dirs)
    if not nominal_vectors:
        print(" FAILED — no vectors returned.")
        sys.exit(1)
    sweep_key = "v-sweep" if "v-sweep" in nominal_vectors else list(nominal_vectors.keys())[0]
    sweep = nominal_vectors[sweep_key]
    n_pts = len(sweep)
    print(f" OK ({n_pts} points)")

    # Use .print vectors if available, otherwise fall back to all voltages
    if print_vectors:
        output_keys = [k for k in print_vectors if k in nominal_vectors]
    else:
        output_keys = [k for k in nominal_vectors if k != sweep_key and "#branch" not in k]

    # Step 6: One-at-a-time sweep
    # Store results: for each output vector, keep nominal + all perturbed traces
    results: dict[str, list[tuple[str, list[float]]]] = {}
    for k in output_keys:
        results[k] = [("nominal", nominal_vectors[k])]

    done = 0
    for p in params:
        for sign, label_sfx in [(+1, "+"), (-1, "-")]:
            new_val = p["value"] * (1 + sign * tol)
            modified = apply_parameter(netlist, p, new_val)
            run_label = f"{p['name']}{label_sfx}"

            _text, vectors = run_spice.run_netlist(dll_path, modified, lib_dirs)
            done += 1

            if not vectors:
                print(f"  {run_label}: FAILED")
                continue

            for k in output_keys:
                if k in vectors:
                    results[k].append((run_label, vectors[k]))

            if done % 8 == 0 or done == 2 * len(params):
                print(f"  Completed {done}/{2 * len(params)} runs")

    # Step 7: Compute error metrics per perturbation
    import csv as csv_mod
    import math
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    md_dir = os.path.dirname(os.path.abspath(md_path))

    # For each output vector and each perturbation, compute:
    #   - max_abs_dev:  max|pert(x) - nom(x)|
    #   - rms_error:    sqrt(mean((pert - nom)²))
    #   - sensitivity:  (rms(Δy)/mean|y_nom|) / (Δp/p)  — unitless
    sensitivity_rows: list[dict] = []

    for vec_key in output_keys:
        traces = results[vec_key]
        nom = traces[0][1]
        nom_mean_abs = sum(abs(v) for v in nom) / len(nom) if nom else 1.0

        for trace_name, trace_data in traces[1:]:
            diffs = [trace_data[j] - nom[j] for j in range(len(nom))]
            max_abs = max(abs(d) for d in diffs)
            rms = math.sqrt(sum(d * d for d in diffs) / len(diffs))

            # Sensitivity coefficient: normalized output change / normalized input change
            # Input change is ±tol (e.g. 0.05), output change normalized by mean|nominal|
            sens = (rms / nom_mean_abs) / tol if nom_mean_abs > 0 else 0.0

            sensitivity_rows.append({
                "output": vec_key,
                "perturbation": trace_name,
                "max_abs_dev": max_abs,
                "rms_error": rms,
                "sensitivity": sens,
            })

    # Sort by RMS error descending to find key drivers
    sensitivity_rows.sort(key=lambda r: r["rms_error"], reverse=True)

    # Save sensitivity summary CSV
    sens_csv_path = os.path.join(md_dir, "wc_sensitivity_summary.csv")
    with open(sens_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv_mod.writer(f)
        writer.writerow(["output", "perturbation", "max_abs_dev", "rms_error", "sensitivity_coeff"])
        for r in sensitivity_rows:
            writer.writerow([r["output"], r["perturbation"],
                             f"{r['max_abs_dev']:.6e}", f"{r['rms_error']:.6e}",
                             f"{r['sensitivity']:.4f}"])
    print(f"\nSensitivity summary: {sens_csv_path}")

    # Build HTML summary table for the top of the report
    # Group by output vector, show top drivers per output
    top_n = 10
    summary_html_parts = []
    summary_html_parts.append(
        '<div style="font-family: Arial, sans-serif; max-width: 1000px; margin: 20px auto;">'
        f'<h2 style="text-align:center;">Worst-Case Sensitivity Summary</h2>'
        f'<p style="text-align:center; color:#666;">'
        f'{os.path.basename(md_path)} &mdash; &pm;{args.tol:.0f}% one-at-a-time '
        f'({2 * len(params)} perturbations, {n_pts} sweep points)</p>'
        '<div style="background:#f8f9fa; border:1px solid #ddd; border-radius:6px; '
        'padding:14px 18px; margin:16px 0; font-size:13px; line-height:1.6;">'
        '<b>Column definitions:</b><br>'
        '<b>Max Abs Dev</b> &mdash; Largest absolute difference between the perturbed '
        'and nominal output at any single sweep point. Shows the worst-case instantaneous shift.<br>'
        '<b>RMS Error</b> &mdash; Root-mean-square of the difference across all sweep points. '
        'Captures the overall &ldquo;energy&rdquo; of the deviation, not just the peak.<br>'
        '<b>Sensitivity</b> &mdash; Unitless coefficient: (RMS&nbsp;&Delta;y&nbsp;/&nbsp;mean|y<sub>nom</sub>|) '
        '&divide; (&Delta;p&nbsp;/&nbsp;p). A value of 1.0 means a 1% parameter change causes a 1% output change. '
        'Directly comparable across parameters with different units.<br>'
        '<b>Impact</b> &mdash; Visual bar proportional to RMS Error relative to the worst perturbation. '
        '<span style="color:#e74c3c;">&#9632;</span>&nbsp;Red&nbsp;&gt;&nbsp;66%, '
        '<span style="color:#f39c12;">&#9632;</span>&nbsp;Orange&nbsp;&gt;&nbsp;33%, '
        '<span style="color:#27ae60;">&#9632;</span>&nbsp;Green&nbsp;&le;&nbsp;33%.'
        '</div>'
    )

    for vec_key in output_keys:
        vec_rows = [r for r in sensitivity_rows if r["output"] == vec_key]
        # Already sorted by rms_error desc globally; re-sort this subset
        vec_rows.sort(key=lambda r: r["rms_error"], reverse=True)
        top = vec_rows[:top_n]
        worst_rms = top[0]["rms_error"] if top else 0.0

        summary_html_parts.append(
            f'<h3 style="margin-top:24px;">Key Error Drivers: <code>{vec_key}</code></h3>'
            '<table style="border-collapse:collapse; width:100%; font-size:14px;">'
            '<thead><tr style="background:#f0f0f0;">'
            '<th style="padding:6px 10px; text-align:left; border-bottom:2px solid #ccc;">Rank</th>'
            '<th style="padding:6px 10px; text-align:left; border-bottom:2px solid #ccc;">Perturbation</th>'
            '<th style="padding:6px 10px; text-align:right; border-bottom:2px solid #ccc;">Max Abs Dev</th>'
            '<th style="padding:6px 10px; text-align:right; border-bottom:2px solid #ccc;">RMS Error</th>'
            '<th style="padding:6px 10px; text-align:right; border-bottom:2px solid #ccc;">Sensitivity</th>'
            '<th style="padding:6px 10px; text-align:left; border-bottom:2px solid #ccc;">Impact</th>'
            '</tr></thead><tbody>'
        )
        for rank, r in enumerate(top, 1):
            # Bar width proportional to rms relative to worst
            bar_pct = (r["rms_error"] / worst_rms * 100) if worst_rms > 0 else 0
            bar_color = "#e74c3c" if bar_pct > 66 else "#f39c12" if bar_pct > 33 else "#27ae60"
            summary_html_parts.append(
                f'<tr style="border-bottom:1px solid #eee;">'
                f'<td style="padding:4px 10px;">{rank}</td>'
                f'<td style="padding:4px 10px; font-family:monospace;">{r["perturbation"]}</td>'
                f'<td style="padding:4px 10px; text-align:right;">{r["max_abs_dev"]:.4e}</td>'
                f'<td style="padding:4px 10px; text-align:right;">{r["rms_error"]:.4e}</td>'
                f'<td style="padding:4px 10px; text-align:right;">{r["sensitivity"]:.4f}</td>'
                f'<td style="padding:4px 10px;">'
                f'<div style="background:{bar_color}; width:{bar_pct:.0f}%; height:14px; '
                f'border-radius:3px; min-width:2px;"></div></td>'
                f'</tr>'
            )
        summary_html_parts.append('</tbody></table>')

    summary_html_parts.append('</div><hr style="margin:30px 0;">')
    summary_html = "\n".join(summary_html_parts)

    print(f"\nSaving results for {len(output_keys)} output vectors:")

    # Build one subplot per output vector
    fig = make_subplots(
        rows=len(output_keys), cols=1,
        subplot_titles=[
            f"Worst-Case Sensitivity: {k}  (±{args.tol:.0f}%, {len(results[k])-1} perturbations)"
            for k in output_keys
        ],
        vertical_spacing=0.06,
    )

    for row_idx, vec_key in enumerate(output_keys, start=1):
        traces = results[vec_key]
        show_legend = row_idx == 1  # only first subplot populates legend

        # ── CSV ─────────────────────────────────────────────────────
        csv_path = os.path.join(md_dir, f"wc_{vec_key}.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv_mod.writer(f)
            header = [sweep_key] + [t[0] for t in traces]
            writer.writerow(header)
            for j in range(n_pts):
                row_data = [sweep[j]] + [t[1][j] for t in traces]
                writer.writerow(row_data)

        # ── Plotly traces ───────────────────────────────────────────
        # Nominal trace (thick black)
        fig.add_trace(
            go.Scatter(
                x=sweep, y=traces[0][1],
                mode="lines",
                name="nominal",
                line=dict(color="black", width=2.5),
                legendgroup="nominal",
                showlegend=show_legend,
            ),
            row=row_idx, col=1,
        )

        # Perturbed traces
        for trace_name, trace_data in traces[1:]:
            fig.add_trace(
                go.Scatter(
                    x=sweep, y=list(trace_data),
                    mode="lines",
                    name=trace_name,
                    line=dict(width=1),
                    opacity=0.55,
                    legendgroup=trace_name,
                    showlegend=show_legend,
                ),
                row=row_idx, col=1,
            )

        fig.update_xaxes(title_text=sweep_key, row=row_idx, col=1)
        fig.update_yaxes(title_text=vec_key, row=row_idx, col=1)

        print(f"  {vec_key}: csv={csv_path}  ({len(traces)} traces)")

    # ── Write combined HTML report ──────────────────────────────────
    fig.update_layout(
        height=450 * len(output_keys),
        title_text=(
            f"Worst-Case Sensitivity Report<br>"
            f"<sup>{os.path.basename(md_path)} — ±{args.tol:.0f}% one-at-a-time"
            f" ({2 * len(params)} perturbations, {n_pts} sweep points)</sup>"
        ),
        title_x=0.5,
        hovermode="x unified",
        legend=dict(font=dict(size=10)),
    )

    report_path = os.path.join(md_dir, "wc_report.html")
    plot_html = fig.to_html(include_plotlyjs=True, full_html=False)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("<html>\n<head><meta charset=\"utf-8\" /></head>\n<body>\n")
        f.write(summary_html)
        f.write(plot_html)
        f.write("\n</body>\n</html>\n")
    print(f"\n  Interactive report: {report_path}")


if __name__ == "__main__":
    main()
