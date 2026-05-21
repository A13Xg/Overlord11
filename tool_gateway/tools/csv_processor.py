"""
CSV Processor tool — read, filter, sort, and summarize CSV data from a file or string.
"""
from __future__ import annotations

import csv
import io
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseTool
from .web_common import make_metadata


class CsvProcessorArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    data: str | None = Field(
        None,
        description="CSV content as a string, or a workspace-relative file path ending in .csv",
    )
    filter_column: str | None = Field(None, description="Column name to filter on")
    filter_value: str | None = Field(None, description="Value that filter_column must equal (case-insensitive)")
    sort_column: str | None = Field(None, description="Column to sort by")
    sort_order: Literal["asc", "desc"] = Field("asc", description="Sort direction")
    columns: list[str] = Field([], description="Subset of columns to include (empty = all)")
    max_rows: int = Field(500, ge=1, le=10000, description="Max rows to return (default 500)")
    operation: Literal["select", "summary", "unique"] = Field(
        "select",
        description="select=return rows, summary=column stats, unique=distinct values per column",
    )


class CsvProcessorTool(BaseTool):
    name = "csv_processor"
    description = (
        "Read, filter, sort, and summarize CSV data. "
        "Input can be a raw CSV string or a workspace-relative .csv file path. "
        "Operations: select (return rows), summary (column statistics), unique (distinct values)."
    )
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    timeout_behavior = "not_applicable"
    examples = [
        {"tool_name": "csv_processor", "arguments": {"data": "data/results.csv", "operation": "summary"}},
        {
            "tool_name": "csv_processor",
            "arguments": {
                "data": "name,age\nAlice,30\nBob,25",
                "filter_column": "age",
                "filter_value": "30",
            },
        },
        {
            "tool_name": "csv_processor",
            "arguments": {
                "data": "data/sales.csv",
                "sort_column": "revenue",
                "sort_order": "desc",
                "max_rows": 20,
            },
        },
    ]
    input_model = CsvProcessorArgs

    def execute(self, args: CsvProcessorArgs) -> dict[str, Any]:
        warnings: list[str] = []

        if not args.data:
            raise ValueError("Either a CSV string or a workspace-relative file path is required")

        # --- Load CSV content ---
        raw_csv = args.data
        source = "inline"
        if args.data.endswith(".csv") and "\n" not in args.data:
            workspace = Path(os.environ.get("OVERLORD11_TASK_DIR") or os.getcwd()).resolve()
            p = Path(args.data)
            target = (workspace / p).resolve() if not p.is_absolute() else p.resolve()
            try:
                target.relative_to(workspace)
            except ValueError as exc:
                raise ValueError("csv file path must resolve within workspace root") from exc
            if not target.exists():
                raise FileNotFoundError(f"CSV file not found: {args.data}")
            raw_csv = target.read_text(encoding="utf-8", errors="replace")
            source = str(target.name)

        # --- Parse CSV ---
        reader = csv.DictReader(io.StringIO(raw_csv))
        try:
            rows = list(reader)
            headers = list(reader.fieldnames or [])
        except csv.Error as exc:
            raise ValueError(f"CSV parse error: {exc}") from exc

        total_rows = len(rows)

        # --- Column subset ---
        if args.columns:
            missing = [c for c in args.columns if c not in headers]
            if missing:
                warnings.append(f"Columns not found: {missing}")
            headers = [h for h in headers if not args.columns or h in args.columns]
            rows = [{k: v for k, v in row.items() if k in headers} for row in rows]

        # --- Filter ---
        if args.filter_column and args.filter_value is not None:
            if args.filter_column not in (reader.fieldnames or []):
                warnings.append(f"filter_column '{args.filter_column}' not found in headers")
            else:
                target_val = args.filter_value.lower()
                rows = [r for r in rows if str(r.get(args.filter_column, "")).lower() == target_val]

        # --- Sort ---
        if args.sort_column:
            if args.sort_column not in headers:
                warnings.append(f"sort_column '{args.sort_column}' not found in headers")
            else:
                def _sort_key(r: dict) -> tuple:
                    v = r.get(args.sort_column, "")
                    try:
                        return (0, float(v))
                    except (ValueError, TypeError):
                        return (1, str(v).lower())

                rows.sort(key=_sort_key, reverse=(args.sort_order == "desc"))

        # --- Operation ---
        if args.operation == "summary":
            summary: dict[str, Any] = {}
            for col in headers:
                values = [r.get(col, "") for r in rows]
                numeric = []
                for v in values:
                    try:
                        numeric.append(float(v))
                    except (ValueError, TypeError):
                        pass
                summary[col] = {
                    "count": len(values),
                    "non_empty": sum(1 for v in values if v),
                    "unique": len(set(values)),
                    **(
                        {
                            "numeric_count": len(numeric),
                            "min": min(numeric),
                            "max": max(numeric),
                            "mean": round(sum(numeric) / len(numeric), 6),
                        }
                        if numeric
                        else {}
                    ),
                }
            return {
                "source": source,
                "operation": "summary",
                "total_rows": total_rows,
                "columns": headers,
                "summary": summary,
                "_warnings": warnings,
                "_metadata": make_metadata(partial_success=bool(warnings), fallbacks_used=[], inferred_values={}),
            }

        elif args.operation == "unique":
            unique: dict[str, list[str]] = {
                col: sorted(set(r.get(col, "") for r in rows))[:200]
                for col in headers
            }
            return {
                "source": source,
                "operation": "unique",
                "total_rows": total_rows,
                "columns": headers,
                "unique_values": unique,
                "_warnings": warnings,
                "_metadata": make_metadata(partial_success=bool(warnings), fallbacks_used=[], inferred_values={}),
            }

        else:  # select
            truncated = len(rows) > args.max_rows
            result_rows = rows[: args.max_rows]
            if truncated:
                warnings.append(f"Results truncated to {args.max_rows} rows (total: {len(rows)})")
            return {
                "source": source,
                "operation": "select",
                "total_rows": total_rows,
                "returned_rows": len(result_rows),
                "columns": headers,
                "rows": result_rows,
                "truncated": truncated,
                "_warnings": warnings,
                "_metadata": make_metadata(partial_success=truncated, fallbacks_used=[], inferred_values={}),
            }
