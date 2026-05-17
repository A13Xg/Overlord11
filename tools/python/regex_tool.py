"""
Overlord11 - Regex Tool
========================
Test, extract, replace, and analyze regular expressions with AI-friendly output.
Provides detailed match information (groups, spans, named captures) useful for
constructing correct patterns iteratively.

Actions:
  test      – Check whether a pattern matches anywhere in a string.
  match     – Try to match at the start of the string (anchored).
  findall   – Find all non-overlapping matches.
  extract   – Extract named or numbered capture groups from all matches.
  replace   – Replace matches with a substitution string (supports backreferences).
  split     – Split a string by a regex pattern.
  validate  – Validate a regex pattern syntax without running it.

Usage (CLI):
    python regex_tool.py --action test --pattern "\\d+" --input "abc 123"
    python regex_tool.py --action findall --pattern "(\\w+)@(\\w+\\.\\w+)" --input "user@example.com"
    python regex_tool.py --action replace --pattern "foo" --input "foo bar foo" --replacement "baz"
    python regex_tool.py --action extract --pattern "(?P<year>\\d{4})-(?P<month>\\d{2})" --input "2024-03"
"""

import argparse
import json
import re
import sys
from typing import Optional


def regex_tool(
    action: str,
    pattern: str,
    input: Optional[str] = None,
    replacement: Optional[str] = None,
    flags: Optional[list] = None,
    max_matches: int = 100,
) -> dict:
    """
    Test, extract, replace, and analyze regular expressions.

    Args:
        action:       Operation: test, match, findall, extract, replace, split, validate.
        pattern:      Regular expression pattern string.
        input:        String to search (required for all actions except validate).
        replacement:  Replacement string for replace action (supports \\1, \\g<name> backrefs).
        flags:        List of regex flag names to apply: IGNORECASE, MULTILINE, DOTALL,
                      VERBOSE, ASCII. Default: none.
        max_matches:  Maximum number of matches to return. Defaults to 100.

    Returns:
        dict with keys:
            status        – "success" or "error"
            action        – action performed
            pattern       – the pattern used
            flags         – flags applied
            matched       – bool, whether any match was found (test/match)
            match_count   – number of matches found
            matches       – list of match detail dicts
            result        – substituted string (replace) or list of parts (split)
            error         – error message (on failure)
            hint          – corrective action (on failure)
    """
    if action not in ("test", "match", "findall", "extract", "replace", "split", "validate"):
        return {
            "status": "error",
            "action": action,
            "error": f"Unknown action: '{action}'",
            "hint": "Use one of: test, match, findall, extract, replace, split, validate",
        }

    # Build flags
    FLAG_MAP = {
        "IGNORECASE": re.IGNORECASE,
        "MULTILINE": re.MULTILINE,
        "DOTALL": re.DOTALL,
        "VERBOSE": re.VERBOSE,
        "ASCII": re.ASCII,
    }
    combined_flags = 0
    applied_flags = []
    for f in (flags or []):
        fu = f.upper()
        if fu in FLAG_MAP:
            combined_flags |= FLAG_MAP[fu]
            applied_flags.append(fu)
        else:
            return {
                "status": "error",
                "action": action,
                "pattern": pattern,
                "error": f"Unknown flag: '{f}'",
                "hint": f"Use one of: {', '.join(FLAG_MAP.keys())}",
            }

    # ── validate ───────────────────────────────────────────────────────────
    if action == "validate":
        try:
            compiled = re.compile(pattern, combined_flags)
            groups = compiled.groups
            named = list(compiled.groupindex.keys())
            return {
                "status": "success",
                "action": "validate",
                "pattern": pattern,
                "valid": True,
                "group_count": groups,
                "named_groups": named,
                "flags": applied_flags,
            }
        except re.error as exc:
            return {
                "status": "error",
                "action": "validate",
                "pattern": pattern,
                "valid": False,
                "error": f"Invalid regex: {exc}",
                "hint": "Check the pattern syntax. Use raw strings (r'...') to avoid double-escaping.",
            }

    # All other actions require input
    if input is None:
        return {
            "status": "error",
            "action": action,
            "pattern": pattern,
            "error": "The 'input' parameter is required",
            "hint": "Provide the string to operate on in the 'input' parameter.",
        }

    # Compile pattern
    try:
        rx = re.compile(pattern, combined_flags)
    except re.error as exc:
        return {
            "status": "error",
            "action": action,
            "pattern": pattern,
            "error": f"Invalid regex pattern: {exc}",
            "hint": "Validate the pattern with the 'validate' action first.",
        }

    def _match_info(m: re.Match) -> dict:
        """Convert a Match object to a serializable dict."""
        info = {
            "text": m.group(0),
            "start": m.start(),
            "end": m.end(),
            "span": [m.start(), m.end()],
        }
        if m.lastindex:
            info["groups"] = list(m.groups())
        if rx.groupindex:
            info["named_groups"] = {k: m.group(k) for k in rx.groupindex}
        return info

    # ── test ───────────────────────────────────────────────────────────────
    if action == "test":
        m = rx.search(input)
        result = {
            "status": "success",
            "action": "test",
            "pattern": pattern,
            "flags": applied_flags,
            "matched": m is not None,
        }
        if m:
            result["first_match"] = _match_info(m)
        return result

    # ── match (anchored at start) ──────────────────────────────────────────
    if action == "match":
        m = rx.match(input)
        result = {
            "status": "success",
            "action": "match",
            "pattern": pattern,
            "flags": applied_flags,
            "matched": m is not None,
        }
        if m:
            result["match"] = _match_info(m)
        return result

    # ── findall ────────────────────────────────────────────────────────────
    if action == "findall":
        all_matches = []
        for m in rx.finditer(input):
            all_matches.append(_match_info(m))
            if len(all_matches) >= max_matches:
                break
        return {
            "status": "success",
            "action": "findall",
            "pattern": pattern,
            "flags": applied_flags,
            "matched": len(all_matches) > 0,
            "match_count": len(all_matches),
            "truncated": len(all_matches) == max_matches,
            "matches": all_matches,
        }

    # ── extract ────────────────────────────────────────────────────────────
    if action == "extract":
        extractions = []
        for m in rx.finditer(input):
            entry = {}
            if rx.groupindex:
                entry = {k: m.group(k) for k in rx.groupindex}
            elif m.lastindex:
                entry = {str(i + 1): m.group(i + 1) for i in range(m.lastindex)}
            else:
                entry = {"0": m.group(0)}
            extractions.append(entry)
            if len(extractions) >= max_matches:
                break
        return {
            "status": "success",
            "action": "extract",
            "pattern": pattern,
            "flags": applied_flags,
            "matched": len(extractions) > 0,
            "match_count": len(extractions),
            "named_groups": list(rx.groupindex.keys()),
            "extractions": extractions,
        }

    # ── replace ────────────────────────────────────────────────────────────
    if action == "replace":
        if replacement is None:
            return {
                "status": "error",
                "action": action,
                "error": "The 'replacement' parameter is required for replace",
                "hint": "Provide a replacement string. Use \\1 or \\g<name> for backreferences.",
            }
        try:
            result_str, count = rx.subn(replacement, input, count=max_matches)
            return {
                "status": "success",
                "action": "replace",
                "pattern": pattern,
                "replacement": replacement,
                "flags": applied_flags,
                "substitution_count": count,
                "result": result_str,
            }
        except re.error as exc:
            return {
                "status": "error",
                "action": action,
                "error": f"Replacement error: {exc}",
                "hint": "Check backreference syntax: \\1, \\2, or \\g<name> for named groups.",
            }

    # ── split ──────────────────────────────────────────────────────────────
    if action == "split":
        parts = rx.split(input, maxsplit=max_matches)
        return {
            "status": "success",
            "action": "split",
            "pattern": pattern,
            "flags": applied_flags,
            "part_count": len(parts),
            "result": parts,
        }

    return {"status": "error", "action": action, "error": "Internal error"}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Overlord11 Regex Tool")
    parser.add_argument("--action", required=True,
                        choices=["test", "match", "findall", "extract", "replace", "split", "validate"])
    parser.add_argument("--pattern", required=True, help="Regex pattern")
    parser.add_argument("--input", default=None, help="Input string")
    parser.add_argument("--replacement", default=None, help="Replacement string for replace action")
    parser.add_argument("--flags", nargs="*", default=None,
                        choices=["IGNORECASE", "MULTILINE", "DOTALL", "VERBOSE", "ASCII"])
    parser.add_argument("--max_matches", type=int, default=100)

    args = parser.parse_args()
    result = regex_tool(
        action=args.action,
        pattern=args.pattern,
        input=args.input,
        replacement=args.replacement,
        flags=args.flags,
        max_matches=args.max_matches,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
