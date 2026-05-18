# Overlord11 WebUI (Shell Runtime Reset)

Clean-slate WebUI runtime baseline for prompt-to-provider execution.

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
- `backend/core/provider_runtime.py` direct provider execution
- `backend/strict_runtime/` strict tool-runtime skeleton (report-only, disabled)
- `config.json` provider/orchestration/tool config

## Diagnostics

- Jobs state: `workspace/.webui_jobs.json`
- Session artifacts: `workspace/<session_id>/artifacts/`
- Canonical job summary: `workspace/<session_id>/artifacts/logs/job_summary.json`
- Engine logs: `logs/master.jsonl`, `logs/sessions/*.jsonl`

## Completion Semantics

Jobs complete when the provider returns a non-empty response and canonical output artifacts are written.

## Output Visibility

- The UI includes a dedicated `RESULT` tab and an `OPEN RESULT` shortcut in job details.
- Primary output resolution prioritizes:
1. `answer.*`
2. `final_output.*`
3. files under `product` / `output` / `outputs`
- If no single primary file is detected, UI falls back to the output directory and workspace ZIP download.

## Runtime Defaults

- Runtime mode is `shell_only`.
- No agent orchestration or tool execution path is active.
- Jobs default to auto-start enabled; when disabled, jobs are queued for manual start.

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

2. Compile critical modules:

```bash
python -m py_compile backend/core/provider_runtime.py backend/core/engine_bridge.py
```

3. Start WebUI and run the interactive matrix:

```bash
python scripts/run_webui.py
```

4. Verify each target session contains a provider response log:

```bash
python - <<'PY'
from pathlib import Path
root = Path("workspace")
missing = []
for d in sorted([p for p in root.iterdir() if p.is_dir()]):
    if d.name == "archive":
        continue
    p = d / "artifacts" / "logs" / "provider_response.json"
    if not p.exists():
        missing.append(d.name)
print("missing_provider_response:", missing)
raise SystemExit(1 if missing else 0)
PY
```

5. Pass/fail criteria:
- Direct prompt-to-provider execution succeeds.
- `provider_response.json` exists for each completed session.
- `output/answer.md` and `final_output.md` are present for completed jobs.
