# Overlord11 Tactical WebUI — How to Run

## Overview

The **Overlord11 Tactical WebUI** is a production-minded, autonomous mission-runner with a live telemetry frontend.  It provides:

- A **FastAPI backend** that creates, starts, pauses, stops, and streams events for *jobs* (autonomous LLM-driven missions).
- A **Server-Sent Events** (SSE) stream so the browser UI updates in real time.
- Full **disk persistence** — every job state, event, and artifact is written to `workspace/jobs/<job_id>/` so jobs survive server restarts.
- A **Tactical Operations Terminal** single-page UI with a military satellite theme.

---

## Quick Start

### 1 — Install dependencies

```bash
pip install -r requirements-webui.txt
```

### 2 — (Optional) Set LLM API key

The runner will work in **stub mode** without a key, but will not make real LLM calls.

```bash
# Anthropic (default active provider in config.json)
export ANTHROPIC_API_KEY="sk-ant-..."

# Or Gemini
export GOOGLE_GEMINI_API_KEY="AIza..."

# Or OpenAI
export OPENAI_API_KEY="sk-..."
```

### 3 — Start the server

```bash
python scripts/run_webui.py
```

The server starts on **http://0.0.0.0:7900** by default.

Options:

```
--host HOST    Bind host (default: 0.0.0.0)
--port PORT    Bind port (default: 7900)
--reload       Enable hot-reload (development)
```

### 4 — Open the UI

Navigate to **http://localhost:7900** in your browser.

---

## Architecture

```
scripts/run_webui.py          Entry point (uvicorn launcher)
webui/
  app.py                      FastAPI application + all endpoints
  models.py                   Pydantic request/response models
  events.py                   Canonical event schema + helpers
  state_store.py              Disk persistence layer
  runner.py                   Autonomous runner loop (asyncio)
  llm_interface.py            Provider-agnostic LLM call interface
  reviewer.py                 Reviewer gate (secrets, diff coverage)
  static/
    index.html                Single-page tactical UI
workspace/
  jobs/
    <job_id>/
      state.json              Latest job state snapshot
      events.jsonl            Append-only event log
      artifacts/              Diffs, test outputs, repair patches
```

---

## Event Schema

Every significant action emits a JSON event.  All events share this envelope:

```json
{
  "ts":     "2026-03-31T23:00:00.000000+00:00",
  "type":   "ITERATION",
  "job_id": "abc123def456",
  "level":  "info",
  ... payload fields ...
}
```

### Event Types

| Type | Level | Description |
|------|-------|-------------|
| `JOB_CREATED` | info | Job persisted for the first time |
| `JOB_STARTING` | info | Runner loop is beginning |
| `STATUS` | info | Generic status change |
| `ITERATION` | info | Start of a runner iteration |
| `TOOL_START` | info | Tool invocation beginning |
| `TOOL_END` | info | Tool invocation finished |
| `VERIFY_START` | info | Verify gate (`tests/test.py --skip-web --quiet`) running |
| `VERIFY_RESULT` | info/warn | Verify gate result (pass/fail + output tail) |
| `REPAIR_START` | warn | Repair loop triggered after verify failure |
| `REPAIR_RESULT` | warn | Repair attempt finished |
| `REVIEW_START` | info | Reviewer gate running |
| `REVIEW_RESULT` | info/warn | Reviewer gate finished (pass/fail + findings) |
| `LLM_CALL_START` | info | LLM API call initiated |
| `LLM_CALL_END` | info | LLM API call finished (elapsed, tokens) |
| `USER_DIRECTIVE` | info | Feedback injected by the user mid-run |
| `ASSUMPTION_LOG` | info/warn | Runner logged an assumption instead of asking |
| `COMPLETE` | info | Job finished successfully |
| `FAILED` | error | Job stopped with error / budget exceeded |
| `PAUSED` | warn | Job paused by user request |
| `RESUMED` | info | Job resumed from PAUSED state |

---

## REST API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/jobs` | Create a new job |
| `GET` | `/api/jobs` | List all jobs (summary) |
| `GET` | `/api/jobs/{id}` | Get full job state |
| `POST` | `/api/jobs/{id}/start` | Start or restart a job |
| `POST` | `/api/jobs/{id}/pause` | Pause a running job |
| `POST` | `/api/jobs/{id}/resume` | Resume a paused job |
| `POST` | `/api/jobs/{id}/stop` | Stop a running/paused job |
| `POST` | `/api/jobs/{id}/directive` | Inject user feedback mid-run |
| `GET` | `/api/jobs/{id}/events` | SSE stream (add `?offset=N` to resume) |
| `GET` | `/api/jobs/{id}/events/tail` | Last N events as JSON array |
| `GET` | `/api/jobs/{id}/artifacts` | List artifact filenames |
| `GET` | `/api/jobs/{id}/artifacts/{name}` | Read artifact text content |
| `GET` | `/api/health` | Health check |
| `GET` | `/docs` | Swagger UI (interactive API docs) |

### Create Job — Request Body

```json
{
  "goal":             "Fix the failing integration test",
  "max_iterations":   10,
  "max_time_seconds": 3600,
  "provider":         null,
  "model":            null,
  "autonomous":       true
}
```

---

## Runner Behaviour

1. **JOB_STARTING**: resolves provider/model from config.json (logs assumption if key missing).
2. **Iteration loop**: at each iteration the runner:
   - Checks time and iteration budgets.
   - Checks cooperative pause/stop flags.
   - Calls the LLM with the goal, iteration number, and last verify output.
   - Executes the returned action (`tool_call` | `patch` | `complete`).
   - Runs the verify gate (`python tests/test.py --skip-web --quiet`).
   - On failure: triggers up to 3 repair attempts.
   - On pass: runs the reviewer gate.
   - On reviewer pass: marks COMPLETE.
3. **Budget exceeded**: marks FAILED with explicit reason.

### Stub Mode

If no API key is configured for the active provider, the runner emits an `ASSUMPTION_LOG` event and uses a stub LLM response (`{"action":"complete","summary":"[STUB] …"}`).  All persistence, event emission, verify gate, and reviewer gate logic still runs.

---

## Autonomy Policy

The runner never asks the user for permission.  If ambiguity exists it:
1. Chooses the most robust best-practice solution.
2. Logs the assumption as an `ASSUMPTION_LOG` event.
3. Continues running.

---

## Feedback / Directives

While a job is running, use the **Inject Directive** panel in the UI (or POST to `/api/jobs/{id}/directive`) to send a message.  It is:
- Persisted to `state.json` → `directives` list.
- Emitted as a `USER_DIRECTIVE` event (visible in the stream immediately).
- Included in the next LLM prompt as part of the context.

---

## SSE Resume

The SSE endpoint supports resuming from a byte offset:

```
GET /api/jobs/{id}/events?offset=12345
```

The client can read `Content-Length` headers or track the byte position of the last successfully processed event in `events.jsonl` to reconnect without replaying the full history.

---

## Testing

```bash
# Run WebUI-specific tests
python -m pytest tests/test_webui.py -v

# Run existing Overlord11 tool tests (skip web)
python tests/test.py --skip-web --quiet
```

---

## Provider Configuration

Provider settings live in `config.json` (never hardcoded).  Switch the active provider:

```json
{
  "providers": {
    "active": "gemini"
  }
}
```

Fallback order on API error: `anthropic → gemini → openai` (configurable via `config.json → orchestration.fallback_provider_order`).
