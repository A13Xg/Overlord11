# Tool Gateway

## Purpose
The tool gateway is the single execution path for all LLM tool calls.

Flow:
1. Parse call payload
2. Validate strict schema
3. Normalize safe aliases
4. Execute tool adapter
5. Return standardized envelope
6. Emit structured logs

## Why structured tool calls
LLMs are not reliable at generating raw CLI flag syntax consistently. The gateway enforces typed contracts and prevents malformed execution.

## Standard call format
```json
{
  "tool_name": "run_command",
  "arguments": {
    "command": "python --version",
    "shell": "auto",
    "timeout_seconds": 30
  }
}
```

## Standard result format
```json
{
  "ok": true,
  "tool_name": "run_command",
  "data": {},
  "warnings": [],
  "errors": [],
  "metadata": {}
}
```

Failures use `ok=false` and structured `errors[]` (`PARSE_ERROR`, `VALIDATION_ERROR`, `UNKNOWN_TOOL`, `EXECUTION_ERROR`).

## Alias behavior
Conservative aliases per tool:

**run_command**: `cmd → command`, `timeout → timeout_seconds`, `cwd → working_directory`, `env → environment`

**write_file**: `file_path → path`

**web_search**: `q → query`, `limit → max_results`, `type → result_type`, `query_text → query`

**web_fetch**: `timeout → timeout_seconds`

**web_extract_text**: `query_text → raw_text`

**web_extract_images**: `max → limit`

**web_image_grabber**: `url → urls`, `path → output_directory`, `max → max_images`

**rss_read**: `url → feed_urls`, `urls → feed_urls`, `limit → max_items`

**dynamic_browser**: `timeout → timeout_seconds`, `selector → wait_selector`

**intelligent_theme_scraper**: `depth → analysis_depth`

**web_code_scraper**: `include_network → include_network_analysis`

**semantic_content_extractor**: `query_text → raw_text`

**search_and_extract_pipeline**: `query → topics`, `urls → seed_urls`

Alias corrections are logged and returned in warnings/metadata. Unknown fields are rejected.
Validation retry hints include allowed keys and a corrected example payload.

## Shell detection
If `shell=auto`:
- Windows: PowerShell preferred, fallback `cmd`
- Linux/macOS: `bash` preferred, fallback `sh`

Result includes `shell_used` and `shell_path` metadata fields.
Default shell is `auto`; omit `shell` unless you need to override selection.

## Workspace boundary policy
- `run_command` is workspace-scoped.
- `working_directory` defaults to `OVERLORD11_TASK_DIR` when present.
- Any `working_directory` resolving outside workspace is rejected.
- Use relative paths inside workspace (for example `.` or `output/`).
- `write_file` resolves relative `path` from `OVERLORD11_TASK_DIR` and rejects outside-workspace targets.

## Examples
Valid dry run:
```json
{
  "tool_name": "run_command",
  "arguments": {
    "command": "npm test",
    "working_directory": ".",
    "dry_run": true
  }
}
```

Invalid example:
```json
{
  "tool_name": "run_command",
  "arguments": {
    "cmd": "python --version",
    "timeout": 30,
    "bad_field": true
  }
}
```
Expected behavior: aliases normalize, `bad_field` fails validation.

## Observability
Each tool call emits a structured event with:
- timestamp
- request_id
- session_id (if provided)
- tool_name
- raw/normalized args
- validation status
- execution status
- duration
- error code

Sensitive keys and environment values are redacted.

## Future expansion
- Add per-tool policy hooks
- Add file/database log sinks
- Add more tool adapters without changing gateway core

