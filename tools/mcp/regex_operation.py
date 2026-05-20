
import json
import re
from typing import Literal, List, Any, Dict

from ._common import fail, ok
from .app import mcp


@mcp.tool(
    name="regex_operation",
    description="Apply a regex operation and return matches/groups/result/match_count in `data`. Prefer this for explicit regex workflows over shell utilities.",
)
def regex_operation(
    pattern: str,
    text: str,
    operation: Literal["match", "find_all", "replace", "split", "validate"],
    replacement: str = "",
    flags: List[Literal["IGNORECASE", "MULTILINE", "DOTALL"]] = [],
) -> Dict[str, Any]:
    """Run a regex operation on input text.

    Args:
        pattern: Regular expression pattern.
        text: Input text to inspect or transform.
        operation: Type of regex operation.
        replacement: Replacement template used for replace operation.
        flags: Regex flags to apply.
    """
    try:
        flag_map = {
            "IGNORECASE": re.IGNORECASE,
            "MULTILINE": re.MULTILINE,
            "DOTALL": re.DOTALL,
        }
        fv = 0
        for flag in flags:
            fv |= flag_map[flag]
        rx = re.compile(pattern, fv)
        matches = []
        groups = []
        result = ""
        match_count = 0
        if operation == "match":
            m = rx.match(text)
            if m:
                matches = [m.group(0)]
                groups = [list(m.groups())]
                result = m.group(0)
                match_count = 1
        elif operation == "find_all":
            found = list(rx.finditer(text))
            matches = [m.group(0) for m in found]
            groups = [list(m.groups()) for m in found]
            match_count = len(found)
        elif operation == "replace":
            result, match_count = rx.subn(replacement, text)
            found = list(rx.finditer(text))
            matches = [m.group(0) for m in found]
            groups = [list(m.groups()) for m in found]
        elif operation == "split":
            result = json.dumps(rx.split(text))
            match_count = len(list(rx.finditer(text)))
        else:
            valid = rx.fullmatch(text) is not None
            result = str(valid)
            match_count = 1 if valid else 0
        return ok(
            {
                "matches": matches,
                "groups": groups,
                "result": str(result),
                "match_count": match_count,
            }
        )
    except Exception as exc:
        return fail(f"Regex operation failed: {exc}")

