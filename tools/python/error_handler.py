"""
Overlord11 - Error Handler Tool
=================================
Self-correcting error analysis with online resource lookup.

Workflow:
  1. INTERPRET  - Parse and classify the error (type, message, traceback).
  2. SELF-FIX   - Apply known fix patterns from an internal knowledge base.
  3. WEB SEARCH - Search Stack Overflow + dev forums for community solutions.
  4. RETRY HINT - Return a structured fix suggestion for the calling agent.
  5. ESCALATE   - If fix cannot be determined, return a parsed, human-readable
                  error report and skip the response_formatter step.

Actions:
  analyze      - Classify and explain an error without attempting a fix.
  self_correct - Full self-correction loop: interpret → fix → search → report.
  search_error - Search web for the error and return top community solutions.
  summarize    - Parse, explain, and summarize an error for direct delivery.

Usage (CLI):
    python error_handler.py --action analyze \
        --error "NameError: name 'foo' is not defined"

    python error_handler.py --action self_correct \
        --error "ModuleNotFoundError: No module named 'requests'" \
        --context "Running tool web_fetch.py"

    python error_handler.py --action search_error \
        --error "sqlite3.OperationalError: no such table: users"

    python error_handler.py --action summarize \
        --error "Traceback (most recent call last):\\n  File 'app.py', line 5\\n    x = 1/0\\nZeroDivisionError: division by zero"
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution and optional log import
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

try:
    sys.path.insert(0, str(SCRIPT_DIR))
    from log_manager import log_tool_invocation, log_error as log_err
    HAS_LOG = True
except ImportError:
    HAS_LOG = False
    def log_tool_invocation(*a, **kw): pass
    def log_err(*a, **kw): pass

# Optional web scraper for richer search
try:
    from web_scraper import search as web_search
    HAS_WEB_SCRAPER = True
except ImportError:
    HAS_WEB_SCRAPER = False

# ---------------------------------------------------------------------------
# Internal knowledge base: common error patterns and their fixes
# ---------------------------------------------------------------------------

_FIX_PATTERNS = [
    # ModuleNotFoundError / ImportError
    {
        "pattern": re.compile(r"ModuleNotFoundError: No module named '(.+?)'", re.IGNORECASE),
        "category": "import_error",
        "severity": "medium",
        "fix_template": "Install the missing module: `pip install {match1}`",
        "explanation": "Python cannot find the package '{match1}' in the current environment.",
    },
    {
        "pattern": re.compile(r"ImportError: cannot import name '(.+?)' from '(.+?)'", re.IGNORECASE),
        "category": "import_error",
        "severity": "medium",
        "fix_template": "Check that '{match1}' exists in '{match2}'. The function/class may have been renamed or removed in the installed version.",
        "explanation": "The symbol '{match1}' does not exist in module '{match2}'.",
    },
    # NameError
    {
        "pattern": re.compile(r"NameError: name '(.+?)' is not defined", re.IGNORECASE),
        "category": "name_error",
        "severity": "medium",
        "fix_template": "Define or import '{match1}' before using it. Check for typos in the variable name.",
        "explanation": "'{match1}' is referenced but has not been assigned in the current scope.",
    },
    # TypeError
    {
        "pattern": re.compile(r"TypeError: (.+?) argument must be (.+?), not (.+)", re.IGNORECASE),
        "category": "type_error",
        "severity": "medium",
        "fix_template": "Convert the argument to the expected type: {match2}. Currently receiving {match3}.",
        "explanation": "A function received an argument of the wrong type.",
    },
    {
        "pattern": re.compile(r"TypeError: '(.+?)' object is not subscriptable", re.IGNORECASE),
        "category": "type_error",
        "severity": "medium",
        "fix_template": "'{match1}' objects do not support indexing. Check that the variable is a list, dict, or tuple.",
        "explanation": "You are trying to index into an object that does not support subscript access.",
    },
    # AttributeError
    {
        "pattern": re.compile(r"AttributeError: '(.+?)' object has no attribute '(.+?)'", re.IGNORECASE),
        "category": "attribute_error",
        "severity": "medium",
        "fix_template": "Check the API docs for '{match1}'. The attribute '{match2}' may not exist or may be named differently in the installed version.",
        "explanation": "'{match1}' does not have a property or method named '{match2}'.",
    },
    # KeyError
    {
        "pattern": re.compile(r"KeyError: '(.+?)'", re.IGNORECASE),
        "category": "key_error",
        "severity": "low",
        "fix_template": "Use dict.get('{match1}', default) instead of dict['{match1}'] to safely access the key, or verify the key exists first.",
        "explanation": "Key '{match1}' was not found in the dictionary.",
    },
    # FileNotFoundError
    {
        "pattern": re.compile(r"FileNotFoundError: \[Errno 2\] No such file or directory: '(.+?)'", re.IGNORECASE),
        "category": "file_error",
        "severity": "medium",
        "fix_template": "Verify that the path '{match1}' exists and the working directory is correct. Use os.path.abspath() to debug path resolution.",
        "explanation": "The file or directory '{match1}' does not exist at the expected location.",
    },
    # PermissionError
    {
        "pattern": re.compile(r"PermissionError: \[Errno 13\] Permission denied: '(.+?)'", re.IGNORECASE),
        "category": "permission_error",
        "severity": "high",
        "fix_template": "Check file/directory permissions for '{match1}'. You may need to run with elevated privileges or change ownership.",
        "explanation": "The process does not have permission to access '{match1}'.",
    },
    # ZeroDivisionError
    {
        "pattern": re.compile(r"ZeroDivisionError", re.IGNORECASE),
        "category": "arithmetic_error",
        "severity": "low",
        "fix_template": "Add a guard before the division: `if denominator != 0: result = numerator / denominator`",
        "explanation": "The code is attempting to divide by zero.",
    },
    # JSONDecodeError
    {
        "pattern": re.compile(r"json\.decoder\.JSONDecodeError|JSONDecodeError", re.IGNORECASE),
        "category": "parse_error",
        "severity": "medium",
        "fix_template": "Validate the JSON input before parsing. Use try/except json.JSONDecodeError. Print or log the raw string to debug malformed content.",
        "explanation": "The input string is not valid JSON.",
    },
    # RecursionError
    {
        "pattern": re.compile(r"RecursionError: maximum recursion depth exceeded", re.IGNORECASE),
        "category": "recursion_error",
        "severity": "high",
        "fix_template": "Add a base case to your recursive function or increase sys.setrecursionlimit(). Consider converting to an iterative approach.",
        "explanation": "The recursion depth limit was exceeded.",
    },
    # ConnectionError / requests
    {
        "pattern": re.compile(r"(ConnectionError|ConnectionRefusedError|requests\.exceptions\.ConnectionError)", re.IGNORECASE),
        "category": "network_error",
        "severity": "high",
        "fix_template": "Verify the target server is running and reachable. Check the URL, port, firewall rules, and network connectivity.",
        "explanation": "A network connection could not be established.",
    },
    # Timeout
    {
        "pattern": re.compile(r"(TimeoutError|requests\.exceptions\.Timeout)", re.IGNORECASE),
        "category": "network_error",
        "severity": "medium",
        "fix_template": "Increase the request timeout or implement a retry strategy with exponential backoff.",
        "explanation": "The operation exceeded the configured timeout.",
    },
    # SyntaxError
    {
        "pattern": re.compile(r"SyntaxError: (.+)", re.IGNORECASE),
        "category": "syntax_error",
        "severity": "high",
        "fix_template": "Fix the syntax error: {match1}. Review the line indicated in the traceback.",
        "explanation": "Python could not parse the source code due to invalid syntax.",
    },
    # IndentationError
    {
        "pattern": re.compile(r"IndentationError: (.+)", re.IGNORECASE),
        "category": "syntax_error",
        "severity": "medium",
        "fix_template": "Fix indentation: {match1}. Use consistent spaces (4 spaces per level) and do not mix tabs and spaces.",
        "explanation": "Python found inconsistent indentation.",
    },
    # OSError / IOError
    {
        "pattern": re.compile(r"(OSError|IOError): (.+)", re.IGNORECASE),
        "category": "io_error",
        "severity": "medium",
        "fix_template": "Handle the OS error: {match2}. Verify paths, permissions, and disk space.",
        "explanation": "An OS-level I/O error occurred.",
    },
]

_SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "unknown": 0}


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _classify_error(error_text: str) -> dict:
    """Parse and classify an error string using pattern matching."""
    # Extract Python traceback info
    tb_match = re.search(
        r'File "(.+?)", line (\d+), in (.+)', error_text
    )
    file_ref = tb_match.group(1) if tb_match else None
    line_no = int(tb_match.group(2)) if tb_match else None
    function_ref = tb_match.group(3) if tb_match else None

    # Match against known patterns
    matched_rule = None
    matched_groups = None
    for rule in _FIX_PATTERNS:
        m = rule["pattern"].search(error_text)
        if m:
            matched_rule = rule
            matched_groups = m.groups()
            break

    # Extract error type from last line of traceback
    last_line = error_text.strip().splitlines()[-1] if error_text.strip() else ""
    error_type_match = re.match(r"^([A-Za-z]+Error|[A-Za-z]+Exception|[A-Za-z]+Warning):", last_line)
    error_type = error_type_match.group(1) if error_type_match else "UnknownError"

    return {
        "error_type": error_type,
        "file": file_ref,
        "line": line_no,
        "function": function_ref,
        "last_line": last_line,
        "category": matched_rule["category"] if matched_rule else "unknown",
        "severity": matched_rule["severity"] if matched_rule else "unknown",
        "matched_rule": matched_rule,
        "matched_groups": matched_groups,
    }


def _apply_fix(classification: dict, context: str = "") -> dict:
    """Generate a fix suggestion from matched rule."""
    rule = classification.get("matched_rule")
    groups = classification.get("matched_groups") or []

    if not rule:
        return {
            "fix_available": False,
            "suggestion": (
                "No known fix pattern matched this error. "
                "Review the traceback, check documentation, or search online."
            ),
        }

    # Substitute match groups into templates
    fix = rule["fix_template"]
    explanation = rule["explanation"]
    for i, g in enumerate(groups, start=1):
        fix = fix.replace(f"{{match{i}}}", g or "")
        explanation = explanation.replace(f"{{match{i}}}", g or "")

    return {
        "fix_available": True,
        "suggestion": fix,
        "explanation": explanation,
        "category": rule["category"],
        "severity": rule["severity"],
    }


def _build_search_query(error_text: str, context: str = "") -> str:
    """Build an effective search query from the error."""
    # Take the most informative line
    last_line = error_text.strip().splitlines()[-1] if error_text.strip() else error_text
    # Strip file paths and line numbers to generalise the query
    clean = re.sub(r'File ".+?", line \d+, in \w+', "", last_line)
    clean = re.sub(r"\s+", " ", clean).strip()
    if context:
        return f"python {clean} {context[:50]}".strip()
    return f"python {clean}".strip()


def _fetch_so_answers(query: str, max_results: int = 3) -> list:
    """Search Stack Overflow via the SE API and return top answer snippets."""
    results = []
    try:
        encoded = urllib.parse.quote(query)
        api_url = (
            f"https://api.stackexchange.com/2.3/search/advanced"
            f"?order=desc&sort=relevance&q={encoded}"
            f"&accepted=True&site=stackoverflow&pagesize={max_results}"
        )
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "Overlord11-ErrorHandler/1.0"},
        )
        import gzip as _gzip
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read()
            # SE API returns gzip-compressed responses
            try:
                raw = _gzip.decompress(raw)
            except Exception:
                pass
            data = json.loads(raw.decode("utf-8", errors="replace"))

        for item in data.get("items", [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "score": item.get("score", 0),
                "answered": item.get("is_answered", False),
                "answer_count": item.get("answer_count", 0),
                "tags": item.get("tags", []),
            })
    except Exception as exc:
        results = [{"error": f"SO API request failed: {exc}"}]

    return results


def _web_search_fallback(query: str, max_results: int = 5) -> list:
    """Fallback to DuckDuckGo via web_scraper if SO API fails."""
    if not HAS_WEB_SCRAPER:
        return []
    try:
        result = web_search(query=query, max_results=max_results)
        if isinstance(result, dict) and "results" in result:
            return result["results"]
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Public actions
# ---------------------------------------------------------------------------

def analyze(error_text: str, context: str = "") -> dict:
    """Classify and explain an error without attempting a fix.

    Args:
        error_text: The raw error message / traceback.
        context: Optional context about what was running when the error occurred.

    Returns:
        dict with error classification, type, severity, and explanation.
    """
    classification = _classify_error(error_text)
    fix = _apply_fix(classification, context)

    return {
        "status": "ok",
        "action": "analyze",
        "error_type": classification["error_type"],
        "category": classification["category"],
        "severity": classification["severity"],
        "file": classification["file"],
        "line": classification["line"],
        "function": classification["function"],
        "last_line": classification["last_line"],
        "explanation": fix.get("explanation", "Unknown error. Review the traceback."),
        "fix_available": fix["fix_available"],
        "suggestion": fix.get("suggestion", ""),
        "context": context,
    }


def search_error(error_text: str, context: str = "", max_results: int = 5) -> dict:
    """Search Stack Overflow and the web for community solutions to the error.

    Args:
        error_text: The raw error message / traceback.
        context: Optional context about what caused the error.
        max_results: Maximum number of search results to return.

    Returns:
        dict with search query, SO answers, and any fallback web results.
    """
    query = _build_search_query(error_text, context)
    so_results = _fetch_so_answers(query, max_results=max_results)
    web_results = []
    if not so_results or all("error" in r for r in so_results):
        web_results = _web_search_fallback(query, max_results=max_results)

    return {
        "status": "ok",
        "action": "search_error",
        "search_query": query,
        "so_results": so_results,
        "web_results": web_results,
        "result_count": len(so_results) + len(web_results),
    }


def self_correct(
    error_text: str,
    context: str = "",
    command: str = "",
    max_search_results: int = 3,
) -> dict:
    """Full self-correction loop.

    Steps:
      1. Classify and interpret the error.
      2. Apply internal fix pattern if matched.
      3. If no internal fix, search Stack Overflow for community solutions.
      4. Return a structured fix suggestion.
      5. If a second attempt is implied and the same error recurs, escalate
         with a plain-language summary (skip response_formatter).

    Args:
        error_text: The raw error message / traceback.
        context: Context about the operation that failed.
        command: The command or code that produced the error (optional).
        max_search_results: Max SO/web results to retrieve.

    Returns:
        dict with classification, fix suggestions, sources, and escalation flag.
    """
    classification = _classify_error(error_text)
    fix = _apply_fix(classification, context)
    timestamp = datetime.now().isoformat()

    # Attempt online search when no internal fix is available
    search_results = {}
    if not fix["fix_available"] or classification["severity"] in ("high", "critical"):
        search_results = search_error(error_text, context, max_search_results)

    # Determine if we should escalate directly to user (skip formatter)
    # Escalate if: no fix found AND no search results
    so_results = search_results.get("so_results", [])
    web_results = search_results.get("web_results", [])
    has_any_result = bool(so_results or web_results) and not all(
        "error" in r for r in (so_results + web_results)
    )
    should_escalate = not fix["fix_available"] and not has_any_result

    return {
        "status": "escalated" if should_escalate else "ok",
        "action": "self_correct",
        "timestamp": timestamp,
        "error_type": classification["error_type"],
        "category": classification["category"],
        "severity": classification["severity"],
        "file": classification["file"],
        "line": classification["line"],
        "context": context,
        "command": command,
        "internal_fix": fix,
        "search_results": search_results,
        "escalate_to_user": should_escalate,
        "escalation_message": (
            _build_escalation_message(error_text, classification, context)
            if should_escalate else None
        ),
        "next_steps": _build_next_steps(fix, search_results, should_escalate),
    }


def summarize(error_text: str, context: str = "") -> dict:
    """Parse, explain, and summarize an error for direct delivery to the user.

    This is the terminal action: it skips the response_formatter and returns
    a plain-language, human-readable error report.

    Args:
        error_text: The raw error message / traceback.
        context: Optional context about the failing operation.

    Returns:
        dict with a human-readable summary ready for direct delivery.
    """
    classification = _classify_error(error_text)
    fix = _apply_fix(classification, context)

    # Build structured summary
    sections = []

    sections.append("## Error Summary\n")
    sections.append(f"**Type**: {classification['error_type']}")
    sections.append(f"**Severity**: {classification['severity'].upper()}")
    if classification["file"]:
        sections.append(f"**Location**: `{classification['file']}`, line {classification['line']}")
    if classification["function"]:
        sections.append(f"**In function**: `{classification['function']}`")
    sections.append(f"\n**What happened**: {fix.get('explanation', classification['last_line'])}")

    if fix["fix_available"]:
        sections.append(f"\n## Suggested Fix\n{fix['suggestion']}")
    else:
        sections.append("\n## Next Steps\nNo automatic fix was found for this error.")
        sections.append("1. Review the full traceback above for the exact line that failed.")
        sections.append("2. Search Stack Overflow or the library documentation for the error message.")
        sections.append("3. Check that all dependencies are installed and at compatible versions.")

    if context:
        sections.append(f"\n## Context\n{context}")

    sections.append(f"\n---\n*Error analysis generated by Overlord11 Error Handler at {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return {
        "status": "ok",
        "action": "summarize",
        "error_type": classification["error_type"],
        "severity": classification["severity"],
        "category": classification["category"],
        "summary": "\n".join(sections),
        "fix_available": fix["fix_available"],
        "suggestion": fix.get("suggestion", ""),
        "direct_delivery": True,  # Signal to orchestrator: deliver this directly
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_escalation_message(error_text: str, classification: dict, context: str) -> str:
    """Build a plain-language escalation message for direct user delivery."""
    lines = [
        "## ❌ Unresolvable Error",
        "",
        f"**Error type**: {classification['error_type']}",
        f"**Severity**: {classification['severity'].upper()}",
    ]
    if classification["file"]:
        lines.append(f"**File**: `{classification['file']}`  **Line**: {classification['line']}")
    if context:
        lines.append(f"**Context**: {context}")
    lines += [
        "",
        "### Full Error",
        f"```\n{error_text.strip()}\n```",
        "",
        "### Analysis",
        "No automatic fix could be determined for this error, and no matching community solutions were found.",
        "Please review the error details above and consult the relevant documentation.",
    ]
    return "\n".join(lines)


def _build_next_steps(fix: dict, search_results: dict, escalate: bool) -> list:
    """Build an ordered list of recommended next steps."""
    steps = []
    if fix["fix_available"]:
        steps.append(f"Apply the suggested fix: {fix['suggestion']}")
    so = search_results.get("so_results", [])
    for r in so[:2]:
        if "link" in r:
            steps.append(f"Review Stack Overflow answer: {r['link']}")
    if escalate:
        steps.append("Escalate to user with the summarize action — this error could not be auto-resolved.")
    return steps


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Overlord11 Error Handler Tool")
    parser.add_argument("--action", required=True,
                        choices=["analyze", "self_correct", "search_error", "summarize"],
                        help="Error handling action to perform")
    parser.add_argument("--error", default="",
                        help="The error message or traceback to process")
    parser.add_argument("--context", default="",
                        help="Context about the operation that produced the error")
    parser.add_argument("--command", default="",
                        help="Command or code that produced the error")
    parser.add_argument("--max_results", type=int, default=3,
                        help="Max search results for search_error / self_correct")

    args = parser.parse_args()

    if not args.error:
        print(json.dumps({"error": "--error is required for all actions"}))
        sys.exit(1)

    start = time.time()

    try:
        if args.action == "analyze":
            result = analyze(args.error, args.context)
        elif args.action == "self_correct":
            result = self_correct(
                args.error, args.context, args.command, args.max_results
            )
        elif args.action == "search_error":
            result = search_error(args.error, args.context, args.max_results)
        elif args.action == "summarize":
            result = summarize(args.error, args.context)
        else:
            result = {"error": f"Unknown action: {args.action}"}

    except Exception as exc:
        result = {"status": "error", "error": str(exc), "action": args.action}
        if HAS_LOG:
            log_err("system", "error_handler", str(exc))

    duration_ms = (time.time() - start) * 1000
    if HAS_LOG:
        log_tool_invocation(
            session_id="system",
            tool_name="error_handler",
            params={"action": args.action},
            result={"status": result.get("status", "error")},
            duration_ms=duration_ms,
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
