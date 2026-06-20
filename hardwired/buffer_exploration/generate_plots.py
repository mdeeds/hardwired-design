"""
Generate comparison plots for AB, LM741, and Sziklai buffer stages.

Outputs in this folder:
- compare_error_vs_input.svg
- compare_vout_vs_load_current.svg
- compare_vout_vs_time.svg
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent


# Load local run_spice.py from this same folder.
def _load_run_spice_module():
    spec = importlib.util.spec_from_file_location("run_spice", HERE / "run_spice.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load local run_spice.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_spice = _load_run_spice_module()


MASTER_DECK = HERE / "simple_ab_buffer.sp"


def load_master_core() -> str:
    """Load master .sp and keep only circuit declarations (no .control/.end)."""
    text = MASTER_DECK.read_text(encoding="utf-8")
    lines = text.splitlines()

    kept: list[str] = []
    in_control = False
    for line in lines:
        low = line.strip().lower()
        if low.startswith(".control"):
            in_control = True
            continue
        if low.startswith(".endc"):
            in_control = False
            continue
        if in_control:
            continue
        if low == ".end":
            continue
        kept.append(line)

    return "\n".join(kept).strip()


def fmt_tick(value: float) -> str:
    mag = abs(value)
    if mag >= 100:
        return f"{value:.0f}"
    if mag >= 10:
        return f"{value:.1f}".rstrip("0").rstrip(".")
    if mag >= 1:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{value:.3f}".rstrip("0").rstrip(".")


def pick_sweep_key(vectors: dict[str, list[float]]) -> str:
    for key in ("i-sweep", "v-sweep", "time"):
        if key in vectors:
            return key
    # Fallback if ngspice returns an unexpected naming.
    return next(iter(vectors.keys()))


def find_index_closest(values: list[float], target: float) -> int:
    return min(range(len(values)), key=lambda i: abs(values[i] - target))


def safe_get(vectors: dict[str, list[float]], key: str, default: float = 0.0) -> float:
    vals = vectors.get(key)
    if not vals:
        return default
    return float(vals[0])


def summary_metrics(
    case_vectors: dict[str, list[float]],
    op_vectors: dict[str, list[float]],
    x_values: list[float],
    force_droop_labels: bool | None = None,
) -> list[tuple[str, str, str, str]]:
    # Compute errors from the active analysis vectors for this specific plot.
    in_values = case_vectors.get("in")
    if in_values and len(in_values) == len(case_vectors["out_ab"]):
        err_ab = [a - b for a, b in zip(case_vectors["out_ab"], in_values)]
        err_741 = [a - b for a, b in zip(case_vectors["out_741"], in_values)]
        err_sz = [a - b for a, b in zip(case_vectors["out_sz"], in_values)]
        in_span = max(in_values) - min(in_values)
        in_mean = sum(in_values) / len(in_values)
        use_droop_labels = abs(in_mean) < 1e-6 and in_span < 1e-6
    else:
        # For analyses with fixed VIN=0, error equals output voltage.
        err_ab = list(case_vectors["out_ab"])
        err_741 = list(case_vectors["out_741"])
        err_sz = list(case_vectors["out_sz"])
        use_droop_labels = True

    i0 = find_index_closest(x_values, 0.0)

    # Quiescent supply currents and power from stage-local supply sources.
    i_ab_pos = abs(safe_get(op_vectors, "vcc_ab#branch"))
    i_ab_neg = abs(safe_get(op_vectors, "vee_ab#branch"))
    i_741_pos = abs(safe_get(op_vectors, "vcc_lm#branch"))
    i_741_neg = abs(safe_get(op_vectors, "vee_lm#branch"))
    i_sz_pos = abs(safe_get(op_vectors, "vcc_sz#branch"))
    i_sz_neg = abs(safe_get(op_vectors, "vee_sz#branch"))

    iq_ab_ma = 1e3 * (i_ab_pos + i_ab_neg)
    iq_741_ma = 1e3 * (i_741_pos + i_741_neg)
    iq_sz_ma = 1e3 * (i_sz_pos + i_sz_neg)

    pq_ab_mw = 1e3 * (12.0 * i_ab_pos + 12.0 * i_ab_neg)
    pq_741_mw = 1e3 * (12.0 * i_741_pos + 12.0 * i_741_neg)
    pq_sz_mw = 1e3 * (12.0 * i_sz_pos + 12.0 * i_sz_neg)

    # AB transistor dissipation estimate at quiescent point.
    # P ~= |Vce * Ic| for QOUTN/QOUTP using collector current sensors.
    v_qn_c = safe_get(op_vectors, "vcc_ab_qn")
    v_qp_c = safe_get(op_vectors, "vee_ab_qp")
    v_out_ab = safe_get(op_vectors, "out_ab")
    ic_qn = abs(safe_get(op_vectors, "vsen_ab_n#branch"))
    ic_qp = abs(safe_get(op_vectors, "vsen_ab_p#branch"))

    p_qn_mw = 1e3 * abs((v_qn_c - v_out_ab) * ic_qn)
    p_qp_mw = 1e3 * abs((v_qp_c - v_out_ab) * ic_qp)
    p_ab_max_mw = max(p_qn_mw, p_qp_mw)

    # Sziklai output transistor dissipation estimate at quiescent point.
    v_szn_c = safe_get(op_vectors, "vcc_sz_qn")
    v_szp_c = safe_get(op_vectors, "vee_sz_qp")
    v_out_sz = safe_get(op_vectors, "out_sz")
    ic_szn = abs(safe_get(op_vectors, "vsen_sz_n#branch"))
    ic_szp = abs(safe_get(op_vectors, "vsen_sz_p#branch"))

    p_szn_mw = 1e3 * abs((v_szn_c - v_out_sz) * ic_szn)
    p_szp_mw = 1e3 * abs((v_szp_c - v_out_sz) * ic_szp)
    p_sz_max_mw = max(p_szn_mw, p_szp_mw)

    if force_droop_labels is not None:
        use_droop_labels = force_droop_labels

    metric_1 = "Max |Vout droop| (V)" if use_droop_labels else "Max |error| (V)"
    metric_2 = "Vout @x=0 (V)" if use_droop_labels else "Offset @x=0 (V)"

    return [
        (metric_1, f"{max(abs(v) for v in err_ab):.4f}", f"{max(abs(v) for v in err_741):.4f}", f"{max(abs(v) for v in err_sz):.4f}"),
        (metric_2, f"{err_ab[i0]:.4f}", f"{err_741[i0]:.4f}", f"{err_sz[i0]:.4f}"),
        ("Quiescent Iq (mA)", f"{iq_ab_ma:.3f}", f"{iq_741_ma:.3f}", f"{iq_sz_ma:.3f}"),
        ("Quiescent Pq (mW)", f"{pq_ab_mw:.3f}", f"{pq_741_mw:.3f}", f"{pq_sz_mw:.3f}"),
        ("Max device Pq (mW)", f"{p_ab_max_mw:.3f}", f"{pq_741_mw:.3f}", f"{p_sz_max_mw:.3f}"),
    ]


def write_overlay_svg(
    x: list[float],
    y_ab: list[float],
    y_741: list[float],
    y_sz: list[float],
    title: str,
    xlabel: str,
    ylabel: str,
    summary_rows: list[tuple[str, str, str, str]],
    out_path: Path,
) -> None:
    width, height = 940, 560
    margin_left, margin_right, margin_top, margin_bottom = 90, 40, 36, 70
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    xmin, xmax = min(x), max(x)
    ymin = min(min(y_ab), min(y_741), min(y_sz))
    ymax = max(max(y_ab), max(y_741), max(y_sz))

    if xmax == xmin:
        xmax = xmin + 1.0
    if ymax == ymin:
        ymax = ymin + 1.0

    ypad = 0.06 * (ymax - ymin)
    ymin -= ypad
    ymax += ypad

    def sx(value: float) -> float:
        return margin_left + (value - xmin) * plot_w / (xmax - xmin)

    def sy(value: float) -> float:
        return margin_top + (ymax - value) * plot_h / (ymax - ymin)

    x_ticks = [xmin + i * (xmax - xmin) / 10 for i in range(11)]
    y_ticks = [ymin + i * (ymax - ymin) / 8 for i in range(9)]

    points_ab = " ".join(f"{sx(a):.2f},{sy(b):.2f}" for a, b in zip(x, y_ab))
    points_741 = " ".join(f"{sx(a):.2f},{sy(b):.2f}" for a, b in zip(x, y_741))
    points_sz = " ".join(f"{sx(a):.2f},{sy(b):.2f}" for a, b in zip(x, y_sz))

    blue = "#0b6efd"
    green = "#1f9d55"
    orange = "#ff7a18"

    svg: list[str] = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
    )
    svg.append(
        '<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="#f8fbff"/>'
        '<stop offset="100%" stop-color="#eef3ff"/>'
        '</linearGradient></defs>'
    )
    svg.append(f'<rect width="{width}" height="{height}" fill="url(#bg)"/>')
    svg.append(
        f'<rect x="{margin_left}" y="{margin_top}" width="{plot_w}" height="{plot_h}" '
        'fill="#fff" stroke="#ccd6e0"/>'
    )

    for tick in x_ticks:
        x_pos = sx(tick)
        svg.append(
            f'<line x1="{x_pos:.2f}" y1="{margin_top}" '
            f'x2="{x_pos:.2f}" y2="{margin_top + plot_h}" stroke="#e6edf5"/>'
        )
        svg.append(
            f'<text x="{x_pos:.2f}" y="{height - margin_bottom + 24}" '
            'font-family="Segoe UI, Arial" font-size="12" text-anchor="middle" fill="#334">'
            f'{fmt_tick(tick)}</text>'
        )

    for tick in y_ticks:
        y_pos = sy(tick)
        svg.append(
            f'<line x1="{margin_left}" y1="{y_pos:.2f}" '
            f'x2="{margin_left + plot_w}" y2="{y_pos:.2f}" stroke="#e6edf5"/>'
        )
        svg.append(
            f'<text x="{margin_left - 10}" y="{y_pos + 4:.2f}" '
            'font-family="Segoe UI, Arial" font-size="12" text-anchor="end" fill="#334">'
            f'{fmt_tick(tick)}</text>'
        )

    x0 = sx(0)
    y0 = sy(0)
    if margin_left <= x0 <= margin_left + plot_w:
        svg.append(
            f'<line x1="{x0:.2f}" y1="{margin_top}" x2="{x0:.2f}" '
            f'y2="{margin_top + plot_h}" stroke="#556" stroke-width="1.4"/>'
        )
    if margin_top <= y0 <= margin_top + plot_h:
        svg.append(
            f'<line x1="{margin_left}" y1="{y0:.2f}" x2="{margin_left + plot_w}" '
            f'y2="{y0:.2f}" stroke="#556" stroke-width="1.4"/>'
        )

    svg.append(f'<polyline points="{points_ab}" fill="none" stroke="{blue}" stroke-width="3"/>')
    svg.append(f'<polyline points="{points_741}" fill="none" stroke="{green}" stroke-width="3"/>')
    svg.append(f'<polyline points="{points_sz}" fill="none" stroke="{orange}" stroke-width="3"/>')

    legend_x = margin_left + 14
    legend_y = margin_top + 14
    svg.append(
        f'<rect x="{legend_x - 8}" y="{legend_y - 12}" width="210" height="64" '
        'rx="6" fill="#ffffffd8" stroke="#ccd6e0"/>'
    )
    svg.append(
        f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 26}" y2="{legend_y}" '
        f'stroke="{blue}" stroke-width="3"/>'
    )
    svg.append(
        f'<text x="{legend_x + 34}" y="{legend_y + 4}" font-family="Segoe UI, Arial" '
        'font-size="12" fill="#223">AB emitter follower</text>'
    )
    svg.append(
        f'<line x1="{legend_x}" y1="{legend_y + 18}" x2="{legend_x + 26}" '
        f'y2="{legend_y + 18}" stroke="{green}" stroke-width="3"/>'
    )
    svg.append(
        f'<text x="{legend_x + 34}" y="{legend_y + 22}" font-family="Segoe UI, Arial" '
        'font-size="12" fill="#223">LM741 baseline</text>'
    )
    svg.append(
        f'<line x1="{legend_x}" y1="{legend_y + 36}" x2="{legend_x + 26}" '
        f'y2="{legend_y + 36}" stroke="{orange}" stroke-width="3"/>'
    )
    svg.append(
        f'<text x="{legend_x + 34}" y="{legend_y + 40}" font-family="Segoe UI, Arial" '
        'font-size="12" fill="#223">Sziklai CFP</text>'
    )

    # Summary table with one column per circuit.
    sum_x = width - 395
    sum_y = margin_top + 10
    sum_w = 370
    row_h = 16
    sum_h = 44 + row_h * (len(summary_rows) + 1)
    svg.append(
        f'<rect x="{sum_x}" y="{sum_y}" width="{sum_w}" height="{sum_h}" '
        'rx="6" fill="#ffffffde" stroke="#ccd6e0"/>'
    )
    svg.append(
        f'<text x="{sum_x + 10}" y="{sum_y + 18}" font-family="Segoe UI, Arial" '
        'font-size="12" fill="#112" font-weight="bold">Summary</text>'
    )

    col_metric = sum_x + 10
    col_ab = sum_x + 205
    col_741 = sum_x + 265
    col_sz = sum_x + 325
    head_y = sum_y + 34
    svg.append(f'<text x="{col_metric}" y="{head_y}" font-family="Segoe UI, Arial" font-size="11" fill="#223" font-weight="bold">Metric</text>')
    svg.append(f'<text x="{col_ab}" y="{head_y}" font-family="Segoe UI, Arial" font-size="11" fill="#223" text-anchor="middle" font-weight="bold">AB</text>')
    svg.append(f'<text x="{col_741}" y="{head_y}" font-family="Segoe UI, Arial" font-size="11" fill="#223" text-anchor="middle" font-weight="bold">LM741</text>')
    svg.append(f'<text x="{col_sz}" y="{head_y}" font-family="Segoe UI, Arial" font-size="11" fill="#223" text-anchor="middle" font-weight="bold">Sziklai</text>')

    y_line_top = sum_y + 40
    svg.append(f'<line x1="{sum_x + 8}" y1="{y_line_top}" x2="{sum_x + sum_w - 8}" y2="{y_line_top}" stroke="#d4dde8"/>')

    for idx, (metric, ab, lm741, sz) in enumerate(summary_rows):
        y_line = y_line_top + 12 + idx * row_h
        if idx % 2 == 1:
            band_y = y_line - 11
            svg.append(
                f'<rect x="{sum_x + 8}" y="{band_y}" width="{sum_w - 16}" height="{row_h}" fill="#f7faff"/>'
            )
        svg.append(
            f'<text x="{col_metric}" y="{y_line}" font-family="Segoe UI, Arial" '
            f'font-size="10.5" fill="#223">{metric}</text>'
        )
        svg.append(f'<text x="{col_ab}" y="{y_line}" font-family="Segoe UI, Arial" font-size="10.5" fill="#223" text-anchor="middle">{ab}</text>')
        svg.append(f'<text x="{col_741}" y="{y_line}" font-family="Segoe UI, Arial" font-size="10.5" fill="#223" text-anchor="middle">{lm741}</text>')
        svg.append(f'<text x="{col_sz}" y="{y_line}" font-family="Segoe UI, Arial" font-size="10.5" fill="#223" text-anchor="middle">{sz}</text>')

    svg.append(
        f'<text x="{width / 2:.2f}" y="24" font-family="Segoe UI, Arial" '
        'font-size="16" text-anchor="middle" fill="#112">'
        f'{title}</text>'
    )
    svg.append(
        f'<text x="{width / 2:.2f}" y="{height - 18}" font-family="Segoe UI, Arial" '
        'font-size="13" text-anchor="middle" fill="#223">'
        f'{xlabel}</text>'
    )
    svg.append(
        f'<text transform="translate(24,{height / 2:.2f}) rotate(-90)" '
        'font-family="Segoe UI, Arial" font-size="13" text-anchor="middle" fill="#223">'
        f'{ylabel}</text>'
    )

    svg.append("</svg>")
    out_path.write_text("\n".join(svg), encoding="utf-8")


def write_overlay_png(
    x: list[float],
    y_ab: list[float],
    y_741: list[float],
    y_sz: list[float],
    title: str,
    xlabel: str,
    ylabel: str,
    summary_rows: list[tuple[str, str, str, str]],
    out_path: Path,
) -> None:
    width, height = 940, 560
    margin_left, margin_right, margin_top, margin_bottom = 90, 40, 36, 70
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    xmin, xmax = min(x), max(x)
    ymin = min(min(y_ab), min(y_741), min(y_sz))
    ymax = max(max(y_ab), max(y_741), max(y_sz))
    if xmax == xmin:
        xmax = xmin + 1.0
    if ymax == ymin:
        ymax = ymin + 1.0
    ypad = 0.06 * (ymax - ymin)
    ymin -= ypad
    ymax += ypad

    def sx(value: float) -> float:
        return margin_left + (value - xmin) * plot_w / (xmax - xmin)

    def sy(value: float) -> float:
        return margin_top + (ymax - value) * plot_h / (ymax - ymin)

    img = Image.new("RGB", (width, height), "#f8fbff")
    draw = ImageDraw.Draw(img)

    draw.rectangle([margin_left, margin_top, margin_left + plot_w, margin_top + plot_h], outline="#ccd6e0", fill="#ffffff")

    x_ticks = [xmin + i * (xmax - xmin) / 10 for i in range(11)]
    y_ticks = [ymin + i * (ymax - ymin) / 8 for i in range(9)]

    for tick in x_ticks:
        x_pos = sx(tick)
        draw.line([(x_pos, margin_top), (x_pos, margin_top + plot_h)], fill="#e6edf5")
        draw.text((x_pos - 12, height - margin_bottom + 10), fmt_tick(tick), fill="#334")

    for tick in y_ticks:
        y_pos = sy(tick)
        draw.line([(margin_left, y_pos), (margin_left + plot_w, y_pos)], fill="#e6edf5")
        draw.text((margin_left - 50, y_pos - 7), fmt_tick(tick), fill="#334")

    x0 = sx(0)
    y0 = sy(0)
    if margin_left <= x0 <= margin_left + plot_w:
        draw.line([(x0, margin_top), (x0, margin_top + plot_h)], fill="#556", width=2)
    if margin_top <= y0 <= margin_top + plot_h:
        draw.line([(margin_left, y0), (margin_left + plot_w, y0)], fill="#556", width=2)

    def _polyline(yvals: list[float], color: str):
        pts = [(sx(a), sy(b)) for a, b in zip(x, yvals)]
        draw.line(pts, fill=color, width=3)

    _polyline(y_ab, "#0b6efd")
    _polyline(y_741, "#1f9d55")
    _polyline(y_sz, "#ff7a18")

    # legend
    draw.rectangle([96, 38, 306, 102], outline="#ccd6e0", fill="#ffffff")
    draw.line([(104, 50), (130, 50)], fill="#0b6efd", width=3)
    draw.text((138, 44), "AB emitter follower", fill="#223")
    draw.line([(104, 68), (130, 68)], fill="#1f9d55", width=3)
    draw.text((138, 62), "LM741 baseline", fill="#223")
    draw.line([(104, 86), (130, 86)], fill="#ff7a18", width=3)
    draw.text((138, 80), "Sziklai CFP", fill="#223")

    # summary table
    sum_x, sum_y, sum_w = width - 395, margin_top + 10, 370
    row_h = 16
    sum_h = 44 + row_h * (len(summary_rows) + 1)
    draw.rectangle([sum_x, sum_y, sum_x + sum_w, sum_y + sum_h], outline="#ccd6e0", fill="#ffffff")
    draw.text((sum_x + 10, sum_y + 10), "Summary", fill="#112")
    col_metric = sum_x + 10
    col_ab = sum_x + 195
    col_741 = sum_x + 255
    col_sz = sum_x + 315
    draw.text((col_metric, sum_y + 26), "Metric", fill="#223")
    draw.text((col_ab, sum_y + 26), "AB", fill="#223")
    draw.text((col_741, sum_y + 26), "LM741", fill="#223")
    draw.text((col_sz, sum_y + 26), "Sziklai", fill="#223")
    draw.line([(sum_x + 8, sum_y + 40), (sum_x + sum_w - 8, sum_y + 40)], fill="#d4dde8")
    for idx, (metric, ab, lm741, sz) in enumerate(summary_rows):
        y_line = sum_y + 44 + idx * row_h
        if idx % 2 == 1:
            draw.rectangle([sum_x + 8, y_line - 2, sum_x + sum_w - 8, y_line + row_h - 2], fill="#f7faff")
        draw.text((col_metric, y_line), metric, fill="#223")
        draw.text((col_ab, y_line), ab, fill="#223")
        draw.text((col_741, y_line), lm741, fill="#223")
        draw.text((col_sz, y_line), sz, fill="#223")

    draw.text((width // 2 - 220, 8), title, fill="#112")
    draw.text((width // 2 - 60, height - 24), xlabel, fill="#223")
    draw.text((10, height // 2), ylabel, fill="#223")

    img.save(out_path)


def main() -> None:
    core = load_master_core()
    cases: list[dict[str, object]] = [
        {
            "name": "compare_error_vs_input",
            "netlist": (
                f"* Compare: error vs input\n{core}\n"
                ".dc VIN -10 10 1\n"
                ".end\n"
            ),
            "extract": lambda v: (
                v[pick_sweep_key(v)],
                [a - b for a, b in zip(v["out_ab"], v[pick_sweep_key(v)])],
                [a - b for a, b in zip(v["out_741"], v[pick_sweep_key(v)])],
                [a - b for a, b in zip(v["out_sz"], v[pick_sweep_key(v)])],
            ),
            "title": "Error vs Input: AB vs LM741 vs Sziklai",
            "xlabel": "Input Voltage (V)",
            "ylabel": "Error (V)",
            "x_scale": 1.0,
            "summary_mode": "error",
        },
        {
            "name": "compare_vout_vs_load_current",
            "netlist": (
                f"* Compare: Vout vs load current\n{core}\n"
                ".dc VLOAD -0.02 0.02 0.002\n"
                ".end\n"
            ),
            "extract": lambda v: (
                v[pick_sweep_key(v)],
                v["out_ab"],
                v["out_741"],
                v["out_sz"],
            ),
            "title": "Output Droop vs Load Current (VIN=0): AB vs LM741 vs Sziklai",
            "xlabel": "Load Current (mA)",
            "ylabel": "Output Voltage (V)",
            "x_scale": 1e3,
            "summary_mode": "droop",
        },
        {
            "name": "compare_vout_vs_time",
            "netlist": (
                f"* Compare: Vout vs time\n{core}\n"
                ".tran 20n 20u\n"
                ".end\n"
            ),
            "extract": lambda v: (
                v[pick_sweep_key(v)],
                v["out_ab"],
                v["out_741"],
                v["out_sz"],
            ),
            "title": "Output Voltage vs Time: AB vs LM741 vs Sziklai",
            "xlabel": "Time (us)",
            "ylabel": "Output Voltage (V)",
            "x_scale": 1e6,
            "summary_mode": "droop",
        },
    ]

    op_netlist = f"* Quiescent metrics\n{core}\n.op\n.end\n"

    dll_path, lib_dirs = run_spice.setup_ngspice([str(HERE)])

    _, op_vectors = run_spice.run_netlist(
        dll_path,
        op_netlist,
        lib_dirs=lib_dirs,
        source_dir=str(HERE),
    )
    created_svg: list[Path] = []
    created_png: list[Path] = []
    for case in cases:
        netlist = str(case["netlist"])
        extract = case["extract"]
        title = str(case["title"])
        xlabel = str(case["xlabel"])
        ylabel = str(case["ylabel"])
        x_scale = float(case["x_scale"])
        summary_mode = str(case["summary_mode"])

        svg_path = HERE / f"{case['name']}.svg"
        png_path = HERE / f"{case['name']}.png"

        _, vectors = run_spice.run_netlist(
            dll_path,
            netlist,
            lib_dirs=lib_dirs,
            source_dir=str(HERE),
        )

        x, y_ab, y_741, y_sz = extract(vectors)
        x_scaled = [value * x_scale for value in x]
        summary_rows = summary_metrics(
            vectors,
            op_vectors,
            x,
            force_droop_labels=(summary_mode == "droop"),
        )

        write_overlay_svg(
            x_scaled,
            y_ab,
            y_741,
            y_sz,
            title,
            xlabel,
            ylabel,
            summary_rows,
            svg_path,
        )
        write_overlay_png(
            x_scaled,
            y_ab,
            y_741,
            y_sz,
            title,
            xlabel,
            ylabel,
            summary_rows,
            png_path,
        )
        created_svg.append(svg_path)
        created_png.append(png_path)

    print("Generated plot files:")
    for path in created_svg:
        print(path)
    print("Generated PNG files:")
    for path in created_png:
        print(path)


if __name__ == "__main__":
    main()
