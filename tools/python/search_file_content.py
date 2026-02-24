import fnmatch
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Optional


def _find_rg() -> str | None:
    """Locate the ripgrep binary. Returns the full path or None."""
    # 1. Subprocess can find it directly (in system PATH)
    try:
        subprocess.run(["rg", "--version"], capture_output=True, check=True)
        return "rg"
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    # 2. Common install locations on Windows
    for candidate in [
        os.path.expandvars(r"%USERPROFILE%\scoop\shims\rg.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\rg.exe"),
        r"C:\ProgramData\chocolatey\bin\rg.exe",
        os.path.expandvars(r"%CARGO_HOME%\bin\rg.exe"),
        os.path.expandvars(r"%USERPROFILE%\.cargo\bin\rg.exe"),
    ]:
        if os.path.isfile(candidate):
            return candidate

    return None


def _python_search(
    pattern: str,
    dir_path: str,
    include: str = None,
    case_sensitive: bool = False,
    fixed_strings: bool = False,
    before: int = 0,
    after: int = 0,
    context: int = 0,
    max_results: int = 20000,
) -> str:
    """Pure-Python fallback when ripgrep is not available.

    Walks the directory tree, reads text files, and matches lines using
    Python's ``re`` module.  Returns JSON-lines output compatible with
    ripgrep's ``--json`` format so downstream consumers don't need to care
    which engine ran.
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    if fixed_strings:
        regex = re.compile(re.escape(pattern), flags)
    else:
        try:
            regex = re.compile(pattern, flags)
        except re.error as exc:
            return json.dumps({"error": f"Invalid regex: {exc}"})

    ctx_before = before or context
    ctx_after = after or context

    skip_dirs = {
        ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
        "dist", "build", ".next", "target", ".tox", ".mypy_cache",
        ".pytest_cache", "coverage", ".nyc_output",
    }

    target = Path(dir_path)
    files_to_search = []

    if target.is_file():
        files_to_search.append(target)
    elif target.is_dir():
        for dirpath, dirnames, filenames in os.walk(target):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fname in filenames:
                if include and not fnmatch.fnmatch(fname, include):
                    continue
                files_to_search.append(Path(dirpath) / fname)
    else:
        return json.dumps({"error": f"Path not found: {dir_path}"})

    output_lines = []
    match_count = 0

    for fpath in files_to_search:
        if match_count >= max_results:
            break
        try:
            lines = fpath.read_text(encoding="utf-8", errors="ignore").splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        for line_no, line_text in enumerate(lines):
            if match_count >= max_results:
                break
            m = regex.search(line_text)
            if not m:
                continue

            match_count += 1

            # Emit the match in ripgrep --json format
            entry = {
                "type": "match",
                "data": {
                    "path": {"text": str(fpath).replace("\\", "/")},
                    "lines": {"text": line_text + "\n"},
                    "line_number": line_no + 1,
                    "submatches": [
                        {"match": {"text": m.group()}, "start": m.start(), "end": m.end()}
                    ],
                },
            }
            output_lines.append(json.dumps(entry))

            # Context lines (before)
            for ci in range(max(0, line_no - ctx_before), line_no):
                ctx_entry = {
                    "type": "context",
                    "data": {
                        "path": {"text": str(fpath).replace("\\", "/")},
                        "lines": {"text": lines[ci] + "\n"},
                        "line_number": ci + 1,
                    },
                }
                output_lines.append(json.dumps(ctx_entry))

            # Context lines (after)
            for ci in range(line_no + 1, min(len(lines), line_no + 1 + ctx_after)):
                ctx_entry = {
                    "type": "context",
                    "data": {
                        "path": {"text": str(fpath).replace("\\", "/")},
                        "lines": {"text": lines[ci] + "\n"},
                        "line_number": ci + 1,
                    },
                }
                output_lines.append(json.dumps(ctx_entry))

    # Summary line (ripgrep compat)
    summary = {"type": "summary", "data": {"stats": {"matched_lines": match_count, "searches_with_match": 1 if match_count else 0}}}
    output_lines.append(json.dumps(summary))

    return "\n".join(output_lines)


# Cache the rg binary location so we only probe once per process
_RG_BIN = _find_rg()


def search_file_content(
    pattern: str,
    dir_path: Optional[str] = None,
    include: Optional[str] = None,
    no_ignore: Optional[bool] = False,
    case_sensitive: Optional[bool] = False,
    fixed_strings: Optional[bool] = False,
    before: Optional[int] = 0,
    after: Optional[int] = 0,
    context: Optional[int] = 0
) -> str:
    """
    Search for a pattern in files and return JSON results.

    Uses ripgrep (rg) when available for speed, otherwise falls back to a
    pure-Python regex search engine that produces the same JSON format.

    Args:
        pattern: The pattern to search for.
        dir_path: Directory or file to search. Defaults to current working directory.
        include: Glob pattern to filter files (e.g., '*.ts').
        no_ignore: If true, searches all files including those usually ignored.
        case_sensitive: If true, search is case-sensitive. Defaults to false.
        fixed_strings: If true, treats the ``pattern`` as a literal string. Defaults to false.
        before: Show this many lines before each match.
        after: Show this many lines after each match.
        context: Show this many lines of context around each match.

    Returns:
        A JSON string representing the search results, or an error message.
    """
    search_path = dir_path or os.getcwd()

    # ── Try ripgrep first ──────────────────────────────────────────────
    if _RG_BIN:
        cmd = [_RG_BIN, "--json", pattern, search_path]
        if include:
            cmd.extend(["-g", include])
        if no_ignore:
            cmd.append("--no-ignore")
        if case_sensitive:
            cmd.append("--case-sensitive")
        else:
            cmd.append("--ignore-case")
        if fixed_strings:
            cmd.append("--fixed-strings")
        if before > 0:
            cmd.extend(["--before-context", str(before)])
        if after > 0:
            cmd.extend(["--after-context", str(after)])
        if context > 0:
            cmd.extend(["--context", str(context)])
        cmd.extend(["--max-count", "20000"])

        try:
            process = subprocess.run(cmd, capture_output=True, text=True, check=False, encoding="utf-8")
            if process.returncode in (0, 1):  # 0 = matches, 1 = no matches
                return process.stdout
            return f"Error executing ripgrep: {process.stderr}"
        except (FileNotFoundError, OSError):
            pass  # Fall through to Python engine

    # ── Pure-Python fallback ───────────────────────────────────────────
    return _python_search(
        pattern=pattern,
        dir_path=search_path,
        include=include,
        case_sensitive=case_sensitive,
        fixed_strings=fixed_strings,
        before=before,
        after=after,
        context=context,
    )


if __name__ == "__main__":
    # Quick self-test
    if not os.path.exists("test_search_dir"):
        os.makedirs("test_search_dir")
    with open("test_search_dir/fileA.txt", "w") as f:
        f.write("This is a test line.\nAnother test line.\nFinal line here.\n")
    with open("test_search_dir/fileB.py", "w") as f:
        f.write("def my_function():\n    print('Hello, world!')\n# This is a comment\n")

    print("--- Searching for 'test' in test_search_dir (case-insensitive) ---")
    print(search_file_content(pattern="test", dir_path="test_search_dir"))

    print("\n--- Searching for 'line' in fileA.txt with context ---")
    print(search_file_content(pattern="line", dir_path="test_search_dir/fileA.txt", context=1))

    print("\n--- Searching for 'print' in .py files (case-sensitive) ---")
    print(search_file_content(pattern="print", dir_path="test_search_dir", include="*.py", case_sensitive=True))

    print("\n--- Searching for non-existent pattern ---")
    print(search_file_content(pattern="nonexistent", dir_path="test_search_dir"))

    # Cleanup
    os.remove("test_search_dir/fileA.txt")
    os.remove("test_search_dir/fileB.py")
    os.rmdir("test_search_dir")
