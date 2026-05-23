#!/usr/bin/env python3
"""
Breadboard layout server for SPICE netlists.

Usage:
    python server.py --netfile path/to/circuit.net [--port 8080]

Parses the SPICE .net file, extracts components and nets, and serves
an interactive breadboard visualization. If a .bb file exists alongside
the .net file, it is loaded as the saved layout state.
"""

import argparse
import http.server
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# ---------------------------------------------------------------------------
# SPICE Netlist Parser
# ---------------------------------------------------------------------------

# Component type classification based on SPICE element prefixes
ELEMENT_TYPES = {
    'R': '2pin',    # Resistor
    'C': '2pin',    # Capacitor
    'L': '2pin',    # Inductor
    'D': '2pin',    # Diode
    'V': '2pin',    # Voltage source
    'I': '2pin',    # Current source
    'Q': '3pin',    # BJT Transistor
    'J': '3pin',    # JFET
    'M': '3pin',    # MOSFET (simplified to 3-pin for breadboard)
    'X': 'subckt',  # Subcircuit instance (IC or module)
    'P': '3pin',    # Potentiometer (3-pin)
}

# Pin labels by component type
PIN_LABELS = {
    'R': ['1', '2'],
    'C': ['+', '-'],
    'L': ['1', '2'],
    'D': ['A', 'K'],
    'V': ['+', '-'],
    'I': ['+', '-'],
    'Q': ['C', 'B', 'E'],      # Collector, Base, Emitter
    'J': ['D', 'G', 'S'],      # Drain, Gate, Source
    'M': ['D', 'G', 'S'],      # Drain, Gate, Source
    'P': ['CW', 'W', 'CCW'],   # Clockwise, Wiper, Counter-clockwise
}

# Nets that are always considered "wired" (power rails)
POWER_NETS = {'vcc', 'vee', 'gnd', '0'}


def parse_netlist(filepath):
    """Parse a SPICE netlist file and extract components and nets.

    Returns:
        dict with keys:
            'components': list of component dicts
            'nets': dict mapping net_name -> list of {component, pin_index, pin_label}
            'title': circuit title string
            'subckt_definitions': set of subcircuit names defined in the file
    """
    components = []
    nets = {}
    title = ''
    subckt_definitions = set()
    in_subckt = False

    with open(filepath, 'r') as f:
        lines = f.readlines()

    # First pass: find .SUBCKT definitions so we can skip their internals
    for line in lines:
        stripped = line.strip()
        m = re.match(r'\.SUBCKT\s+(\S+)', stripped, re.IGNORECASE)
        if m:
            subckt_definitions.add(m.group(1).upper())

    # Second pass: parse top-level components
    for line in lines:
        stripped = line.strip()

        # Skip empty lines and comments
        if not stripped or stripped.startswith('*'):
            continue

        # Title
        if stripped.lower().startswith('.title'):
            title = stripped[6:].strip()
            continue

        # Track subcircuit blocks to skip internal elements
        if re.match(r'\.SUBCKT\b', stripped, re.IGNORECASE):
            in_subckt = True
            continue
        if re.match(r'\.ends\b', stripped, re.IGNORECASE):
            in_subckt = False
            continue

        # Skip lines inside subcircuit definitions
        if in_subckt:
            continue

        # Skip directives
        if stripped.startswith('.'):
            continue

        # Parse component instances
        tokens = stripped.split()
        if len(tokens) < 2:
            continue

        name = tokens[0]
        prefix = name[0].upper()

        if prefix not in ELEMENT_TYPES:
            continue

        comp_type = ELEMENT_TYPES[prefix]

        # Extract net connections based on component type
        if comp_type == '2pin':
            if len(tokens) < 3:
                continue
            pin_nets = [tokens[1], tokens[2]]
            pin_labels = PIN_LABELS.get(prefix, ['1', '2'])
            # Extract value (everything after the two net names that isn't a param)
            value_parts = []
            for t in tokens[3:]:
                if '=' in t:
                    break
                value_parts.append(t)
            value = ' '.join(value_parts) if value_parts else ''

            components.append({
                'name': name,
                'type': '2pin',
                'prefix': prefix,
                'pins': pin_nets,
                'pin_labels': pin_labels,
                'value': value,
                'slots': 5,
            })

        elif comp_type == '3pin':
            if len(tokens) < 4:
                continue
            pin_nets = [tokens[1], tokens[2], tokens[3]]
            pin_labels = PIN_LABELS.get(prefix, ['1', '2', '3'])
            model = tokens[4] if len(tokens) > 4 else ''

            components.append({
                'name': name,
                'type': '3pin',
                'prefix': prefix,
                'pins': pin_nets,
                'pin_labels': pin_labels,
                'value': model,
                'slots': 3,
            })

        elif comp_type == 'subckt':
            # Subcircuit instance: X<name> <net1> <net2> ... <subckt_name> [params]
            # Find the subcircuit name by matching against known definitions
            # or take the last non-parameter token
            subckt_name = None
            param_nets = []
            for i, t in enumerate(tokens[1:], 1):
                if '=' in t:
                    break
                # Check if this token is a known subcircuit
                if t.upper() in subckt_definitions:
                    subckt_name = t
                    param_nets = tokens[1:i]
                    break
                param_nets.append(t)

            if subckt_name is None:
                # Heuristic: last token before any param is the subckt name
                non_param = [t for t in tokens[1:] if '=' not in t]
                if len(non_param) >= 2:
                    subckt_name = non_param[-1]
                    param_nets = non_param[:-1]
                else:
                    continue

            # For ICs (8-pin DIP), we need exactly the right pin count
            # Pad or truncate to 8 pins for DIP layout
            actual_pins = param_nets
            if len(actual_pins) < 8:
                # Pad with 'NC' (no connect)
                actual_pins = actual_pins + ['NC'] * (8 - len(actual_pins))
            elif len(actual_pins) > 8:
                actual_pins = actual_pins[:8]

            pin_labels = [f'{i+1}' for i in range(8)]

            components.append({
                'name': name,
                'type': 'ic',
                'prefix': prefix,
                'pins': actual_pins,
                'pin_labels': pin_labels,
                'value': subckt_name,
                'slots': 8,
            })

    # Build net index
    for comp in components:
        for pin_idx, net_name in enumerate(comp['pins']):
            net_key = net_name.lower()
            if net_key == 'nc':
                continue
            if net_key not in nets:
                nets[net_key] = []
            nets[net_key].append({
                'component': comp['name'],
                'pin_index': pin_idx,
                'pin_label': comp['pin_labels'][pin_idx],
            })

    return {
        'components': components,
        'nets': nets,
        'title': title,
        'subckt_definitions': list(subckt_definitions),
    }


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------

class BreadboardHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler for the breadboard application."""

    netlist_data = None
    bb_filepath = None
    html_dir = None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/' or path == '/index.html':
            self.serve_file('index.html', 'text/html')
        elif path == '/api/netlist':
            self.send_json(self.netlist_data)
        elif path == '/api/layout':
            layout = self.load_bb_file()
            self.send_json(layout)
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == '/api/layout':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            try:
                layout_data = json.loads(body)
                self.save_bb_file(layout_data)
                self.send_json({'status': 'ok'})
            except json.JSONDecodeError:
                self.send_error(400, 'Invalid JSON')
        else:
            self.send_error(404)

    def serve_file(self, filename, content_type):
        filepath = os.path.join(self.html_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', f'{content_type}; charset=utf-8')
            self.send_header('Content-Length', len(content.encode('utf-8')))
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
        except FileNotFoundError:
            self.send_error(404)

    def send_json(self, data):
        body = json.dumps(data).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def load_bb_file(self):
        if self.bb_filepath and os.path.exists(self.bb_filepath):
            try:
                with open(self.bb_filepath, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {'wires': [], 'bridges': [], 'component_positions': {}}

    def save_bb_file(self, data):
        if self.bb_filepath:
            with open(self.bb_filepath, 'w') as f:
                json.dump(data, f, indent=2)

    def log_message(self, format, *args):
        # Quieter logging
        pass


def main():
    parser = argparse.ArgumentParser(
        description='Breadboard layout server for SPICE netlists'
    )
    parser.add_argument(
        '--netfile', '-n',
        required=True,
        help='Path to the SPICE .net file'
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=8080,
        help='Port to serve on (default: 8080)'
    )
    args = parser.parse_args()

    netfile = Path(args.netfile).resolve()
    if not netfile.exists():
        print(f"Error: File not found: {netfile}", file=sys.stderr)
        sys.exit(1)

    # Look for matching .bb file
    bb_file = netfile.with_suffix('.bb')

    print(f"Parsing netlist: {netfile}")
    netlist_data = parse_netlist(str(netfile))
    print(f"  Title: {netlist_data['title']}")
    print(f"  Components: {len(netlist_data['components'])}")
    for comp in netlist_data['components']:
        print(f"    {comp['name']} ({comp['type']}): {comp['pins']} = {comp['value']}")
    print(f"  Nets: {len(netlist_data['nets'])}")
    print(f"  Layout file: {bb_file} ({'found' if bb_file.exists() else 'will create on save'})")

    # Configure handler
    BreadboardHandler.netlist_data = netlist_data
    BreadboardHandler.bb_filepath = str(bb_file)
    BreadboardHandler.html_dir = str(Path(__file__).parent)

    server = http.server.HTTPServer(('0.0.0.0', args.port), BreadboardHandler)
    print(f"\nServing breadboard at http://localhost:{args.port}")
    print("Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == '__main__':
    main()