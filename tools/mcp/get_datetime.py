from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from ._common import fail, ok
from .app import mcp


@mcp.tool(
    name="get_datetime",
    description="Return timezone-aware datetime details in `data` including ISO, unix timestamp, formatted string, timezone, and components. Use this for normalized time data instead of parsing shell date output.",
)
def get_datetime(
    timezone: str = "UTC",
    format: str = "%Y-%m-%d %H:%M:%S",
    offset_days: int = 0,
) -> dict:
    """Get current datetime with timezone and offset.

    Args:
        timezone: IANA timezone name.
        format: strftime format string used for `formatted`.
        offset_days: Day offset from now; negative is past, positive is future.
    """
    try:
        now = dt.datetime.now(ZoneInfo(timezone)) + dt.timedelta(days=offset_days)
        return ok(
            {
                "iso": now.isoformat(),
                "unix_timestamp": now.timestamp(),
                "formatted": now.strftime(format),
                "timezone": timezone,
                "components": {
                    "year": now.year,
                    "month": now.month,
                    "day": now.day,
                    "hour": now.hour,
                    "minute": now.minute,
                    "second": now.second,
                    "weekday": now.weekday(),
                },
            }
        )
    except Exception as exc:
        return fail(f"Datetime resolution failed: {exc}. Verify timezone and format.")

