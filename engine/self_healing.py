"""
Overlord11 Engine - Self-Healing System
==========================================
Error classification, retry logic, and failure logging.
"""

import json
import sys
import time
import traceback as tb
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

_BASE_DIR = Path(__file__).resolve().parent.parent
_LOGS_DIR = _BASE_DIR / "logs"
_ERROR_LOG_MD = _BASE_DIR / "ErrorLog.md"


class ErrorType(str, Enum):
    TOOL_FAILURE = "TOOL_FAILURE"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    API_ERROR = "API_ERROR"
    LOGIC_ERROR = "LOGIC_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"


@dataclass
class ErrorRecord:
    error_type: ErrorType
    message: str
    tool_name: Optional[str] = None
    traceback: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    attempt_count: int = 1


class SelfHealingEngine:
    """Classify errors, build retry hints, and log failures/successes."""

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def classify_error(self, exception: Exception, tool_name: Optional[str] = None) -> ErrorRecord:
        """Classify an exception into a structured ErrorRecord."""
        message = str(exception)
        traceback_str = tb.format_exc()
        error_type = self._detect_type(exception, message)
        return ErrorRecord(
            error_type=error_type,
            message=message,
            tool_name=tool_name,
            traceback=traceback_str,
        )

    def _detect_type(self, exception: Exception, message: str) -> ErrorType:
        lower = message.lower()
        if isinstance(exception, SyntaxError):
            return ErrorType.SYNTAX_ERROR
        if isinstance(exception, TimeoutError) or "timeout" in lower or "timed out" in lower:
            return ErrorType.TIMEOUT_ERROR
        if any(k in lower for k in ("api", "http", "status code", "rate limit", "429", "503")):
            return ErrorType.API_ERROR
        if isinstance(exception, (ImportError, ModuleNotFoundError, AttributeError, NameError, TypeError, ValueError)):
            return ErrorType.RUNTIME_ERROR
        if "tool" in lower or "not found" in lower:
            return ErrorType.TOOL_FAILURE
        return ErrorType.LOGIC_ERROR

    # ------------------------------------------------------------------
    # Report building
    # ------------------------------------------------------------------

    def build_error_report(self, record: ErrorRecord) -> str:
        """Format an error report suitable for re-injection into agent context."""
        lines = [
            "⚠️ ERROR DETECTED — Self-Healing Report",
            f"Type      : {record.error_type.value}",
            f"Timestamp : {record.timestamp}",
            f"Attempt   : {record.attempt_count} / {self.max_retries}",
        ]
        if record.tool_name:
            lines.append(f"Tool      : {record.tool_name}")
        lines += [
            f"Message   : {record.message}",
            "",
            "Suggested actions:",
        ]
        lines += self._suggest_fixes(record)
        if record.traceback and record.traceback.strip() != "NoneType: None":
            lines += ["", "Traceback (last 5 lines):", *record.traceback.strip().splitlines()[-5:]]
        return "\n".join(lines)

    def _suggest_fixes(self, record: ErrorRecord) -> list:
        suggestions = {
            ErrorType.SYNTAX_ERROR: ["- Review the generated code for syntax errors", "- Re-generate with explicit formatting instructions"],
            ErrorType.TIMEOUT_ERROR: ["- Retry with a smaller input or fewer tokens", "- Break the task into smaller subtasks"],
            ErrorType.API_ERROR: ["- Wait briefly and retry", "- Switch to fallback provider"],
            ErrorType.TOOL_FAILURE: ["- Verify tool exists and parameters are correct", "- Check tool schema in tools/defs/"],
            ErrorType.RUNTIME_ERROR: ["- Check imports and module availability", "- Ensure correct parameter types"],
            ErrorType.LOGIC_ERROR: ["- Re-examine the task requirements", "- Request agent to reconsider approach"],
        }
        return suggestions.get(record.error_type, ["- Retry the operation"])

    # ------------------------------------------------------------------
    # Retry control
    # ------------------------------------------------------------------

    def should_retry(self, record: ErrorRecord) -> bool:
        """Return True if the error is retryable and attempts remain."""
        non_retryable = {ErrorType.SYNTAX_ERROR, ErrorType.LOGIC_ERROR}
        if record.error_type in non_retryable:
            return False
        return record.attempt_count < self.max_retries

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log_failure(self, record: ErrorRecord, session_id: Optional[str] = None) -> None:
        """Write failure to ErrorLog.md and logs/."""
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)

        # JSON log
        log_file = _LOGS_DIR / "self_healing.jsonl"
        entry = {
            "event": "failure",
            "session_id": session_id,
            "error_type": record.error_type.value,
            "message": record.message,
            "tool_name": record.tool_name,
            "attempt_count": record.attempt_count,
            "timestamp": record.timestamp,
        }
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Markdown log
        md_entry = (
            f"\n## [{record.timestamp}] {record.error_type.value}\n"
            f"- **Tool**: {record.tool_name or 'N/A'}\n"
            f"- **Message**: {record.message}\n"
            f"- **Attempt**: {record.attempt_count}\n"
            f"- **Session**: {session_id or 'N/A'}\n"
        )
        with _ERROR_LOG_MD.open("a", encoding="utf-8") as fh:
            fh.write(md_entry)

    def log_success(self, record: ErrorRecord, fix_description: str) -> None:
        """Mark an error as resolved in the logs."""
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_file = _LOGS_DIR / "self_healing.jsonl"
        entry = {
            "event": "resolved",
            "error_type": record.error_type.value,
            "tool_name": record.tool_name,
            "fix": fix_description,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
