"""
notification_tool — Send real-time browser notifications to the operator.

When an agent calls this tool, it writes a NOTIFICATION event to the
master log (logs/master.jsonl) and prints a JSON payload to stdout that
the engine picks up and broadcasts over the existing SSE pipe.

The frontend converts NOTIFICATION events into browser toasts (Web
Notifications API) when the user has granted permission, and always
shows them in the event feed regardless.

Severity levels and their UI colours:
    info    → teal   (general status updates, findings)
    success → green  (milestone reached, task confirmed)
    warning → amber  (unexpected condition, needs attention)
    error   → red    (critical finding, blocker, handoff required)

Return dict:
    {
        "status": "success",
        "action": "notify",
        "title": str,
        "message": str,
        "severity": str,
        "session_id": str | None,
    }
"""

import json
import logging
import sys
from typing import Optional

log = logging.getLogger("overlord11.notification_tool")

_VALID_SEVERITIES = {"info", "success", "warning", "error"}


def notification_tool(
    title: str,
    message: str,
    severity: str = "info",
    session_id: Optional[str] = None,
) -> dict:
    """
    Emit a NOTIFICATION event for the operator.

    Args:
        title:      Short bold heading (max 80 chars).
        message:    Body text (max 300 chars).
        severity:   'info' | 'success' | 'warning' | 'error'.
        session_id: Optional session ID for log correlation.

    Returns:
        Standard success dict with the notification payload echoed back.
    """
    # ── Validation ───────────────────────────────────────────────────
    title = str(title).strip()[:80]
    message = str(message).strip()[:300]

    if not title:
        return {
            "status": "error",
            "action": "notify",
            "error": "title is required and cannot be empty",
            "hint": "Provide a short, descriptive title for the notification.",
        }

    if severity not in _VALID_SEVERITIES:
        severity = "info"

    # ── Build the notification payload ───────────────────────────────
    # The engine broadcasts this dict as-is over SSE as a NOTIFICATION event.
    # The tool_executor picks up the printed JSON from stdout (subprocess
    # strategy) or the return value (direct import strategy).
    payload = {
        "status": "success",
        "action": "notify",
        "title": title,
        "message": message,
        "severity": severity,
        "session_id": session_id,
        # Signal to the engine's event system to emit a NOTIFICATION event
        "_notification": True,
    }

    log.info(
        "Notification [%s]: %s — %s (session=%s)",
        severity.upper(), title, message, session_id,
    )

    return payload


# ---------------------------------------------------------------------------
# Tool main() — called by ToolExecutor (direct import strategy)
# ---------------------------------------------------------------------------

def main(
    title: str = "",
    message: str = "",
    severity: str = "info",
    session_id: Optional[str] = None,
    **_kwargs,
) -> dict:
    """Entry point used by the engine's ToolExecutor."""
    return notification_tool(
        title=title,
        message=message,
        severity=severity,
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Send a browser notification to the operator.")
    parser.add_argument("--title",      required=True, help="Notification title (max 80 chars)")
    parser.add_argument("--message",    required=True, help="Notification body (max 300 chars)")
    parser.add_argument("--severity",   default="info", choices=list(_VALID_SEVERITIES))
    parser.add_argument("--session_id", default=None,  help="Session ID for log correlation")
    args = parser.parse_args()

    result = notification_tool(
        title=args.title,
        message=args.message,
        severity=args.severity,
        session_id=args.session_id,
    )
    print(json.dumps(result, indent=2))
