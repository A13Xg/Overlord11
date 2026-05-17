"""
Overlord11 - Datetime Tool
===========================
Parse, format, calculate, and convert dates and times. Pure stdlib — no external
dependencies. Useful for timestamping events, scheduling relative offsets, and
interpreting dates in various formats.

Actions:
  now        – Return current date/time in multiple formats and timezones.
  parse      – Parse a date/time string into a structured dict.
  format     – Format a date/time string or timestamp into a specified format.
  add        – Add a duration (days, hours, minutes, seconds, weeks) to a datetime.
  subtract   – Subtract a duration from a datetime.
  diff       – Calculate the difference between two datetimes.
  convert    – Convert a datetime from one timezone to another.
  timestamp  – Convert Unix timestamp to datetime or vice versa.
  validate   – Check whether a date/time string is valid.

Usage (CLI):
    python datetime_tool.py --action now
    python datetime_tool.py --action parse --input "2024-03-15T14:30:00"
    python datetime_tool.py --action add --input "2024-01-01" --days 30
    python datetime_tool.py --action diff --start "2024-01-01" --end "2024-12-31"
    python datetime_tool.py --action format --input "2024-03-15" --output_format "%B %d, %Y"
"""

import argparse
import json
import sys
from datetime import datetime, date, timedelta, timezone
from typing import Optional


# Common date/time format strings to try when parsing
PARSE_FORMATS = [
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%Y%m%d",
]

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"


def _try_parse(s: str) -> Optional[datetime]:
    """Try to parse a string with multiple common formats."""
    s = s.strip()
    for fmt in PARSE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _dt_to_dict(dt: datetime, label: str = "datetime") -> dict:
    """Convert a datetime to a structured info dict."""
    return {
        label: dt.strftime(ISO_FORMAT),
        "date": dt.strftime("%Y-%m-%d"),
        "time": dt.strftime("%H:%M:%S"),
        "year": dt.year,
        "month": dt.month,
        "day": dt.day,
        "hour": dt.hour,
        "minute": dt.minute,
        "second": dt.second,
        "weekday": dt.strftime("%A"),
        "weekday_num": dt.weekday(),  # 0=Monday
        "day_of_year": dt.timetuple().tm_yday,
        "iso_format": dt.strftime(ISO_FORMAT),
        "timestamp": dt.timestamp() if hasattr(dt, "timestamp") else None,
    }


def datetime_tool(
    action: str,
    input: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    output_format: Optional[str] = None,
    days: float = 0,
    hours: float = 0,
    minutes: float = 0,
    seconds: float = 0,
    weeks: float = 0,
    timezone_name: Optional[str] = None,
    unix_timestamp: Optional[float] = None,
) -> dict:
    """
    Parse, format, calculate, and convert dates and times.

    Args:
        action:         Operation: now, parse, format, add, subtract, diff, convert, timestamp, validate.
        input:          Date/time string to operate on (most actions).
        start:          Start datetime string (diff action).
        end:            End datetime string (diff action).
        output_format:  strftime format string for format action (e.g., '%B %d, %Y').
        days:           Days to add/subtract.
        hours:          Hours to add/subtract.
        minutes:        Minutes to add/subtract.
        seconds:        Seconds to add/subtract.
        weeks:          Weeks to add/subtract.
        timezone_name:  Timezone name for convert action (e.g., 'UTC', 'UTC+5').
        unix_timestamp: Unix timestamp for timestamp action (alternative to input).

    Returns:
        dict with structured date/time information and status/error fields.
    """
    valid_actions = ("now", "parse", "format", "add", "subtract", "diff",
                     "convert", "timestamp", "validate")
    if action not in valid_actions:
        return {
            "status": "error",
            "action": action,
            "error": f"Unknown action: '{action}'",
            "hint": f"Use one of: {', '.join(valid_actions)}",
        }

    # ── now ────────────────────────────────────────────────────────────────
    if action == "now":
        utc_now = datetime.now(timezone.utc)
        local_now = datetime.now()
        return {
            "status": "success",
            "action": "now",
            **_dt_to_dict(local_now, "local"),
            "utc": utc_now.strftime(ISO_FORMAT),
            "utc_date": utc_now.strftime("%Y-%m-%d"),
            "utc_timestamp": utc_now.timestamp(),
            "formats": {
                "iso8601": local_now.strftime("%Y-%m-%dT%H:%M:%S"),
                "rfc2822": local_now.strftime("%a, %d %b %Y %H:%M:%S"),
                "human": local_now.strftime("%B %d, %Y %I:%M %p"),
                "date_only": local_now.strftime("%Y-%m-%d"),
                "time_only": local_now.strftime("%H:%M:%S"),
            },
        }

    # ── validate ───────────────────────────────────────────────────────────
    if action == "validate":
        if not input:
            return {
                "status": "error",
                "action": action,
                "error": "The 'input' parameter is required for validate",
                "hint": "Provide a date/time string to validate.",
            }
        dt = _try_parse(input)
        return {
            "status": "success",
            "action": "validate",
            "input": input,
            "valid": dt is not None,
            "parsed": dt.strftime(ISO_FORMAT) if dt else None,
        }

    # ── parse ──────────────────────────────────────────────────────────────
    if action == "parse":
        if not input:
            return {
                "status": "error",
                "action": action,
                "error": "The 'input' parameter is required for parse",
                "hint": "Provide a date/time string to parse.",
            }
        dt = _try_parse(input)
        if dt is None:
            return {
                "status": "error",
                "action": action,
                "input": input,
                "error": f"Cannot parse date/time string: '{input}'",
                "hint": "Supported formats include ISO 8601 (YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS) and common locale formats.",
            }
        return {"status": "success", "action": "parse", "input": input, **_dt_to_dict(dt)}

    # ── format ─────────────────────────────────────────────────────────────
    if action == "format":
        if not input:
            return {
                "status": "error",
                "action": action,
                "error": "The 'input' parameter is required for format",
                "hint": "Provide a date/time string in 'input'.",
            }
        dt = _try_parse(input)
        if dt is None:
            return {
                "status": "error",
                "action": action,
                "input": input,
                "error": f"Cannot parse date/time string: '{input}'",
                "hint": "Provide an ISO 8601 date/time string.",
            }
        fmt = output_format or ISO_FORMAT
        try:
            formatted = dt.strftime(fmt)
        except Exception as exc:
            return {
                "status": "error",
                "action": action,
                "error": f"Invalid format string: {exc}",
                "hint": "Use strftime format codes, e.g., '%Y-%m-%d', '%B %d, %Y', '%I:%M %p'",
            }
        return {
            "status": "success",
            "action": "format",
            "input": input,
            "output_format": fmt,
            "result": formatted,
        }

    # ── add / subtract ─────────────────────────────────────────────────────
    if action in ("add", "subtract"):
        if not input:
            return {
                "status": "error",
                "action": action,
                "error": "The 'input' parameter is required",
                "hint": "Provide a date/time string to modify.",
            }
        dt = _try_parse(input)
        if dt is None:
            return {
                "status": "error",
                "action": action,
                "input": input,
                "error": f"Cannot parse date/time string: '{input}'",
                "hint": "Provide an ISO 8601 date/time string.",
            }
        delta = timedelta(days=days, hours=hours, minutes=minutes,
                          seconds=seconds, weeks=weeks)
        result_dt = dt + delta if action == "add" else dt - delta
        return {
            "status": "success",
            "action": action,
            "input": input,
            "delta": {
                "weeks": weeks, "days": days, "hours": hours,
                "minutes": minutes, "seconds": seconds,
                "total_seconds": delta.total_seconds(),
            },
            "original": dt.strftime(ISO_FORMAT),
            **_dt_to_dict(result_dt, "result"),
        }

    # ── diff ───────────────────────────────────────────────────────────────
    if action == "diff":
        if not start or not end:
            return {
                "status": "error",
                "action": action,
                "error": "Both 'start' and 'end' parameters are required for diff",
                "hint": "Provide two date/time strings to compare.",
            }
        dt_start = _try_parse(start)
        dt_end = _try_parse(end)
        errors = []
        if dt_start is None:
            errors.append(f"Cannot parse start: '{start}'")
        if dt_end is None:
            errors.append(f"Cannot parse end: '{end}'")
        if errors:
            return {
                "status": "error",
                "action": action,
                "error": "; ".join(errors),
                "hint": "Provide ISO 8601 date/time strings.",
            }
        delta = dt_end - dt_start
        total_seconds = delta.total_seconds()
        abs_seconds = abs(total_seconds)
        return {
            "status": "success",
            "action": "diff",
            "start": start,
            "end": end,
            "earlier_is_start": total_seconds >= 0,
            "total_seconds": total_seconds,
            "absolute_seconds": abs_seconds,
            "total_days": delta.days,
            "hours": int(abs_seconds // 3600),
            "minutes": int((abs_seconds % 3600) // 60),
            "seconds": int(abs_seconds % 60),
            "human_readable": _format_delta(abs_seconds),
        }

    # ── timestamp ──────────────────────────────────────────────────────────
    if action == "timestamp":
        if unix_timestamp is not None:
            try:
                dt = datetime.fromtimestamp(float(unix_timestamp))
                return {
                    "status": "success",
                    "action": "timestamp",
                    "unix_timestamp": unix_timestamp,
                    **_dt_to_dict(dt, "local"),
                    "utc": datetime.fromtimestamp(float(unix_timestamp), tz=timezone.utc).strftime(ISO_FORMAT),
                }
            except (ValueError, OSError) as exc:
                return {
                    "status": "error",
                    "action": action,
                    "error": f"Invalid Unix timestamp: {exc}",
                    "hint": "Provide a valid Unix timestamp (seconds since epoch).",
                }
        if input:
            dt = _try_parse(input)
            if dt is None:
                return {
                    "status": "error",
                    "action": action,
                    "error": f"Cannot parse date/time string: '{input}'",
                    "hint": "Provide an ISO 8601 date/time string.",
                }
            return {
                "status": "success",
                "action": "timestamp",
                "input": input,
                "unix_timestamp": dt.timestamp(),
                "unix_timestamp_ms": int(dt.timestamp() * 1000),
            }
        return {
            "status": "error",
            "action": action,
            "error": "Provide either 'input' (datetime string → timestamp) or 'unix_timestamp' (timestamp → datetime)",
            "hint": "Set 'input' to a datetime string or 'unix_timestamp' to a Unix epoch value.",
        }

    # ── convert (timezone) ─────────────────────────────────────────────────
    if action == "convert":
        if not input:
            return {
                "status": "error",
                "action": action,
                "error": "The 'input' parameter is required for convert",
                "hint": "Provide a date/time string in 'input' and target timezone in 'timezone_name'.",
            }
        dt = _try_parse(input)
        if dt is None:
            return {
                "status": "error",
                "action": action,
                "error": f"Cannot parse date/time string: '{input}'",
                "hint": "Provide an ISO 8601 date/time string.",
            }
        if not timezone_name:
            return {
                "status": "error",
                "action": action,
                "error": "The 'timezone_name' parameter is required for convert",
                "hint": "Provide a timezone name like 'UTC', 'UTC+5', 'UTC-8'.",
            }
        try:
            tz = _parse_timezone(timezone_name)
            dt_aware = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
            dt_converted = dt_aware.astimezone(tz)
            return {
                "status": "success",
                "action": "convert",
                "input": input,
                "source_tz": "local/unspecified",
                "target_tz": timezone_name,
                "result": dt_converted.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "result_iso": dt_converted.strftime(ISO_FORMAT),
            }
        except Exception as exc:
            return {
                "status": "error",
                "action": action,
                "error": f"Timezone conversion failed: {exc}",
                "hint": "Use timezone names like 'UTC', 'UTC+5', 'UTC-8'. For named zones, install pytz.",
            }

    return {"status": "error", "action": action, "error": "Internal error"}


def _format_delta(total_seconds: float) -> str:
    """Format a duration as a human-readable string."""
    s = int(total_seconds)
    if s < 60:
        return f"{s} second{'s' if s != 1 else ''}"
    if s < 3600:
        m = s // 60
        return f"{m} minute{'s' if m != 1 else ''}"
    if s < 86400:
        h = s // 3600
        m = (s % 3600) // 60
        return f"{h}h {m}m" if m else f"{h} hour{'s' if h != 1 else ''}"
    d = s // 86400
    h = (s % 86400) // 3600
    return f"{d}d {h}h" if h else f"{d} day{'s' if d != 1 else ''}"


def _parse_timezone(name: str):
    """Parse a timezone name. Supports 'UTC', 'UTC+N', 'UTC-N'."""
    import re
    name = name.strip()
    if name.upper() == "UTC":
        return timezone.utc
    m = re.match(r"UTC([+-])(\d+)(?::(\d+))?", name, re.IGNORECASE)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        hours = int(m.group(2))
        minutes = int(m.group(3) or 0)
        offset = timedelta(hours=hours, minutes=minutes) * sign
        return timezone(offset)
    # Try pytz if available
    try:
        import pytz
        return pytz.timezone(name)
    except Exception:
        pass
    raise ValueError(f"Unknown timezone: '{name}'. Use 'UTC', 'UTC+N', or install pytz for named zones.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Overlord11 Datetime Tool")
    parser.add_argument("--action", required=True,
                        choices=["now", "parse", "format", "add", "subtract",
                                 "diff", "convert", "timestamp", "validate"])
    parser.add_argument("--input", default=None)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--output_format", default=None)
    parser.add_argument("--days", type=float, default=0)
    parser.add_argument("--hours", type=float, default=0)
    parser.add_argument("--minutes", type=float, default=0)
    parser.add_argument("--seconds", type=float, default=0)
    parser.add_argument("--weeks", type=float, default=0)
    parser.add_argument("--timezone_name", default=None)
    parser.add_argument("--unix_timestamp", type=float, default=None)

    args = parser.parse_args()
    result = datetime_tool(
        action=args.action,
        input=args.input,
        start=args.start,
        end=args.end,
        output_format=args.output_format,
        days=args.days,
        hours=args.hours,
        minutes=args.minutes,
        seconds=args.seconds,
        weeks=args.weeks,
        timezone_name=args.timezone_name,
        unix_timestamp=args.unix_timestamp,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
