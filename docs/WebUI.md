# Overlord11 Tactical WebUI — Operations Manual

**Source of truth:** `docs/TacticalWebUI_MasterPlan.md`

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements-webui.txt
```

### 2. Run the server
```bash
python scripts/run_webui.py
# → http://localhost:7900  (UI)
# → http://localhost:7900/docs  (Swagger API docs)
```

Custom port:
```bash
python scripts/run_webui.py --port 8080
```

### 3. Open the UI
Navigate to `http://localhost:7900` in any modern browser.

---

## Architecture Summary

```
scripts/run_webui.py        Entry point (uvicorn)
webui/
  app.py                    FastAPI routes
  runner.py                 Autonomous runner loop (asyncio task per job)
  events.py                 Stable event schema (schema_version 0.1)
  models.py                 Pydantic state / request models
  state_store.py            Disk persistence layer
  llm_interface.py          High-level LLM call helper
  providers/
    base.py                 Abstract LLMProvider interface
    anthropic_adapter.py    Anthropic Messages API
    gemini_adapter.py       Google Gemini API
    openai_adapter.py       OpenAI Chat Completions API
    router.py               Provider selection (reads config.json)
  reviewer.py               Rule-based reviewer gate
  static/index.html         Single-page tactical WebUI
workspace/
  jobs/<job_id>/
    state.json
    events.jsonl
    artifacts/
      verify/               Verify gate output logs
      install/              pip install logs
      diffs/                Unified diff patches
      plans/                StepPlan JSON files
      reports/              Reviewer reports
```

---

## LLM Provider Configuration

The runner reads `config.json` to select the active provider and model.  
Set the corresponding API key environment variable:

| Provider | Env var |
|----------|---------|
| anthropic | `ANTHROPIC_API_KEY` |
| gemini | `GOOGLE_GEMINI_API_KEY` |
| openai | `OPENAI_API_KEY` |

If no key is set, the runner operates in **dry-run mode** — it emits
`LLM_UNAVAILABLE` events and uses a stub response to exercise all pipeline
stages without making real API calls.

---

## API Reference + curl Examples

### Health check
```bash
curl http://localhost:7900/api/health
# {"status":"ok","service":"overlord11-webui","schema_version":"0.1"}
```

### Create a job
```bash
curl -s -X POST http://localhost:7900/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"goal":"Fix all failing unit tests","max_iterations":5,"max_time_seconds":600}'
```

Create a job with a custom verify command:
```bash
curl -s -X POST http://localhost:7900/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"goal":"Optimize queries","verify_command":["python","-m","pytest","tests/","--tb=short","-q"]}'
```

Response:
```json
{
  "job_id": "1ec416376a14",
  "goal": "Fix all failing unit tests",
  "status": "PENDING",
  "created_at": "2026-03-31T22:00:00.000000+00:00",
  "max_iterations": 5,
  "max_time_seconds": 600,
  "verify_command": null
}
```

### Start a job
```bash
JOB_ID="1ec416376a14"
curl -X POST http://localhost:7900/api/jobs/$JOB_ID/start
```

### Stream events (SSE)
```bash
curl -N http://localhost:7900/api/jobs/$JOB_ID/events
```

Resume from a byte offset (e.g. after disconnect):
```bash
curl -N "http://localhost:7900/api/jobs/$JOB_ID/events?since=2048"
```

### Get last 20 events (JSON)
```bash
curl "http://localhost:7900/api/jobs/$JOB_ID/events/tail?n=20"
```

### Pause a job
```bash
curl -X POST "http://localhost:7900/api/jobs/$JOB_ID/pause?pause=true"
```

### Resume a job
```bash
curl -X POST "http://localhost:7900/api/jobs/$JOB_ID/pause?pause=false"
```

### Stop a job
```bash
curl -X POST http://localhost:7900/api/jobs/$JOB_ID/stop
```

### Inject a directive (mid-run)
```bash
curl -X POST http://localhost:7900/api/jobs/$JOB_ID/directive \
  -H "Content-Type: application/json" \
  -d '{"text":"Focus on the database tests first","severity":"high","tags":["database"]}'
```

### Get job state snapshot
```bash
curl http://localhost:7900/api/jobs/$JOB_ID
```

### List all jobs
```bash
curl http://localhost:7900/api/jobs
```

### List artifacts (with metadata)
```bash
curl http://localhost:7900/api/jobs/$JOB_ID/artifacts
```

Response:
```json
{
  "job_id": "1ec416376a14",
  "artifacts": [
    {"path": "verify/iter_001.log", "size": 1234, "mtime": 1743455200.0},
    {"path": "diffs/iter_001.patch", "size": 512, "mtime": 1743455210.0}
  ]
}
```

### Fetch artifact content
```bash
curl "http://localhost:7900/api/jobs/$JOB_ID/artifacts/verify/iter_001.log"
```

---

## Runner Loop Overview

```
JOB_STARTING
└─ for iteration 1..N:
   ├─ Apply pending directives → DIRECTIVES_APPLIED
   ├─ Plan step (LLM) → PLAN_CREATED | LLM_UNAVAILABLE
   ├─ Execute action:
   │   ├─ patch      → PATCH_APPLY_START / PATCH_APPLY_RESULT
   │   ├─ tool_call  → STEP_START / STEP_END (see Built-in Tools below)
   │   └─ complete   → (exits loop)
   ├─ Verify gate (verify_command or default test.py) → VERIFY_RESULT
   │   └─ If FAIL:
   │       ├─ Detect ModuleNotFoundError → venv install → VERIFY_RETRY
   │       └─ LLM repair (up to 3 attempts) → REPAIR_RESULT
   └─ Reviewer gate (secrets, diff coverage) → REVIEW_RESULT
COMPLETE | FAILED | STOPPED | TIME_BUDGET_EXCEEDED | ITERATION_BUDGET_EXCEEDED
```

### Built-in tools

The runner supports four safe built-in tools in the `tool_call` action:

| Tool | Args | Notes |
|------|------|-------|
| `shell` | `command` (str), `timeout` (int, default 60) | Runs in project root via `bash -c`. Output truncated to 2 000 chars. |
| `read_file` | `path` (str, relative) | Returns up to 8 000 chars. Rejects paths outside project root. |
| `write_file` | `path` (str), `content` (str) | Creates dirs as needed. Persisted as `diffs/write_<name>` artifact. Rejects paths outside project root. |
| `list_dir` | `path` (str, default `.`) | Returns up to 200 entries with `[dir]` / `     ` prefix. |

All tools emit `STEP_START` before and `STEP_END` after execution.

### Self-healing venv (Milestone C)
When verify fails with `ModuleNotFoundError: No module named 'X'`, the runner:
1. Creates `workspace/jobs/<id>/.venv` (once per job)
2. Installs the missing package via `pip install X`
3. Re-runs verify using the venv python interpreter
4. Emits `DEP_INSTALL_START`, `DEP_INSTALL_RESULT`, `VERIFY_RETRY`
5. Guards: max 20 packages per job; skips if same package already installed

### Custom verify command
Pass `verify_command` when creating a job to use any test runner:
```bash
# Use pytest instead of tests/test.py
curl -X POST http://localhost:7900/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"goal":"...","verify_command":["python","-m","pytest","tests/","-q","--tb=short"]}'
```
If `verify_command` is `null` (default) and `tests/test.py` does not exist in the project root, the runner emits a `VERIFY_RESULT` with `passed=false` and `returncode=-1` rather than crashing.

---

## Running Tests
```bash
# Full webui smoke tests (66 tests)
python -m pytest tests/test_webui.py -v

# Existing Overlord11 tool tests
python tests/test.py --skip-web --quiet
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: No module named 'fastapi'` | `pip install -r requirements-webui.txt` |
| Server starts but UI blank | Check browser console; ensure `webui/static/index.html` exists |
| SSE stream disconnects | Use `?since=<offset>` to resume; offset is byte position in events.jsonl |
| LLM calls fail with 401 | Set `ANTHROPIC_API_KEY` / `GOOGLE_GEMINI_API_KEY` / `OPENAI_API_KEY` env var |
| Jobs stuck in RUNNING after restart | Jobs persist state to disk; create a new job or POST /stop |
| "Invalid job_id format" (400) | Job IDs are 12 hex chars — copy from create-job response |
