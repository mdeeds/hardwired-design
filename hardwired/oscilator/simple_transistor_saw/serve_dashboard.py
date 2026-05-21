import os
import csv
import json
import sys
import urllib.parse
import subprocess
import argparse
import re
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

# Resolve paths dynamically
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Global variables for dynamic configuration
NETLIST_PATH = ""
CSV_PATH = ""
headers = []
data_cache = {}
stats_cache = {}

def find_run_spice_script():
    curr = os.path.dirname(os.path.abspath(__file__))
    while True:
        candidate = os.path.join(curr, "scripts", "run_spice.py")
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent
    # Default fallback assuming typical repository layout
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts", "run_spice.py")

def ensure_savecurrents_in_netlist(netlist_path):
    if not os.path.isfile(netlist_path):
        return
    try:
        with open(netlist_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        if not re.search(r'\.options\s+savecurrents', content, re.IGNORECASE):
            print(f"Injecting '.options savecurrents' into {netlist_path} for power analysis...")
            end_match = list(re.finditer(r'^\s*\.end\b', content, re.IGNORECASE | re.MULTILINE))
            if end_match:
                idx = end_match[-1].start()
                content = content[:idx] + ".options savecurrents\n" + content[idx:]
            else:
                content += "\n.options savecurrents\n"
            
            with open(netlist_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
    except Exception as e:
        print(f"Warning: Failed to ensure savecurrents in netlist: {e}")

def resolve_paths(netlist_arg):
    global NETLIST_PATH, CSV_PATH
    NETLIST_PATH = os.path.abspath(netlist_arg)
    
    # Ensure .options savecurrents is in the netlist file
    ensure_savecurrents_in_netlist(NETLIST_PATH)
    
    netlist_dir = os.path.dirname(NETLIST_PATH)
    
    # Read the first line of the netlist to get the label (matching run_spice.py naming logic)
    label = "block_0"
    if os.path.isfile(NETLIST_PATH):
        with open(NETLIST_PATH, 'r', encoding='utf-8', errors='replace') as f:
            first_line = f.readline().strip()
            if first_line.startswith("*"):
                label = first_line.lstrip("* ").strip()
            else:
                label = Path(NETLIST_PATH).stem
                
    safe_label = re.sub(r"[^\w\-]", "_", label)[:60]
    csv_filename = f"sim_output_0_{safe_label}.csv"
    CSV_PATH = os.path.join(netlist_dir, csv_filename)

def ensure_simulation():
    global NETLIST_PATH, CSV_PATH
    if not os.path.exists(CSV_PATH):
        print(f"Simulation CSV not found at {CSV_PATH}. Running initial simulation...")
        run_spice_script = find_run_spice_script()
        cmd = [sys.executable, run_spice_script, NETLIST_PATH]
        print(f"Executing: {' '.join(cmd)}")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if res.returncode != 0:
                print(f"Startup simulation failed (code {res.returncode}):\n{res.stdout}\n{res.stderr}")
            else:
                print("Startup simulation finished successfully.")
        except Exception as e:
            print(f"Error running initial simulation: {e}")

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
        
        # Reset data cache
        data_cache = {}
        # Initialize lists for each column
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
                        
    if 'time' not in data_cache:
        print("Error: Missing 'time' signal in simulation output CSV.")
        return False

    row_count = len(data_cache['time'])
    print(f"Successfully loaded {row_count} data points with {len(headers)} signals in memory.")
    
    # Calculate stats (safely handled for backward compatibility)
    calculate_stats()
    return True

def calculate_stats():
    global stats_cache, data_cache
    times = data_cache.get('time', [])
    v_ramp = data_cache.get('v_ramp', [])
    
    # If the active netlist doesn't have v_ramp, we construct a generic statistics cache
    if not v_ramp or not times:
        stats_cache = {
            "avg_peak": 0.0,
            "avg_trough": 0.0,
            "ptp": 0.0,
            "period_ms": 0.0,
            "frequency_hz": 0.0,
            "total_time_ms": round(times[-1] * 1000.0, 2) if times else 0.0,
            "datapoints": len(times) if times else 0
        }
        return
    
    try:
        # Peak and trough detection using a sliding window for sawtooth circuit
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
                
        clean_peaks = []
        for p in peaks:
            if not clean_peaks or (p[0] - clean_peaks[-1][0] > 0.0001):
                clean_peaks.append(p)
                
        clean_troughs = []
        for tr in troughs:
            if not clean_troughs or (tr[0] - clean_troughs[-1][0] > 0.0001):
                clean_troughs.append(tr)
                
        avg_peak = sum(p[1] for p in clean_peaks) / len(clean_peaks) if clean_peaks else 0.0
        avg_trough = sum(tr[1] for tr in clean_troughs) / len(clean_troughs) if clean_troughs else 0.0
        
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
    except Exception as e:
        print(f"Warning: Error calculating stats: {e}")

# --- SPICE Parser and Power Calculator Engine ---

class SubcircuitDef:
    def __init__(self, name, pins):
        self.name = name.upper()
        self.pins = [p.upper() for p in pins]
        self.components = [] # List of list of tokens

class ExpandedComponent:
    def __init__(self, refdes, type_char, nodes, value_str, parent_sub=None):
        self.refdes = refdes # Full hierarchical name, e.g. "XU1.RC1" or "R_SET"
        self.type_char = type_char # 'R', 'C', 'Q', 'D', 'V', 'I', 'G', etc.
        self.nodes = nodes # List of global node names
        self.value_str = value_str # e.g. "7.957E3" or "BC337"
        self.parent_sub = parent_sub # e.g. "XU1" or None

def parse_spice_value(val_str):
    val_str = val_str.strip().lower()
    m = re.match(r"^([+-]?[0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?)([a-z]*)", val_str)
    if not m:
        return 0.0
    num_part = float(m.group(1))
    scale_part = m.group(2)
    
    # Sort scales by length descending so 'meg' matches before 'm'
    scales = [
        ('meg', 1e6),
        ('t', 1e12),
        ('g', 1e9),
        ('k', 1e3),
        ('u', 1e-6),
        ('n', 1e-9),
        ('p', 1e-12),
        ('f', 1e-15),
        ('m', 1e-3)
    ]
    for prefix, mult in scales:
        if scale_part.startswith(prefix):
            return num_part * mult
    return num_part

def parse_spice_file(file_path, subckts_dict, visited_files=None):
    if visited_files is None:
        visited_files = set()
    
    file_path = os.path.abspath(file_path)
    if file_path in visited_files:
        return []
    visited_files.add(file_path)
    
    if not os.path.isfile(file_path):
        return []
        
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
        
    lines = []
    for line in content.splitlines():
        line_strip = line.strip()
        if not line_strip:
            continue
        if line_strip.startswith('+') and lines:
            lines[-1] = lines[-1] + " " + line_strip[1:]
        else:
            lines.append(line_strip)
            
    current_subckt = None
    components = []
    
    for line in lines:
        if line.startswith('*') or line.startswith(';'):
            continue
        if ';' in line:
            line = line.split(';', 1)[0]
        if '$' in line:
            line = line.split('$', 1)[0]
            
        tokens = line.strip().split()
        if not tokens:
            continue
            
        first_token = tokens[0].upper()
        
        if first_token == '.SUBCKT':
            if len(tokens) >= 3:
                subname = tokens[1].upper()
                pins = tokens[2:]
                current_subckt = SubcircuitDef(subname, pins)
                subckts_dict[subname] = current_subckt
            continue
        elif first_token == '.ENDS':
            current_subckt = None
            continue
            
        if first_token in ('.LIB', '.INCLUDE'):
            if len(tokens) >= 2:
                rel_path = tokens[1].strip('"\'')
                inc_path = os.path.join(os.path.dirname(file_path), rel_path)
                parse_spice_file(inc_path, subckts_dict, visited_files)
            continue
            
        if first_token.startswith('.'):
            continue
            
        if current_subckt is not None:
            current_subckt.components.append(tokens)
        else:
            components.append(tokens)
            
    return components

def expand_subcircuit(inst_name, subname, external_nodes, subckts_dict, expanded_list):
    subname = subname.upper()
    if subname not in subckts_dict:
        return
        
    subdef = subckts_dict[subname]
    pin_mapping = {}
    for i, pin in enumerate(subdef.pins):
        if i < len(external_nodes):
            pin_mapping[pin] = external_nodes[i]
            
    def resolve_node(node):
        node_upper = node.upper()
        if node_upper == '0':
            return '0'
        if node_upper in pin_mapping:
            return pin_mapping[node_upper]
        return f"{inst_name.lower()}.{node.lower()}"
        
    for comp_tokens in subdef.components:
        refdes = comp_tokens[0]
        type_char = refdes[0].upper()
        h_refdes = f"{inst_name.upper()}.{refdes.upper()}"
        
        if type_char == 'X':
            sub_type = comp_tokens[-1]
            sub_nodes = [resolve_node(n) for n in comp_tokens[1:-1]]
            expand_subcircuit(h_refdes, sub_type, sub_nodes, subckts_dict, expanded_list)
        else:
            if type_char in ('R', 'C', 'L', 'D', 'V', 'I'):
                if len(comp_tokens) >= 4:
                    nodes = [resolve_node(comp_tokens[1]), resolve_node(comp_tokens[2])]
                    val_str = comp_tokens[3]
                    expanded_list.append(ExpandedComponent(h_refdes, type_char, nodes, val_str, parent_sub=inst_name.upper()))
            elif type_char == 'Q':
                if len(comp_tokens) >= 5:
                    if len(comp_tokens) == 5:
                        nodes = [resolve_node(comp_tokens[1]), resolve_node(comp_tokens[2]), resolve_node(comp_tokens[3])]
                        val_str = comp_tokens[4]
                    else:
                        nodes = [resolve_node(comp_tokens[1]), resolve_node(comp_tokens[2]), resolve_node(comp_tokens[3]), resolve_node(comp_tokens[4])]
                        val_str = comp_tokens[5]
                    expanded_list.append(ExpandedComponent(h_refdes, type_char, nodes, val_str, parent_sub=inst_name.upper()))

def get_all_expanded_components(top_components, subckts_dict):
    expanded_list = []
    top_level_simple = []
    subcircuit_instances = {}
    
    for tokens in top_components:
        refdes = tokens[0]
        refdes_upper = refdes.upper()
        type_char = refdes_upper[0]
        
        if type_char == 'X':
            sub_type = tokens[-1]
            sub_nodes = tokens[1:-1]
            subcircuit_instances[refdes_upper] = {
                "name": refdes_upper,
                "type": sub_type,
                "nodes": sub_nodes
            }
            expand_subcircuit(refdes_upper, sub_type, sub_nodes, subckts_dict, expanded_list)
        else:
            if type_char in ('R', 'C', 'L', 'D', 'V', 'I'):
                if len(tokens) >= 4:
                    nodes = [tokens[1], tokens[2]]
                    val_str = tokens[3]
                    comp = ExpandedComponent(refdes_upper, type_char, nodes, val_str)
                    expanded_list.append(comp)
                    top_level_simple.append(comp)
            elif type_char == 'Q':
                if len(tokens) >= 5:
                    if len(tokens) == 5:
                        nodes = [tokens[1], tokens[2], tokens[3]]
                        val_str = tokens[4]
                    else:
                        nodes = [tokens[1], tokens[2], tokens[3], tokens[4]]
                        val_str = tokens[5]
                    comp = ExpandedComponent(refdes_upper, type_char, nodes, val_str)
                    expanded_list.append(comp)
                    top_level_simple.append(comp)
                    
    return expanded_list, top_level_simple, subcircuit_instances

def get_component_currents_and_power(comp, data_cache):
    time_len = len(data_cache.get('time', []))
    if time_len == 0:
        return [], []
        
    def get_voltage(node):
        node_lower = node.lower()
        if node_lower == '0':
            return [0.0] * time_len
        for k in data_cache.keys():
            if k.lower() == node_lower:
                return data_cache[k]
        return [0.0] * time_len
        
    def get_vector(vec_name):
        v_lower = vec_name.lower()
        for k in data_cache.keys():
            if k.lower() == v_lower:
                return data_cache[k]
        return None
        
    current = [0.0] * time_len
    power = [0.0] * time_len
    
    refdes_base = comp.refdes.split('.')[-1].lower()
    
    if comp.parent_sub:
        parent_lower = comp.parent_sub.lower()
        prefix = f"@{comp.type_char.lower()}.{parent_lower}.{refdes_base}"
    else:
        prefix = f"@{comp.refdes.lower()}"
        
    if comp.type_char == 'R':
        i_vec = get_vector(f"{prefix}[i]")
        if i_vec:
            r_val = parse_spice_value(comp.value_str)
            current = [abs(val) for val in i_vec]
            power = [val**2 * r_val for val in i_vec]
        else:
            v1 = get_voltage(comp.nodes[0])
            v2 = get_voltage(comp.nodes[1])
            r_val = parse_spice_value(comp.value_str)
            if r_val > 0:
                power = [(v1[j] - v2[j])**2 / r_val for j in range(time_len)]
                current = [abs(v1[j] - v2[j]) / r_val for j in range(time_len)]
                
    elif comp.type_char in ('C', 'L', 'D'):
        suffix = "[i]" if comp.type_char != 'D' else "[id]"
        i_vec = get_vector(f"{prefix}{suffix}")
        if not i_vec and comp.type_char == 'D':
            i_vec = get_vector(f"{prefix}[i]")
            
        if i_vec:
            v1 = get_voltage(comp.nodes[0])
            v2 = get_voltage(comp.nodes[1])
            current = [abs(val) for val in i_vec]
            power = [(v1[j] - v2[j]) * i_vec[j] for j in range(time_len)]
            
    elif comp.type_char == 'Q':
        ic_vec = get_vector(f"{prefix}[ic]")
        ib_vec = get_vector(f"{prefix}[ib]")
        ie_vec = get_vector(f"{prefix}[ie]")
        
        vc = get_voltage(comp.nodes[0])
        vb = get_voltage(comp.nodes[1])
        ve = get_voltage(comp.nodes[2])
        
        vs = get_voltage(comp.nodes[3]) if len(comp.nodes) >= 4 else [0.0] * time_len
        is_vec = get_vector(f"{prefix}[is]")
        
        for j in range(time_len):
            ic = ic_vec[j] if ic_vec else 0.0
            ib = ib_vec[j] if ib_vec else 0.0
            ie = ie_vec[j] if ie_vec else 0.0
            iss = is_vec[j] if is_vec else 0.0
            
            current[j] = max(abs(ic), abs(ib), abs(ie), abs(iss))
            power[j] = (vc[j] - ve[j]) * ic + (vb[j] - ve[j]) * ib
            if len(comp.nodes) >= 4:
                power[j] += (vs[j] - ve[j]) * iss
                
    elif comp.type_char == 'V':
        v_name = comp.refdes.lower()
        if comp.parent_sub:
            i_vec = get_vector(f"v.{comp.parent_sub.lower()}.{refdes_base}#branch")
            if not i_vec:
                i_vec = get_vector(f"e.{comp.parent_sub.lower()}.{refdes_base}#branch")
        else:
            i_vec = get_vector(f"{v_name}#branch")
            
        if i_vec:
            v1 = get_voltage(comp.nodes[0])
            v2 = get_voltage(comp.nodes[1])
            current = [abs(val) for val in i_vec]
            power = [(v1[j] - v2[j]) * i_vec[j] for j in range(time_len)]
            
    elif comp.type_char == 'I':
        i_vec = get_vector(f"{prefix}[current]")
        if i_vec:
            v1 = get_voltage(comp.nodes[0])
            v2 = get_voltage(comp.nodes[1])
            current = [abs(val) for val in i_vec]
            power = [(v1[j] - v2[j]) * i_vec[j] for j in range(time_len)]
            
    return current, power

def calculate_power_analysis():
    global NETLIST_PATH, data_cache
    if not data_cache or 'time' not in data_cache:
        return []
        
    time_len = len(data_cache['time'])
    
    # 1. Parse SPICE files
    subckts_dict = {}
    top_components = parse_spice_file(NETLIST_PATH, subckts_dict)
    
    # 2. Expand hierarchy (only keeping top-level simple components)
    expanded_list, top_level_simple, subcircuit_instances = get_all_expanded_components(top_components, subckts_dict)
    
    analysis_results = []
    
    # 3. Calculate for each top-level simple component
    for comp in top_level_simple:
        current, power = get_component_currents_and_power(comp, data_cache)
        if not current or not power:
            continue
            
        max_i = max(current) if current else 0.0
        
        # Accurate time-weighted average power using trapezoidal integration for variable SPICE time steps
        if 'time' in data_cache and len(data_cache['time']) > 1:
            time_arr = data_cache['time']
            total_time = time_arr[-1] - time_arr[0]
            if total_time > 0:
                integral = 0.0
                for i in range(len(power) - 1):
                    integral += 0.5 * (power[i] + power[i+1]) * (time_arr[i+1] - time_arr[i])
                avg_p = integral / total_time
            else:
                avg_p = sum(power)/len(power) if power else 0.0
        else:
            avg_p = sum(power)/len(power) if power else 0.0
        
        type_desc = {
            'R': 'Resistor',
            'C': 'Capacitor',
            'L': 'Inductor',
            'D': 'Diode',
            'Q': 'BJT',
            'V': 'Voltage Source',
            'I': 'Current Source'
        }.get(comp.type_char, 'Component')
        
        analysis_results.append({
            "name": comp.refdes,
            "type": type_desc,
            "nodes": ", ".join(comp.nodes),
            "max_current": max_i,
            "avg_power": avg_p,
            "is_subcircuit": False
        })
        
    return analysis_results

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
            
            # Dynamic alphabetically sorted signals list (filtering out subcircuit-internal nodes with '.')
            signals = sorted([h for h in headers if h != 'time' and '.' not in h], key=str.lower)
            
            response = {
                "signals": signals,
                "stats": stats_cache,
                "netlist_name": os.path.basename(NETLIST_PATH),
                "netlist_path": NETLIST_PATH
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))
            
        elif path == "/api/netlist":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                with open(NETLIST_PATH, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.wfile.write(json.dumps({
                    "netlist": content,
                    "netlist_name": os.path.basename(NETLIST_PATH)
                }).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"error": f"Failed to read netlist: {e}"}).encode('utf-8'))
            
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
            
        elif path == "/api/power":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                results = calculate_power_analysis()
                self.wfile.write(json.dumps(results).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        if path == "/api/save_netlist":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                payload = json.loads(post_data.decode('utf-8'))
                netlist_content = payload.get('netlist', '')
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"Invalid JSON payload: {e}".encode('utf-8'))
                return
            
            # 1. Overwrite the active netlist file
            try:
                # Ensure .options savecurrents is in the netlist content
                if not re.search(r'\.options\s+savecurrents', netlist_content, re.IGNORECASE):
                    end_match = list(re.finditer(r'^\s*\.end\b', netlist_content, re.IGNORECASE | re.MULTILINE))
                    if end_match:
                        # Insert right before the last .end line
                        idx = end_match[-1].start()
                        netlist_content = netlist_content[:idx] + ".options savecurrents\n" + netlist_content[idx:]
                    else:
                        netlist_content += "\n.options savecurrents\n"
                
                with open(NETLIST_PATH, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(netlist_content)
                print(f"Saved updated netlist to: {NETLIST_PATH}")
            except Exception as e:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": f"Failed to write netlist file: {e}"}).encode('utf-8'))
                return
                
            # 2. Run SPICE re-simulation dynamically
            if os.path.exists(CSV_PATH):
                try:
                    os.remove(CSV_PATH)
                    print(f"Removed old simulation CSV at: {CSV_PATH}")
                except Exception as e:
                    print(f"Warning: Could not remove old CSV: {e}")

            run_spice_script = find_run_spice_script()
            print(f"Triggering SPICE simulation from web dashboard...")
            cmd = [sys.executable, run_spice_script, NETLIST_PATH]
            
            try:
                process = subprocess.run(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE, 
                    text=True,
                    timeout=180
                )
                
                combined_output = process.stdout + "\n" + process.stderr
                
                if process.returncode != 0:
                    print("SPICE simulation failed.")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "status": "error",
                        "message": f"SPICE Simulation failed with return code {process.returncode}.",
                        "log": combined_output
                    }).encode('utf-8'))
                    return
                    
                # 3. Reload data on success
                print("SPICE simulation succeeded. Reloading CSV...")
                if load_csv_data():
                    signals = sorted([h for h in headers if h != 'time'], key=str.lower)
                    
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "status": "success",
                        "message": "Simulation succeeded and data reloaded successfully!",
                        "stats": stats_cache,
                        "signals": signals,
                        "log": combined_output
                    }).encode('utf-8'))
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "status": "error",
                        "message": "Simulation completed, but failed to parse the resulting CSV file.",
                        "log": combined_output
                    }).encode('utf-8'))
                    
            except subprocess.TimeoutExpired:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "error",
                    "message": "SPICE Simulation timed out.",
                    "log": "Process timed out."
                }).encode('utf-8'))
            except Exception as e:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "error",
                    "message": f"Internal exception occurred: {e}",
                    "log": str(e)
                }).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Interactive SPICE Simulation Dashboard</title>
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
            outline: none;
        }
        
        button:hover {
            background-color: #2a2a3f;
            border-color: var(--accent-cyan);
        }
        
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
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
        
        /* Tab styles */
        .tab-container {
            display: flex;
            border-bottom: 2px solid var(--border-color);
            margin-bottom: 16px;
            gap: 8px;
        }
        
        .tab {
            padding: 10px 20px;
            cursor: pointer;
            font-weight: 600;
            font-size: 14px;
            color: var(--text-muted);
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            transition: all 0.2s;
            border-bottom: 3px solid transparent;
            margin-bottom: -2px;
            user-select: none;
        }
        
        .tab:hover {
            color: var(--text-primary);
            background-color: rgba(255, 255, 255, 0.03);
        }
        
        .tab.active {
            color: var(--accent-cyan);
            border-bottom: 3px solid var(--accent-cyan);
            background-color: rgba(0, 255, 204, 0.05);
        }
        
        .tab-panel {
            display: none;
        }
        
        .tab-panel.active {
            display: block;
        }
        
        #chart-container {
            width: 100%;
            height: 520px;
            background-color: var(--card-bg);
            border-radius: 8px;
        }
        
        /* Monospace Code Editor Area */
        .editor-container {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        #netlist-code {
            width: 100%;
            height: 480px;
            background-color: #0b0b12;
            color: #e0e0ed;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            font-family: 'Space Mono', monospace;
            font-size: 13px;
            padding: 16px;
            line-height: 1.6;
            resize: vertical;
            outline: none;
            tab-size: 4;
        }
        
        #netlist-code:focus {
            border-color: var(--accent-cyan);
            box-shadow: 0 0 10px rgba(0, 255, 204, 0.1);
        }
        
        #netlist-code:disabled {
            opacity: 0.7;
        }
        
        .editor-actions {
            display: flex;
            justify-content: flex-end;
            gap: 12px;
            align-items: center;
        }
        
        .btn-action {
            max-width: 200px;
            padding: 10px 20px;
            font-weight: 600;
            font-size: 13px;
            border-radius: 6px;
            border: 1px solid var(--accent-cyan);
            background-color: rgba(0, 255, 204, 0.1);
            color: var(--accent-cyan);
            transition: all 0.2s;
        }
        
        .btn-action:hover:not(:disabled) {
            background-color: rgba(0, 255, 204, 0.2);
            box-shadow: 0 0 12px rgba(0, 255, 204, 0.3);
        }
        
        /* Developer Console Log styles */
        .console-container {
            background-color: #08080c;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px;
            margin-top: 16px;
        }
        
        .console-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 11px;
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            border-bottom: 1px solid #1a1a26;
            padding-bottom: 6px;
            margin-bottom: 8px;
            letter-spacing: 0.5px;
        }
        
        .console-log {
            max-height: 180px;
            overflow-y: auto;
            font-family: 'Space Mono', monospace;
            font-size: 12px;
            color: #a0a0c0;
            white-space: pre-wrap;
            line-height: 1.5;
            padding: 4px;
        }
        
        .console-log::-webkit-scrollbar {
            width: 4px;
        }
        .console-log::-webkit-scrollbar-track {
            background: #08080c;
        }
        .console-log::-webkit-scrollbar-thumb {
            background: #1e1e2d;
            border-radius: 2px;
        }
        
        .console-log.error {
            color: #ff4757;
        }
        
        .console-log.success {
            color: #2ed573;
        }
        
        .console-log.info {
            color: #70a1ff;
        }
        
        /* Power Table & Analysis Styles */
        .power-table-container {
            overflow-x: auto;
            background: rgba(255, 255, 255, 0.01);
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }
        
        .power-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            text-align: left;
        }
        
        .power-table th, .power-table td {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
        }
        
        .power-table th {
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.5px;
            background-color: rgba(255, 255, 255, 0.02);
        }
        
        .power-table th.sortable-th {
            cursor: pointer;
            user-select: none;
            position: relative;
            transition: color 0.2s, background-color 0.2s;
        }
        
        .power-table th.sortable-th:hover {
            color: var(--accent-cyan);
            background-color: rgba(255, 255, 255, 0.05);
        }
        
        .power-table th.sortable-th::after {
            content: ' ↕';
            opacity: 0.35;
            font-size: 10px;
            margin-left: 6px;
            display: inline-block;
            transition: opacity 0.2s, transform 0.2s;
        }
        
        .power-table th.sortable-th.sorted-desc::after {
            content: ' ↓';
            opacity: 1;
            color: var(--accent-cyan);
        }
        
        .power-table th.sortable-th.sorted-asc::after {
            content: ' ↑';
            opacity: 1;
            color: var(--accent-cyan);
        }
        
        .power-table tbody tr {
            transition: background-color 0.2s;
        }
        
        .power-table tbody tr:hover {
            background-color: rgba(255, 255, 255, 0.02);
        }
        
        .power-table .refdes {
            font-family: 'Space Mono', monospace;
            font-weight: 600;
            color: var(--accent-cyan);
        }
        
        .power-table .refdes.subcircuit {
            color: var(--accent-gold);
        }
        
        .power-table .type-badge {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
            background-color: #1e1e2d;
            border: 1px solid var(--border-color);
            color: var(--text-muted);
        }
        
        .power-table .nodes-val {
            font-family: 'Space Mono', monospace;
            color: var(--text-muted);
            font-size: 12px;
        }
        
        .thermal-bar-container {
            width: 120px;
            height: 6px;
            background-color: #1a1a26;
            border-radius: 3px;
            overflow: hidden;
            display: inline-block;
            vertical-align: middle;
            margin-right: 8px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        .thermal-bar-fill {
            height: 100%;
            width: 0%;
            border-radius: 3px;
            transition: width 0.5s ease-out;
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
            <h1>Interactive SPICE Simulation Dashboard</h1>
            <p id="active-netlist-subtitle" style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">Active Netlist: Loading...</p>
        </div>
        <div class="header-meta">
            <span class="status-badge"><span style="width: 6px; height: 6px; background-color: var(--accent-cyan); border-radius: 50%; display: inline-block; margin-right: 6px; box-shadow: 0 0 8px var(--accent-cyan);"></span>Server Active</span>
            <div id="source-file-info" style="font-family: 'Space Mono', monospace; font-size: 11px; margin-top: 4px;">Source: Loading...</div>
        </div>
    </header>

    <!-- Core Grid -->
    <div class="dashboard-grid">
        
        <!-- Sidebar Controls -->
        <div>
            <div class="card" style="margin-bottom: 16px;">
                <div class="card-title">Sidebar Controls</div>
                <div class="sidebar-controls">
                    
                    <div class="btn-group">
                        <button class="btn-primary" onclick="selectAll()">Select All</button>
                        <button onclick="clearAll()">Clear All</button>
                    </div>
                    
                    <div class="slider-container">
                        <div class="slider-header">
                            <span>Decimation / Downsampling</span>
                            <span class="value" id="decimate-val">20x</span>
                        </div>
                        <input type="range" id="decimate-slider" min="1" max="100" value="20" onchange="updateDecimateLabel(this.value); updatePlot();">
                        <div style="display: flex; justify-content: space-between; font-size: 9px; color: var(--text-muted); margin-top: 6px;">
                            <span>1x (Hi-Res)</span>
                            <span>20x (Smooth)</span>
                            <span>100x (Low-Res)</span>
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
        </div>
        
        <!-- Main Panel with Tabs -->
        <div>
            <div class="tab-container">
                <div class="tab active" onclick="switchTab('tab-waveforms', this)">Waveforms Dashboard</div>
                <div class="tab" onclick="switchTab('tab-power', this)">Power & Currents</div>
                <div class="tab" onclick="switchTab('tab-editor', this)">Netlist Editor</div>
            </div>
            
            <!-- Panel 1: Chart Dashboard -->
            <div id="panel-waveforms" class="tab-panel active">
                <div class="card" style="padding: 12px; min-height: 540px;">
                    <div id="chart-container"></div>
                </div>
            </div>
            
            <!-- Panel 2: Power & Currents Analysis -->
            <div id="panel-power" class="tab-panel">
                <div class="card" style="min-height: 540px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
                        <div class="card-title" style="margin-bottom:0;">Power & Currents Analysis</div>
                        <div style="font-size: 12px; color: var(--text-muted);">
                            Values calculated dynamically from simulation transient data
                        </div>
                    </div>
                    
                    <div class="power-table-container">
                        <table class="power-table">
                            <thead>
                                <tr>
                                    <th class="sortable-th" onclick="handlePowerSort('name')">RefDes</th>
                                    <th class="sortable-th" onclick="handlePowerSort('type')">Component Type</th>
                                    <th class="sortable-th" onclick="handlePowerSort('nodes')">Terminals / Nodes</th>
                                    <th class="sortable-th" onclick="handlePowerSort('max_current')">Max Leg Current</th>
                                    <th class="sortable-th" onclick="handlePowerSort('avg_power')">Avg Power Dissipation</th>
                                    <th class="sortable-th" onclick="handlePowerSort('avg_power')">Thermal Footprint</th>
                                </tr>
                            </thead>
                            <tbody id="power-table-body">
                                <tr>
                                    <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 40px;">
                                        Loading analysis data...
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <!-- Panel 3: Netlist Editor -->
            <div id="panel-editor" class="tab-panel">
                <div class="card" style="min-height: 540px;">
                    <div class="editor-container">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <div class="card-title" id="editor-card-title" style="margin-bottom:0;">Edit Netlist</div>
                            <div class="editor-actions">
                                <button class="btn-action" id="btn-save" onclick="saveAndResimulate()">Save & Re-simulate</button>
                            </div>
                        </div>
                        
                        <textarea id="netlist-code" spellcheck="false" placeholder="Loading netlist source code..."></textarea>
                        
                        <div class="console-container">
                            <div class="console-header">
                                <span>SPICE Simulation Console Log</span>
                                <span id="console-status" style="color:var(--text-muted)">Idle</span>
                            </div>
                            <div id="console-log" class="console-log info">Welcome to the interactive SPICE terminal. Load the editor, make changes, and press "Save & Re-simulate".</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
    </div>

    <script>
        let availableSignals = [];
        const palette = [
            '#00ffcc', // Vibrant Cyan
            '#00bfff', // Sky Blue
            '#ff007f', // Deep Pink
            '#ffd700', // Gold
            '#a278ff', // Violet
            '#ff7a00', // Orange
            '#2ed573', // Emerald Green
            '#ff4757', // Coral Red
            '#70a1ff', // Soft Blue
            '#5352ed', // Royal Blue
            '#ffa502'  // Bright Orange
        ];
        
        window.addEventListener('DOMContentLoaded', () => {
            fetchSignalsList();
            
            // Support Tab key indentation in textarea
            document.getElementById('netlist-code').addEventListener('keydown', function(e) {
                if (e.key === 'Tab') {
                    e.preventDefault();
                    const start = this.selectionStart;
                    const end = this.selectionEnd;
                    
                    // Insert tab character
                    this.value = this.value.substring(0, start) + "\\t" + this.value.substring(end);
                    
                    // Put caret in right place
                    this.selectionStart = this.selectionEnd = start + 1;
                }
            });
        });
        
        // Tab switching logic
        function switchTab(tabId, el) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            el.classList.add('active');
            
            document.getElementById('panel-waveforms').classList.remove('active');
            document.getElementById('panel-editor').classList.remove('active');
            document.getElementById('panel-power').classList.remove('active');
            
            if (tabId === 'tab-waveforms') {
                document.getElementById('panel-waveforms').classList.add('active');
                updatePlot();
            } else if (tabId === 'tab-power') {
                document.getElementById('panel-power').classList.add('active');
                fetchPowerAnalysis();
            } else if (tabId === 'tab-editor') {
                document.getElementById('panel-editor').classList.add('active');
                loadNetlistSource();
            }
        }
        
        let powerData = [];
        let sortKey = ''; // Starts empty for default sorting
        let sortDesc = true;

        function fetchPowerAnalysis() {
            const tableBody = document.getElementById('power-table-body');
            tableBody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 40px;">
                        Calculating dynamic power dissipation and peak branch currents...
                    </td>
                </tr>
            `;
            
            fetch('/api/power')
                .then(res => res.json())
                .then(data => {
                    powerData = data;
                    renderPowerTable();
                })
                .catch(err => {
                    console.error('Error fetching power analysis:', err);
                    tableBody.innerHTML = `
                        <tr>
                            <td colspan="6" style="text-align: center; color: var(--accent-pink); padding: 40px; font-weight: 500;">
                                Error loading power analysis from server.
                            </td>
                        </tr>
                    `;
                });
        }
        
        function formatCurrent(val) {
            if (val === null || val === undefined || isNaN(val)) return '0.00 A';
            const absVal = Math.abs(val);
            if (absVal === 0) return '0.00 A';
            if (absVal < 1e-6) return (val * 1e9).toFixed(2) + ' nA';
            if (absVal < 1e-3) return (val * 1e6).toFixed(2) + ' µA';
            if (absVal < 1.0) return (val * 1e3).toFixed(2) + ' mA';
            return val.toFixed(3) + ' A';
        }
        
        function formatPower(val) {
            if (val === null || val === undefined || isNaN(val)) return '0.00 W';
            const absVal = Math.abs(val);
            if (absVal === 0) return '0.00 W';
            if (absVal < 1e-6) return (val * 1e9).toFixed(2) + ' nW';
            if (absVal < 1e-3) return (val * 1e6).toFixed(2) + ' µW';
            if (absVal < 1.0) return (val * 1e3).toFixed(2) + ' mW';
            return val.toFixed(3) + ' W';
        }
        
        function handlePowerSort(key) {
            if (sortKey === key) {
                sortDesc = !sortDesc;
            } else {
                sortKey = key;
                sortDesc = true; // Default to descending order (higher current/power first)
            }
            
            // Update the column headers' visual status class
            const thElements = document.querySelectorAll('.power-table th.sortable-th');
            thElements.forEach(th => {
                th.classList.remove('sorted-asc', 'sorted-desc');
                if (th.getAttribute('onclick').includes(`'${key}'`)) {
                    th.classList.add(sortDesc ? 'sorted-desc' : 'sorted-asc');
                }
            });
            
            renderPowerTable();
        }
        
        function renderPowerTable() {
            const tableBody = document.getElementById('power-table-body');
            tableBody.innerHTML = '';
            
            if (!powerData || powerData.length === 0) {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 40px;">
                            No component current/power vectors found. Try triggering a simulation or checking netlist.
                        </td>
                    </tr>
                `;
                return;
            }
            
            // Create a copy of data for sorting
            let sortedData = [...powerData];
            
            if (sortKey) {
                sortedData.sort((a, b) => {
                    let valA = a[sortKey];
                    let valB = b[sortKey];
                    
                    if (typeof valA === 'string') {
                        valA = valA.toLowerCase();
                        valB = valB.toLowerCase();
                        return sortDesc ? valB.localeCompare(valA) : valA.localeCompare(valB);
                    }
                    
                    if (valA === null || valA === undefined) valA = 0;
                    if (valB === null || valB === undefined) valB = 0;
                    return sortDesc ? valB - valA : valA - valB;
                });
            } else {
                // Default sorting: subcircuits first, then top level, sorted alphabetically
                sortedData.sort((a, b) => {
                    if (a.is_subcircuit !== b.is_subcircuit) {
                        return a.is_subcircuit ? -1 : 1;
                    }
                    return a.name.localeCompare(b.name);
                });
            }
            
            // Find max power to scale the visual thermal bars
            let maxAvgPower = 0;
            powerData.forEach(item => {
                if (item.avg_power > maxAvgPower) {
                    maxAvgPower = item.avg_power;
                }
            });
            
            sortedData.forEach(item => {
                const tr = document.createElement('tr');
                
                // RefDes cell
                const tdName = document.createElement('td');
                tdName.className = 'refdes' + (item.is_subcircuit ? ' subcircuit' : '');
                tdName.innerText = item.name;
                tr.appendChild(tdName);
                
                // Type cell
                const tdType = document.createElement('td');
                const spanType = document.createElement('span');
                spanType.className = 'type-badge';
                spanType.innerText = item.type;
                tdType.appendChild(spanType);
                tr.appendChild(tdType);
                
                // Terminals cell
                const tdNodes = document.createElement('td');
                tdNodes.className = 'nodes-val';
                tdNodes.innerText = item.nodes;
                tr.appendChild(tdNodes);
                
                // Max Current cell
                const tdCurrent = document.createElement('td');
                tdCurrent.style.fontWeight = '500';
                tdCurrent.innerText = formatCurrent(item.max_current);
                tr.appendChild(tdCurrent);
                
                // Avg Power cell
                const tdPower = document.createElement('td');
                tdPower.style.fontWeight = '500';
                tdPower.innerText = formatPower(item.avg_power);
                tr.appendChild(tdPower);
                
                // Thermal Footprint / bar cell
                const tdThermal = document.createElement('td');
                
                const percentage = maxAvgPower > 0 ? (item.avg_power / maxAvgPower) * 100 : 0;
                
                const barContainer = document.createElement('div');
                barContainer.className = 'thermal-bar-container';
                
                const barFill = document.createElement('div');
                barFill.className = 'thermal-bar-fill';
                barFill.style.width = '0%'; // Start at 0% for transition
                
                // Dynamic HSL coloring: 0% is healthy green, 100% is high-temp red
                const hue = 120 - Math.min(percentage, 100) * 1.2;
                barFill.style.backgroundColor = `hsl(${hue}, 100%, 50%)`;
                barFill.style.boxShadow = `0 0 8px hsl(${hue}, 100%, 50%)`;
                
                barContainer.appendChild(barFill);
                tdThermal.appendChild(barContainer);
                
                const percentageText = document.createElement('span');
                percentageText.style.fontFamily = 'Space Mono, monospace';
                percentageText.style.fontSize = '12px';
                percentageText.style.color = 'var(--text-muted)';
                percentageText.innerText = percentage.toFixed(1) + '%';
                tdThermal.appendChild(percentageText);
                
                tr.appendChild(tdThermal);
                tableBody.appendChild(tr);
                
                // Animate bar fill
                setTimeout(() => {
                    barFill.style.width = percentage.toFixed(1) + '%';
                }, 50);
            });
        }
        
        function loadNetlistSource() {
            const textCode = document.getElementById('netlist-code');
            textCode.disabled = true;
            writeConsole("Fetching latest netlist source code from server...", "info");
            
            fetch('/api/netlist')
                .then(res => res.json())
                .then(data => {
                    if (data.netlist) {
                        textCode.value = data.netlist;
                        writeConsole("Source file loaded successfully: " + (data.netlist_name || "Netlist"), "success");
                    } else if (data.error) {
                        writeConsole("Error fetching netlist: " + data.error, "error");
                    }
                    textCode.disabled = false;
                })
                .catch(err => {
                    writeConsole("Connection failure during netlist fetch: " + err, "error");
                    textCode.disabled = false;
                });
        }
        
        function writeConsole(text, type = "info") {
            const logArea = document.getElementById('console-log');
            const statusArea = document.getElementById('console-status');
            
            logArea.className = 'console-log ' + type;
            logArea.innerText = text;
            logArea.scrollTop = logArea.scrollHeight;
            
            if (type === 'error') {
                statusArea.innerText = "Simulation Error";
                statusArea.style.color = "#ff4757";
            } else if (type === 'success') {
                statusArea.innerText = "Success";
                statusArea.style.color = "#2ed573";
            } else if (type === 'info') {
                statusArea.innerText = "Simulating...";
                statusArea.style.color = "#70a1ff";
            }
        }
        
        function saveAndResimulate() {
            const textCode = document.getElementById('netlist-code');
            const saveBtn = document.getElementById('btn-save');
            const netlistText = textCode.value;
            
            // Lock UI controls
            textCode.disabled = true;
            saveBtn.disabled = true;
            saveBtn.innerText = "Running SPICE...";
            
            writeConsole("Saving netlist and executing SPICE simulation synchronously on the server... Please wait.", "info");
            
            fetch('/api/save_netlist', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ netlist: netlistText })
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    writeConsole("SUCCESS! SPICE simulation finished and data re-calculated successfully.\\n\\nSIMULATION PROCESS OUTPUT:\\n" + data.log, "success");
                    
                    // Reload checkboxes with potential new signal names
                    if (data.signals) {
                        availableSignals = data.signals;
                        renderSignalsCheckboxes();
                    } else {
                        fetchSignalsList();
                    }
                    
                    saveBtn.innerText = "Saved successfully!";
                    setTimeout(() => {
                        saveBtn.innerText = "Save & Re-simulate";
                        saveBtn.disabled = false;
                        textCode.disabled = false;
                        
                        const waveTabEl = document.querySelector('.tab[onclick*="tab-waveforms"]');
                        switchTab('tab-waveforms', waveTabEl);
                    }, 1200);
                    
                } else {
                    writeConsole("SIMULATION FAILURE! Output logs are below:\\n\\n" + data.message + "\\n\\n" + data.log, "error");
                    saveBtn.innerText = "Save & Re-simulate";
                    saveBtn.disabled = false;
                    textCode.disabled = false;
                }
            })
            .catch(err => {
                writeConsole("CRITICAL SERVER ERROR DURING RE-SIMULATION:\\n" + err, "error");
                saveBtn.innerText = "Save & Re-simulate";
                saveBtn.disabled = false;
                textCode.disabled = false;
            });
        }
        
        function fetchSignalsList() {
            fetch('/api/signals')
                .then(res => res.json())
                .then(data => {
                    availableSignals = data.signals;
                    renderSignalsCheckboxes();
                    
                    // Update header title and source path dynamically
                    if (data.netlist_name) {
                        document.getElementById('active-netlist-subtitle').innerText = `Active Netlist: ${data.netlist_name}`;
                        document.getElementById('source-file-info').innerText = `Source: ${data.netlist_name}`;
                        
                        const editorTitleEl = document.getElementById('editor-card-title');
                        if (editorTitleEl) {
                            editorTitleEl.innerText = `Edit ${data.netlist_name}`;
                        }
                    }
                    
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
            
            availableSignals.forEach((sig, idx) => {
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
                
                const sigColor = palette[idx % palette.length];
                const dot = document.createElement('span');
                dot.className = 'priority-indicator';
                dot.style.backgroundColor = sigColor;
                dot.style.boxShadow = `0 0 6px ${sigColor}`;
                item.appendChild(dot);
                
                listDiv.appendChild(item);
            });
        }
        
        function setDefaultSelection() {
            const checkboxes = document.querySelectorAll('#signals-list input[type="checkbox"]');
            checkboxes.forEach((cb, idx) => {
                if (idx < 3) {
                    cb.checked = true;
                }
            });
            updatePlot();
        }
        
        function selectAll() {
            const checkboxes = document.querySelectorAll('#signals-list input[type="checkbox"]');
            checkboxes.forEach(cb => cb.checked = true);
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
                        const sigIdx = availableSignals.indexOf(sig);
                        const sigColor = palette[sigIdx % palette.length];
                        return {
                            x: timeMs,
                            y: data[sig],
                            name: sig,
                            type: 'scatter',
                            mode: 'lines',
                            line: {
                                width: 2.0,
                                color: sigColor
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

def run_server(start_port=8000):
    port = start_port
    max_attempts = 10
    server = None
    
    for attempt in range(max_attempts):
        try:
            server = HTTPServer(('localhost', port), DashboardHandler)
            print("=" * 70)
            print(f"  Interactive SPICE Simulation Dashboard Server Started!")
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
    parser = argparse.ArgumentParser(description="Serve a dynamic simulation dashboard for any SPICE netlist.")
    parser.add_argument(
        "netlist_path",
        nargs="?",
        default=os.path.join(BASE_DIR, "simple_transistor_saw.net"),
        help="Path to the SPICE netlist (.net, .sp, .cir, .spice) (default: local simple_transistor_saw.net)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to serve the dashboard on (default: 8000)"
    )
    args = parser.parse_args()
    
    # Resolve absolute paths and dynamically calculate CSV output name
    resolve_paths(args.netlist_path)
    
    # Ensure simulation runs at least once so CSV data is generated
    ensure_simulation()
    
    # Load the CSV data and run the HTTP server
    if load_csv_data():
        run_server(args.port)
    else:
        print("Failed to load CSV data. Aborting server start.")
        sys.exit(1)
