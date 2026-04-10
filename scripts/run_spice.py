"""
run_spice.py — Run SPICE netlists through ngspice (shared library),
               saving CSV + text output.

Usage:
    python run_spice.py [path/to/DESIGN.md | path/to/netlist.sp] [--libdir path/to/libs]

If a .md file is given (default: DESIGN.md), SPICE blocks are extracted
from fenced ```spice code blocks.  If a SPICE file (.sp, .cir, .spice,
.net) is given, it is used directly as a netlist.

The --libdir option adds a directory to ngspice's source search path,
allowing .include/.lib directives to find model files.

Requirements:
    - Python 3.8+
    - ngspice.dll in KiCad's bin directory (auto-detected)
"""

import argparse
import csv
import ctypes
import os
import re
import sys
import tempfile
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    c_bool,
    c_char_p,
    c_double,
    c_int,
    c_short,
    c_void_p,
)
from pathlib import Path

# ── Defaults ────────────────────────────────────────────────────────
KICAD_BASE = r"C:\Program Files\KiCad"

# ── ngspice vector_info struct ──────────────────────────────────────
class NgComplex(Structure):
    _fields_ = [("cx_real", c_double), ("cx_imag", c_double)]

class VectorInfo(Structure):
    _fields_ = [
        ("v_name", c_char_p),
        ("v_type", c_int),
        ("v_flags", c_short),
        ("v_realdata", POINTER(c_double)),
        ("v_compdata", POINTER(NgComplex)),
        ("v_length", c_int),
    ]

# ── Callback types expected by ngspice shared API ───────────────────
CB_SENDCHAR = CFUNCTYPE(c_int, c_char_p, c_int, c_void_p)
CB_SENDSTAT = CFUNCTYPE(c_int, c_char_p, c_int, c_void_p)
CB_EXIT = CFUNCTYPE(c_int, c_int, c_bool, c_bool, c_int, c_void_p)
CB_SENDDATA = CFUNCTYPE(c_int, c_void_p, c_int, c_int, c_void_p)
CB_SENDINIT = CFUNCTYPE(c_int, c_void_p, c_int, c_void_p)
CB_BGTHREAD = CFUNCTYPE(c_int, c_bool, c_int, c_void_p)


def extract_spice_blocks(md_path: str) -> list[tuple[str, str]]:
    """Return list of (label, netlist_text) from ```spice fenced blocks."""
    text = Path(md_path).read_text(encoding="utf-8")
    pattern = re.compile(r"```spice\s*\n(.*?)```", re.DOTALL)
    blocks = pattern.findall(text)
    results = []
    for i, block in enumerate(blocks):
        first_line = block.strip().split("\n")[0]
        if first_line.startswith("*"):
            label = first_line.lstrip("* ").strip()
        else:
            label = f"block_{i}"
        results.append((label, block))
    return results


def find_kicad_version_dir() -> str:
    """Find the newest KiCad version directory."""
    if not os.path.isdir(KICAD_BASE):
        raise FileNotFoundError(f"KiCad base directory not found: {KICAD_BASE}")

    versions = []
    for entry in os.listdir(KICAD_BASE):
        ver_dir = os.path.join(KICAD_BASE, entry)
        if os.path.isdir(ver_dir):
            try:
                ver = tuple(int(p) for p in entry.split("."))
            except ValueError:
                ver = (0,)
            versions.append((ver, ver_dir))
    versions.sort(key=lambda x: x[0], reverse=True)

    if versions:
        return versions[0][1]

    raise FileNotFoundError(
        f"No KiCad version directories found in {KICAD_BASE}"
    )


def find_ngspice_dll(kicad_dir: str) -> str:
    """Locate ngspice.dll inside a KiCad version directory."""
    candidate = os.path.join(kicad_dir, "bin", "ngspice.dll")
    if os.path.isfile(candidate):
        return candidate
    raise FileNotFoundError(
        f"ngspice.dll not found at {candidate}"
    )


def run_netlist(
    dll_path: str,
    netlist: str,
    lib_dirs: list[str] | None = None,
) -> tuple[str, dict[str, list[float]]]:
    """Run netlist, return (text_output, {vector_name: [values]})."""
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
    dll_dir = os.path.dirname(dll_path)
    os.add_dll_directory(dll_dir)
    ng = ctypes.CDLL(dll_path)

    # ── ngSpice_Init ────────────────────────────────────────────────
    ng.ngSpice_Init.restype = c_int
    ng.ngSpice_Init.argtypes = [
        CB_SENDCHAR, CB_SENDSTAT, CB_EXIT,
        CB_SENDDATA, CB_SENDINIT, CB_BGTHREAD,
        c_void_p,
    ]
    rc = ng.ngSpice_Init(
        cb_sendchar, cb_sendstat, cb_exit,
        cb_senddata, cb_sendinit, cb_bgthread,
        None,
    )
    if rc != 0:
        raise RuntimeError(f"ngSpice_Init failed with code {rc}")

    # ── Configure command interface ─────────────────────────────────
    ng.ngSpice_Command.restype = c_int
    ng.ngSpice_Command.argtypes = [c_char_p]

    # ── Set library search paths ────────────────────────────────────
    if lib_dirs:
        for lib_dir in lib_dirs:
            abs_dir = os.path.abspath(lib_dir).replace("\\", "/")
            cmd = f'set sourcepath = ( {abs_dir} $sourcepath )'.encode("utf-8")
            ng.ngSpice_Command(cmd)
            print(f"  Added library path: {abs_dir}")

    # ── Write netlist to temp file, then source it ──────────────────
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".cir", delete=False, encoding="utf-8"
    ) as f:
        cleaned = netlist.strip()
        if not cleaned.lower().endswith(".end"):
            cleaned += "\n.end\n"
        f.write(cleaned)
        tmp_path = f.name

    try:
        ng.ngSpice_Command(f"source {tmp_path}".encode("utf-8"))
        ng.ngSpice_Command(b"run")

        # Also run print all for the text output (backward compat)
        ng.ngSpice_Command(b"print all")
    finally:
        os.unlink(tmp_path)

    # ── Extract vector data via ngspice API ─────────────────────────
    vectors: dict[str, list[float]] = {}

    # ngSpice_CurPlot() → current plot name
    ng.ngSpice_CurPlot.restype = c_char_p
    ng.ngSpice_CurPlot.argtypes = []
    plot_name = ng.ngSpice_CurPlot()
    if not plot_name:
        return "\n".join(output_lines), vectors
    plot_name = plot_name.decode("utf-8")

    # ngSpice_AllVecs(plotname) → null-terminated char** of vector names
    ng.ngSpice_AllVecs.restype = POINTER(c_char_p)
    ng.ngSpice_AllVecs.argtypes = [c_char_p]
    vec_names_ptr = ng.ngSpice_AllVecs(plot_name.encode("utf-8"))
    if not vec_names_ptr:
        return "\n".join(output_lines), vectors

    vec_names: list[str] = []
    i = 0
    while vec_names_ptr[i]:
        vec_names.append(vec_names_ptr[i].decode("utf-8"))
        i += 1

    # ngGet_Vec_Info(vecname) → pointer to VectorInfo struct
    ng.ngGet_Vec_Info.restype = POINTER(VectorInfo)
    ng.ngGet_Vec_Info.argtypes = [c_char_p]

    for vname in vec_names:
        qualified = f"{plot_name}.{vname}"
        vi_ptr = ng.ngGet_Vec_Info(qualified.encode("utf-8"))
        if not vi_ptr:
            continue
        vi = vi_ptr.contents
        length = vi.v_length
        if vi.v_realdata and length > 0:
            vectors[vname] = [vi.v_realdata[j] for j in range(length)]
        elif vi.v_compdata and length > 0:
            # For complex data, store magnitude
            vectors[vname] = [
                (vi.v_compdata[j].cx_real**2 + vi.v_compdata[j].cx_imag**2)**0.5
                for j in range(length)
            ]

    return "\n".join(output_lines), vectors


def write_csv(csv_path: str, vectors: dict[str, list[float]]) -> None:
    """Write vectors dict to a CSV file."""
    if not vectors:
        return
    names = list(vectors.keys())
    length = len(vectors[names[0]])
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(names)
        for i in range(length):
            writer.writerow([vectors[name][i] for name in names])


def setup_ngspice(
    extra_lib_dirs: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Find ngspice DLL and assemble library search paths.

    Returns (dll_path, lib_dirs).
    """
    kicad_dir = find_kicad_version_dir()
    dll_path = find_ngspice_dll(kicad_dir)

    lib_dirs = list(extra_lib_dirs or [])
    kicad_spice_lib = os.path.join(kicad_dir, "share", "kicad", "symbols")
    if os.path.isdir(kicad_spice_lib):
        lib_dirs.append(kicad_spice_lib)

    return dll_path, lib_dirs


SPICE_EXTENSIONS = {".sp", ".cir", ".spice", ".net"}


def is_spice_file(path: str) -> bool:
    """Return True if *path* looks like a raw SPICE netlist file."""
    return Path(path).suffix.lower() in SPICE_EXTENSIONS


def load_blocks(path: str) -> list[tuple[str, str]]:
    """Return (label, netlist) pairs from *path*.

    For .md files, extracts fenced ```spice blocks.
    For SPICE files, returns the whole file as a single block.
    """
    if is_spice_file(path):
        text = Path(path).read_text(encoding="utf-8")
        first_line = text.strip().split("\n")[0]
        if first_line.startswith("*"):
            label = first_line.lstrip("* ").strip()
        else:
            label = Path(path).stem
        return [(label, text)]
    else:
        blocks = extract_spice_blocks(path)
        if not blocks:
            raise ValueError(f"No ```spice blocks found in '{path}'.")
        return blocks


def run_md(
    md_path: str,
    extra_lib_dirs: list[str] | None = None,
    save_outputs: bool = True,
) -> list[tuple[str, str, dict[str, list[float]]]]:
    """Load SPICE netlist(s) from *md_path* and run each, return results.

    Accepts .md files (extracts ```spice blocks) or SPICE files directly.
    Returns list of (label, text_output, vectors) per block.
    When *save_outputs* is True, writes .txt and .csv next to the source file.
    """
    if not os.path.isfile(md_path):
        raise FileNotFoundError(f"'{md_path}' not found.")

    blocks = load_blocks(md_path)

    dll_path, lib_dirs = setup_ngspice(extra_lib_dirs)
    md_dir = os.path.dirname(os.path.abspath(md_path))
    results = []

    for i, (label, netlist) in enumerate(blocks):
        text_output, vectors = run_netlist(dll_path, netlist, lib_dirs)

        if save_outputs:
            safe_label = re.sub(r"[^\w\-]", "_", label)[:60]
            out_path = os.path.join(md_dir, f"sim_output_{i}_{safe_label}.txt")
            Path(out_path).write_text(text_output, encoding="utf-8")
            if vectors:
                csv_path = os.path.join(md_dir, f"sim_output_{i}_{safe_label}.csv")
                write_csv(csv_path, vectors)

        results.append((label, text_output, vectors))

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run SPICE netlists from .md or .sp/.cir/.spice/.net files."
    )
    parser.add_argument(
        "md_path",
        nargs="?",
        default="DESIGN.md",
        help="Path to a DESIGN.md or SPICE netlist file (default: DESIGN.md)",
    )
    parser.add_argument(
        "--libdir",
        action="append",
        default=[],
        help="Add a directory to ngspice's library search path "
             "(can be specified multiple times)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    md_path = args.md_path

    if not os.path.isfile(md_path):
        print(f"Error: '{md_path}' not found.", file=sys.stderr)
        sys.exit(1)

    try:
        blocks = load_blocks(md_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    kind = "SPICE file" if is_spice_file(md_path) else f"'{md_path}'"
    print(f"Found {len(blocks)} SPICE block(s) in {kind}.")
    dll_path, lib_dirs = setup_ngspice(args.libdir)
    print(f"Using ngspice: {dll_path}")
    if lib_dirs:
        print(f"Library paths: {', '.join(lib_dirs)}")
    print()

    md_dir = os.path.dirname(os.path.abspath(md_path))
    for i, (label, netlist) in enumerate(blocks):
        safe_label = re.sub(r"[^\w\-]", "_", label)[:60]
        print(f"{'='*60}")
        print(f"Running block {i}: {label}")
        print(f"{'='*60}")

        text_output, vectors = run_netlist(dll_path, netlist, lib_dirs)

        # Save text output (backward compatible)
        out_name = f"sim_output_{i}_{safe_label}.txt"
        out_path = os.path.join(md_dir, out_name)
        Path(out_path).write_text(text_output, encoding="utf-8")
        print(f">> Text output saved to: {out_path}")

        # Save CSV
        if vectors:
            csv_name = f"sim_output_{i}_{safe_label}.csv"
            csv_path = os.path.join(md_dir, csv_name)
            write_csv(csv_path, vectors)
            print(f">> CSV output saved to:  {csv_path}")
            print(f"   Vectors: {', '.join(vectors.keys())}")
            print(f"   Data points: {len(vectors[list(vectors.keys())[0]])}")
        else:
            print(">> No vector data extracted (simulation may have failed)")

        print()


if __name__ == "__main__":
    main()
