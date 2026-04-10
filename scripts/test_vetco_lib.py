"""
test_vetco_lib.py — Verify every model in vetco_eurorack.lib parses and
                    converges under ngspice.

Runs vetco_eurorack_test.cir via the KiCad ngspice DLL and scans the
simulation output for errors / fatal messages, then reports a per-model
pass/fail summary.

Usage (from repo root or scripts/):
    python scripts/test_vetco_lib.py
    python scripts/test_vetco_lib.py --verbose
"""

import argparse
import re
import sys
from pathlib import Path

# ── Repo layout ──────────────────────────────────────────────────────
SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT   = SCRIPTS_DIR.parent
MODELS_DIR  = REPO_ROOT / "models"
CIR_FILE    = MODELS_DIR / "vetco_eurorack_test.cir"

# Make run_spice importable regardless of cwd
sys.path.insert(0, str(SCRIPTS_DIR))
import run_spice  # noqa: E402 (after sys.path fixup)

# ── All 24 model names we expect to be exercised ─────────────────────
EXPECTED_MODELS = [
    # BJTs
    "VET123AP", "NTE159", "NTE123A", "NTE159M",
    "NTE47", "NTE196", "NTE197", "NTE288",
    # JFETs
    "NTE457", "NTE458", "NTE467", "NTE489",
    "VET469", "NTE460", "NTE326",
    # Op-amps
    "LM741N", "LM358N", "NTE987", "NTE976",
    "LMC6482", "LMC6492",
    # Audio amps
    "LM386", "NTE824", "NTE983",
]

# Patterns in ngspice output that indicate a real problem
FATAL_PATTERNS = [
    re.compile(r"(?i)\bfatal\b"),
    re.compile(r"(?i)error:"),
    re.compile(r"(?i)unknown subckt"),
    re.compile(r"(?i)unknown model"),
    re.compile(r"(?i)could not find (model|subckt)"),
    re.compile(r"(?i)can't find model"),
    re.compile(r"(?i)singular matrix"),
    re.compile(r"(?i)no convergence"),
    re.compile(r"(?i)timestep too small"),
]

# Patterns that look scary but are harmless
IGNORE_PATTERNS = [
    re.compile(r"(?i)warning.*lmc648"),   # our own embedded *** WARNING *** comments
    re.compile(r"(?i)\*\*\* warning"),
    re.compile(r"(?i)note:"),
    re.compile(r"(?i)circuit not parsed"),  # spurious post-.op from run_spice's "print all"
    re.compile(r"(?i)can't find the initialization file spinit"),  # no spinit in KiCad install
]


def check_output(text: str, verbose: bool = False) -> list[str]:
    """Scan ngspice text output and return a list of problem lines."""
    problems: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(p.search(stripped) for p in IGNORE_PATTERNS):
            continue
        if any(p.search(stripped) for p in FATAL_PATTERNS):
            problems.append(stripped)
        elif verbose:
            print(f"  ngspice: {stripped}")
    return problems


def check_models_in_output(text: str) -> dict[str, str]:
    """
    For each expected model name, decide PASS or FAIL based on
    whether ngspice complained about it specifically.
    Returns {model_name: "PASS" | "FAIL  <reason>"}.
    """
    results: dict[str, str] = {}
    for model in EXPECTED_MODELS:
        # Look for any error line that mentions this model name
        pattern = re.compile(re.escape(model), re.IGNORECASE)
        bad_lines = [
            line.strip()
            for line in text.splitlines()
            if pattern.search(line)
            and any(p.search(line) for p in FATAL_PATTERNS)
        ]
        if bad_lines:
            results[model] = f"FAIL  — {bad_lines[0]}"
        else:
            results[model] = "PASS"
    return results


def main():
    parser = argparse.ArgumentParser(description="Test vetco_eurorack.lib via ngspice")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print all ngspice output lines")
    args = parser.parse_args()

    if not CIR_FILE.exists():
        print(f"ERROR: Test circuit not found: {CIR_FILE}", file=sys.stderr)
        sys.exit(1)

    print(f"Test circuit : {CIR_FILE}")
    print(f"Library dir  : {MODELS_DIR}")

    try:
        dll_path, base_lib_dirs = run_spice.setup_ngspice()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # Add models/ so that `.LIB "vetco_eurorack.lib"` resolves
    lib_dirs = [str(MODELS_DIR)] + base_lib_dirs
    print(f"ngspice DLL  : {dll_path}")
    print()

    print("Running simulation (.op only — should finish in <1 s) …")
    netlist = CIR_FILE.read_text(encoding="utf-8")

    # ngspice resolves relative paths from the *temp* file location, not the
    # original .cir.  Replace .LIB with .include (always includes whole file)
    # and inject the absolute path so it resolves correctly.
    lib_abs = str(MODELS_DIR / "vetco_eurorack.lib").replace("\\", "/")
    netlist_patched = re.sub(
        r'(?im)^\.lib\s+"[^"]*"',
        f'.include "{lib_abs}"',
        netlist,
    )
    if netlist_patched == netlist:
        print(f"  WARNING: .LIB directive not found in netlist — check {CIR_FILE.name}")
    else:
        print(f"  Resolved library: {lib_abs}")
    netlist = netlist_patched

    text_output, vectors = run_spice.run_netlist(dll_path, netlist, lib_dirs)

    # ── Global error scan ────────────────────────────────────────────
    problems = check_output(text_output, verbose=args.verbose)

    # ── Per-model results ────────────────────────────────────────────
    model_results = check_models_in_output(text_output)

    # ── Report ───────────────────────────────────────────────────────
    print()
    print("=" * 55)
    print("MODEL PARSE / CONVERGENCE RESULTS")
    print("=" * 55)

    col_w = max(len(m) for m in EXPECTED_MODELS) + 2
    categories = {
        "Bipolar Junction Transistors (BJT)": EXPECTED_MODELS[:8],
        "Junction FETs (JFET)":               EXPECTED_MODELS[8:15],
        "Operational Amplifiers":             EXPECTED_MODELS[15:21],
        "Audio Amplifiers & Preamps":         EXPECTED_MODELS[21:],
    }
    fail_count = 0
    for cat, models in categories.items():
        print(f"\n  {cat}")
        for m in models:
            status = model_results[m]
            if "FAIL" in status:
                fail_count += 1
            tag = "✗" if "FAIL" in status else "✓"
            print(f"    {tag}  {m:<{col_w}} {status}")

    print()
    if problems and not any("FAIL" in s for s in model_results.values()):
        print("  Other issues detected in output:")
        for p in problems[:10]:
            print(f"    !! {p}")
        print()

    total = len(EXPECTED_MODELS)
    passed = total - fail_count
    print("=" * 55)
    if fail_count == 0 and not problems:
        print(f"  RESULT: ALL {total}/{total} MODELS PASSED ✓")
    elif fail_count == 0:
        print(f"  RESULT: {passed}/{total} models OK — review warnings above")
    else:
        print(f"  RESULT: {passed}/{total} passed, {fail_count} FAILED")
    print("=" * 55)

    # Save full ngspice log next to the .cir file
    log_path = MODELS_DIR / "vetco_eurorack_test.log"
    log_path.write_text(text_output, encoding="utf-8")
    print(f"\nFull ngspice log: {log_path}")

    sys.exit(1 if fail_count > 0 or problems else 0)


if __name__ == "__main__":
    main()
