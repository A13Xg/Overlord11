"""Re-test the 2 failing API e2e tests with updated prompts/assertions."""
from __future__ import annotations
import json, time, sys, urllib.request
from pathlib import Path

BASE = "http://localhost:7900"
ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "workspace"

RESET = "\033[0m"; GREEN = "\033[92m"; RED = "\033[91m"; BOLD = "\033[1m"; CYAN = "\033[96m"


def req(method, path, body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=20) as resp:
        return json.loads(resp.read().decode())


def poll(token, jid, timeout=300):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        j = req("GET", f"/api/jobs/{jid}", token=token)
        if j.get("status") in ("completed", "failed"):
            return j
        time.sleep(3)
    return req("GET", f"/api/jobs/{jid}", token=token)


def run_test(name, title, prompt, checks, timeout=300):
    print(f"\n  {CYAN}> {name}{RESET}")
    jid = req("POST", "/api/jobs", {"title": title, "prompt": prompt, "auto_start": True}, token)["job_id"]
    print(f"    Job ID: {jid}")
    job = poll(token, jid, timeout)
    status = job.get("status")
    mode = job.get("completion_mode", "?")
    tools = job.get("tool_call_count", 0)
    print(f"    status={status}  mode={mode}  tools={tools}")
    if status == "failed":
        err = job.get("error", "unknown")
        print(f"  {RED}FAIL{RESET} {name}: job failed [{err}]")
        return False
    sid = job.get("session_id")
    sd = WORKSPACE / sid if sid else None
    out = None
    if sd:
        for n in ("final_output.md", "answer.md", "final_output.txt"):
            p = sd / n
            if p.exists():
                out = p.read_text(encoding="utf-8", errors="replace")
                break
    ok = True
    for ct, cv in checks:
        if ct == "tool_calls" and tools < cv:
            print(f"  {RED}FAIL{RESET} {name}: tool_calls={tools} < {cv}")
            ok = False
        elif ct == "output_contains":
            if out is None:
                print(f"  {RED}FAIL{RESET} {name}: no output file found")
                ok = False
            elif cv.lower() not in out.lower():
                snippet = out[:200].replace("\n", " ")
                print(f"  {RED}FAIL{RESET} {name}: output lacks {cv!r}. Got: {snippet!r}")
                ok = False
    if ok:
        print(f"  {GREEN}PASS{RESET} {name}")
    return ok


token = req("POST", "/api/auth/login", {"username": "admin", "password": "admin"})["token"]
print(f"  {GREEN}Auth OK{RESET}")

passed = 0
failed = 0

# --- Test 1: calculator + write_file ---
ok1 = run_test(
    "calculator + write_file",
    "Calculator & File Write Test",
    """You must use tools. No prose-only response is accepted.
Step 1: Use the calculator tool with expression="sqrt(144) * pi" and precision=4.
Step 2: Use the calculator tool with expression="2 ** 10 + 100".
Step 3: Use the write_file tool to write the two results as a markdown table to path="final_output.md".
The table should have columns: Expression | Result""",
    [("tool_calls", 3), ("output_contains", "37.6991")],
)
if ok1:
    passed += 1
else:
    failed += 1

# --- Test 2: json_transform ---
ok2 = run_test(
    "json_transform",
    "JSON Transform Test",
    """You must use tools. No prose-only response is accepted.
Step 1: Use json_transform with data='{"name":"Overlord11","version":"2.3.0"}' and transform="pretty"
Step 2: Use json_transform with data='{"config":{"engine":{"workers":4}}}' and transform="flatten"
Step 3: Use json_transform with data='{"alpha":1,"beta":2,"gamma":3}' and transform="keys"
Step 4: Use the write_file tool to save all three results to path="final_output.md" as a markdown document.""",
    [("tool_calls", 4), ("output_contains", "Overlord11")],
)
if ok2:
    passed += 1
else:
    failed += 1

print(f"\n{BOLD}Re-test Results: {GREEN}{passed} passed{RESET}, {RED}{failed} failed{RESET} / 2 total{RESET}")
sys.exit(0 if not failed else 1)
