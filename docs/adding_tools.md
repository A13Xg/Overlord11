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

## 3. Register tool
Register tool in gateway setup via `ToolRegistry.register_tool(...)`.

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
