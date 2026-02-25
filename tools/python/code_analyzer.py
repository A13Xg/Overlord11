"""
Overlord11 - Code Analyzer
===============================
Static analysis tool for code quality metrics. Measures complexity, detects
code smells, finds dead code patterns, and analyzes import structure.

Usage:
    python code_analyzer.py --path /path/to/project
    python code_analyzer.py --path . --language python
    python code_analyzer.py --file /path/to/specific_file.py
    python code_analyzer.py --path . --check complexity
"""

import ast
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from log_manager import log_tool_invocation

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", "target", ".tox", ".mypy_cache",
    ".pytest_cache", "coverage", ".nyc_output",
}

LANGUAGE_EXTS = {
    "python": [".py"],
    "javascript": [".js", ".mjs", ".cjs", ".jsx"],
    "typescript": [".ts", ".tsx"],
    "go": [".go"],
    "rust": [".rs"],
    "java": [".java"],
    "csharp": [".cs"],
}


def analyze_code(root_path: str, language: str = None,
                 single_file: str = None, check: str = "all") -> dict:
    """Analyze code quality across a project or single file."""
    start_time = time.time()

    result = {
        "analyzed_at": datetime.now().isoformat(),
        "check": check,
        "files_analyzed": 0,
        "file_reports": [],
        "summary": {},
    }

    if single_file:
        fpath = Path(single_file).resolve()
        if not fpath.exists():
            return {"error": f"File not found: {single_file}"}
        report = _analyze_file(fpath, check)
        result["files_analyzed"] = 1
        result["file_reports"].append(report)
    else:
        root = Path(root_path).resolve()
        if not root.exists():
            return {"error": f"Path not found: {root_path}"}

        # Determine target extensions
        target_exts = set()
        if language:
            target_exts = set(LANGUAGE_EXTS.get(language.lower(), []))
        else:
            for exts in LANGUAGE_EXTS.values():
                target_exts.update(exts)

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

            for fname in filenames:
                fpath = Path(dirpath) / fname
                if fpath.suffix.lower() in target_exts:
                    report = _analyze_file(fpath, check, root)
                    result["file_reports"].append(report)
                    result["files_analyzed"] += 1

    # Generate summary
    result["summary"] = _generate_summary(result["file_reports"])
    result["analysis_duration_ms"] = round((time.time() - start_time) * 1000, 1)

    return result


def _analyze_file(fpath: Path, check: str = "all", root: Path = None) -> dict:
    """Analyze a single file."""
    rel_path = str(fpath.relative_to(root)).replace("\\", "/") if root else str(fpath)
    report = {
        "file": rel_path,
        "language": _detect_language(fpath),
        "size_bytes": fpath.stat().st_size,
    }

    try:
        content = fpath.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
    except OSError:
        report["error"] = "Could not read file"
        return report

    report["total_lines"] = len(lines)
    report["blank_lines"] = sum(1 for l in lines if not l.strip())
    report["comment_lines"] = _count_comments(lines, report["language"])
    report["code_lines"] = report["total_lines"] - report["blank_lines"] - report["comment_lines"]

    if check in ("all", "complexity"):
        report["complexity"] = _analyze_complexity(content, fpath, report["language"])

    if check in ("all", "smells"):
        report["code_smells"] = _detect_smells(content, lines, report["language"])

    if check in ("all", "imports"):
        report["imports"] = _analyze_imports(content, report["language"])

    if check in ("all", "functions"):
        report["functions"] = _extract_functions(content, report["language"])

    return report


def _detect_language(fpath: Path) -> str:
    """Detect language from file extension."""
    ext = fpath.suffix.lower()
    for lang, exts in LANGUAGE_EXTS.items():
        if ext in exts:
            return lang
    return "unknown"


def _count_comments(lines: list, language: str) -> int:
    """Count comment lines."""
    count = 0
    in_block = False

    for line in lines:
        stripped = line.strip()

        if language in ("python",):
            if stripped.startswith("#"):
                count += 1
            elif '"""' in stripped or "'''" in stripped:
                if stripped.count('"""') == 1 or stripped.count("'''") == 1:
                    in_block = not in_block
                count += 1
            elif in_block:
                count += 1

        elif language in ("javascript", "typescript", "java", "csharp", "go", "rust"):
            if in_block:
                count += 1
                if "*/" in stripped:
                    in_block = False
            elif stripped.startswith("//"):
                count += 1
            elif stripped.startswith("/*"):
                count += 1
                if "*/" not in stripped:
                    in_block = True

    return count


def _analyze_complexity(content: str, fpath: Path, language: str) -> dict:
    """Analyze code complexity."""
    result = {
        "cyclomatic_total": 0,
        "max_nesting_depth": 0,
        "long_functions": [],
        "complex_functions": [],
    }

    if language == "python":
        result = _python_complexity(content, fpath)
    else:
        # Generic complexity for other languages
        result = _generic_complexity(content, language)

    return result


def _python_complexity(content: str, fpath: Path) -> dict:
    """Python-specific complexity analysis using AST."""
    result = {
        "cyclomatic_total": 0,
        "max_nesting_depth": 0,
        "long_functions": [],
        "complex_functions": [],
    }

    try:
        tree = ast.parse(content)
    except SyntaxError:
        result["error"] = "Syntax error - could not parse"
        return result

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_name = node.name
            start_line = node.lineno
            end_line = node.end_lineno or start_line
            func_lines = end_line - start_line + 1

            # Calculate cyclomatic complexity
            complexity = 1  # Base complexity
            for child in ast.walk(node):
                if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                    complexity += 1
                elif isinstance(child, ast.BoolOp):
                    complexity += len(child.values) - 1
                elif isinstance(child, (ast.Assert, ast.Raise)):
                    complexity += 1

            result["cyclomatic_total"] += complexity

            if func_lines > 50:
                result["long_functions"].append({
                    "name": func_name,
                    "line": start_line,
                    "length": func_lines,
                })

            if complexity > 10:
                result["complex_functions"].append({
                    "name": func_name,
                    "line": start_line,
                    "complexity": complexity,
                })

    # Max nesting depth
    result["max_nesting_depth"] = _calc_max_nesting(content)

    return result


def _generic_complexity(content: str, language: str) -> dict:
    """Generic complexity analysis using pattern matching."""
    result = {
        "cyclomatic_total": 0,
        "max_nesting_depth": 0,
        "long_functions": [],
        "complex_functions": [],
    }

    # Count branching keywords
    branch_patterns = {
        "javascript": r'\b(if|else if|while|for|catch|case|\?\?|&&|\|\|)\b',
        "typescript": r'\b(if|else if|while|for|catch|case|\?\?|&&|\|\|)\b',
        "go": r'\b(if|else if|for|switch|case|select)\b',
        "rust": r'\b(if|else if|while|for|loop|match|=>)\b',
        "java": r'\b(if|else if|while|for|catch|case|&&|\|\|)\b',
        "csharp": r'\b(if|else if|while|for|foreach|catch|case|&&|\|\|)\b',
    }

    pattern = branch_patterns.get(language, r'\b(if|else if|while|for)\b')
    result["cyclomatic_total"] = len(re.findall(pattern, content))
    result["max_nesting_depth"] = _calc_max_nesting(content)

    return result


def _calc_max_nesting(content: str) -> int:
    """Calculate maximum nesting depth via indentation."""
    max_depth = 0
    for line in content.splitlines():
        if line.strip():
            indent = len(line) - len(line.lstrip())
            # Approximate nesting (assuming 4-space or 2-space indent)
            depth = indent // 2
            max_depth = max(max_depth, depth)
    return min(max_depth, 20)  # Cap at reasonable value


def _detect_smells(content: str, lines: list, language: str) -> list:
    """Detect common code smells."""
    smells = []

    # Long lines
    for i, line in enumerate(lines, 1):
        if len(line) > 120:
            smells.append({
                "type": "long_line",
                "line": i,
                "length": len(line),
                "message": f"Line exceeds 120 characters ({len(line)} chars)"
            })
            if len(smells) > 50:  # Cap smell reporting
                smells.append({"type": "truncated", "message": "Too many smells, stopping detection"})
                break

    # TODO/FIXME/HACK/XXX comments
    for i, line in enumerate(lines, 1):
        for marker in ("TODO", "FIXME", "HACK", "XXX", "BUG"):
            if marker in line.upper():
                smells.append({
                    "type": "marker_comment",
                    "line": i,
                    "marker": marker,
                    "message": line.strip()[:100]
                })

    # Duplicate consecutive blank lines
    consecutive_blank = 0
    for i, line in enumerate(lines, 1):
        if not line.strip():
            consecutive_blank += 1
            if consecutive_blank >= 3:
                smells.append({
                    "type": "excessive_blank_lines",
                    "line": i,
                    "message": f"3+ consecutive blank lines"
                })
                consecutive_blank = 0
        else:
            consecutive_blank = 0

    # Python-specific
    if language == "python":
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Bare except
            if re.match(r'^except\s*:', stripped):
                smells.append({
                    "type": "bare_except",
                    "line": i,
                    "message": "Bare except clause - catches all exceptions including SystemExit"
                })
            # Star import
            if re.match(r'^from\s+\S+\s+import\s+\*', stripped):
                smells.append({
                    "type": "star_import",
                    "line": i,
                    "message": "Wildcard import pollutes namespace"
                })
            # Mutable default argument
            if re.match(r'^def\s+\w+\(.*=\s*(\[\]|\{\}|set\(\))', stripped):
                smells.append({
                    "type": "mutable_default",
                    "line": i,
                    "message": "Mutable default argument - shared across calls"
                })

    # JS/TS-specific
    if language in ("javascript", "typescript"):
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if "== " in stripped and "===" not in stripped and "!==" not in stripped:
                if not stripped.startswith("//") and not stripped.startswith("*"):
                    smells.append({
                        "type": "loose_equality",
                        "line": i,
                        "message": "Loose equality (==) - prefer strict equality (===)"
                    })
            if re.match(r'\bvar\s+', stripped):
                smells.append({
                    "type": "var_usage",
                    "line": i,
                    "message": "Using 'var' - prefer 'const' or 'let'"
                })

    return smells


def _analyze_imports(content: str, language: str) -> dict:
    """Analyze import structure."""
    imports = {"standard": [], "third_party": [], "local": [], "total": 0}

    if language == "python":
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                match = re.match(r'^(?:from\s+(\S+)|import\s+(\S+))', stripped)
                if match:
                    module = match.group(1) or match.group(2)
                    root_module = module.split(".")[0]

                    # Rough classification
                    if root_module.startswith("."):
                        imports["local"].append(stripped)
                    elif root_module in _PYTHON_STDLIB:
                        imports["standard"].append(stripped)
                    else:
                        imports["third_party"].append(stripped)
                    imports["total"] += 1

    elif language in ("javascript", "typescript"):
        for line in content.splitlines():
            stripped = line.strip()
            match = re.match(r'(?:import|require)\s*\(?[\'"]([^\'"]+)', stripped)
            if match:
                module_path = match.group(1)
                if module_path.startswith("."):
                    imports["local"].append(module_path)
                elif module_path.startswith("@") or not "/" in module_path:
                    imports["third_party"].append(module_path)
                else:
                    imports["third_party"].append(module_path)
                imports["total"] += 1

    return imports


def _extract_functions(content: str, language: str) -> list:
    """Extract function/method signatures."""
    functions = []

    if language == "python":
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = [a.arg for a in node.args.args]
                    functions.append({
                        "name": node.name,
                        "line": node.lineno,
                        "args": args,
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                        "has_docstring": (isinstance(node.body[0], ast.Expr)
                                          and isinstance(node.body[0].value, ast.Constant)
                                          and isinstance(node.body[0].value.value, str))
                                         if node.body else False,
                        "decorators": [_get_decorator_name(d) for d in node.decorator_list],
                    })
        except SyntaxError:
            pass

    elif language in ("javascript", "typescript"):
        # Regex-based extraction
        patterns = [
            r'(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)',
            r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(?([^)]*)\)?\s*=>',
            r'(\w+)\s*\(([^)]*)\)\s*\{',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                name = match.group(1)
                args_str = match.group(2).strip()
                line = content[:match.start()].count('\n') + 1
                functions.append({
                    "name": name,
                    "line": line,
                    "args_str": args_str,
                })

    return functions


def _get_decorator_name(node) -> str:
    """Get decorator name from AST node."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_get_decorator_name(node.value)}.{node.attr}"
    elif isinstance(node, ast.Call):
        return _get_decorator_name(node.func)
    return "unknown"


def _generate_summary(reports: list) -> dict:
    """Generate summary from file reports."""
    summary = {
        "total_files": len(reports),
        "total_lines": 0,
        "total_code_lines": 0,
        "total_comment_lines": 0,
        "total_blank_lines": 0,
        "total_smells": 0,
        "total_functions": 0,
        "languages": defaultdict(int),
        "avg_complexity": 0,
        "worst_files": [],
    }

    complexities = []
    for r in reports:
        summary["total_lines"] += r.get("total_lines", 0)
        summary["total_code_lines"] += r.get("code_lines", 0)
        summary["total_comment_lines"] += r.get("comment_lines", 0)
        summary["total_blank_lines"] += r.get("blank_lines", 0)
        summary["total_smells"] += len(r.get("code_smells", []))
        summary["total_functions"] += len(r.get("functions", []))
        summary["languages"][r.get("language", "unknown")] += 1

        cx = r.get("complexity", {}).get("cyclomatic_total", 0)
        if cx:
            complexities.append({"file": r["file"], "complexity": cx})

    if complexities:
        summary["avg_complexity"] = round(
            sum(c["complexity"] for c in complexities) / len(complexities), 1)
        summary["worst_files"] = sorted(
            complexities, key=lambda x: x["complexity"], reverse=True)[:10]

    summary["languages"] = dict(summary["languages"])
    return summary


# Python standard library modules (common subset)
_PYTHON_STDLIB = {
    "abc", "argparse", "ast", "asyncio", "base64", "bisect", "calendar",
    "cmath", "collections", "concurrent", "configparser", "contextlib",
    "copy", "csv", "ctypes", "dataclasses", "datetime", "decimal",
    "difflib", "email", "enum", "errno", "faulthandler", "fileinput",
    "fnmatch", "fractions", "functools", "gc", "getpass", "glob",
    "gzip", "hashlib", "heapq", "hmac", "html", "http", "importlib",
    "inspect", "io", "ipaddress", "itertools", "json", "keyword",
    "linecache", "locale", "logging", "lzma", "math", "mimetypes",
    "multiprocessing", "numbers", "operator", "os", "pathlib", "pickle",
    "platform", "pprint", "profile", "queue", "random", "re",
    "secrets", "select", "shelve", "shlex", "shutil", "signal",
    "site", "socket", "sqlite3", "ssl", "statistics", "string",
    "struct", "subprocess", "sys", "sysconfig", "tempfile", "textwrap",
    "threading", "time", "timeit", "tkinter", "token", "tokenize",
    "tomllib", "trace", "traceback", "types", "typing", "unicodedata",
    "unittest", "urllib", "uuid", "venv", "warnings", "wave",
    "weakref", "webbrowser", "xml", "xmlrpc", "zipfile", "zipimport",
    "zlib",
}


# --- CLI Interface ---

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Overlord11 Code Analyzer")
    parser.add_argument("--path", default=None, help="Project root to analyze")
    parser.add_argument("--file", default=None, help="Single file to analyze")
    parser.add_argument("--language", default=None, help="Filter by language")
    parser.add_argument("--check", default="all",
                        choices=["all", "complexity", "smells", "imports", "functions"],
                        help="Type of analysis")
    parser.add_argument("--output", default=None, help="Write result to JSON file")
    parser.add_argument("--session_id", default=None, help="Session ID for logging")

    args = parser.parse_args()

    if not args.path and not args.file:
        args.path = "."

    session_id = args.session_id or "unset"

    start = time.time()
    result = analyze_code(
        root_path=args.path,
        language=args.language,
        single_file=args.file,
        check=args.check
    )
    duration_ms = (time.time() - start) * 1000

    log_tool_invocation(
        session_id=session_id,
        tool_name="code_analyzer",
        params={"path": args.path or args.file, "language": args.language, "check": args.check},
        result={"status": "error" if "error" in result else "success",
                "files_analyzed": result.get("files_analyzed", 0)},
        duration_ms=duration_ms
    )

    output_str = json.dumps(result, indent=2, default=str)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output_str, encoding="utf-8")
        print(f"Analysis written to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
