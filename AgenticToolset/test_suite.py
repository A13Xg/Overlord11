#!/usr/bin/env python3
"""
AgenticToolset - Integration Test Suite
=========================================
Exercises every tool (8) and validates every agent definition (9).
Produces a structured pass/fail report.

Usage:
    python test_suite.py              # Run all tests
    python test_suite.py --verbose    # Verbose output
    python test_suite.py --tools      # Tools only
    python test_suite.py --agents     # Agents only
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = BASE_DIR / "tools" / "python"
AGENTS_DIR = BASE_DIR / "agents"

# --- Test Results Tracking ---

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.details = []

    def record(self, name: str, passed: bool, message: str = ""):
        if passed:
            self.passed += 1
            self.details.append({"name": name, "status": "PASS", "message": message})
        else:
            self.failed += 1
            self.details.append({"name": name, "status": "FAIL", "message": message})

    def skip(self, name: str, reason: str):
        self.skipped += 1
        self.details.append({"name": name, "status": "SKIP", "message": reason})

    def summary(self) -> dict:
        return {
            "total": self.passed + self.failed + self.skipped,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
        }


results = TestResults()
VERBOSE = False


def log(msg: str):
    print(msg)


def vlog(msg: str):
    if VERBOSE:
        print(f"    {msg}")


# --- Tool Runner ---

def run_tool(tool_name: str, args: list, test_name: str,
             expect_json: bool = True, expect_error: bool = False) -> dict:
    """Run a tool CLI command and validate the output."""
    cmd = [sys.executable, str(TOOLS_DIR / f"{tool_name}.py")] + args

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, cwd=str(BASE_DIR),
        )
    except subprocess.TimeoutExpired:
        results.record(test_name, False, "Timed out after 30s")
        log(f"  FAIL  {test_name} (timeout)")
        return {}
    except Exception as e:
        results.record(test_name, False, f"Exception: {e}")
        log(f"  FAIL  {test_name} ({e})")
        return {}

    if expect_error:
        ok = proc.returncode != 0
        results.record(test_name, ok,
                       f"exit={proc.returncode}" if ok else "Expected error but got success")
        log(f"  {'PASS' if ok else 'FAIL'}  {test_name}")
        return {}

    if proc.returncode != 0:
        results.record(test_name, False,
                       f"exit={proc.returncode}: {proc.stderr[:200]}")
        log(f"  FAIL  {test_name} (exit {proc.returncode})")
        vlog(proc.stderr[:300])
        return {}

    if expect_json:
        try:
            output = json.loads(proc.stdout)
            results.record(test_name, True)
            log(f"  PASS  {test_name}")
            return output
        except json.JSONDecodeError:
            results.record(test_name, False,
                           f"Invalid JSON output: {proc.stdout[:200]}")
            log(f"  FAIL  {test_name} (bad JSON)")
            return {}
    else:
        results.record(test_name, True, proc.stdout[:200])
        log(f"  PASS  {test_name}")
        return {"_raw": proc.stdout}


# === TOOL TESTS ===

def test_session_manager(session_id: str):
    """Test session_manager: create, status, log_change, log_agent, log_tool,
    add_note, close, list, active."""
    log("\n--- session_manager ---")

    # status
    run_tool("session_manager",
             ["--action", "status", "--session_id", session_id],
             "session_manager: status")

    # log_change
    run_tool("session_manager",
             ["--action", "log_change", "--session_id", session_id,
              "--data", json.dumps({
                  "file": "test_file.py", "action": "created",
                  "summary": "Integration test file"})],
             "session_manager: log_change")

    # log_agent
    run_tool("session_manager",
             ["--action", "log_agent", "--session_id", session_id,
              "--data", '{"agent_id": "AGNT_DIR_01"}'],
             "session_manager: log_agent")

    # log_tool
    run_tool("session_manager",
             ["--action", "log_tool", "--session_id", session_id,
              "--data", '{"tool_name": "project_scanner"}'],
             "session_manager: log_tool")

    # add_note
    run_tool("session_manager",
             ["--action", "add_note", "--session_id", session_id,
              "--data", '{"note": "Integration test note"}'],
             "session_manager: add_note")

    # active
    run_tool("session_manager",
             ["--action", "active"],
             "session_manager: active")


def test_project_scanner(session_id: str):
    """Test project_scanner: scan, compact, depth."""
    log("\n--- project_scanner ---")

    out = run_tool("project_scanner",
                   ["--path", str(BASE_DIR), "--session_id", session_id],
                   "project_scanner: full scan")
    if out:
        ok = out.get("project_name") == "AgenticToolset"
        results.record("project_scanner: correct project_name", ok,
                       f"got: {out.get('project_name')}")
        log(f"  {'PASS' if ok else 'FAIL'}  project_scanner: correct project_name")

    run_tool("project_scanner",
             ["--path", str(BASE_DIR), "--compact", "--session_id", session_id],
             "project_scanner: compact mode")

    run_tool("project_scanner",
             ["--path", str(BASE_DIR), "--depth", "2", "--session_id", session_id],
             "project_scanner: depth=2")


def test_dependency_analyzer(session_id: str):
    """Test dependency_analyzer: full analysis, security check."""
    log("\n--- dependency_analyzer ---")

    run_tool("dependency_analyzer",
             ["--path", str(BASE_DIR), "--session_id", session_id],
             "dependency_analyzer: full analysis")

    run_tool("dependency_analyzer",
             ["--path", str(BASE_DIR), "--check", "security",
              "--session_id", session_id],
             "dependency_analyzer: security check")


def test_code_analyzer(session_id: str):
    """Test code_analyzer: single file, project-wide, specific checks."""
    log("\n--- code_analyzer ---")

    run_tool("code_analyzer",
             ["--file", str(TOOLS_DIR / "log_manager.py"),
              "--session_id", session_id],
             "code_analyzer: single file (log_manager.py)")

    run_tool("code_analyzer",
             ["--path", str(TOOLS_DIR), "--language", "python",
              "--session_id", session_id],
             "code_analyzer: project python files")

    run_tool("code_analyzer",
             ["--file", str(TOOLS_DIR / "session_manager.py"),
              "--check", "complexity", "--session_id", session_id],
             "code_analyzer: complexity check")


def test_metrics_collector(session_id: str):
    """Test metrics_collector: LOC, files, functions."""
    log("\n--- metrics_collector ---")

    run_tool("metrics_collector",
             ["--path", str(BASE_DIR), "--metric", "loc",
              "--session_id", session_id],
             "metrics_collector: LOC metrics")

    run_tool("metrics_collector",
             ["--path", str(BASE_DIR), "--metric", "files",
              "--session_id", session_id],
             "metrics_collector: file metrics")

    run_tool("metrics_collector",
             ["--path", str(BASE_DIR), "--metric", "functions",
              "--session_id", session_id],
             "metrics_collector: function metrics")


def test_scaffold_generator(session_id: str, temp_dir: Path):
    """Test scaffold_generator: list templates, generate scaffold."""
    log("\n--- scaffold_generator ---")

    out = run_tool("scaffold_generator",
                   ["--list-templates", "--session_id", session_id],
                   "scaffold_generator: list templates")
    if out:
        ok = isinstance(out, list) and len(out) >= 4
        results.record("scaffold_generator: has >= 4 templates", ok,
                       f"count={len(out) if isinstance(out, list) else 'N/A'}")
        log(f"  {'PASS' if ok else 'FAIL'}  scaffold_generator: has >= 4 templates")

    scaffold_dir = temp_dir / "test_scaffold"
    out = run_tool("scaffold_generator",
                   ["--template", "python_cli", "--name", "test_app",
                    "--output", str(scaffold_dir),
                    "--description", "Test application",
                    "--session_id", session_id],
                   "scaffold_generator: generate python_cli")
    if out:
        ok = out.get("status") == "success" and out.get("total_files", 0) > 0
        results.record("scaffold_generator: scaffold has files", ok,
                       f"files={out.get('total_files')}")
        log(f"  {'PASS' if ok else 'FAIL'}  scaffold_generator: scaffold has files")


def test_log_manager(session_id: str):
    """Test log_manager: log_decision, log_agent_switch, log_error,
    log_event, query, summary, list_sessions."""
    log("\n--- log_manager ---")

    run_tool("log_manager",
             ["--action", "log_decision", "--session_id", session_id,
              "--data", json.dumps({
                  "agent": "AGNT_ARC_02",
                  "decision": "Use REST API",
                  "reasoning": "Integration test decision"})],
             "log_manager: log_decision")

    run_tool("log_manager",
             ["--action", "log_agent_switch", "--session_id", session_id,
              "--data", json.dumps({
                  "from": "AGNT_DIR_01", "to": "AGNT_ARC_02",
                  "reason": "Design phase"})],
             "log_manager: log_agent_switch")

    run_tool("log_manager",
             ["--action", "log_error", "--session_id", session_id,
              "--data", json.dumps({
                  "source": "test_suite", "error": "Test error message"})],
             "log_manager: log_error")

    run_tool("log_manager",
             ["--action", "log_event", "--session_id", session_id,
              "--data", json.dumps({
                  "event_type": "test_event", "detail": "Integration test"})],
             "log_manager: log_event")

    run_tool("log_manager",
             ["--action", "query", "--session_id", session_id, "--last_n", "10"],
             "log_manager: query")

    run_tool("log_manager",
             ["--action", "summary", "--session_id", session_id],
             "log_manager: summary")

    run_tool("log_manager",
             ["--action", "list_sessions"],
             "log_manager: list_sessions")


def test_web_scraper(session_id: str):
    """Test web_scraper: detect_type, scrape_full, extract_article, extract_text, search, find_feeds, parse_feed."""
    log("\n--- web_scraper ---")

    # detect_type
    out = run_tool("web_scraper",
                   ["--action", "detect_type", "--url", "https://example.com",
                    "--session_id", session_id],
                   "web_scraper: detect_type")
    if out:
        ok = "detection" in out and "detected_type" in out.get("detection", {})
        results.record("web_scraper: detect_type returns detection", ok,
                       f"type={out.get('detection', {}).get('detected_type', 'N/A')}")
        log(f"  {'PASS' if ok else 'FAIL'}  web_scraper: detect_type returns detection")

    # extract_text
    out = run_tool("web_scraper",
                   ["--action", "extract_text", "--url", "https://example.com",
                    "--session_id", session_id],
                   "web_scraper: extract_text")
    if out:
        ok = "text" in out or "full_text" in out
        results.record("web_scraper: extract_text returns text", ok)
        log(f"  {'PASS' if ok else 'FAIL'}  web_scraper: extract_text returns text")

    # search (DuckDuckGo)
    out = run_tool("web_scraper",
                   ["--action", "search", "--query", "python programming",
                    "--max_results", "3", "--session_id", session_id],
                   "web_scraper: search")
    if out:
        ok = "results" in out and isinstance(out["results"], list)
        results.record("web_scraper: search returns results list", ok,
                       f"count={out.get('count', 'N/A')}")
        log(f"  {'PASS' if ok else 'FAIL'}  web_scraper: search returns results list")

    # find_feeds (example.com likely has no feeds - that's fine, tests the code path)
    out = run_tool("web_scraper",
                   ["--action", "find_feeds",
                    "--url", "https://example.com",
                    "--session_id", session_id],
                   "web_scraper: find_feeds")
    if out:
        ok = "feeds_found" in out or "feeds" in out
        results.record("web_scraper: find_feeds returns structure", ok,
                       f"feeds_found={out.get('feeds_found', 'N/A')}")
        log(f"  {'PASS' if ok else 'FAIL'}  web_scraper: find_feeds returns structure")

    # parse_feed (use a known public RSS feed)
    out = run_tool("web_scraper",
                   ["--action", "parse_feed",
                    "--url", "https://www.reddit.com/r/python/.rss",
                    "--max_entries", "3", "--session_id", session_id],
                   "web_scraper: parse_feed")
    if out:
        ok = "entries" in out or "feed_info" in out
        results.record("web_scraper: parse_feed returns entries", ok,
                       f"entry_count={out.get('entry_count', 'N/A')}")
        log(f"  {'PASS' if ok else 'FAIL'}  web_scraper: parse_feed returns entries")


# === AGENT VALIDATION ===

AGENTS = [
    ("orchestrator.md",    "AGNT_DIR_01", "Orchestrator"),
    ("architect.md",       "AGNT_ARC_02", "Architect"),
    ("implementer.md",     "AGNT_COD_03", "Implementer"),
    ("reviewer.md",        "AGNT_REV_04", "Reviewer"),
    ("debugger.md",        "AGNT_DBG_05", "Debugger"),
    ("researcher.md",      "AGNT_RES_06", "Researcher"),
    ("tester.md",          "AGNT_TST_07", "Tester"),
    ("doc_writer.md",      "AGNT_DOC_08", "Doc Writer"),
    ("web_scraper_specialist.md",  "AGNT_WSC_09", "Web Scraper Specialist"),
]


def test_agents():
    """Validate all agent definition files."""
    log("\n=== AGENT VALIDATION ===")

    for filename, agent_id, agent_name in AGENTS:
        log(f"\n--- {agent_id} ({agent_name}) ---")
        agent_file = AGENTS_DIR / filename
        test_prefix = f"agent:{agent_id}"

        # File exists
        if not agent_file.exists():
            results.record(f"{test_prefix}: file exists", False,
                           f"{filename} not found")
            log(f"  FAIL  {test_prefix}: file exists")
            continue

        results.record(f"{test_prefix}: file exists", True)
        log(f"  PASS  {test_prefix}: file exists")

        content = agent_file.read_text(encoding="utf-8")

        checks = {
            "has agent ID": agent_id in content,
            "has Identity section": "## Identity" in content,
            "has Responsibilities": "Responsibilities" in content,
            "has Workflow/Process/Methodology/Principles": (
                "Workflow" in content or "Process" in content
                or "Methodology" in content or "Principles" in content
            ),
            "has Output Format": "Output Format" in content,
            "has Quality Checklist": "Quality Checklist" in content,
            "no stale CT_ prefix": "CT_" not in content,
            "no stale ClaudeToolset": "ClaudeToolset" not in content,
            "references AgenticToolset": "AgenticToolset" in content,
        }

        for check_name, passed in checks.items():
            results.record(f"{test_prefix}: {check_name}", passed)
            log(f"  {'PASS' if passed else 'FAIL'}  {test_prefix}: {check_name}")


# === CONFIG VALIDATION ===

def test_config():
    """Validate config.json has all agents and tools registered."""
    log("\n=== CONFIG VALIDATION ===")

    config_path = BASE_DIR / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as e:
        results.record("config.json: readable", False, str(e))
        log(f"  FAIL  config.json: readable ({e})")
        return

    results.record("config.json: readable", True)
    log("  PASS  config.json: readable")

    # Check project name
    ok = config.get("project_name") == "AgenticToolset"
    results.record("config.json: project_name=AgenticToolset", ok,
                   f"got: {config.get('project_name')}")
    log(f"  {'PASS' if ok else 'FAIL'}  config.json: project_name=AgenticToolset")

    # Check all agents registered
    agent_reg = config.get("agent_registry", {})
    for _, agent_id, agent_name in AGENTS:
        ok = agent_id in agent_reg
        results.record(f"config.json: {agent_id} registered", ok)
        log(f"  {'PASS' if ok else 'FAIL'}  config.json: {agent_id} registered")

    # Check all tools registered
    tool_reg = config.get("tool_registry", {})
    expected_tools = [
        "log_manager", "project_scanner", "dependency_analyzer",
        "code_analyzer", "session_manager", "metrics_collector",
        "scaffold_generator", "web_scraper",
    ]
    for tool_name in expected_tools:
        ok = tool_name in tool_reg
        results.record(f"config.json: {tool_name} registered", ok)
        log(f"  {'PASS' if ok else 'FAIL'}  config.json: {tool_name} registered")

    # Check no stale references
    config_text = config_path.read_text(encoding="utf-8")
    ok = "ClaudeToolset" not in config_text
    results.record("config.json: no ClaudeToolset refs", ok)
    log(f"  {'PASS' if ok else 'FAIL'}  config.json: no ClaudeToolset refs")

    ok = "CT_DIR" not in config_text and "CT_ARC" not in config_text
    results.record("config.json: no CT_ agent IDs", ok)
    log(f"  {'PASS' if ok else 'FAIL'}  config.json: no CT_ agent IDs")


# === MAIN ===

def main():
    global VERBOSE
    import argparse

    parser = argparse.ArgumentParser(
        description="AgenticToolset Integration Test Suite"
    )
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")
    parser.add_argument("--tools", action="store_true",
                        help="Run tool tests only")
    parser.add_argument("--agents", action="store_true",
                        help="Run agent tests only")
    args = parser.parse_args()
    VERBOSE = args.verbose

    run_tools = not args.agents or args.tools
    run_agents = not args.tools or args.agents

    log("=" * 60)
    log("AgenticToolset Integration Test Suite")
    log("=" * 60)
    start_time = time.time()

    temp_dir = Path(tempfile.mkdtemp(prefix="agentictoolset_test_"))
    session_id = None

    try:
        if run_tools:
            log("\n=== TOOL TESTS ===")

            # Create a session first (used by all other tests)
            log("\n--- session_manager (create) ---")
            out = run_tool("session_manager",
                           ["--action", "create",
                            "--description", "Integration test session"],
                           "session_manager: create")
            session_id = out.get("session_id", "test_fallback")
            log(f"  Session ID: {session_id}")

            test_session_manager(session_id)
            test_project_scanner(session_id)
            test_dependency_analyzer(session_id)
            test_code_analyzer(session_id)
            test_metrics_collector(session_id)
            test_scaffold_generator(session_id, temp_dir)
            test_log_manager(session_id)
            test_web_scraper(session_id)

            # Close the session
            log("\n--- session_manager (close) ---")
            run_tool("session_manager",
                     ["--action", "close", "--session_id", session_id,
                      "--description", "Test session completed"],
                     "session_manager: close")

            run_tool("session_manager",
                     ["--action", "list"],
                     "session_manager: list (post-close)")

        if run_agents:
            test_agents()

        # Always run config validation
        test_config()

    finally:
        # Cleanup
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

    # --- Report ---
    duration = time.time() - start_time
    summary = results.summary()

    log("\n" + "=" * 60)
    log("TEST RESULTS")
    log("=" * 60)
    log(f"  Total:   {summary['total']}")
    log(f"  Passed:  {summary['passed']}")
    log(f"  Failed:  {summary['failed']}")
    log(f"  Skipped: {summary['skipped']}")
    log(f"  Duration: {duration:.1f}s")
    log("")

    if summary["failed"] > 0:
        log("FAILURES:")
        for d in results.details:
            if d["status"] == "FAIL":
                log(f"  - {d['name']}: {d['message']}")
        log("")

    if summary["failed"] == 0:
        log("ALL TESTS PASSED")
        sys.exit(0)
    else:
        log(f"FAILED ({summary['failed']} failures)")
        sys.exit(1)


if __name__ == "__main__":
    main()
