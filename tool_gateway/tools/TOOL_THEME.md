# Tool Theme Rules

This file defines the shared style contract for all gateway tool adapters.

## Naming
- Tool `name` must be `snake_case`.
- Argument keys must be `snake_case`.
- Public runtime tools in this environment are `run_command` and `write_file`.

## Input Schema
- Use strict Pydantic models.
- Set `extra="forbid"` by default.
- Use explicit defaults for optional fields.
- Reject ambiguous/unknown fields.
- Keep conservative alias normalization in `tool_gateway/normalizer.py`.

## Result Contract
- Tool gateway returns the standard envelope:
  - `ok`, `tool_name`, `data`, `warnings`, `errors`, `metadata`.
- Tool adapter `execute()` should return deterministic dict data.
- Include workspace and execution metadata when relevant.

## Error And Warning Style
- Validation failures should be recoverable with actionable retry hints.
- Error messages should name invalid/missing fields explicitly.
- Warnings should be concise and operationally useful.

## Workspace Safety
- All file writes and command execution must stay inside `OVERLORD11_TASK_DIR`.
- Relative paths resolve from `OVERLORD11_TASK_DIR`.
- Absolute/outside-workspace paths are rejected.

## Examples
- Each tool must include realistic examples aligned to current schema.
- Include at least one safe default example and one override example where applicable.
