import os
import csv
import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

# Resolve paths dynamically
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILENAME = "sim_output_0_Precision_Sawtooth_Oscillator_Core_with_Active_BJT_Reset.csv"
CSV_PATH = os.path.join(BASE_DIR, CSV_FILENAME)

# Global variables for caching
headers = []
data_cache = {}
stats_cache = {}

def load_csv_data():
    global headers, data_cache, stats_cache
    if not os.path.exists(CSV_PATH):
        print(f"Error: CSV file not found at {CSV_PATH}")
        return False
    
    print(f"Loading simulation CSV from {CSV_PATH}...")
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        try:
            headers = next(reader)
        except StopIteration:
            print("Error: CSV is empty")
            return False
        
        # Initialize dictionary lists for each column
        for h in headers:
            data_cache[h] = []
        
        # Load and parse values
        for row in reader:
            if not row:
                continue
            for i, val in enumerate(row):
                if i < len(headers):
                    try:
                        data_cache[headers[i]].append(float(val))
                    except ValueError:
                        data_cache[headers[i]].append(val)
                        
    row_count = len(data_cache[headers[0]])
    print(f"Successfully loaded {row_count} data points with {len(headers)} signals in memory.")
    
    # Calculate stats
    calculate_stats()
    return True

def calculate_stats():
    global stats_cache, data_cache
    v_ramp = data_cache.get('v_ramp', [])
    times = data_cache.get('time', [])
    if not v_ramp or not times:
        print("Warning: v_ramp or time signals not found in CSV. Statistics skipped.")
        return
    
    # Peak and trough detection using a sliding window
    window = 15
    peaks = []
    troughs = []
    
    for i in range(window, len(v_ramp) - window):
        val = v_ramp[i]
        is_peak = True
        is_trough = True
        for j in range(i - window, i + window + 1):
            if v_ramp[j] > val:
                is_peak = False
            if v_ramp[j] < val:
                is_trough = False
        if is_peak:
            peaks.append((times[i], val))
        elif is_trough:
            troughs.append((times[i], val))
            
    # De-duplicate adjacent hits due to noise or flat spots (at least 0.1ms apart)
    clean_peaks = []
    for p in peaks:
        if not clean_peaks or (p[0] - clean_peaks[-1][0] > 0.0001):
            clean_peaks.append(p)
            
    clean_troughs = []
    for tr in troughs:
        if not clean_troughs or (tr[0] - clean_troughs[-1][0] > 0.0001):
            clean_troughs.append(tr)
            
    # Calculate averages
    avg_peak = sum(p[1] for p in clean_peaks) / len(clean_peaks) if clean_peaks else 0.0
    avg_trough = sum(tr[1] for tr in clean_troughs) / len(clean_troughs) if clean_troughs else 0.0
    
    # Calculate period and frequency
    avg_freq = 0.0
    avg_period = 0.0
    if len(clean_peaks) > 1:
        periods = [clean_peaks[i][0] - clean_peaks[i-1][0] for i in range(1, len(clean_peaks))]
        avg_period = sum(periods) / len(periods)
        avg_freq = 1.0 / avg_period if avg_period > 0 else 0.0
        
    stats_cache = {
        "avg_peak": round(avg_peak, 4),
        "avg_trough": round(avg_trough, 4),
        "ptp": round(avg_peak - avg_trough, 4),
        "period_ms": round(avg_period * 1000.0, 4),
        "frequency_hz": round(avg_freq, 2),
        "total_time_ms": round(times[-1] * 1000.0, 2),
        "datapoints": len(times)
    }
    
    print("--- Circuit Waveform Metrics Calculated ---")
    print(f"  * High Peak (Max Threshold):  {stats_cache['avg_peak']:.4f} V")
    print(f"  * Low Trough (Min Threshold): {stats_cache['avg_trough']:.4f} V")
    print(f"  * Oscillation Frequency:      {stats_cache['frequency_hz']:.2f} Hz")
    print("-" * 43)

class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Mute logging to stdout to keep console clean and readable
        pass

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)
        
        if path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_DASHBOARD.encode('utf-8'))
            
        elif path == "/api/signals":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            # Sort signals: prioritize v_ramp, v_comp_out, v_comp_in+, v_base_reset
            signals = [h for h in headers if h != 'time']
            priority = ['v_ramp', 'v_comp_out', 'v_comp_in+', 'v_base_reset']
            ordered_signals = [p for p in priority if p in signals]
            ordered_signals += [s for s in signals if s not in priority]
            
            response = {
                "signals": ordered_signals,
                "stats": stats_cache
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))
            
        elif path == "/api/data":
            cols_param = query.get('cols', [''])
            requested_cols = [c.strip() for c in cols_param[0].split(',') if c.strip() in data_cache]
            
            decimate_param = query.get('decimate', ['20'])
            try:
                decimate_val = max(1, int(decimate_param[0]))
            except ValueError:
                decimate_val = 20
                
            time_data = data_cache.get('time', [])
            sliced_time = time_data[::decimate_val]
            
            sliced_data = {"time": sliced_time}
            for col in requested_cols:
                sliced_data[col] = data_cache[col][::decimate_val]
                
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(sliced_data).encode('utf-8'))
            
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sawtooth Oscillator Simulation Dashboard</title>
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Space+Mono&display=swap" rel="stylesheet">
    <!-- Plotly.js CDN -->
    <script src="https://cdn.plot.ly/plotly-2.24.1.min.js"></script>
    <style>
        :root {
            --bg-color: #0f0f14;
            --card-bg: #151522;
            --border-color: #242436;
            --text-primary: #f0f0f5;
            --text-muted: #8e8eaf;
            --accent-cyan: #00ffcc;
            --accent-pink: #ff007f;
            --accent-gold: #ffd700;
            --accent-blue: #00bfff;
        }
        
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        
        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            line-height: 1.5;
            padding: 24px;
        }
        
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 16px;
            margin-bottom: 24px;
        }
        
        h1 {
            font-size: 24px;
            font-weight: 700;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #00ffcc, #00bfff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .header-meta {
            text-align: right;
            font-size: 13px;
            color: var(--text-muted);
        }
        
        .status-badge {
            display: inline-flex;
            align-items: center;
            background-color: rgba(0, 255, 204, 0.1);
            color: var(--accent-cyan);
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 4px;
            border: 1px solid rgba(0, 255, 204, 0.2);
        }
        
        .dashboard-grid {
            display: grid;
            grid-template-columns: 320px 1fr;
            gap: 24px;
            align-items: start;
        }
        
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
        }
        
        .card-title {
            font-size: 15px;
            font-weight: 600;
            margin-bottom: 16px;
            color: var(--text-primary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-left: 3px solid var(--accent-cyan);
            padding-left: 10px;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        
        .stat-card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 16px;
            text-align: center;
            position: relative;
            overflow: hidden;
            transition: transform 0.2s, border-color 0.2s;
        }
        
        .stat-card:hover {
            transform: translateY(-2px);
            border-color: rgba(0, 255, 204, 0.3);
        }
        
        .stat-label {
            font-size: 11px;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 6px;
        }
        
        .stat-value {
            font-size: 22px;
            font-weight: 700;
            font-family: 'Space Mono', monospace;
            color: var(--accent-cyan);
        }
        
        .stat-unit {
            font-size: 12px;
            color: var(--text-muted);
            font-weight: 400;
            margin-left: 2px;
        }
        
        .sidebar-controls {
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-bottom: 16px;
        }
        
        .btn-group {
            display: flex;
            gap: 8px;
        }
        
        button {
            flex: 1;
            background-color: #1e1e2d;
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 8px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 500;
            font-size: 12px;
            transition: all 0.2s;
        }
        
        button:hover {
            background-color: #2a2a3f;
            border-color: var(--accent-cyan);
        }
        
        button.btn-primary {
            background-color: rgba(0, 255, 204, 0.15);
            border-color: var(--accent-cyan);
            color: var(--accent-cyan);
        }
        
        button.btn-primary:hover {
            background-color: rgba(0, 255, 204, 0.25);
        }
        
        .slider-container {
            background-color: #1a1a26;
            border-radius: 8px;
            padding: 12px;
            border: 1px solid var(--border-color);
        }
        
        .slider-header {
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            color: var(--text-muted);
            margin-bottom: 6px;
        }
        
        .slider-header span.value {
            color: var(--accent-cyan);
            font-weight: 600;
            font-family: 'Space Mono', monospace;
        }
        
        input[type="range"] {
            width: 100%;
            accent-color: var(--accent-cyan);
            cursor: pointer;
        }
        
        .search-box {
            position: relative;
        }
        
        .search-box input {
            width: 100%;
            background-color: #1a1a26;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            color: var(--text-primary);
            padding: 8px 12px;
            font-size: 13px;
            outline: none;
            transition: border-color 0.2s;
        }
        
        .search-box input:focus {
            border-color: var(--accent-cyan);
        }
        
        .checkbox-container {
            max-height: 480px;
            overflow-y: auto;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            background-color: #12121c;
            padding: 8px;
        }
        
        .checkbox-container::-webkit-scrollbar {
            width: 6px;
        }
        .checkbox-container::-webkit-scrollbar-track {
            background: #12121c;
        }
        .checkbox-container::-webkit-scrollbar-thumb {
            background: #2a2a3f;
            border-radius: 3px;
        }
        .checkbox-container::-webkit-scrollbar-thumb:hover {
            background: var(--accent-cyan);
        }
        
        .checkbox-item {
            display: flex;
            align-items: center;
            padding: 8px 10px;
            border-radius: 4px;
            cursor: pointer;
            transition: background-color 0.2s;
            font-size: 13px;
            font-family: 'Space Mono', monospace;
        }
        
        .checkbox-item:hover {
            background-color: #1c1c2a;
        }
        
        .checkbox-item input {
            margin-right: 10px;
            accent-color: var(--accent-cyan);
            cursor: pointer;
            width: 15px;
            height: 15px;
        }
        
        .priority-indicator {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-left: auto;
        }
        
        .info-list {
            font-size: 13px;
            color: var(--text-muted);
        }
        
        .info-list li {
            margin-bottom: 8px;
            padding-left: 14px;
            position: relative;
        }
        
        .info-list li::before {
            content: "•";
            color: var(--accent-cyan);
            position: absolute;
            left: 0;
            font-weight: bold;
        }
        
        .info-list strong {
            color: var(--text-primary);
        }
        
        #chart-container {
            width: 100%;
            height: 520px;
            background-color: var(--card-bg);
            border-radius: 8px;
        }
        
        @media (max-width: 900px) {
            .dashboard-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>

    <header>
        <div>
            <h1>Sawtooth Oscillator Simulation Dashboard</h1>
            <p style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">Precision Sawtooth Oscillator Core with Active BJT Reset</p>
        </div>
        <div class="header-meta">
            <span class="status-badge"><span style="width: 6px; height: 6px; background-color: var(--accent-cyan); border-radius: 50%; display: inline-block; margin-right: 6px; box-shadow: 0 0 8px var(--accent-cyan);"></span>Server Active</span>
            <div style="font-family: 'Space Mono', monospace; font-size: 11px; margin-top: 4px;">Source: simple_transistor_saw.net</div>
        </div>
    </header>

    <!-- Stats Grid -->
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-label">Oscillation Frequency</div>
            <div class="stat-value" id="stat-freq">--<span class="stat-unit">Hz</span></div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Average Period</div>
            <div class="stat-value" id="stat-period">--<span class="stat-unit">ms</span></div>
        </div>
        <div class="stat-card">
            <div class="stat-label">High Peak (Max Threshold)</div>
            <div class="stat-value" id="stat-peak">--<span class="stat-unit">V</span></div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Low Trough (Min Threshold)</div>
            <div class="stat-value" id="stat-trough">--<span class="stat-unit">V</span></div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Peak-to-Peak Amplitude</div>
            <div class="stat-value" id="stat-ptp">--<span class="stat-unit">V</span></div>
        </div>
    </div>

    <!-- Core Grid -->
    <div class="dashboard-grid">
        
        <!-- Sidebar Controls -->
        <div>
            <div class="card" style="margin-bottom: 16px;">
                <div class="card-title">Sidebar Controls</div>
                <div class="sidebar-controls">
                    
                    <div class="btn-group">
                        <button class="btn-primary" onclick="loadCorePreset()">Core Signals</button>
                        <button onclick="clearAll()">Clear All</button>
                    </div>
                    
                    <div class="slider-container">
                        <div class="slider-header">
                            <span>Decimation / Downsampling</span>
                            <span class="value" id="decimate-val">20x</span>
                        </div>
                        <input type="range" id="decimate-slider" min="1" max="100" value="20" onchange="updateDecimateLabel(this.value); updatePlot();">
                        <div style="display: flex; justify-content: space-between; font-size: 9px; color: var(--text-muted); margin-top: 6px;">
                            <span>1x (100k pts)</span>
                            <span>20x (5k pts)</span>
                            <span>100x (1k pts)</span>
                        </div>
                    </div>
                    
                    <div class="search-box">
                        <input type="text" id="signal-search" placeholder="Search net signals..." onkeyup="filterSignals()">
                    </div>
                    
                </div>
                
                <div class="checkbox-container" id="signals-list">
                    <div style="text-align: center; color: var(--text-muted); padding: 20px; font-size: 13px;">Loading signals...</div>
                </div>
            </div>
            
            <div class="card">
                <div class="card-title">Circuit Notes</div>
                <ul class="info-list">
                    <li><strong>Linear Downward Ramp</strong>: Driven by the <strong>LM358</strong> and <strong>BC337</strong> constant-current sink pulling charge out of the <strong>0.01µF</strong> capacitor C1.</li>
                    <li><strong>Dynamic High Threshold</strong>: Nominal Schmitt trigger threshold is +6.0V. The capacitor reaches <strong>+6.46V</strong> due to comparator propagation delay and BC337 switch-off times.</li>
                    <li><strong>Trough Level</strong>: Reaches almost exactly <strong>-5.96V</strong>, matching the design threshold of -6.0V.</li>
                    <li><strong>Active BJT Reset</strong>: Active reset transistor pulls the capacitor rapidly back up to terminate the cycle.</li>
                </ul>
            </div>
        </div>
        
        <!-- Main Plot Card -->
        <div>
            <div class="card" style="padding: 12px; min-height: 540px;">
                <div id="chart-container"></div>
            </div>
        </div>
        
    </div>

    <script>
        let availableSignals = [];
        const priorityColors = {
            'v_ramp': '#00ffcc',      // Cyan
            'v_comp_out': '#ffd700',  // Gold
            'v_comp_in+': '#ff007f',  // Pink
            'v_base_reset': '#00bfff', // Deep Sky Blue
            'v_emit': '#a278ff',      // Violet
            'v_base': '#ff7a00',      // Orange
            'vin_ctrl': '#2ed573'     // Emerald Green
        };
        
        window.addEventListener('DOMContentLoaded', () => {
            fetchSignalsList();
        });
        
        function fetchSignalsList() {
            fetch('/api/signals')
                .then(res => res.json())
                .then(data => {
                    availableSignals = data.signals;
                    renderSignalsCheckboxes();
                    renderStats(data.stats);
                    setDefaultSelection();
                })
                .catch(err => {
                    console.error('Error fetching signals:', err);
                    document.getElementById('signals-list').innerHTML = 
                        `<div style="text-align: center; color: var(--accent-pink); padding: 20px; font-size: 13px;">Failed to load signals from server.</div>`;
                });
        }
        
        function renderSignalsCheckboxes() {
            const listDiv = document.getElementById('signals-list');
            listDiv.innerHTML = '';
            
            availableSignals.forEach(sig => {
                const item = document.createElement('label');
                item.className = 'checkbox-item';
                item.dataset.sig = sig.toLowerCase();
                
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.value = sig;
                cb.onchange = updatePlot;
                
                const nameSpan = document.createElement('span');
                nameSpan.innerText = sig;
                
                item.appendChild(cb);
                item.appendChild(nameSpan);
                
                if (priorityColors[sig]) {
                    const dot = document.createElement('span');
                    dot.className = 'priority-indicator';
                    dot.style.backgroundColor = priorityColors[sig];
                    dot.style.boxShadow = `0 0 6px ${priorityColors[sig]}`;
                    item.appendChild(dot);
                }
                
                listDiv.appendChild(item);
            });
        }
        
        function renderStats(stats) {
            if (!stats) return;
            document.getElementById('stat-freq').innerHTML = `${stats.frequency_hz.toLocaleString()}<span class="stat-unit">Hz</span>`;
            document.getElementById('stat-period').innerHTML = `${stats.period_ms.toFixed(3)}<span class="stat-unit">ms</span>`;
            document.getElementById('stat-peak').innerHTML = `${stats.avg_peak.toFixed(2)}<span class="stat-unit">V</span>`;
            document.getElementById('stat-trough').innerHTML = `${stats.avg_trough.toFixed(2)}<span class="stat-unit">V</span>`;
            document.getElementById('stat-ptp').innerHTML = `${stats.ptp.toFixed(2)}<span class="stat-unit">V</span>`;
        }
        
        function setDefaultSelection() {
            const defaults = ['v_ramp', 'v_comp_out', 'v_comp_in+'];
            const checkboxes = document.querySelectorAll('#signals-list input[type="checkbox"]');
            checkboxes.forEach(cb => {
                if (defaults.includes(cb.value)) {
                    cb.checked = true;
                }
            });
            updatePlot();
        }
        
        function loadCorePreset() {
            const core = ['v_ramp', 'v_comp_out', 'v_comp_in+'];
            const checkboxes = document.querySelectorAll('#signals-list input[type="checkbox"]');
            checkboxes.forEach(cb => {
                cb.checked = core.includes(cb.value);
            });
            updatePlot();
        }
        
        function clearAll() {
            const checkboxes = document.querySelectorAll('#signals-list input[type="checkbox"]');
            checkboxes.forEach(cb => cb.checked = false);
            updatePlot();
        }
        
        function updateDecimateLabel(val) {
            document.getElementById('decimate-val').innerText = val + 'x';
        }
        
        function filterSignals() {
            const query = document.getElementById('signal-search').value.toLowerCase().trim();
            const items = document.querySelectorAll('#signals-list .checkbox-item');
            
            items.forEach(item => {
                const name = item.dataset.sig;
                if (name.includes(query)) {
                    item.style.display = 'flex';
                } else {
                    item.style.display = 'none';
                }
            });
        }
        
        function updatePlot() {
            const selected = [];
            const checkboxes = document.querySelectorAll('#signals-list input[type="checkbox"]');
            checkboxes.forEach(cb => {
                if (cb.checked) selected.push(cb.value);
            });
            
            if (selected.length === 0) {
                Plotly.newPlot('chart-container', [], getChartLayout());
                return;
            }
            
            const decimation = document.getElementById('decimate-slider').value;
            const queryUrl = `/api/data?cols=${encodeURIComponent(selected.join(','))}&decimate=${decimation}`;
            
            fetch(queryUrl)
                .then(res => res.json())
                .then(data => {
                    const timeMs = data.time.map(t => t * 1000.0);
                    const traces = selected.map(sig => {
                        return {
                            x: timeMs,
                            y: data[sig],
                            name: sig,
                            type: 'scatter',
                            mode: 'lines',
                            line: {
                                width: sig === 'v_ramp' ? 2.5 : 1.5,
                                color: priorityColors[sig] || null
                            }
                        };
                    });
                    
                    const layout = getChartLayout();
                    Plotly.react('chart-container', traces, layout, {responsive: true});
                })
                .catch(err => {
                    console.error('Error fetching plot data:', err);
                });
        }
        
        function getChartLayout() {
            return {
                paper_bgcolor: '#151522',
                plot_bgcolor: '#101018',
                margin: { l: 60, r: 20, t: 40, b: 60 },
                font: {
                    family: 'Outfit, sans-serif',
                    color: '#f0f0f5'
                },
                xaxis: {
                    title: 'Time (ms)',
                    gridcolor: '#242436',
                    zerolinecolor: '#242436',
                    ticksuffix: ' ms'
                },
                yaxis: {
                    title: 'Voltage (V)',
                    gridcolor: '#242436',
                    zerolinecolor: '#242436',
                    autorange: true
                },
                legend: {
                    orientation: 'h',
                    y: 1.05,
                    x: 0,
                    font: { size: 12 }
                },
                hovermode: 'closest',
                dragmode: 'zoom'
            };
        }
    </script>
</body>
</html>
"""

def run_server():
    port = 8000
    max_attempts = 10
    server = None
    
    for attempt in range(max_attempts):
        try:
            server = HTTPServer(('localhost', port), DashboardHandler)
            print("=" * 70)
            print(f"  Sawtooth Oscillator Simulation Dashboard Server Started!")
            print(f"  * Local Web URL: http://localhost:{port}")
            print(f"  * Press Ctrl+C to shut down the server.")
            print("=" * 70)
            break
        except OSError as e:
            if attempt < max_attempts - 1:
                print(f"Port {port} is busy. Trying port {port + 1}...")
                port += 1
            else:
                print(f"Error: Could not bind to any port in the 8000-8009 range: {e}")
                sys.exit(1)
                
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping web server...")
        server.server_close()
        print("Server stopped. Bye!")

if __name__ == "__main__":
    if load_csv_data():
        run_server()
    else:
        print("Failed to load CSV data. Aborting server start.")
        sys.exit(1)
