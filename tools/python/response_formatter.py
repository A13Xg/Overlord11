"""
Overlord11 - Response Formatter
=================================
Decides the best output format for a given request and content, then
renders the content in that format.  This is the tool that replaces the ad-hoc
"output tier" logic agents used to do in their heads.

Actions:
  decide   - Analyse the request + content and return the recommended format
             (json | plain_text | markdown | html | csv | yaml) with rationale.
  format   - Render content in a specific format.
  auto     - Decide format and immediately render (combines decide + format).

Formats supported:
  json        - Structured data, APIs, key-value pairs, tables with consistent schema.
  plain_text  - Short answers, one-liners, simple facts.
  markdown    - Moderate-complexity docs, how-tos, comparisons, summaries.
  html        - Complex / publication-quality reports, dashboards, visuals.
  csv         - Tabular data, datasets, exports.
  yaml        - Configuration files, structured but human-friendly data.

Usage (CLI):
    python response_formatter.py --action decide \
        --request "Give me a list of users and their emails" \
        --content '[{"name": "Alice", "email": "a@x.com"}]'

    python response_formatter.py --action format \
        --format_type markdown \
        --content "# My Report\\n..."

    python response_formatter.py --action auto \
        --request "Show me Python package vulnerabilities with severity ratings" \
        --content '{"packages": [...], "summary": "..."}'
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path resolution and optional log import
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

try:
    sys.path.insert(0, str(SCRIPT_DIR))
    from log_manager import log_tool_invocation, log_error
    HAS_LOG = True
except ImportError:
    HAS_LOG = False
    def log_tool_invocation(*a, **kw): pass
    def log_error(*a, **kw): pass


# ---------------------------------------------------------------------------
# Format decision signals (keyword heuristics)
# ---------------------------------------------------------------------------

# Signals that push toward more structured / richer formats
_HTML_SIGNALS = [
    "detailed", "full", "breakdown", "visualize", "publish", "infographic",
    "comprehensive", "dashboard", "report", "chart", "graph", "formatted",
    "presentation", "export html", "html report", "styled",
]
_MARKDOWN_SIGNALS = [
    "summary", "how-to", "how to", "guide", "comparison", "document", "docs",
    "documentation", "explain", "describe", "list steps", "step by step",
    "write up", "writeup", "readme",
]
_JSON_SIGNALS = [
    "json", "api", "data", "dataset", "structure", "schema", "key value",
    "key-value", "parse", "extract", "payload", "endpoint", "response", "object",
    "serialize", "deserialize",
]
_CSV_SIGNALS = [
    "csv", "spreadsheet", "table", "tabular", "export", "rows", "columns",
    "dataset",
]
_YAML_SIGNALS = [
    "yaml", "yml", "config", "configuration", "settings",
]

# Content detection heuristics
_LOOKS_LIKE_JSON = re.compile(r"^\s*[\[{]")
_LOOKS_LIKE_CSV = re.compile(r"^[^\n]+,[^\n]+\n", re.MULTILINE)
_LOOKS_LIKE_YAML = re.compile(r"^\w[\w\s]*:\s+\S", re.MULTILINE)
_LOOKS_LIKE_HTML = re.compile(r"<(html|head|body|div|p|h[1-6]|table)", re.IGNORECASE)
_LOOKS_LIKE_MARKDOWN = re.compile(r"^#{1,6}\s+|^\*{1,2}|^-\s+|\[.+\]\(.+\)", re.MULTILINE)


def _score_signals(text: str, signals: list) -> int:
    """Count how many signal phrases appear in the text (lowercase)."""
    lower = text.lower()
    return sum(1 for s in signals if s in lower)


def _detect_content_type(content: str) -> str:
    """Heuristically detect what the content already looks like."""
    stripped = content.strip()
    if _LOOKS_LIKE_HTML.search(stripped):
        return "html"
    if _LOOKS_LIKE_JSON.match(stripped):
        try:
            json.loads(stripped)
            return "json"
        except ValueError:
            pass
    if _LOOKS_LIKE_CSV.search(stripped):
        return "csv"
    if _LOOKS_LIKE_YAML.search(stripped):
        return "yaml"
    if _LOOKS_LIKE_MARKDOWN.search(stripped):
        return "markdown"
    return "plain_text"


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------

def decide(request: str, content: str = "", context: str = "") -> dict:
    """Analyse the request and content, return the recommended output format.

    Args:
        request: The original user/agent request text.
        content: The raw content that needs to be formatted.
        context: Optional additional context (e.g., downstream use).

    Returns:
        dict with recommended format, confidence score, and rationale.
    """
    combined = f"{request} {context}".lower()
    content_type = _detect_content_type(content) if content else "unknown"

    # Score each format
    scores = {
        "html":       _score_signals(combined, _HTML_SIGNALS)       * 3,
        "markdown":   _score_signals(combined, _MARKDOWN_SIGNALS)   * 2,
        "json":       _score_signals(combined, _JSON_SIGNALS)        * 2,
        "csv":        _score_signals(combined, _CSV_SIGNALS)         * 2,
        "yaml":       _score_signals(combined, _YAML_SIGNALS)        * 2,
        "plain_text": 1,  # baseline
    }

    # Boost from detected content type
    if content_type in scores:
        scores[content_type] += 2

    # Content-length heuristics — short content rarely needs HTML
    content_len = len(content)
    if content_len < 200:
        scores["html"] = max(0, scores["html"] - 2)
        scores["plain_text"] += 1
    elif content_len > 2000:
        scores["html"] += 1
        scores["markdown"] += 1

    # Pick winner
    best_format = max(scores, key=lambda k: scores[k])
    total = sum(scores.values()) or 1
    confidence = round(scores[best_format] / total, 3)

    rationale_parts = []
    if _score_signals(combined, _HTML_SIGNALS):
        rationale_parts.append("request contains publication/visualization keywords")
    if content_type != "unknown":
        rationale_parts.append(f"content auto-detected as {content_type}")
    if content_len > 2000:
        rationale_parts.append("content is long (>2000 chars), richer format preferred")
    if not rationale_parts:
        rationale_parts.append("default to plain_text for short/simple content")

    return {
        "status": "ok",
        "recommended_format": best_format,
        "confidence": confidence,
        "rationale": "; ".join(rationale_parts),
        "scores": scores,
        "detected_content_type": content_type,
    }


# ---------------------------------------------------------------------------
# Format renderers
# ---------------------------------------------------------------------------

def _render_json(content: str) -> str:
    """Pretty-print JSON content, or wrap plain content in a JSON envelope."""
    stripped = content.strip()
    try:
        parsed = json.loads(stripped)
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError):
        # Wrap in an envelope
        return json.dumps({"content": stripped}, indent=2, ensure_ascii=False)


def _render_plain_text(content: str) -> str:
    """Return content as plain text, stripping Markdown markers."""
    # Remove Markdown bold/italic and heading markers
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", content)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    return text.strip()


def _render_markdown(content: str) -> str:
    """Return content in Markdown — pass through if already Markdown."""
    return content.strip()


def _render_html(content: str, title: str = "Report") -> str:
    """Wrap content in a self-contained styled HTML page."""
    # Convert Markdown headings and lists to basic HTML
    html_content = content
    html_content = re.sub(r"^#### (.+)$", r"<h4>\1</h4>", html_content, flags=re.MULTILINE)
    html_content = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html_content, flags=re.MULTILINE)
    html_content = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html_content, flags=re.MULTILINE)
    html_content = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html_content, flags=re.MULTILINE)
    html_content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html_content)
    html_content = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html_content)
    html_content = re.sub(r"^- (.+)$", r"<li>\1</li>", html_content, flags=re.MULTILINE)
    html_content = re.sub(r"(<li>.*?</li>)", r"<ul>\1</ul>", html_content, flags=re.DOTALL)
    html_content = html_content.replace("\n\n", "</p><p>")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         max-width: 960px; margin: 40px auto; padding: 0 20px;
         color: #333; line-height: 1.6; }}
  h1 {{ color: #1a1a2e; border-bottom: 3px solid #4a90d9; padding-bottom: 8px; }}
  h2 {{ color: #2c3e50; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
  h3, h4 {{ color: #34495e; }}
  code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-family: monospace; }}
  pre {{ background: #f4f4f4; padding: 16px; border-radius: 6px; overflow-x: auto; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
  th {{ background: #4a90d9; color: white; }}
  tr:nth-child(even) {{ background: #f9f9f9; }}
  .generated {{ color: #888; font-size: 0.85em; margin-top: 40px; }}
</style>
</head>
<body>
<p>{html_content}</p>
<p class="generated">Generated by Overlord11 Response Formatter</p>
</body>
</html>"""


def _render_csv(content: str) -> str:
    """Return content as CSV — pass through if already CSV, else attempt JSON→CSV conversion."""
    stripped = content.strip()
    # Already looks like CSV
    if _LOOKS_LIKE_CSV.match(stripped):
        return stripped
    # Try JSON array of objects → CSV
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            headers = list(parsed[0].keys())
            rows = [",".join(str(row.get(h, "")) for h in headers) for row in parsed]
            return ",".join(headers) + "\n" + "\n".join(rows)
    except (json.JSONDecodeError, ValueError, KeyError):
        pass
    return stripped


def _render_yaml(content: str) -> str:
    """Return content in YAML format."""
    stripped = content.strip()
    # Try JSON → YAML conversion
    try:
        import yaml
        parsed = json.loads(stripped)
        return yaml.dump(parsed, default_flow_style=False, allow_unicode=True)
    except ImportError:
        pass
    except (json.JSONDecodeError, ValueError):
        pass
    # If already YAML or plain text, return as-is
    return stripped


def format_content(content: str, format_type: str, title: str = "Report") -> dict:
    """Render content in the specified format.

    Args:
        content: Raw content string to format.
        format_type: Target format (json|plain_text|markdown|html|csv|yaml).
        title: Document title (used for HTML output).

    Returns:
        dict with rendered content and format metadata.
    """
    format_type = format_type.lower().strip()
    valid_formats = {"json", "plain_text", "markdown", "html", "csv", "yaml"}
    if format_type not in valid_formats:
        return {
            "status": "error",
            "error": f"Unknown format: '{format_type}'. Choose from: {sorted(valid_formats)}",
        }

    renderers = {
        "json": _render_json,
        "plain_text": _render_plain_text,
        "markdown": _render_markdown,
        "html": lambda c: _render_html(c, title),
        "csv": _render_csv,
        "yaml": _render_yaml,
    }

    try:
        rendered = renderers[format_type](content)
    except Exception as exc:
        return {"status": "error", "error": f"Render failed: {exc}", "format": format_type}

    return {
        "status": "ok",
        "format": format_type,
        "rendered": rendered,
        "char_count": len(rendered),
    }


def auto(request: str, content: str, context: str = "", title: str = "Report") -> dict:
    """Decide the best format and immediately render the content.

    Args:
        request: The original request text.
        content: Raw content to format.
        context: Optional additional context.
        title: Document title (used if HTML is chosen).

    Returns:
        dict with decision metadata and rendered content.
    """
    decision = decide(request, content, context)
    fmt = decision["recommended_format"]
    rendered = format_content(content, fmt, title)

    return {
        "status": "ok",
        "decision": decision,
        "format": fmt,
        "rendered": rendered.get("rendered", ""),
        "char_count": rendered.get("char_count", 0),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Overlord11 Response Formatter")
    parser.add_argument("--action", required=True,
                        choices=["decide", "format", "auto"],
                        help="Action to perform")
    parser.add_argument("--request", default="",
                        help="The original request text (for decide/auto)")
    parser.add_argument("--content", default="",
                        help="Content to format or analyse")
    parser.add_argument("--format_type", default="markdown",
                        choices=["json", "plain_text", "markdown", "html", "csv", "yaml"],
                        help="Target format for the 'format' action")
    parser.add_argument("--context", default="",
                        help="Optional additional context for decide/auto")
    parser.add_argument("--title", default="Report",
                        help="Document title for HTML output")

    args = parser.parse_args()
    start = time.time()

    try:
        if args.action == "decide":
            result = decide(args.request, args.content, args.context)
        elif args.action == "format":
            result = format_content(args.content, args.format_type, args.title)
        elif args.action == "auto":
            result = auto(args.request, args.content, args.context, args.title)
        else:
            result = {"error": f"Unknown action: {args.action}"}

    except Exception as exc:
        result = {"status": "error", "error": str(exc), "action": args.action}
        if HAS_LOG:
            log_error("system", "response_formatter", str(exc))

    duration_ms = (time.time() - start) * 1000
    if HAS_LOG:
        log_tool_invocation(
            session_id="system",
            tool_name="response_formatter",
            params={"action": args.action, "format_type": getattr(args, "format_type", None)},
            result={"status": result.get("status", "error")},
            duration_ms=duration_ms,
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
