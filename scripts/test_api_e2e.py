"""
End-to-end API integration tests — submits real jobs to the running server,
polls for completion, and validates workspace artifacts.

Usage: python scripts/test_api_e2e.py
Server must be running on localhost:7900.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any
import urllib.request
import urllib.parse
import urllib.error

BASE = "http://localhost:7900"
ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "workspace"

RESET  = "\033[0m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"

# ---------------------------------------------------------------------------
# HTTP helpers (no requests dep needed — uses stdlib)
# ---------------------------------------------------------------------------

def _req(method: str, path: str, body: dict | None = None, token: str | None = None) -> dict:
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode()
        raise RuntimeError(f"HTTP {exc.code} {exc.reason} — {body_text[:300]}") from exc


def login() -> str:
    r = _req("POST", "/api/auth/login", {"username": "admin", "password": "admin"})
    return r["token"]


def submit_job(token: str, title: str, prompt: str) -> str:
    r = _req("POST", "/api/jobs", {"title": title, "prompt": prompt, "auto_start": True}, token)
    return r["job_id"]


def get_job(token: str, job_id: str) -> dict:
    return _req("GET", f"/api/jobs/{job_id}", token=token)


def poll_until_done(token: str, job_id: str, timeout_s: int = 300) -> dict:
    deadline = time.monotonic() + timeout_s
    interval = 3
    while time.monotonic() < deadline:
        job = get_job(token, job_id)
        status = job.get("status")
        if status in ("completed", "failed"):
            return job
        if status == "rate_limited":
            print(f"    {YELLOW}[rate_limited — waiting]{RESET}", end="\r")
        time.sleep(interval)
    return get_job(token, job_id)  # final check


# ---------------------------------------------------------------------------
# Artifact helpers
# ---------------------------------------------------------------------------

def find_session_dir(job: dict) -> Path | None:
    sid = job.get("session_id")
    if not sid:
        return None
    d = WORKSPACE / sid
    return d if d.exists() else None


def find_final_output(session_dir: Path) -> str | None:
    for name in ("final_output.md", "answer.md", "final_output.txt"):
        p = session_dir / name
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


def find_artifact_files(session_dir: Path) -> list[str]:
    arts = session_dir / "artifacts"
    if not arts.exists():
        return []
    return [str(p.relative_to(session_dir)) for p in arts.rglob("*") if p.is_file()]


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

passed: list[str] = []
failed: list[tuple[str, str]] = []


def run_job_test(
    token: str,
    test_name: str,
    title: str,
    prompt: str,
    checks: list[tuple[str, Any]] | None = None,
    timeout_s: int = 300,
) -> dict:
    """
    Submit a job, wait for completion, run checks.
    checks: list of (type, value) where type is:
      - "status" → job['status'] == value
      - "completion_mode" → job['completion_mode'] == value
      - "tool_calls" → job['tool_call_count'] >= value
      - "output_contains" → final_output text contains value (case-insensitive)
      - "artifact_exists" → any artifact path contains value substring
    """
    print(f"\n  {CYAN}▶ {test_name}{RESET}")
    print(f"    Submitting: {title!r}")
    try:
        job_id = submit_job(token, title, prompt)
        print(f"    Job ID: {job_id}")
    except Exception as exc:
        failed.append((test_name, f"Submit failed: {exc}"))
        print(f"  {RED}FAIL{RESET} {test_name}: Submit error: {exc}")
        return {}

    print(f"    Polling (up to {timeout_s}s)...", end=" ", flush=True)
    job = poll_until_done(token, job_id, timeout_s)
    status = job.get("status")
    mode = job.get("completion_mode", "?")
    tool_calls = job.get("tool_call_count", 0)
    print(f"status={status}  mode={mode}  tools={tool_calls}")

    session_dir = find_session_dir(job)
    output_text = find_final_output(session_dir) if session_dir else None
    artifacts = find_artifact_files(session_dir) if session_dir else []

    if status == "failed":
        err = job.get("error", "no error info")
        failed.append((test_name, f"Job failed: {err[:200]}"))
        print(f"  {RED}FAIL{RESET} {test_name}: job FAILED — {err[:200]}")
        return job

    issues: list[str] = []
    for check_type, expected in (checks or []):
        if check_type == "status":
            if status != expected:
                issues.append(f"status={status!r} expected {expected!r}")
        elif check_type == "completion_mode":
            if mode != expected:
                issues.append(f"completion_mode={mode!r} expected {expected!r}")
        elif check_type == "tool_calls":
            if tool_calls < expected:
                issues.append(f"tool_call_count={tool_calls} < {expected}")
        elif check_type == "output_contains":
            if output_text is None:
                issues.append(f"no output file found in {session_dir}")
            elif expected.lower() not in output_text.lower():
                snippet = output_text[:200].replace("\n", " ")
                issues.append(f"output does not contain {expected!r}. Got: {snippet!r}")
        elif check_type == "artifact_exists":
            if not any(expected.lower() in a.lower() for a in artifacts):
                issues.append(f"no artifact path contains {expected!r}. Got: {artifacts}")

    if issues:
        reason = "; ".join(issues)
        failed.append((test_name, reason))
        print(f"  {RED}FAIL{RESET} {test_name}: {reason}")
        if output_text:
            print(f"    Output preview: {output_text[:300].replace(chr(10), ' ')!r}")
    else:
        passed.append(test_name)
        out_len = len(output_text) if output_text else 0
        print(f"  {GREEN}PASS{RESET} {test_name} (output={out_len}ch, artifacts={len(artifacts)})")

    return job


# ---------------------------------------------------------------------------
# Test definitions
# ---------------------------------------------------------------------------

def main():
    print(f"\n{BOLD}{'='*60}")
    print("Overlord11 — End-to-End API Integration Tests")
    print(f"{'='*60}{RESET}")

    # Auth
    try:
        token = login()
        print(f"  {GREEN}Auth OK{RESET} — token acquired")
    except Exception as exc:
        print(f"  {RED}Auth FAILED{RESET}: {exc}")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Test 1 — Utility tools (calculator, json_transform, write_file)
    # -----------------------------------------------------------------------
    print(f"\n{BOLD}--- Test Group 1: Utility Tools ---{RESET}")
    run_job_test(
        token,
        "calculator + write_file",
        "Calculator & File Write Test",
        """You must use tools — no prose-only response is accepted.

Step 1: Use the calculator tool to evaluate the expression "sqrt(144) * pi" with precision=4. 
Step 2: Use the calculator tool to evaluate "2 ** 10 + 100".
Step 3: Use the write_file tool to save the two results as a markdown table to "final_output.md". 
The table should have columns: Expression | Result.""",
        checks=[
            ("status", "completed"),
            ("tool_calls", 3),
            ("output_contains", "37.6991"),
        ],
    )

    # -----------------------------------------------------------------------
    # Test 2 — json_transform
    # -----------------------------------------------------------------------
    run_job_test(
        token,
        "json_transform",
        "JSON Transform Test",
        """You must use tools — no prose-only response is accepted.

Use the json_transform tool to perform these 3 operations:
1. Pretty-print this JSON: {"name":"Overlord11","version":"2.3.0","tools":13,"active":true}
2. Flatten this nested JSON: {"config":{"engine":{"workers":4,"timeout":30},"db":{"host":"localhost"}}}
3. Get the keys of: {"alpha":1,"beta":2,"gamma":3,"delta":4}

Then use the write_file tool to save all 3 results to final_output.md as a markdown document with a section for each result.""",
        checks=[
            ("status", "completed"),
            ("tool_calls", 4),
            ("output_contains", "Overlord11"),
        ],
    )

    # -----------------------------------------------------------------------
    # Test 3 — web_fetch + web_extract_text
    # -----------------------------------------------------------------------
    print(f"\n{BOLD}--- Test Group 2: Basic Web Tools ---{RESET}")
    run_job_test(
        token,
        "web_fetch + web_extract_text",
        "Web Fetch & Text Extract Test",
        """You must use tools — no prose-only response is accepted.

Step 1: Use web_fetch to fetch https://example.com and note the HTTP status code.
Step 2: Use web_extract_text on https://example.com to get the clean text content.
Step 3: Write to final_output.md:
- The HTTP status code from step 1
- The page title from step 2
- The first 100 characters of the clean text""",
        checks=[
            ("status", "completed"),
            ("tool_calls", 2),
            ("output_contains", "200"),
        ],
    )

    # -----------------------------------------------------------------------
    # Test 4 — web_search
    # -----------------------------------------------------------------------
    run_job_test(
        token,
        "web_search",
        "Web Search Test",
        """You must use tools — no prose-only response is accepted.

Use the web_search tool to search for "Python programming language features" in text mode with max_results=5.
Write to final_output.md:
- The number of results returned
- The title and URL of each result as a numbered list""",
        checks=[
            ("status", "completed"),
            ("tool_calls", 1),
        ],
        timeout_s=180,
    )

    # -----------------------------------------------------------------------
    # Test 5 — rss_read
    # -----------------------------------------------------------------------
    run_job_test(
        token,
        "rss_read",
        "RSS Feed Read Test",
        """You must use tools — no prose-only response is accepted.

Use the rss_read tool to read the RSS feed at https://planetpython.org/rss20.xml with max_items=5.
Write to final_output.md:
- The feed title (if available)
- A numbered list of the item titles and publication dates""",
        checks=[
            ("status", "completed"),
            ("tool_calls", 1),
        ],
    )

    # -----------------------------------------------------------------------
    # Test 6 — web_extract_images + image_scraper
    # -----------------------------------------------------------------------
    print(f"\n{BOLD}--- Test Group 3: Image Tools ---{RESET}")
    run_job_test(
        token,
        "web_extract_images + image_scraper",
        "Image Extraction Test",
        """You must use tools — no prose-only response is accepted.

Step 1: Use web_extract_images on https://www.python.org with limit=10.
Step 2: Use image_scraper on https://www.python.org with limit=5 and require_https=true.
Write to final_output.md:
- How many images web_extract_images found
- How many images image_scraper found
- The first 3 image URLs from image_scraper (if any)""",
        checks=[
            ("status", "completed"),
            ("tool_calls", 2),
        ],
    )

    # -----------------------------------------------------------------------
    # Test 7 — semantic_content_extractor
    # -----------------------------------------------------------------------
    print(f"\n{BOLD}--- Test Group 4: Extraction Tools ---{RESET}")
    run_job_test(
        token,
        "semantic_content_extractor",
        "Semantic Extraction Test",
        """You must use tools — no prose-only response is accepted.

Use the semantic_content_extractor tool with this raw_text:
"Contact our team at support@acme.com or billing@acme.org. 
Sales hotline: +1-800-555-0199. Emergency: (555) 123-4567.
Basic plan starts at $9.99/month. Pro plan: $49.99/month. Enterprise: $199/month.
FAQ: Q: How do I cancel? A: Log in and click Account Settings. Q: Is there a free trial? A: Yes, 14 days."

Write to final_output.md the extracted: emails, phone numbers, prices, and FAQ pairs.""",
        checks=[
            ("status", "completed"),
            ("tool_calls", 1),
            ("output_contains", "support@acme.com"),
        ],
    )

    # -----------------------------------------------------------------------
    # Test 8 — intelligent_theme_scraper + web_code_scraper
    # -----------------------------------------------------------------------
    run_job_test(
        token,
        "intelligent_theme_scraper + web_code_scraper",
        "Theme & Code Scraper Test",
        """You must use tools — no prose-only response is accepted.

Step 1: Use intelligent_theme_scraper on https://example.com to analyze its design system.
Step 2: Use web_code_scraper on https://example.com to detect JS bundles and frameworks.
Write to final_output.md a brief analysis with:
- Color palette found (if any)
- Frameworks detected (if any)
- Number of JS bundles found""",
        checks=[
            ("status", "completed"),
            ("tool_calls", 2),
        ],
    )

    # -----------------------------------------------------------------------
    # Test 9 — html_report_generator
    # -----------------------------------------------------------------------
    print(f"\n{BOLD}--- Test Group 5: Report Generation ---{RESET}")
    run_job_test(
        token,
        "html_report_generator",
        "HTML Report Generation Test",
        """You must use tools — no prose-only response is accepted.

Use the html_report_generator tool to create a styled HTML report with:
- title: "Overlord11 System Test Report"
- theme: "dark"
- include_toc: true
- output_path: "artifacts/system_test_report.html"
- content (markdown):
## Test Summary
All 17 tools have been verified operational.

## Tool Categories
| Category | Tools |
|----------|-------|
| System | run_command, write_file |
| Web | web_fetch, web_search, web_extract_text, web_extract_images |
| Utility | calculator, json_transform, html_report_generator |

## Status
All systems nominal.

After generating the report, write to final_output.md: the output_path and the size in bytes.""",
        checks=[
            ("status", "completed"),
            ("tool_calls", 1),
            ("output_contains", "system_test_report"),
            ("artifact_exists", "system_test_report.html"),
        ],
    )

    # -----------------------------------------------------------------------
    # Test 10 — dynamic_browser + search_and_extract_pipeline
    # -----------------------------------------------------------------------
    run_job_test(
        token,
        "dynamic_browser + search_and_extract_pipeline",
        "Browser & Pipeline Test",
        """You must use tools — no prose-only response is accepted.

Step 1: Use dynamic_browser to load https://example.com and get the page title.
Step 2: Use search_and_extract_pipeline with seed_urls=["https://example.com"] and max_results=1.
Write to final_output.md:
- The page title from dynamic_browser
- How many documents the pipeline returned""",
        checks=[
            ("status", "completed"),
            ("tool_calls", 2),
        ],
    )

    # -----------------------------------------------------------------------
    # Test 11 — run_command (safe system tool)
    # -----------------------------------------------------------------------
    print(f"\n{BOLD}--- Test Group 6: System Tools ---{RESET}")
    run_job_test(
        token,
        "run_command",
        "Shell Command Test",
        """You must use tools — no prose-only response is accepted.

Step 1: Use run_command to execute: python --version
Step 2: Use run_command to execute: python -c "import sys; print(f'Path entries: {len(sys.path)}')"
Write to final_output.md the output of both commands.""",
        checks=[
            ("status", "completed"),
            ("tool_calls", 2),
            ("output_contains", "Python"),
        ],
    )

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    total = len(passed) + len(failed)
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}Results: {GREEN}{len(passed)} passed{RESET}, {RED}{len(failed)} failed{RESET} / {total} total{RESET}")

    if failed:
        print(f"\n{RED}Failed tests:{RESET}")
        for name, reason in failed:
            print(f"  ✗ {name}: {reason[:300]}")

    # Write JSON report
    report = {
        "passed": passed,
        "failed": [{"name": n, "reason": r} for n, r in failed],
        "total": total,
        "pass_rate": f"{len(passed)/total*100:.0f}%" if total else "0%",
    }
    report_path = ROOT / "workspace" / "api_test_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nReport: {report_path}")
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
