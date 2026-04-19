"""
debug_helper.py — Generate an interactive HTML circuit debug helper.

Usage:
    python debug_helper.py <input_file> [--output <output.html>]

Input accepts:
    .csv                    — Simulation CSV (from run_spice.py)
    .md                     — DESIGN.md with ```spice code blocks
    .cir/.sp/.spice/.net    — Raw SPICE netlist

The generated HTML provides:
    - Comparison table with up to 5 selectable operating points
    - Simulated values next to user-input fields for measurements
    - Interactive plots for each .print/.probe node
    - Measurement persistence via localStorage
"""

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_spice


# ── SPICE netlist parsing ───────────────────────────────────────────


def parse_print_probe(netlist: str) -> list[str]:
    """Extract node names from .print and .probe directives."""
    lines = netlist.splitlines()
    merged: list[str] = []
    for line in lines:
        s = line.strip()
        if s.startswith("+") and merged:
            merged[-1] += " " + s[1:]
        else:
            merged.append(s)

    nodes: list[str] = []
    for line in merged:
        lo = line.lower().strip()
        if not (lo.startswith(".print") or lo.startswith(".probe")):
            continue
        for m in re.finditer(r"([vi])\(([^)]+)\)", line, re.IGNORECASE):
            vtype = m.group(1).lower()
            name = m.group(2).strip().lower()
            csv_name = name if vtype == "v" else f"{name}#branch"
            if csv_name not in nodes:
                nodes.append(csv_name)
    return nodes


# ── CSV helpers ─────────────────────────────────────────────────────


def load_csv_data(path: str) -> tuple[list[str], list[list[float]]]:
    """Load CSV, return (headers, rows_of_floats)."""
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
        rows = [[float(x) for x in row] for row in reader]
    return headers, rows


def find_sweep_var(headers: list[str]) -> str | None:
    """Find the sweep-variable column in CSV headers."""
    for h in headers:
        if h.lower().endswith("-sweep"):
            return h
    return None


# ── Node ordering ───────────────────────────────────────────────────


def order_nodes(
    headers: list[str],
    print_nodes: list[str],
    sweep_var: str | None,
) -> tuple[list[str], list[str]]:
    """Order nodes: .print/.probe first then rest.  Returns (all, primary)."""
    exclude = {sweep_var.lower()} if sweep_var else set()
    available = [h for h in headers if h.lower() not in exclude]

    primary: list[str] = []
    seen: set[str] = set()
    for pn in print_nodes:
        for h in available:
            if h.lower() == pn and h.lower() not in seen:
                primary.append(h)
                seen.add(h.lower())
                break

    rest = [h for h in available if h.lower() not in seen]

    if not primary:
        return available, available
    return primary + rest, primary


def try_find_print_nodes(csv_path: str) -> list[str]:
    """Try to locate DESIGN.md near the CSV and extract .print/.probe nodes."""
    csv_dir = os.path.dirname(os.path.abspath(csv_path))
    md_path = os.path.join(csv_dir, "DESIGN.md")
    if os.path.isfile(md_path):
        try:
            blocks = run_spice.extract_spice_blocks(md_path)
            nodes: list[str] = []
            for _, netlist in blocks:
                for n in parse_print_probe(netlist):
                    if n not in nodes:
                        nodes.append(n)
            return nodes
        except Exception:
            pass
    return []


# ── HTML generation ─────────────────────────────────────────────────

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Debug Helper — %%TITLE%%</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,monospace;
     background:#fafafa;color:#222;padding:16px}
h1{font-size:1.2em;margin-bottom:12px}
.tab-bar{display:flex;flex-wrap:wrap;gap:2px;border-bottom:2px solid #333}
.tab{padding:8px 16px;border:1px solid #ccc;border-bottom:none;background:#e8e8e8;
     cursor:pointer;font-size:.85em;border-radius:4px 4px 0 0}
.tab:hover{background:#d0d0d0}
.tab.active{background:#fff;border-color:#333;font-weight:700}
.tab-content{display:none;border:1px solid #333;border-top:none;padding:16px;background:#fff}
.tab-content.active{display:block}
.settings-bar{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:12px;align-items:center}
.settings-bar label{font-size:.8em;font-weight:700}
.settings-bar select{font-family:monospace;font-size:.85em;padding:2px 4px}
.table-wrap{overflow-x:auto}
table{border-collapse:collapse;font-size:.8em;font-family:monospace;white-space:nowrap}
th,td{border:1px solid #ccc;padding:4px 8px;text-align:right}
th{background:#f0f0f0;position:sticky;top:0}
td:first-child,th:first-child{text-align:left;background:#f8f8f8;font-weight:700;
                                position:sticky;left:0;z-index:1}
th:first-child{z-index:2}
.sep-row td{background:#e0e0e0;font-weight:700;text-align:center!important;
             font-size:.75em;color:#666;border-left:none;border-right:none}
input.meas{width:80px;font-family:monospace;font-size:.85em;padding:2px 4px;
            border:1px solid #aaa;background:#fffff0;text-align:right}
input.meas:focus{outline:2px solid #4a90d9;background:#fff}
.indicator{display:inline-block;width:8px;height:8px;border-radius:50%;margin-left:4px;
           vertical-align:middle}
.ind-ok{background:#2ecc40}.ind-warn{background:#ff851b}.ind-bad{background:#ff4136}
.ind-none{background:transparent}
.sim-col{background:#f8fbff}
.chart-wrap{max-width:900px;margin:0 auto}
.clear-btn{margin-left:auto;font-size:.75em;padding:4px 10px;cursor:pointer;
            background:#f5f5f5;border:1px solid #bbb;border-radius:3px}
.clear-btn:hover{background:#e0e0e0}
</style>
</head>
<body>
<h1>Debug Helper &mdash; %%TITLE%%</h1>
<div class="tab-bar">
%%TAB_BUTTONS%%</div>

<div id="table" class="tab-content active">
    <div class="settings-bar" id="settings-bar">
        <button class="clear-btn" onclick="clearAll()">Clear measurements</button>
    </div>
    <div class="table-wrap">
        <table id="main-table">
            <thead id="table-head"></thead>
            <tbody id="table-body"></tbody>
        </table>
    </div>
</div>

%%CHART_CONTAINERS%%
<script>
// ═══ Embedded simulation data ═══
%%DATA_JS%%
// ═══ State ═══
let selectedRows = [...INITIAL_ROWS];
let measurements = {};
let charts = {};

// ═══ Engineering notation ═══
const SI = [
    [1e12,'T'],[1e9,'G'],[1e6,'M'],[1e3,'k'],
    [1,''],[1e-3,'m'],[1e-6,'µ'],[1e-9,'n'],[1e-12,'p'],[1e-15,'f']
];

function fmtEng(val, unit) {
    if (val === 0) return '0 ' + unit;
    let av = Math.abs(val);
    for (let [scale, pfx] of SI) {
        if (av >= scale * 0.999) {
            let v = val / scale;
            let s = Number(v.toPrecision(4)).toString();
            return s + ' ' + pfx + unit;
        }
    }
    return val.toExponential(3) + ' ' + unit;
}

function nodeUnit(name) {
    return name.includes('#branch') ? 'A' : 'V';
}

function parseEng(str) {
    if (!str || !str.trim()) return null;
    str = str.trim();
    let m = str.match(/^([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)\s*([TGMkmuUnNpPfF\u00b5]?)\s*[VAva\u03a9\u2126]?\s*$/);
    if (!m) return null;
    let num = parseFloat(m[1]);
    let pfx = m[2];
    const mult = {'T':1e12,'G':1e9,'M':1e6,'k':1e3,'K':1e3,
                  'm':1e-3,'u':1e-6,'U':1e-6,'\u00b5':1e-6,
                  'n':1e-9,'p':1e-12,'f':1e-15};
    let lower = pfx;
    if (lower === 'N') lower = 'n';
    if (lower === 'P') lower = 'p';
    if (lower === 'F') lower = 'f';
    if (lower && mult[lower] !== undefined) num *= mult[lower];
    return isNaN(num) ? null : num;
}

// ═══ LocalStorage ═══
const LS_KEY = 'dbg_' + TITLE.replace(/\W/g, '_');

function loadMeasurements() {
    try {
        let s = localStorage.getItem(LS_KEY);
        if (s) measurements = JSON.parse(s);
    } catch(e) {}
}

function saveMeasurements() {
    localStorage.setItem(LS_KEY, JSON.stringify(measurements));
}

function clearAll() {
    if (!confirm('Clear all saved measurements?')) return;
    measurements = {};
    saveMeasurements();
    updateTable();
    updateAllCharts();
}

// ═══ Settings selectors ═══
function initSettings() {
    let bar = document.getElementById('settings-bar');
    let clearBtn = bar.querySelector('.clear-btn');
    for (let i = 0; i < NUM_SETTINGS; i++) {
        let label = document.createElement('label');
        label.textContent = 'Setting ' + (i + 1) + ': ';
        let sel = document.createElement('select');
        sel.id = 'setting-' + i;
        for (let j = 0; j < SWEEP_DATA.length; j++) {
            let opt = document.createElement('option');
            opt.value = j;
            opt.textContent = fmtEng(SWEEP_DATA[j], SWEEP_UNIT);
            if (j === selectedRows[i]) opt.selected = true;
            sel.appendChild(opt);
        }
        sel.addEventListener('change', function() {
            selectedRows[i] = parseInt(this.value);
            updateTable();
        });
        label.appendChild(sel);
        bar.insertBefore(label, clearBtn);
    }
}

// ═══ Table ═══
function buildTableHeader() {
    let head = document.getElementById('table-head');
    let tr1 = document.createElement('tr');
    let th0 = document.createElement('th');
    th0.rowSpan = 2; th0.textContent = 'Node';
    tr1.appendChild(th0);
    for (let i = 0; i < NUM_SETTINGS; i++) {
        let th = document.createElement('th');
        th.colSpan = 2;
        th.id = 'setting-label-' + i;
        tr1.appendChild(th);
    }
    head.appendChild(tr1);

    let tr2 = document.createElement('tr');
    for (let i = 0; i < NUM_SETTINGS; i++) {
        let ths = document.createElement('th'); ths.textContent = 'Sim'; ths.className = 'sim-col';
        let thm = document.createElement('th'); thm.textContent = 'Measured';
        tr2.appendChild(ths); tr2.appendChild(thm);
    }
    head.appendChild(tr2);
}

function updateTable() {
    let body = document.getElementById('table-body');
    body.innerHTML = '';

    for (let i = 0; i < NUM_SETTINGS; i++) {
        let lbl = document.getElementById('setting-label-' + i);
        if (lbl) lbl.textContent = fmtEng(SWEEP_DATA[selectedRows[i]], SWEEP_UNIT);
    }

    for (let ni = 0; ni < ALL_NODES.length; ni++) {
        if (ni === SEP_INDEX && SEP_INDEX > 0 && SEP_INDEX < ALL_NODES.length) {
            let sepTr = document.createElement('tr');
            sepTr.className = 'sep-row';
            let sepTd = document.createElement('td');
            sepTd.colSpan = 1 + NUM_SETTINGS * 2;
            sepTd.textContent = '\u2014 additional nodes \u2014';
            sepTr.appendChild(sepTd);
            body.appendChild(sepTr);
        }

        let node = ALL_NODES[ni];
        let unit = nodeUnit(node);
        let tr = document.createElement('tr');

        let tdName = document.createElement('td');
        tdName.textContent = node;
        tr.appendChild(tdName);

        for (let si = 0; si < NUM_SETTINGS; si++) {
            let rowIdx = selectedRows[si];
            let simVal = NODE_DATA[node][rowIdx];

            let tdSim = document.createElement('td');
            tdSim.className = 'sim-col';
            tdSim.textContent = fmtEng(simVal, unit);
            tr.appendChild(tdSim);

            let tdMeas = document.createElement('td');
            let inp = document.createElement('input');
            inp.type = 'text'; inp.className = 'meas'; inp.placeholder = unit;
            let measKey = node + ':' + rowIdx;
            if (measurements[measKey]) inp.value = measurements[measKey];

            let ind = document.createElement('span');
            ind.className = 'indicator ind-none';

            inp.addEventListener('change', (function(n, ri, indicator, sv) {
                return function() {
                    measurements[n + ':' + ri] = this.value;
                    saveMeasurements();
                    updateIndicator(indicator, sv, this.value);
                    updateAllCharts();
                };
            })(node, rowIdx, ind, simVal));

            if (measurements[measKey]) updateIndicator(ind, simVal, measurements[measKey]);

            tdMeas.appendChild(inp);
            tdMeas.appendChild(ind);
            tr.appendChild(tdMeas);
        }
        body.appendChild(tr);
    }
}

function updateIndicator(ind, simVal, measStr) {
    let measVal = parseEng(measStr);
    if (measVal === null) { ind.className = 'indicator ind-none'; return; }
    let ref = Math.abs(simVal);
    if (ref < 1e-15) ref = 1e-15;
    let pctErr = Math.abs(measVal - simVal) / ref * 100;
    ind.className = 'indicator ' + (pctErr < 5 ? 'ind-ok' : pctErr < 20 ? 'ind-warn' : 'ind-bad');
}

// ═══ Charts ═══
function initChart(tabId) {
    let idx = parseInt(tabId.split('-')[1]);
    let node = PRIMARY_NODES[idx];
    let unit = nodeUnit(node);
    let canvas = document.getElementById('chart-' + idx);

    let simPoints = SWEEP_DATA.map((x, i) => ({x: x, y: NODE_DATA[node][i]}));
    let measPoints = getMeasPoints(node);

    let chart = new Chart(canvas, {
        type: 'scatter',
        data: {
            datasets: [
                {
                    label: node + ' (sim)',
                    data: simPoints,
                    type: 'line',
                    borderColor: '#3366cc',
                    backgroundColor: 'rgba(51,102,204,0.08)',
                    fill: true,
                    pointRadius: 0,
                    borderWidth: 2,
                    order: 2
                },
                {
                    label: node + ' (measured)',
                    data: measPoints,
                    type: 'scatter',
                    borderColor: '#cc3333',
                    backgroundColor: '#cc3333',
                    pointRadius: 6,
                    pointStyle: 'crossRot',
                    order: 1
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                title: { display: true, text: node + ' vs ' + (SWEEP_VAR || 'index') },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            return ctx.dataset.label + ': ' + fmtEng(ctx.parsed.y, unit)
                                 + ' @ ' + fmtEng(ctx.parsed.x, SWEEP_UNIT);
                        }
                    }
                }
            },
            scales: {
                x: { title: { display: true, text: (SWEEP_VAR || 'index') + ' (' + SWEEP_UNIT + ')' }, type: 'linear' },
                y: { title: { display: true, text: node + ' (' + unit + ')' } }
            }
        }
    });

    charts[tabId] = { chart: chart, nodeIdx: idx };
}

function getMeasPoints(node) {
    let points = [];
    for (let ri = 0; ri < SWEEP_DATA.length; ri++) {
        let key = node + ':' + ri;
        if (measurements[key]) {
            let val = parseEng(measurements[key]);
            if (val !== null) points.push({ x: SWEEP_DATA[ri], y: val });
        }
    }
    return points;
}

function updateAllCharts() {
    for (let tabId in charts) {
        let info = charts[tabId];
        let node = PRIMARY_NODES[info.nodeIdx];
        info.chart.data.datasets[1].data = getMeasPoints(node);
        info.chart.update();
    }
}

// ═══ Tabs ═══
function switchTab(btn) {
    let tabId = btn.dataset.tab;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(tabId).classList.add('active');
    if (tabId.startsWith('plot-') && !charts[tabId]) initChart(tabId);
}

// ═══ Init ═══
loadMeasurements();
initSettings();
buildTableHeader();
updateTable();
</script>
</body>
</html>"""


def generate_html(
    title: str,
    sweep_var: str | None,
    all_nodes: list[str],
    primary_nodes: list[str],
    headers: list[str],
    rows: list[list[float]],
) -> str:
    """Generate the complete HTML debug helper."""

    # Prepare data for JSON embedding
    sweep_idx = headers.index(sweep_var) if sweep_var else None
    sweep_data = (
        [r[sweep_idx] for r in rows]
        if sweep_idx is not None
        else list(range(len(rows)))
    )
    sweep_unit = (
        "A"
        if sweep_var and sweep_var.lower().startswith("i")
        else "V"
        if sweep_var
        else ""
    )

    node_data: dict[str, list[float]] = {}
    for n in all_nodes:
        idx = headers.index(n)
        node_data[n] = [r[idx] for r in rows]

    n_rows = len(rows)
    num_settings = min(5, n_rows)
    if n_rows <= 5:
        init_rows = list(range(n_rows))
    else:
        init_rows = [
            round(i * (n_rows - 1) / (num_settings - 1))
            for i in range(num_settings)
        ]

    sep_idx = len(primary_nodes) if primary_nodes != all_nodes else -1

    # Tab buttons
    tabs_html = (
        '    <button class="tab active" data-tab="table" '
        "onclick=\"switchTab(this)\">Table</button>\n"
    )
    for i, node in enumerate(primary_nodes):
        tabs_html += (
            f'    <button class="tab" data-tab="plot-{i}" '
            f'onclick="switchTab(this)">{node}</button>\n'
        )

    # Chart containers
    charts_html = ""
    for i in range(len(primary_nodes)):
        charts_html += (
            f'<div id="plot-{i}" class="tab-content">'
            f'<div class="chart-wrap"><canvas id="chart-{i}"></canvas></div></div>\n'
        )

    # Data injection block
    data_js = (
        f"const TITLE = {json.dumps(title)};\n"
        f"const SWEEP_VAR = {json.dumps(sweep_var or '')};\n"
        f"const SWEEP_UNIT = {json.dumps(sweep_unit)};\n"
        f"const SWEEP_DATA = {json.dumps(sweep_data)};\n"
        f"const ALL_NODES = {json.dumps(all_nodes)};\n"
        f"const PRIMARY_NODES = {json.dumps(primary_nodes)};\n"
        f"const NODE_DATA = {json.dumps(node_data)};\n"
        f"const NUM_SETTINGS = {num_settings};\n"
        f"const INITIAL_ROWS = {json.dumps(init_rows)};\n"
        f"const SEP_INDEX = {sep_idx};\n"
    )

    html = TEMPLATE
    html = html.replace("%%TITLE%%", title)
    html = html.replace("%%TAB_BUTTONS%%", tabs_html)
    html = html.replace("%%CHART_CONTAINERS%%", charts_html)
    html = html.replace("%%DATA_JS%%", data_js)
    return html


# ── CLI ─────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an interactive HTML circuit debug helper."
    )
    parser.add_argument(
        "input_file",
        help="CSV, DESIGN.md, or SPICE netlist (.cir/.sp/.spice/.net)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output HTML path (default: next to input file)",
    )
    return parser.parse_args()


def process_csv(
    csv_path: str,
    print_nodes: list[str],
    title: str,
    output_path: str | None,
) -> None:
    """Load a CSV and generate the HTML debug helper."""
    headers, rows = load_csv_data(csv_path)

    if not rows:
        print(f"Warning: CSV '{csv_path}' has no data rows.", file=sys.stderr)
        return

    sweep_var = find_sweep_var(headers)
    all_nodes, primary_nodes = order_nodes(headers, print_nodes, sweep_var)

    if not all_nodes:
        print(f"Warning: no plottable nodes in '{csv_path}'.", file=sys.stderr)
        return

    html = generate_html(title, sweep_var, all_nodes, primary_nodes, headers, rows)

    out = output_path or csv_path.rsplit(".", 1)[0] + "_debug.html"
    Path(out).write_text(html, encoding="utf-8")
    print(f"Generated: {out}")


def main() -> None:
    args = parse_args()
    input_path = os.path.abspath(args.input_file)
    ext = Path(input_path).suffix.lower()

    if not os.path.isfile(input_path):
        print(f"Error: '{input_path}' not found.", file=sys.stderr)
        sys.exit(1)

    if ext == ".csv":
        print_nodes = try_find_print_nodes(input_path)
        title = Path(input_path).stem
        process_csv(input_path, print_nodes, title, args.output)

    elif ext in (".md", ".cir", ".sp", ".spice", ".net"):
        # Run simulation via run_spice
        try:
            blocks = run_spice.load_blocks(input_path)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

        print(f"Found {len(blocks)} SPICE block(s).")
        results = run_spice.run_md(input_path, save_outputs=True)
        input_dir = os.path.dirname(input_path)

        for i, (label, _text_out, vectors) in enumerate(results):
            if not vectors:
                print(f"  Block {i} ({label}): no data, skipping.")
                continue

            safe_label = re.sub(r"[^\w\-]", "_", label)[:60]
            csv_path = os.path.join(
                input_dir, f"sim_output_{i}_{safe_label}.csv"
            )
            if not os.path.isfile(csv_path):
                print(f"  Block {i}: CSV not found, skipping.")
                continue

            # Parse .print/.probe from the block's netlist
            print_nodes = parse_print_probe(blocks[i][1]) if i < len(blocks) else []

            out = args.output if len(results) == 1 and args.output else None
            process_csv(csv_path, print_nodes, label, out)
    else:
        print(f"Error: unsupported file type '{ext}'.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
