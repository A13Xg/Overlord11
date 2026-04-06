"""
Overlord11 - Simple Test Launcher
===================================
Runs the full test suite and outputs a clean PASS / FAIL report.
Designed for quick CI checks and agentic pipelines.

Usage:
    python tests/run_tests.py                    run all tests, print report
    python tests/run_tests.py --skip-web         skip internet-dependent tests
    python tests/run_tests.py --tool calculator  run one tool
    python tests/run_tests.py --json             emit machine-readable JSON only
"""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── constants ──────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
TEST_SCRIPT  = SCRIPT_DIR / "test.py"
RESULTS_JSON = SCRIPT_DIR / "test_results.json"

ANSI_GREEN  = "\033[92m"
ANSI_RED    = "\033[91m"
ANSI_YELLOW = "\033[93m"
ANSI_CYAN   = "\033[96m"
ANSI_BOLD   = "\033[1m"
ANSI_DIM    = "\033[2m"
ANSI_RESET  = "\033[0m"


def _no_color() -> bool:
    """Return True when colour output should be suppressed."""
    return (
        os.environ.get("NO_COLOR")
        or not sys.stdout.isatty()
        or "--no-color" in sys.argv
        or "--json" in sys.argv          # JSON mode: pure text
    )


def c(code: str) -> str:
    """Return ANSI code or empty string depending on color mode."""
    return "" if _no_color() else code


def run_suite(extra_args: list[str]) -> int:
    """
    Invoke tests/test.py as a subprocess with --quiet mode (summary + failures only)
    so the inner suite handles all complexity.  Writes test_results.json.

    Returns:
        Exit code from the test process (0 = all pass, 1 = failures).
    """
    cmd = [sys.executable, str(TEST_SCRIPT), "--quiet", "--output", str(RESULTS_JSON)]
    cmd.extend(extra_args)
    proc = subprocess.run(cmd, capture_output=False)  # let output flow to terminal
    return proc.returncode


def print_summary() -> int:
    """
    Read test_results.json and print a compact PASS / FAIL table.

    Returns:
        Number of failed tests.
    """
    if not RESULTS_JSON.exists():
        print(f"{c(ANSI_RED)}No results file found at {RESULTS_JSON}{c(ANSI_RESET)}")
        return 1

    data = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    total   = data.get("total_tests", 0)
    passed  = data.get("passed", 0)
    failed  = data.get("failed", 0)
    results = data.get("results", [])

    # Group by tool for per-tool summary
    tools: dict[str, dict] = {}
    for entry in results:
        t = entry["tool"]
        if t not in tools:
            tools[t] = {"pass": 0, "fail": 0, "failures": []}
        if entry["passed"]:
            tools[t]["pass"] += 1
        else:
            tools[t]["fail"] += 1
            tools[t]["failures"].append(entry["test"])

    print()
    print(f"{c(ANSI_BOLD)}{'─' * 72}{c(ANSI_RESET)}")
    print(f"{c(ANSI_BOLD)}  OVERLORD11 TEST REPORT{c(ANSI_RESET)}")
    print(f"{c(ANSI_DIM)}  Session: {data.get('session_id', '?')}  |  Run: {data.get('run_at', '?')[:19]}{c(ANSI_RESET)}")
    print(f"{c(ANSI_BOLD)}{'─' * 72}{c(ANSI_RESET)}")
    print()

    col_w = 30   # tool name column width
    print(f"  {c(ANSI_BOLD)}{'TOOL':<{col_w}} STATUS   PASS/TOTAL  FAILURES{c(ANSI_RESET)}")
    print(f"  {'─' * 68}")

    for tool_name, stats in sorted(tools.items()):
        tool_total  = stats["pass"] + stats["fail"]
        all_pass    = stats["fail"] == 0
        status_str  = f"{c(ANSI_GREEN)}PASS{c(ANSI_RESET)}" if all_pass else f"{c(ANSI_RED)}FAIL{c(ANSI_RESET)}"
        score_str   = f"{stats['pass']}/{tool_total}"
        fail_detail = ""
        if stats["failures"]:
            # Show first failure name, truncated
            first = stats["failures"][0][:35]
            extras = len(stats["failures"]) - 1
            fail_detail = first + (f" +{extras} more" if extras else "")
        print(f"  {tool_name:<{col_w}} {status_str:<4}     {score_str:<10}  {c(ANSI_DIM)}{fail_detail}{c(ANSI_RESET)}")

    print()
    print(f"{c(ANSI_BOLD)}{'─' * 72}{c(ANSI_RESET)}")

    # Overall result
    if failed == 0:
        badge = f"{c(ANSI_GREEN)}{c(ANSI_BOLD)}ALL PASS{c(ANSI_RESET)}"
    else:
        badge = f"{c(ANSI_RED)}{c(ANSI_BOLD)}{failed} FAILED{c(ANSI_RESET)}"

    print(f"  {badge}   {passed}/{total} tests  |  {len(tools)} tools")
    print(f"{c(ANSI_BOLD)}{'─' * 72}{c(ANSI_RESET)}")
    print()

    return failed


def print_json_report() -> int:
    """Print the raw JSON results file — for machine / pipeline consumption."""
    if not RESULTS_JSON.exists():
        print(json.dumps({"error": "No results file found"}))
        return 1
    data = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return data.get("failed", 1)


def main() -> None:
    """
    Parse a minimal set of flags, run the suite, then print the report.
    Any flag not understood here is forwarded directly to tests/test.py.
    """
    args = sys.argv[1:]

    json_mode  = "--json" in args
    skip_web   = "--skip-web" in args
    no_color   = "--no-color" in args

    # Flags to forward to the inner test runner
    forward: list[str] = []
    i = 0
    known_local = {"--json", "--no-color"}
    while i < len(args):
        if args[i] in known_local:
            i += 1
            continue
        forward.append(args[i])
        # If this flag takes a value (e.g., --tool calculator), include the next token
        if args[i] in ("--tool", "--output") and i + 1 < len(args):
            i += 1
            forward.append(args[i])
        i += 1

    # Always use no-color when piping / JSON mode
    if no_color or json_mode:
        forward.append("--no-color")

    if not json_mode:
        print(f"\n{c(ANSI_CYAN)}{c(ANSI_BOLD)}  Overlord11 Test Launcher{c(ANSI_RESET)}")
        print(f"  Running suite...\n")

    exit_code = run_suite(forward)

    if json_mode:
        failed = print_json_report()
    else:
        failed = print_summary()

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
