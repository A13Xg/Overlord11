"""
JSON Schema Validator tool — validate a JSON document against a JSON Schema (Draft 7 / 2020-12).
Uses pure-Python jsonschema if available, otherwise falls back to structural checks.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseTool
from .web_common import make_metadata


class JsonSchemaValidatorArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    data: str = Field(..., description="JSON string (or URL) to validate")
    json_schema: str = Field(..., description="JSON Schema as a string (Draft 7 or 2020-12)")
    stop_on_first_error: bool = Field(
        False, description="Stop at first validation error (faster) vs collect all errors"
    )


class JsonSchemaValidatorTool(BaseTool):
    name = "json_schema_validator"
    description = (
        "Validate a JSON document against a JSON Schema (Draft 7 / 2020-12). "
        "Returns a list of validation errors with paths, or confirms validity. "
        "Useful for verifying API responses, config files, or structured data."
    )
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    timeout_behavior = "not_applicable"
    examples = [
        {
            "tool_name": "json_schema_validator",
            "arguments": {
                "data": "{\"name\": \"Alice\", \"age\": 30}",
                "json_schema": "{\"type\": \"object\", \"required\": [\"name\", \"age\"], \"properties\": {\"name\": {\"type\": \"string\"}, \"age\": {\"type\": \"integer\"}}}",
            },
        },
        {
            "tool_name": "json_schema_validator",
            "arguments": {
                "data": "[1, 2, \"three\"]",
                "json_schema": "{\"type\": \"array\", \"items\": {\"type\": \"number\"}}",
            },
        },
    ]
    input_model = JsonSchemaValidatorArgs

    def execute(self, args: JsonSchemaValidatorArgs) -> dict[str, Any]:
        warnings: list[str] = []

        # --- Parse document ---
        try:
            document = json.loads(args.data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON data: {exc}") from exc

        # --- Parse schema ---
        try:
            schema_obj = json.loads(args.json_schema)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON Schema: {exc}") from exc

        # --- Validate ---
        errors: list[dict[str, Any]] = []
        validator_used = "jsonschema"

        try:
            import jsonschema  # type: ignore
            from jsonschema import Draft7Validator, ValidationError

            validator = Draft7Validator(schema_obj)
            if args.stop_on_first_error:
                try:
                    validator.validate(document)
                except ValidationError as exc:
                    errors.append({
                        "path": ".".join(str(p) for p in exc.absolute_path) or "(root)",
                        "message": exc.message,
                        "schema_path": ".".join(str(p) for p in exc.absolute_schema_path),
                        "failed_value": repr(exc.instance)[:200],
                    })
            else:
                for error in validator.iter_errors(document):
                    errors.append({
                        "path": ".".join(str(p) for p in error.absolute_path) or "(root)",
                        "message": error.message,
                        "schema_path": ".".join(str(p) for p in error.absolute_schema_path),
                        "failed_value": repr(error.instance)[:200],
                    })

        except ImportError:
            # Fallback: basic type check only
            validator_used = "builtin_basic"
            warnings.append(
                "jsonschema package not installed; only basic type checking performed. "
                "Install with: pip install jsonschema"
            )
            schema_type = schema_obj.get("type")
            if schema_type:
                type_map = {
                    "object": dict, "array": list, "string": str,
                    "number": (int, float), "integer": int, "boolean": bool, "null": type(None),
                }
                expected = type_map.get(schema_type)
                if expected and not isinstance(document, expected):
                    errors.append({
                        "path": "(root)",
                        "message": f"Expected type '{schema_type}', got {type(document).__name__}",
                        "schema_path": "type",
                        "failed_value": repr(document)[:200],
                    })

        return {
            "valid": len(errors) == 0,
            "error_count": len(errors),
            "errors": errors,
            "validator_used": validator_used,
            "_warnings": warnings,
            "_metadata": make_metadata(
                partial_success=bool(warnings),
                fallbacks_used=["builtin_basic"] if validator_used == "builtin_basic" else [],
                inferred_values={},
            ),
        }
