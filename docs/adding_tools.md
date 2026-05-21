# Adding Tools

## 1. Implement a tool adapter
Create a class under `tool_gateway/tools/` inheriting `BaseTool`.
Follow the shared style in `tool_gateway/tools/TOOL_THEME.md`.

Required fields:
- `name`
- `description`
- `input_model` (Pydantic, `extra=forbid`)
- `risk_level`
- `destructive`
- `supports_dry_run`
- `examples`

Required method:
- `execute(args)` returning a `dict`

## 2. Define strict schema
Use Pydantic constraints for:
- required fields
- type checks
- enum constraints
- min/max numeric limits

Do not allow unknown fields unless intentionally required.

## 3. Register the tool

Four places need updating:

**a) `tool_gateway/tools/__init__.py`** — add import and `__all__` entry.

**b) `tool_gateway/normalizer.py`** — add an entry in `ALIASES_BY_TOOL` for any argument aliases the LLM might use (e.g. shorthand names). Omit if no aliases are needed.

**c) `tool_gateway/validator.py`** — add an entry in `_ALLOWED_KEYS_BY_TOOL` (list of accepted argument names) and `_EXAMPLES_BY_TOOL` (a minimal valid call payload). These power validation retry hints.

**d) `engine/tool_executor.py`** — import the new tool class and call `registry.register_tool(YourNewTool())` in `ToolExecutor.__init__`.

## 4. Add tests
At minimum:
- valid input
- missing required input
- wrong type
- unknown field rejection
- core success/failure behavior

## 5. Keep behavior deterministic
- No silent guessing
- No mixed result shapes
- Always return structured envelope via gateway

## 6. Logging
Ensure sensitive data is redacted. Include meaningful warnings instead of hidden behavior.
