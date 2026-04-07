"""
run_spice.py — Extract SPICE netlists from a DESIGN.md file and run them
               through ngspice (shared library), saving the output.

Usage:
    python run_spice.py [path/to/DESIGN.md]

If no path is given, defaults to DESIGN.md in the current directory.

Requirements:
    - Python 3.8+
    - ngspice.dll in KiCad's bin directory (auto-detected)
"""

import ctypes
import os
import re
import sys
import tempfile
from ctypes import (
    CFUNCTYPE,
    POINTER,
    c_bool,
    c_char_p,
    c_double,
    c_int,
    c_void_p,
)
from pathlib import Path

# ── Defaults ────────────────────────────────────────────────────────
NGSPICE_DLL_PATHS = [
    r"C:\Program Files\KiCad\10.0\bin\ngspice.dll",
    r"C:\Program Files\KiCad\9.0\bin\ngspice.dll",
]

# ── Callback types expected by ngspice shared API ───────────────────
# int SendChar(char* msg, int id, void* user)
CB_SENDCHAR = CFUNCTYPE(c_int, c_char_p, c_int, c_void_p)
# int SendStat(char* msg, int id, void* user)
CB_SENDSTAT = CFUNCTYPE(c_int, c_char_p, c_int, c_void_p)
# int ControlledExit(int status, bool immediate, bool quit, int id, void* user)
CB_EXIT = CFUNCTYPE(c_int, c_int, c_bool, c_bool, c_int, c_void_p)
# int SendData(void* vecvaluesall, int count, int id, void* user)
CB_SENDDATA = CFUNCTYPE(c_int, c_void_p, c_int, c_int, c_void_p)
# int SendInitData(void* vecinfoall, int id, void* user)
CB_SENDINIT = CFUNCTYPE(c_int, c_void_p, c_int, c_void_p)
# int BGThreadRunning(bool running, int id, void* user)
CB_BGTHREAD = CFUNCTYPE(c_int, c_bool, c_int, c_void_p)


def extract_spice_blocks(md_path: str) -> list[tuple[str, str]]:
    """Return list of (label, netlist_text) from ```spice fenced blocks."""
    text = Path(md_path).read_text(encoding="utf-8")
    pattern = re.compile(r"```spice\s*\n(.*?)```", re.DOTALL)
    blocks = pattern.findall(text)
    results = []
    for i, block in enumerate(blocks):
        # Use the first comment line as a label, or a generic name
        first_line = block.strip().split("\n")[0]
        if first_line.startswith("*"):
            label = first_line.lstrip("* ").strip()
        else:
            label = f"block_{i}"
        results.append((label, block))
    return results


def find_ngspice_dll() -> str:
    """Locate ngspice.dll, checking known paths."""
    for p in NGSPICE_DLL_PATHS:
        if os.path.isfile(p):
            return p
    raise FileNotFoundError(
        "ngspice.dll not found. Searched:\n  " + "\n  ".join(NGSPICE_DLL_PATHS)
    )


def run_netlist(dll_path: str, netlist: str) -> str:
    """Load ngspice shared lib, source the netlist, run, return captured output."""
    output_lines: list[str] = []

    # ── Callbacks ───────────────────────────────────────────────────
    @CB_SENDCHAR
    def cb_sendchar(msg, ng_id, user):
        line = msg.decode("utf-8", errors="replace") if msg else ""
        output_lines.append(line)
        return 0

    @CB_SENDSTAT
    def cb_sendstat(msg, ng_id, user):
        return 0

    @CB_EXIT
    def cb_exit(status, immediate, quit_flag, ng_id, user):
        return 0

    @CB_SENDDATA
    def cb_senddata(vecs, count, ng_id, user):
        return 0

    @CB_SENDINIT
    def cb_sendinit(vecs, ng_id, user):
        return 0

    @CB_BGTHREAD
    def cb_bgthread(running, ng_id, user):
        return 0

    # ── Load DLL ────────────────────────────────────────────────────
    # Add the DLL directory to the DLL search path
    dll_dir = os.path.dirname(dll_path)
    os.add_dll_directory(dll_dir)
    ng = ctypes.CDLL(dll_path)

    # ── ngSpice_Init ────────────────────────────────────────────────
    ng.ngSpice_Init.restype = c_int
    ng.ngSpice_Init.argtypes = [
        CB_SENDCHAR,   # SendChar
        CB_SENDSTAT,   # SendStat
        CB_EXIT,       # ControlledExit
        CB_SENDDATA,   # SendData
        CB_SENDINIT,   # SendInitData
        CB_BGTHREAD,   # BGThreadRunning
        c_void_p,      # userData
    ]
    rc = ng.ngSpice_Init(
        cb_sendchar, cb_sendstat, cb_exit,
        cb_senddata, cb_sendinit, cb_bgthread,
        None,
    )
    if rc != 0:
        raise RuntimeError(f"ngSpice_Init failed with code {rc}")

    # ── Write netlist to temp file, then source it ──────────────────
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".cir", delete=False, encoding="utf-8"
    ) as f:
        # ngspice requires a title line and .end
        cleaned = netlist.strip()
        if not cleaned.lower().endswith(".end"):
            cleaned += "\n.end\n"
        f.write(cleaned)
        tmp_path = f.name

    try:
        ng.ngSpice_Command.restype = c_int
        ng.ngSpice_Command.argtypes = [c_char_p]

        # Source the circuit file
        cmd = f"source {tmp_path}".encode("utf-8")
        ng.ngSpice_Command(cmd)

        # Run the simulation
        ng.ngSpice_Command(b"run")

        # Print results (invokes the .print statements in the netlist)
        ng.ngSpice_Command(b"print all")
    finally:
        os.unlink(tmp_path)

    return "\n".join(output_lines)


def main():
    md_path = sys.argv[1] if len(sys.argv) > 1 else "DESIGN.md"
    if not os.path.isfile(md_path):
        print(f"Error: '{md_path}' not found.", file=sys.stderr)
        sys.exit(1)

    blocks = extract_spice_blocks(md_path)
    if not blocks:
        print(f"No ```spice blocks found in '{md_path}'.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(blocks)} SPICE block(s) in '{md_path}'.")
    dll_path = find_ngspice_dll()
    print(f"Using ngspice: {dll_path}\n")

    # Run each block and save output alongside the .md file
    md_dir = os.path.dirname(os.path.abspath(md_path))
    for i, (label, netlist) in enumerate(blocks):
        safe_label = re.sub(r"[^\w\-]", "_", label)[:60]
        print(f"{'='*60}")
        print(f"Running block {i}: {label}")
        print(f"{'='*60}")

        output = run_netlist(dll_path, netlist)

        # Save to file
        out_name = f"sim_output_{i}_{safe_label}.txt"
        out_path = os.path.join(md_dir, out_name)
        Path(out_path).write_text(output, encoding="utf-8")
        print(output)
        print(f"\n>> Output saved to: {out_path}\n")


if __name__ == "__main__":
    main()
