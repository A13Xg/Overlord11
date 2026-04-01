# Overlord11 Tactical WebUI — Event Schema Reference

**Schema version:** `0.1`  
**File:** `workspace/jobs/<job_id>/events.jsonl`  
**Encoding:** UTF-8, one JSON object per line, append-only.

---

## Envelope (every event)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | string | ✓ | Always `"0.1"` |
| `ts` | string | ✓ | UTC ISO-8601 timestamp |
| `type` | string | ✓ | Event type (see table below) |
| `job_id` | string | ✓ | 12-hex-char job identifier |
| `level` | string | ✓ | `info` \| `warn` \| `error` |
| `phase` | string | - | Runner phase label (optional) |
| `iteration` | int | - | Current iteration number (optional) |
| `artifact_ref` | string | - | Relative path to related artifact (optional) |

All additional fields are payload fields specific to the event type.

---

## Event Types

### Lifecycle

| Type | Level | Key Payload Fields |
|------|-------|--------------------|
| `JOB_CREATED` | info | `goal`, `max_iterations` |
| `JOB_STARTING` | info | `goal` |
| `STATUS` | info | `status` (JobStatus string) |
| `PAUSED` | info | `iteration` |
| `RESUMED` | info | `iteration` |
| `STOPPED` | info | `reason` |
| `COMPLETE` | info | `reason` (success summary) |
| `FAILED` | error | `reason` |
| `TIME_BUDGET_EXCEEDED` | error | `reason` |
| `ITERATION_BUDGET_EXCEEDED` | error | `reason` |

### Iteration + Directives

| Type | Level | Key Payload Fields |
|------|-------|--------------------|
| `ITERATION` | info | `iteration`, `max_iterations`, `elapsed_s` |
| `USER_DIRECTIVE` | info | `text`, `severity`, `tags` |
| `DIRECTIVES_APPLIED` | info | `count`, `directives` (text list) |
| `ASSUMPTION_LOG` | warn | `message` |

### Verify Gate

| Type | Level | Key Payload Fields |
|------|-------|--------------------|
| `VERIFY_START` | info | `iteration` |
| `VERIFY_RESULT` | info/warn | `passed` (bool), `returncode`, `output_tail`, `artifact_ref` |
| `VERIFY_RETRY` | info | `iteration`, `reason` |

### Self-healing / Dependency Install

| Type | Level | Key Payload Fields |
|------|-------|--------------------|
| `DEP_INSTALL_START` | info | `package`, `venv_path`, `iteration` |
| `DEP_INSTALL_RESULT` | info/error | `package`, `success` (bool), `output_tail`, `artifact_ref` |

### Repair

| Type | Level | Key Payload Fields |
|------|-------|--------------------|
| `REPAIR_START` | info | `iteration`, `verify_output_tail` |
| `REPAIR_RESULT` | info/warn | `iteration`, `attempt`, `success` (bool), `method`, `package` |

### LLM / Provider

| Type | Level | Key Payload Fields |
|------|-------|--------------------|
| `LLM_CALL_START` | info | `provider`, `model` |
| `LLM_CALL_END` | info | `provider`, `model`, `elapsed_s`, `input_tokens`, `output_tokens` |
| `LLM_UNAVAILABLE` | warn | `reason`, `provider`, `model`, `mode` (`dry_run`) |

### Step Planning / Patching (Phase 2)

| Type | Level | Key Payload Fields |
|------|-------|--------------------|
| `PLAN_CREATED` | info | `iteration`, `artifact_ref` |
| `STEP_START` | info | `tool`, `args` (see built-in tools below) |
| `STEP_END` | info/warn | `tool`, `success`, `output` (first 500 chars) |
| `PATCH_APPLY_START` | info | `iteration`, `rationale` |
| `PATCH_APPLY_RESULT` | info/error | `iteration`, `success`, `output`, `artifact_ref` |

**Built-in tools (`tool` field values):**

| Tool | Args | Description |
|------|------|-------------|
| `shell` | `command` (str), `timeout` (int, default 60) | Run a shell command in the project root |
| `read_file` | `path` (str, relative to project root) | Read a text file (max 8 000 chars) |
| `write_file` | `path` (str), `content` (str) | Write/overwrite a file; persisted as artifact |
| `list_dir` | `path` (str, default `.`) | List directory entries with type prefix |

### Review

| Type | Level | Key Payload Fields |
|------|-------|--------------------|
| `REVIEW_START` | info | `iteration` |
| `REVIEW_RESULT` | info/warn | `passed`, `summary`, `findings`, `artifact_ref` |

### Artifacts

| Type | Level | Key Payload Fields |
|------|-------|--------------------|
| `ARTIFACT_WRITTEN` | info | `artifact_ref` (relative path) |

---

## Example Events

### JOB_CREATED
```json
{
  "schema_version": "0.1",
  "ts": "2026-03-31T22:00:00.000000+00:00",
  "type": "JOB_CREATED",
  "job_id": "1ec416376a14",
  "level": "info",
  "goal": "Fix failing unit tests",
  "max_iterations": 10
}
```

### VERIFY_RESULT (failure)
```json
{
  "schema_version": "0.1",
  "ts": "2026-03-31T22:01:05.123456+00:00",
  "type": "VERIFY_RESULT",
  "job_id": "1ec416376a14",
  "level": "warn",
  "iteration": 1,
  "passed": false,
  "returncode": 1,
  "output_tail": "ModuleNotFoundError: No module named 'requests'",
  "artifact_ref": "verify/iter_001.log"
}
```

### DEP_INSTALL_RESULT
```json
{
  "schema_version": "0.1",
  "ts": "2026-03-31T22:01:15.000000+00:00",
  "type": "DEP_INSTALL_RESULT",
  "job_id": "1ec416376a14",
  "level": "info",
  "iteration": 1,
  "package": "requests",
  "success": true,
  "artifact_ref": "install/iter_001_requests.log"
}
```

### USER_DIRECTIVE
```json
{
  "schema_version": "0.1",
  "ts": "2026-03-31T22:02:00.000000+00:00",
  "type": "USER_DIRECTIVE",
  "job_id": "1ec416376a14",
  "level": "info",
  "text": "Focus on fixing the database tests first",
  "severity": "high",
  "tags": ["database", "priority"]
}
```

### LLM_UNAVAILABLE (dry-run mode)
```json
{
  "schema_version": "0.1",
  "ts": "2026-03-31T22:01:00.000000+00:00",
  "type": "LLM_UNAVAILABLE",
  "job_id": "1ec416376a14",
  "level": "warn",
  "reason": "No API key for provider 'anthropic'",
  "provider": "anthropic",
  "model": "claude-opus-4-5",
  "mode": "dry_run"
}
```

---

## Artifact Layout

```
workspace/jobs/<job_id>/
  state.json
  events.jsonl
  artifacts/
    verify/      iter_001.log, iter_002.log …
    install/     iter_001_requests.log …
    diffs/       iter_001.patch …
    plans/       step_001.json …
    reports/     review_iter_001.json …
```

Artifact paths in events use relative paths (e.g. `verify/iter_001.log`)
that can be fetched via `GET /api/jobs/{id}/artifacts/<path>`.
