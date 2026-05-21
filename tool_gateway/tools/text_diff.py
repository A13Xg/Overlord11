"""
Text Diff tool — compute a unified diff between two text strings.
Returns the diff as unified-diff text and structured hunk data.
"""
from __future__ import annotations

import difflib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseTool
from .web_common import make_metadata


class TextDiffArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    text_a: str = Field(..., description="Original text (left side / before)")
    text_b: str = Field(..., description="New text (right side / after)")
    label_a: str = Field("original", description="Label for the original text")
    label_b: str = Field("modified", description="Label for the modified text")
    context_lines: int = Field(3, ge=0, le=20, description="Lines of context around each change")
    format: Literal["unified", "summary", "side_by_side"] = Field(
        "unified",
        description="unified=full diff text, summary=change counts only, side_by_side=parallel comparison",
    )


class TextDiffTool(BaseTool):
    name = "text_diff"
    description = (
        "Compare two text strings and return the differences. "
        "Supports unified diff, change summary, and side-by-side formats. "
        "Useful for comparing outputs, validating transformations, or tracking changes."
    )
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    timeout_behavior = "not_applicable"
    examples = [
        {
            "tool_name": "text_diff",
            "arguments": {
                "text_a": "Hello world\nLine two",
                "text_b": "Hello world\nLine 2\nLine three",
            },
        },
        {
            "tool_name": "text_diff",
            "arguments": {
                "text_a": "version: 1.0",
                "text_b": "version: 2.0",
                "label_a": "v1",
                "label_b": "v2",
                "format": "summary",
            },
        },
    ]
    input_model = TextDiffArgs

    def execute(self, args: TextDiffArgs) -> dict[str, Any]:
        lines_a = args.text_a.splitlines(keepends=True)
        lines_b = args.text_b.splitlines(keepends=True)

        # Ensure trailing newline for clean diff
        if lines_a and not lines_a[-1].endswith("\n"):
            lines_a[-1] += "\n"
        if lines_b and not lines_b[-1].endswith("\n"):
            lines_b[-1] += "\n"

        diff_lines = list(
            difflib.unified_diff(
                lines_a,
                lines_b,
                fromfile=args.label_a,
                tofile=args.label_b,
                n=args.context_lines,
            )
        )

        added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
        changed = min(added, removed)
        net_added = added - changed
        net_removed = removed - changed

        identical = len(diff_lines) == 0

        base: dict[str, Any] = {
            "identical": identical,
            "added_lines": added,
            "removed_lines": removed,
            "changed_lines": changed,
            "net_added": net_added,
            "net_removed": net_removed,
            "lines_a": len(lines_a),
            "lines_b": len(lines_b),
            "_warnings": [],
        }

        if args.format == "summary":
            return {
                **base,
                "format": "summary",
                "_metadata": make_metadata(partial_success=False, fallbacks_used=[], inferred_values={}),
            }

        elif args.format == "side_by_side":
            matcher = difflib.SequenceMatcher(None, lines_a, lines_b)
            pairs: list[dict[str, Any]] = []
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    pairs.append({
                        "tag": tag,
                        "left": lines_a[i].rstrip("\n") if i < len(lines_a) else None,
                        "right": lines_b[j].rstrip("\n") if j < len(lines_b) else None,
                    })
                # Handle unequal block lengths
                la, lb = i2 - i1, j2 - j1
                if la > lb:
                    for i in range(i1 + lb, i2):
                        pairs.append({"tag": tag, "left": lines_a[i].rstrip("\n"), "right": None})
                elif lb > la:
                    for j in range(j1 + la, j2):
                        pairs.append({"tag": tag, "left": None, "right": lines_b[j].rstrip("\n")})
            return {
                **base,
                "format": "side_by_side",
                "pairs": pairs[:2000],
                "truncated": len(pairs) > 2000,
                "_metadata": make_metadata(partial_success=False, fallbacks_used=[], inferred_values={}),
            }

        else:  # unified
            diff_text = "".join(diff_lines)
            return {
                **base,
                "format": "unified",
                "diff": diff_text,
                "_metadata": make_metadata(partial_success=False, fallbacks_used=[], inferred_values={}),
            }
