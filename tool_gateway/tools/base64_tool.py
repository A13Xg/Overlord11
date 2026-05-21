"""
Base64 Tool — encode and decode base64 data, with support for URL-safe variants.
"""
from __future__ import annotations

import base64
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseTool
from .web_common import make_metadata


class Base64Args(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    operation: Literal["encode", "decode"] = Field(..., description="encode or decode")
    data: str = Field(..., min_length=1, description="Text to encode, or base64 string to decode")
    variant: Literal["standard", "urlsafe"] = Field(
        "standard", description="standard or urlsafe (uses - and _ instead of + and /)"
    )
    encoding: str = Field(
        "utf-8", description="Text encoding for encode (input→bytes) or decode (bytes→text)"
    )


class Base64Tool(BaseTool):
    name = "base64_tool"
    description = (
        "Encode text to base64 or decode base64 back to text. "
        "Supports standard and URL-safe variants. "
        "Useful for embedding data in JSON, creating safe identifiers, or processing API payloads."
    )
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    timeout_behavior = "not_applicable"
    examples = [
        {
            "tool_name": "base64_tool",
            "arguments": {"operation": "encode", "data": "Hello, Overlord11!"},
        },
        {
            "tool_name": "base64_tool",
            "arguments": {"operation": "decode", "data": "SGVsbG8sIE92ZXJsb3JkMTEh"},
        },
        {
            "tool_name": "base64_tool",
            "arguments": {"operation": "encode", "data": "data+value", "variant": "urlsafe"},
        },
    ]
    input_model = Base64Args

    def execute(self, args: Base64Args) -> dict[str, Any]:
        warnings: list[str] = []

        if args.operation == "encode":
            try:
                raw_bytes = args.data.encode(args.encoding)
            except (LookupError, UnicodeEncodeError) as exc:
                raise ValueError(f"Encoding error: {exc}") from exc

            if args.variant == "urlsafe":
                result = base64.urlsafe_b64encode(raw_bytes).decode("ascii")
            else:
                result = base64.b64encode(raw_bytes).decode("ascii")

            return {
                "operation": "encode",
                "input_bytes": len(raw_bytes),
                "output_length": len(result),
                "result": result,
                "variant": args.variant,
                "_warnings": warnings,
                "_metadata": make_metadata(partial_success=False, fallbacks_used=[], inferred_values={}),
            }

        else:  # decode
            # Clean up common formatting
            b64_clean = args.data.strip().replace("\n", "").replace(" ", "")
            # Add padding if needed
            pad = 4 - len(b64_clean) % 4
            if pad != 4:
                b64_clean += "=" * pad

            try:
                if args.variant == "urlsafe":
                    raw_bytes = base64.urlsafe_b64decode(b64_clean)
                else:
                    raw_bytes = base64.b64decode(b64_clean)
            except Exception as exc:
                raise ValueError(f"Invalid base64 input: {exc}") from exc

            try:
                text = raw_bytes.decode(args.encoding)
                decode_ok = True
            except (UnicodeDecodeError, LookupError):
                text = raw_bytes.decode("latin-1")
                warnings.append(f"Could not decode as {args.encoding}; used latin-1 fallback")
                decode_ok = False

            return {
                "operation": "decode",
                "input_length": len(args.data.strip()),
                "output_bytes": len(raw_bytes),
                "result": text,
                "variant": args.variant,
                "clean_decode": decode_ok,
                "_warnings": warnings,
                "_metadata": make_metadata(
                    partial_success=bool(warnings), fallbacks_used=[], inferred_values={}
                ),
            }
