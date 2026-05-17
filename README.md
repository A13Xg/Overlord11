# Overlord11 WebUI (Minimal Baseline)

Minimal runtime baseline for the Overlord11 WebUI stack.

## Run

```bash
pip install -r requirements.txt
python scripts/run_webui.py
```

Default URL: `http://localhost:7900`

Optional for HTML screenshot artifacts:

```bash
playwright install chromium
```

## Core Runtime Paths

- `backend/` FastAPI + APIs + SSE
- `frontend/` WebUI pages
- `engine/` orchestration runner + provider bridge + tool execution
- `tools/` tool schemas + implementations
- `agents/` runtime agent prompts
- `config.json` provider/orchestration/tool config

## Diagnostics

- Jobs state: `workspace/.webui_jobs.json`
- Session artifacts: `workspace/<session_id>/artifacts/`
- Canonical job summary: `workspace/<session_id>/artifacts/logs/job_summary.json`
- Engine logs: `logs/master.jsonl`, `logs/sessions/*.jsonl`

## Completion Semantics

Non-trivial tasks must execute parseable tool calls. Prose-only non-trivial responses are treated as invalid completion and fail with explicit reason metadata.

## Output Visibility

- The UI includes a dedicated `RESULT` tab and an `OPEN RESULT` shortcut in job details.
- Primary output resolution prioritizes:
1. `answer.*`
2. `final_output.*`
3. files under `product` / `output` / `outputs`
- If no single primary file is detected, UI falls back to the output directory and workspace ZIP download.

## Runtime Defaults

- New jobs default to `TRY DIFFERENT MODEL` rate-limit behavior.
- New jobs default to auto-start enabled; when disabled, jobs are created queued for manual start.
- Shell execution defaults to strict style guards with environment-aware shell preference (`reject_on_shell_mismatch=true`, `auto_switch_shell=true`).

## Stabilization Gate

Before starting feature work or preparing a release, complete this gate in order:

1. Path policy and root determinism checks pass.
2. Completion semantics regression tests pass.
3. Interactive smoke matrix (`Test1`-`Test8`) passes.
4. Job summary artifacts are emitted for each completed/failed session.

### Programmatic Gate Steps

1. Run unit regressions:

```bash
python -m unittest discover -s tests -v
```

2. Validate tool contracts (schema ↔ implementation ↔ CLI):

```bash
python -m unittest tests/test_tool_contracts.py -v
```

3. Compile critical modules:

```bash
python -m py_compile engine/tool_executor.py engine/runner.py engine/session_manager.py backend/core/engine_bridge.py
```

4. Start WebUI and run the interactive matrix:

```bash
python scripts/run_webui.py
```

5. Verify each target session contains a job summary:

```bash
python - <<'PY'
from pathlib import Path
root = Path("workspace")
missing = []
for d in sorted([p for p in root.iterdir() if p.is_dir()]):
    if d.name == "archive":
        continue
    p = d / "artifacts" / "logs" / "job_summary.json"
    if not p.exists():
        missing.append(d.name)
print("missing_job_summary:", missing)
raise SystemExit(1 if missing else 0)
PY
```

6. Pass/fail criteria:
- No write attempts outside task workspace in normal mode.
- No false completion for delegation-only output.
- No false no-effect failure when valid tool execution occurred.
- `job_summary.json` exists for each session and includes:
  - `job_title`
  - `completion_mode`
  - `tool_call_count`
  - `artifact_count`
