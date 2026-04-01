# Tactical WebUI + Autonomous Mission Control (Master Plan)

**Branch:** `tactical-webui-orchestrator`  
**Repo:** `A13Xg/Overlord11`  
**Goal:** A modern, clean, futuristic, feature-rich, *status-transparent* and *process-verbose* WebUI + backend system that lets a user direct an AI to build production-ready solutions over time, with corrective/additive iteration and objective completion gates.

**Theme:** Tactical command terminal (satellite tracking / missile command / C2 console). Atmosphere is welcome, but readability and operational clarity come first.

---

## 0) Non-interactive autonomy rules (MANDATORY)

1. **Do not ask the user permission to proceed.**
2. If ambiguity exists, choose safe defaults and **log assumptions** (do not block).
3. Prefer **robust-first, minimal-diff** changes.
4. **Never claim COMPLETE** unless verification gates pass.
5. Everything must be observable: **events + artifacts + state** must be persisted.
6. All text/JSON I/O must be UTF-8; JSON must use `ensure_ascii=False`.

---

## 1) System overview

Build a system consisting of:

### A) Backend API (FastAPI)
- Create/start/pause/resume/stop jobs
- Stream job events in real time (SSE preferred)
- Fetch job state snapshot
- Add user directives (feedback injection)
- Browse/download artifacts

### B) Runner (background execution)
- Executes the mission loop autonomously
- Emits structured events for every action
- Runs verify gates and repair loops
- Can self-heal common dependency failures (job-scoped venv)
- Later: uses provider-agnostic LLM interface to plan/repair/review

### C) WebUI (tactical console)
- Mission creation + controls
- Live telemetry feed
- System panels: verify/repair/review, budgets, provider/model
- Directive console
- Artifact viewer
- Later: fleet dashboard, replay, approvals, etc.

---

## 2) Disk persistence layout (MUST)

All jobs must be persistent and observable without the UI:

```
workspace/
  jobs/
    <job_id>/
      state.json
      events.jsonl
      artifacts/
        verify/
        install/
        diffs/
        plans/
        reports/
```

### State
- Path: `workspace/jobs/<job_id>/state.json`
- Must update after every status change and iteration.

### Event log
- Path: `workspace/jobs/<job_id>/events.jsonl`
- Append-only. One JSON object per line.

### Artifacts
- Logs, patches, plans, reports, etc.
- Events must contain `artifact_ref` whenever an artifact is written.

---

## 3) Event schema (CONTRACT)

### Schema version
Every event MUST include:
- `schema_version`: string (start with `"0.1"`)
- `ts`: UTC ISO string
- `type`: string
- `job_id`: string
- `level`: `info | warn | error`

Common optional fields:
- `phase`, `iteration`, `summary`, `tool`, `agent_profile`, `artifact_ref`

### Required event emitter
Implement a single helper used everywhere:
- `emit_event(store, job_id, type, level="info", **payload)`

### Minimum event types (implement first)
- `JOB_CREATED`, `JOB_STARTING`
- `STATUS` (payload includes `status`)
- `ITERATION`
- `VERIFY_START`, `VERIFY_RESULT`
- `REPAIR_START`, `REPAIR_RESULT`
- `DEP_INSTALL_START`, `DEP_INSTALL_RESULT`
- `VERIFY_RETRY`
- `USER_DIRECTIVE`, `DIRECTIVES_APPLIED`
- `ARTIFACT_WRITTEN`
- Terminal statuses: `COMPLETE`, `FAILED`, `STOPPED`, `PAUSED`, `TIME_BUDGET_EXCEEDED`, `ITERATION_BUDGET_EXCEEDED`

Document the schema and examples in `docs/EventSchema.md`.

---

## 4) API contract (Phase 1 required)

Base prefix: `/api`

### Jobs
- `POST /jobs` → create job
- `POST /jobs/{job_id}/start`
- `POST /jobs/{job_id}/pause?pause=true|false`
- `POST /jobs/{job_id}/stop`
- `GET /jobs/{job_id}` → state snapshot

### Event stream
- `GET /jobs/{job_id}/events?since=<byte_offset>` → SSE stream
  - Must support resuming via byte offset.

### Directives
- `POST /jobs/{job_id}/directive`
  - body: `{ "text": "...", "severity": "normal|high", "tags": [] }`
  - Must be persisted to `pending_directives[]` in state.

### Artifacts
- `GET /jobs/{job_id}/artifacts` → list artifacts (path/size/mtime)
- `GET /jobs/{job_id}/artifacts/<path>` → fetch artifact content (secure; no traversal)

Document curl examples in `docs/WebUI.md`.

---

## 5) Runner loop (Phase 1 required)

The runner must execute in the background and follow this loop:

1. Emit `STATUS: RUNNING`
2. For each iteration until done or budget exceeded:
   - Apply pending directives (emit `DIRECTIVES_APPLIED`)
   - Run verify gate:
     - command: `python tests/test.py --skip-web --quiet`
     - emit `VERIFY_START` and `VERIFY_RESULT`
     - persist full verify output to `artifacts/verify/iter_<n>.log` and emit `ARTIFACT_WRITTEN`
   - If verify passes: run review gate (rule-based initially) then mark COMPLETE
   - If verify fails: run repair step

Budgets:
- time budget seconds
- max iterations

Hard rule:
- **No COMPLETE** unless verify gate returns exit code 0.

---

## 6) Self-healing repair loop (Phase 1.5 required)

Implement deterministic self-heal when verify fails due to missing Python modules.

### Detect
Look for:
- `ModuleNotFoundError: No module named 'X'`

### Repair
- Create a job-scoped venv:
  - recommended: `workspace/jobs/<job_id>/.venv`
- Install missing package into that venv:
  - `<venv_python> -m pip install <pkg>`
- Persist pip output to:
  - `artifacts/install/iter_<n>_<pkg>.log`
- Re-run verify using venv python:
  - `<venv_python> tests/test.py --skip-web --quiet`

### Guardrails
- Max 20 new packages per job
- If the same missing module repeats after install, fail with explicit reason
- Respect time and iteration budgets

Update state:
- `venv_path`
- `installed_packages[]`
- `last_repair` summary

---

## 7) Autonomy core (Phase 2 — implement after Phase 1 works)

### Provider-agnostic LLM interface
Implement:
- `providers/base.py` interface
- adapters: `openai_adapter.py`, `anthropic_adapter.py`, `gemini_adapter.py` (stubs acceptable at first)
- routing: choose provider/model by task profile

Events:
- `LLM_CALL_START`, `LLM_CALL_RESULT`, `LLM_UNAVAILABLE`

### StepPlan schema (machine-executable)
Persist per step:
- `artifacts/plans/step_<n>.json`

### Patch application
Implement safe unified diff apply:
- reject outside-root paths
- persist patches to `artifacts/diffs/iter_<n>.patch`

Events:
- `PLAN_CREATED`, `STEP_START`, `STEP_END`
- `PATCH_APPLY_START`, `PATCH_APPLY_RESULT`

### LLM-driven repair loop
On verify failure:
- build repair prompt using verify logs + goal + recent diff summary
- require LLM to output a patch (diff)
- apply patch
- re-run verify
- escalate provider/model after repeated failures

---

## 8) Rule-based reviewer gate (Phase 2)

Before COMPLETE, run a rule-based reviewer that checks:
- obvious secret patterns (redact, block if found)
- dangerous file writes
- diff size warnings

Events:
- `REVIEW_START`, `REVIEW_RESULT`

---

## 9) WebUI requirements (implement after backend contract is stable)

### MVP pages
- Mission create/start controls
- Telemetry stream view (filter/search/autoscroll)
- Systems panel (state snapshot + verify/repair status)
- Directive console
- Artifacts browser + log viewer

### Theme
- Dark graphite background
- Subtle grid/radar overlay
- Neon cyan/green accents, amber warnings, red errors
- Monospace for logs, condensed headings
- Optional subtle scanline

---

## 10) Implementation order (DO THIS)

Implement in small commits, each leaving the repo runnable:

1) Backend skeleton + persistence + runner + SSE (Milestone A)
2) Event schema helper + docs + directives + artifacts endpoints (Milestone B)
3) Self-healing venv repair loop (Milestone C)
4) Autonomy scaffolding: provider interface + StepPlan + patch apply (Milestone D)
5) UI MVP wired to endpoints (Milestone UI-1)

Do not jump ahead to later platform features until items 1–5 work.

---

## 11) Verification gates (run frequently)

Minimum:
- `python tests/test.py --skip-web --quiet`

Also validate manually:
- backend starts
- create job → start → stream events
- directive endpoint works
- artifacts list/fetch works

---

## 12) Required docs

- `docs/WebUI.md` must include:
  - how to run backend
  - how to run UI
  - curl examples
  - troubleshooting

- `docs/EventSchema.md` must include:
  - event schema definition
  - event type list
  - event examples

---

## 13) Final output expectations for the agent

When you finish each milestone, output:
1) full list of changed/new files
2) run commands
3) curl examples
4) short note on what changed and what remains

Do not stop at scaffolding—complete milestones end-to-end.
