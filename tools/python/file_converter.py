"""
Overlord11 - File Converter Tool
==================================
Converts files between common formats without relying on heavyweight
third-party binaries.  Uses built-in Python libraries by default and
progressively enhances with optional packages when available.

Supported conversions:
  json ↔ yaml          - Interchange format conversion
  json ↔ csv           - Flat list-of-dicts  ↔  CSV table
  json  → markdown     - Dict/list → formatted Markdown table
  csv   → markdown     - CSV table → Markdown table
  csv   → json         - CSV rows → JSON array
  markdown → html      - Markdown to basic HTML page
  text  → json         - Plain text wrapped in JSON envelope
  html  → text         - Strip HTML tags, return plain text
  json  → text         - Pretty-print JSON to plain text

Actions:
  convert      - Convert a file from one format to another.
  list_formats - List all supported conversion routes.
  detect       - Auto-detect the format of a file.

Usage (CLI):
    python file_converter.py --action list_formats
    python file_converter.py --action detect --input /path/to/file.json
    python file_converter.py --action convert \
        --input /path/to/data.json --output /path/to/data.yaml
    python file_converter.py --action convert \
        --input /path/to/data.csv --output /path/to/data.md
    python file_converter.py --action convert \
        --input /path/to/page.html --output /path/to/page.txt
"""

import argparse
import csv
import html as html_lib
import io
import json
import re
import sys
import time
from pathlib import Path

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

# Optional enhancements
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# ---------------------------------------------------------------------------
# Conversion route registry
# ---------------------------------------------------------------------------

SUPPORTED_ROUTES = [
    ("json", "yaml"),
    ("yaml", "json"),
    ("json", "csv"),
    ("csv", "json"),
    ("json", "markdown"),
    ("csv", "markdown"),
    ("csv", "yaml"),
    ("markdown", "html"),
    ("text", "json"),
    ("html", "text"),
    ("json", "text"),
]

FORMAT_EXTENSIONS = {
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".csv": "csv",
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "html",
    ".htm": "html",
    ".txt": "text",
}


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def detect_format(file_path: str) -> dict:
    """Auto-detect the format of a file by extension and content sniffing.

    Args:
        file_path: Path to the file.

    Returns:
        dict with detected format and confidence.
    """
    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "error": f"File not found: {file_path}"}

    # Extension-based detection (high confidence)
    ext = path.suffix.lower()
    if ext in FORMAT_EXTENSIONS:
        return {
            "status": "ok",
            "file": str(path),
            "format": FORMAT_EXTENSIONS[ext],
            "method": "extension",
            "confidence": "high",
        }

    # Content sniffing (medium confidence)
    try:
        content = path.read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError as e:
        return {"status": "error", "error": str(e)}

    stripped = content.strip()
    if stripped.startswith(("{", "[")):
        try:
            json.loads(stripped)
            fmt = "json"
        except ValueError:
            fmt = "text"
    elif re.match(r"^\w[\w\s]*:\s+\S", stripped, re.MULTILINE):
        fmt = "yaml"
    elif re.match(r"^[^\n]+,[^\n]+\n", stripped, re.MULTILINE):
        fmt = "csv"
    elif re.search(r"<(html|head|body|div)", stripped, re.IGNORECASE):
        fmt = "html"
    elif re.search(r"^#{1,6}\s+", stripped, re.MULTILINE):
        fmt = "markdown"
    else:
        fmt = "text"

    return {
        "status": "ok",
        "file": str(path),
        "format": fmt,
        "method": "content_sniffing",
        "confidence": "medium",
    }


# ---------------------------------------------------------------------------
# Converters
# ---------------------------------------------------------------------------

def _json_to_yaml(data: str) -> str:
    """Convert JSON string to YAML."""
    parsed = json.loads(data)
    if HAS_YAML:
        return yaml.dump(parsed, default_flow_style=False, allow_unicode=True)
    # Fallback: simple key: value rendering (only for shallow dicts)
    if isinstance(parsed, dict):
        lines = []
        for k, v in parsed.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
            else:
                lines.append(f"{k}: {v}")
        return "\n".join(lines)
    return json.dumps(parsed, indent=2, ensure_ascii=False)


def _yaml_to_json(data: str) -> str:
    """Convert YAML string to JSON."""
    if HAS_YAML:
        parsed = yaml.safe_load(data)
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    return json.dumps({"error": "PyYAML not installed — pip install pyyaml",
                        "raw_yaml": data}, indent=2, ensure_ascii=False)


def _json_to_csv(data: str) -> str:
    """Convert JSON array-of-objects to CSV."""
    parsed = json.loads(data)
    if not isinstance(parsed, list):
        parsed = [parsed]  # wrap single object
    if not parsed:
        return ""
    headers = list(parsed[0].keys()) if isinstance(parsed[0], dict) else ["value"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore",
                            lineterminator="\n")
    writer.writeheader()
    for row in parsed:
        if isinstance(row, dict):
            writer.writerow(row)
        else:
            writer.writerow({"value": str(row)})
    return buf.getvalue()


def _csv_to_json(data: str) -> str:
    """Convert CSV string to JSON array-of-objects."""
    reader = csv.DictReader(io.StringIO(data))
    rows = list(reader)
    return json.dumps(rows, indent=2, ensure_ascii=False)


def _dict_or_list_to_markdown(parsed: object, title: str = "") -> str:
    """Convert a Python dict or list to Markdown."""
    lines = []
    if title:
        lines.append(f"# {title}\n")

    if isinstance(parsed, list):
        if parsed and isinstance(parsed[0], dict):
            # Table
            headers = list(parsed[0].keys())
            lines.append("| " + " | ".join(str(h) for h in headers) + " |")
            lines.append("| " + " | ".join("---" for _ in headers) + " |")
            for row in parsed:
                lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
        else:
            for item in parsed:
                lines.append(f"- {item}")
    elif isinstance(parsed, dict):
        for k, v in parsed.items():
            if isinstance(v, (dict, list)):
                lines.append(f"\n## {k}\n")
                lines.append(_dict_or_list_to_markdown(v))
            else:
                lines.append(f"**{k}**: {v}")
    else:
        lines.append(str(parsed))

    return "\n".join(lines)


def _json_to_markdown(data: str) -> str:
    """Convert JSON to Markdown."""
    parsed = json.loads(data)
    return _dict_or_list_to_markdown(parsed)


def _csv_to_markdown(data: str) -> str:
    """Convert CSV to Markdown table."""
    reader = csv.reader(io.StringIO(data))
    rows = list(reader)
    if not rows:
        return ""
    header = rows[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _csv_to_yaml(data: str) -> str:
    """Convert CSV to YAML."""
    reader = csv.DictReader(io.StringIO(data))
    rows = list(reader)
    if HAS_YAML:
        return yaml.dump(rows, default_flow_style=False, allow_unicode=True)
    return json.dumps(rows, indent=2, ensure_ascii=False)


def _markdown_to_html(data: str, title: str = "Document") -> str:
    """Convert Markdown to a self-contained HTML page."""
    content = data
    content = re.sub(r"^#### (.+)$", r"<h4>\1</h4>", content, flags=re.MULTILINE)
    content = re.sub(r"^### (.+)$", r"<h3>\1</h3>", content, flags=re.MULTILINE)
    content = re.sub(r"^## (.+)$", r"<h2>\1</h2>", content, flags=re.MULTILINE)
    content = re.sub(r"^# (.+)$", r"<h1>\1</h1>", content, flags=re.MULTILINE)
    content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
    content = re.sub(r"\*(.+?)\*", r"<em>\1</em>", content)
    content = re.sub(r"`(.+?)`", r"<code>\1</code>", content)
    content = re.sub(r"^\- (.+)$", r"<li>\1</li>", content, flags=re.MULTILINE)
    content = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', content)
    content = content.replace("\n\n", "</p>\n<p>")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{html_lib.escape(title)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 900px; margin: 40px auto; padding: 0 20px;
         color: #333; line-height: 1.6; }}
  h1 {{ border-bottom: 2px solid #4a90d9; padding-bottom: 8px; }}
  code {{ background: #f4f4f4; padding: 2px 5px; border-radius: 3px; }}
  pre  {{ background: #f4f4f4; padding: 16px; border-radius: 6px; overflow-x: auto; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; }}
  th {{ background: #4a90d9; color: white; }}
</style>
</head>
<body>
<p>{content}</p>
</body>
</html>"""


def _html_to_text(data: str) -> str:
    """Strip HTML tags and return plain text."""
    if HAS_BS4:
        soup = BeautifulSoup(data, "html.parser")
        return soup.get_text(separator="\n", strip=True)
    # Fallback: regex-based stripping
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", data, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _json_to_text(data: str) -> str:
    """Pretty-print JSON as readable plain text."""
    try:
        parsed = json.loads(data)
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    except ValueError:
        return data


def _text_to_json(data: str) -> str:
    """Wrap plain text in a JSON envelope."""
    return json.dumps({"content": data, "line_count": data.count("\n") + 1},
                      indent=2, ensure_ascii=False)


# Route dispatcher
_ROUTES = {
    ("json",     "yaml"):     _json_to_yaml,
    ("yaml",     "json"):     _yaml_to_json,
    ("json",     "csv"):      _json_to_csv,
    ("csv",      "json"):     _csv_to_json,
    ("json",     "markdown"): _json_to_markdown,
    ("csv",      "markdown"): _csv_to_markdown,
    ("csv",      "yaml"):     _csv_to_yaml,
    ("markdown", "html"):     _markdown_to_html,
    ("html",     "text"):     _html_to_text,
    ("json",     "text"):     _json_to_text,
    ("text",     "json"):     _text_to_json,
}


# ---------------------------------------------------------------------------
# Main convert function
# ---------------------------------------------------------------------------

def convert(
    input_path: str,
    output_path: str = None,
    from_format: str = None,
    to_format: str = None,
    title: str = "Document",
) -> dict:
    """Convert a file from one format to another.

    Args:
        input_path: Path to the source file.
        output_path: Path for the converted output file.
                     Auto-derived from input_path + to_format extension if omitted.
        from_format: Source format (auto-detected if omitted).
        to_format: Target format (derived from output_path extension if omitted).
        title: Title for HTML/Markdown output documents.

    Returns:
        dict with conversion status and output file path.
    """
    in_path = Path(input_path)
    if not in_path.exists():
        return {"status": "error", "error": f"Input file not found: {input_path}"}

    # Detect source format
    if not from_format:
        detection = detect_format(input_path)
        if detection.get("status") == "error":
            return detection
        from_format = detection["format"]

    from_format = from_format.lower().strip()

    # Determine target format
    if not to_format and output_path:
        out_ext = Path(output_path).suffix.lower()
        to_format = FORMAT_EXTENSIONS.get(out_ext)

    if not to_format:
        return {"status": "error",
                "error": "Cannot determine target format. Provide --to_format or an output path with a recognised extension."}

    to_format = to_format.lower().strip()

    # Validate route
    route = (from_format, to_format)
    if route not in _ROUTES:
        return {
            "status": "error",
            "error": f"Conversion from '{from_format}' to '{to_format}' is not supported.",
            "supported_routes": [f"{a} → {b}" for a, b in SUPPORTED_ROUTES],
        }

    # Read input
    try:
        content = in_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"status": "error", "error": f"Cannot read input file: {e}"}

    # Convert
    try:
        converter = _ROUTES[route]
        if route == ("markdown", "html"):
            result_text = converter(content, title)
        else:
            result_text = converter(content)
    except Exception as exc:
        return {"status": "error", "error": f"Conversion failed: {exc}",
                "from": from_format, "to": to_format}

    # Determine output path
    ext_map = {
        "json": ".json", "yaml": ".yaml", "csv": ".csv",
        "markdown": ".md", "html": ".html", "text": ".txt",
    }
    if not output_path:
        output_path = str(in_path.with_suffix(ext_map.get(to_format, ".out")))

    out_path = Path(output_path)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result_text, encoding="utf-8")
    except OSError as e:
        return {"status": "error", "error": f"Cannot write output file: {e}"}

    return {
        "status": "ok",
        "input": str(in_path),
        "output": str(out_path),
        "from_format": from_format,
        "to_format": to_format,
        "input_size_bytes": in_path.stat().st_size,
        "output_size_bytes": out_path.stat().st_size,
    }


def list_formats() -> dict:
    """Return all supported conversion routes."""
    return {
        "status": "ok",
        "routes": [{"from": a, "to": b} for a, b in SUPPORTED_ROUTES],
        "formats": sorted(FORMAT_EXTENSIONS.values()),
        "note": (
            "Install optional packages for richer output: "
            "'pip install pyyaml beautifulsoup4'"
        ),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Overlord11 File Converter Tool")
    parser.add_argument("--action", required=True,
                        choices=["convert", "detect", "list_formats"],
                        help="Action to perform")
    parser.add_argument("--input", default=None, help="Input file path")
    parser.add_argument("--output", default=None, help="Output file path")
    parser.add_argument("--from_format", default=None,
                        help="Source format (auto-detected if omitted)")
    parser.add_argument("--to_format", default=None,
                        help="Target format (derived from output extension if omitted)")
    parser.add_argument("--title", default="Document",
                        help="Document title for HTML/Markdown output")

    args = parser.parse_args()
    start = time.time()

    try:
        if args.action == "list_formats":
            result = list_formats()
        elif args.action == "detect":
            if not args.input:
                result = {"error": "--input is required for detect"}
            else:
                result = detect_format(args.input)
        elif args.action == "convert":
            if not args.input:
                result = {"error": "--input is required for convert"}
            else:
                result = convert(
                    input_path=args.input,
                    output_path=args.output,
                    from_format=args.from_format,
                    to_format=args.to_format,
                    title=args.title,
                )
        else:
            result = {"error": f"Unknown action: {args.action}"}

    except Exception as exc:
        result = {"status": "error", "error": str(exc), "action": args.action}
        if HAS_LOG:
            log_error("system", "file_converter", str(exc))

    duration_ms = (time.time() - start) * 1000
    if HAS_LOG:
        log_tool_invocation(
            session_id="system",
            tool_name="file_converter",
            params={"action": args.action, "from": args.from_format, "to": args.to_format},
            result={"status": result.get("status", "error")},
            duration_ms=duration_ms,
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
