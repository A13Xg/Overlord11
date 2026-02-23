"""
AgenticToolset - Metrics Collector
==================================
Collects and reports code metrics: lines of code, function counts, file size
distributions, language breakdowns, test coverage estimation, and change frequency.

Usage:
    python metrics_collector.py --path /path/to/project
    python metrics_collector.py --path . --metric loc
    python metrics_collector.py --path . --metric all --output metrics.json
"""

import json
import os
import re
import subprocess
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
    ".pytest_cache", "coverage", ".nyc_output", ".cache",
}

SOURCE_EXTS = {
    ".py", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".go", ".rs",
    ".java", ".cs", ".cpp", ".cc", ".c", ".h", ".hpp", ".rb", ".php",
    ".swift", ".kt", ".scala", ".vue", ".svelte", ".dart", ".zig",
    ".ex", ".exs", ".erl", ".hs", ".ml", ".lua", ".sh", ".bash",
    ".sql", ".r", ".R",
}

TEST_INDICATORS = {
    "test_", "_test.", ".test.", ".spec.", "_spec.", "tests/", "test/",
    "__tests__/", "spec/", "specs/",
}


def collect_metrics(root_path: str, metric: str = "all") -> dict:
    """Collect comprehensive code metrics."""
    root = Path(root_path).resolve()
    if not root.exists():
        return {"error": f"Path not found: {root_path}"}

    start_time = time.time()

    result = {
        "project_root": str(root),
        "collected_at": datetime.now().isoformat(),
        "metric_type": metric,
    }

    if metric in ("all", "loc"):
        result["lines_of_code"] = _collect_loc(root)

    if metric in ("all", "files"):
        result["file_metrics"] = _collect_file_metrics(root)

    if metric in ("all", "functions"):
        result["function_metrics"] = _collect_function_metrics(root)

    if metric in ("all", "tests"):
        result["test_metrics"] = _collect_test_metrics(root)

    if metric in ("all", "git"):
        result["git_metrics"] = _collect_git_metrics(root)

    if metric in ("all", "size"):
        result["size_metrics"] = _collect_size_metrics(root)

    result["collection_duration_ms"] = round((time.time() - start_time) * 1000, 1)
    return result


def _collect_loc(root: Path) -> dict:
    """Collect lines-of-code metrics by language."""
    lang_stats = defaultdict(lambda: {"files": 0, "total_lines": 0,
                                       "code_lines": 0, "blank_lines": 0,
                                       "comment_lines": 0})
    total = {"files": 0, "total_lines": 0, "code_lines": 0,
             "blank_lines": 0, "comment_lines": 0}

    ext_to_lang = {
        ".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript",
        ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
        ".go": "Go", ".rs": "Rust", ".java": "Java", ".cs": "C#",
        ".cpp": "C++", ".cc": "C++", ".c": "C", ".h": "C/C++",
        ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
        ".kt": "Kotlin", ".scala": "Scala", ".vue": "Vue",
        ".svelte": "Svelte", ".dart": "Dart", ".sh": "Shell",
        ".sql": "SQL", ".lua": "Lua", ".zig": "Zig",
        ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    }

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for fname in filenames:
            fpath = Path(dirpath) / fname
            ext = fpath.suffix.lower()
            lang = ext_to_lang.get(ext)
            if not lang:
                continue

            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                lines = content.splitlines()
            except OSError:
                continue

            n_total = len(lines)
            n_blank = sum(1 for l in lines if not l.strip())
            n_comment = _count_comment_lines(lines, ext)
            n_code = n_total - n_blank - n_comment

            lang_stats[lang]["files"] += 1
            lang_stats[lang]["total_lines"] += n_total
            lang_stats[lang]["code_lines"] += n_code
            lang_stats[lang]["blank_lines"] += n_blank
            lang_stats[lang]["comment_lines"] += n_comment

            total["files"] += 1
            total["total_lines"] += n_total
            total["code_lines"] += n_code
            total["blank_lines"] += n_blank
            total["comment_lines"] += n_comment

    return {
        "by_language": dict(sorted(lang_stats.items(),
                                   key=lambda x: x[1]["code_lines"], reverse=True)),
        "total": total,
    }


def _count_comment_lines(lines: list, ext: str) -> int:
    """Count comment lines based on file extension."""
    count = 0
    in_block = False

    for line in lines:
        stripped = line.strip()

        if ext == ".py":
            if stripped.startswith("#"):
                count += 1
        elif ext in (".js", ".mjs", ".jsx", ".ts", ".tsx", ".go", ".rs",
                     ".java", ".cs", ".cpp", ".cc", ".c", ".h", ".swift",
                     ".kt", ".scala", ".dart", ".zig"):
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
        elif ext == ".rb":
            if stripped.startswith("#"):
                count += 1
        elif ext in (".sh", ".bash"):
            if stripped.startswith("#") and not stripped.startswith("#!"):
                count += 1
        elif ext in (".html", ".xml"):
            if "<!--" in stripped:
                count += 1
        elif ext in (".css", ".scss"):
            if in_block:
                count += 1
                if "*/" in stripped:
                    in_block = False
            elif stripped.startswith("/*"):
                count += 1
                if "*/" not in stripped:
                    in_block = True

    return count


def _collect_file_metrics(root: Path) -> dict:
    """Collect file-level metrics."""
    files_by_ext = defaultdict(int)
    size_buckets = {"tiny_0_1kb": 0, "small_1_10kb": 0, "medium_10_50kb": 0,
                    "large_50_200kb": 0, "huge_200kb_plus": 0}
    largest_files = []
    total_files = 0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for fname in filenames:
            fpath = Path(dirpath) / fname
            ext = fpath.suffix.lower() or "(no ext)"
            total_files += 1
            files_by_ext[ext] += 1

            try:
                size = fpath.stat().st_size
            except OSError:
                continue

            size_kb = size / 1024
            if size_kb < 1:
                size_buckets["tiny_0_1kb"] += 1
            elif size_kb < 10:
                size_buckets["small_1_10kb"] += 1
            elif size_kb < 50:
                size_buckets["medium_10_50kb"] += 1
            elif size_kb < 200:
                size_buckets["large_50_200kb"] += 1
            else:
                size_buckets["huge_200kb_plus"] += 1

            rel = str(fpath.relative_to(root)).replace("\\", "/")
            largest_files.append({"file": rel, "size_bytes": size})

    largest_files.sort(key=lambda x: x["size_bytes"], reverse=True)

    return {
        "total_files": total_files,
        "by_extension": dict(sorted(files_by_ext.items(),
                                    key=lambda x: x[1], reverse=True)),
        "size_distribution": size_buckets,
        "largest_files": largest_files[:15],
    }


def _collect_function_metrics(root: Path) -> dict:
    """Count functions/methods across the project."""
    import ast as ast_module

    func_counts = defaultdict(int)
    class_counts = defaultdict(int)
    total_functions = 0
    total_classes = 0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for fname in filenames:
            fpath = Path(dirpath) / fname
            ext = fpath.suffix.lower()

            if ext == ".py":
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                    tree = ast_module.parse(content)
                    funcs = sum(1 for n in ast_module.walk(tree)
                                if isinstance(n, (ast_module.FunctionDef, ast_module.AsyncFunctionDef)))
                    classes = sum(1 for n in ast_module.walk(tree)
                                 if isinstance(n, ast_module.ClassDef))
                    rel = str(fpath.relative_to(root)).replace("\\", "/")
                    func_counts[rel] = funcs
                    class_counts[rel] = classes
                    total_functions += funcs
                    total_classes += classes
                except (SyntaxError, OSError):
                    pass

            elif ext in (".js", ".mjs", ".jsx", ".ts", ".tsx"):
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                    func_pattern = r'(?:function\s+\w+|(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?(?:\([^)]*\)|[a-zA-Z_]\w*)\s*=>|\w+\s*\([^)]*\)\s*\{)'
                    funcs = len(re.findall(func_pattern, content))
                    class_pattern = r'\bclass\s+\w+'
                    classes = len(re.findall(class_pattern, content))
                    rel = str(fpath.relative_to(root)).replace("\\", "/")
                    func_counts[rel] = funcs
                    class_counts[rel] = classes
                    total_functions += funcs
                    total_classes += classes
                except OSError:
                    pass

    return {
        "total_functions": total_functions,
        "total_classes": total_classes,
        "top_files_by_functions": sorted(
            [{"file": k, "functions": v} for k, v in func_counts.items()],
            key=lambda x: x["functions"], reverse=True
        )[:15],
    }


def _collect_test_metrics(root: Path) -> dict:
    """Estimate test coverage based on file structure."""
    test_files = []
    source_files = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        rel_dir = str(Path(dirpath).relative_to(root)).replace("\\", "/")

        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() not in SOURCE_EXTS:
                continue

            rel = str(fpath.relative_to(root)).replace("\\", "/")
            is_test = any(indicator in rel.lower() for indicator in TEST_INDICATORS)

            if is_test:
                test_files.append(rel)
            else:
                source_files.append(rel)

    ratio = len(test_files) / len(source_files) if source_files else 0

    return {
        "test_files": len(test_files),
        "source_files": len(source_files),
        "test_to_source_ratio": round(ratio, 3),
        "test_file_list": test_files[:30],
        "has_test_config": any(
            (root / f).exists() for f in [
                "pytest.ini", "pyproject.toml", "jest.config.js",
                "jest.config.ts", "vitest.config.ts", ".mocharc.yml",
                "karma.conf.js", "phpunit.xml",
            ]
        ),
    }


def _collect_git_metrics(root: Path) -> dict:
    """Collect git-based metrics (requires git)."""
    if not (root / ".git").exists():
        return {"available": False, "reason": "Not a git repository"}

    result = {"available": True}

    try:
        # Total commits
        out = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            capture_output=True, text=True, cwd=root, timeout=10
        )
        result["total_commits"] = int(out.stdout.strip()) if out.returncode == 0 else None

        # Contributors
        out = subprocess.run(
            ["git", "shortlog", "-sn", "--all"],
            capture_output=True, text=True, cwd=root, timeout=10
        )
        if out.returncode == 0:
            contributors = []
            for line in out.stdout.strip().splitlines():
                parts = line.strip().split("\t", 1)
                if len(parts) == 2:
                    contributors.append({"commits": int(parts[0].strip()), "name": parts[1].strip()})
            result["contributors"] = contributors[:20]

        # Most changed files (last 100 commits)
        out = subprocess.run(
            ["git", "log", "--pretty=format:", "--name-only", "-100"],
            capture_output=True, text=True, cwd=root, timeout=15
        )
        if out.returncode == 0:
            file_freq = defaultdict(int)
            for line in out.stdout.splitlines():
                line = line.strip()
                if line:
                    file_freq[line] += 1
            result["most_changed_files"] = sorted(
                [{"file": k, "changes": v} for k, v in file_freq.items()],
                key=lambda x: x["changes"], reverse=True
            )[:15]

        # Recent activity (commits per week over last 8 weeks)
        out = subprocess.run(
            ["git", "log", "--format=%aI", "--since=8 weeks ago"],
            capture_output=True, text=True, cwd=root, timeout=10
        )
        if out.returncode == 0:
            from datetime import datetime as dt
            weekly = defaultdict(int)
            for line in out.stdout.strip().splitlines():
                if line:
                    try:
                        date = dt.fromisoformat(line.strip())
                        week_key = date.strftime("%Y-W%W")
                        weekly[week_key] += 1
                    except ValueError:
                        pass
            result["weekly_activity"] = dict(sorted(weekly.items()))

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        result["error"] = "Could not run git commands"

    return result


def _collect_size_metrics(root: Path) -> dict:
    """Collect project size metrics."""
    total_size = 0
    dir_sizes = {}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and d != ".git"]
        dir_size = 0

        for fname in filenames:
            try:
                fsize = (Path(dirpath) / fname).stat().st_size
                dir_size += fsize
                total_size += fsize
            except OSError:
                pass

        rel = str(Path(dirpath).relative_to(root)).replace("\\", "/") or "."
        if len(Path(dirpath).relative_to(root).parts) <= 2:
            dir_sizes[rel] = dir_size

    return {
        "total_size_bytes": total_size,
        "total_size_human": _human_size(total_size),
        "directory_sizes": sorted(
            [{"dir": k, "size_bytes": v, "size_human": _human_size(v)}
             for k, v in dir_sizes.items()],
            key=lambda x: x["size_bytes"], reverse=True
        )[:20],
    }


def _human_size(size_bytes: int) -> str:
    """Convert bytes to human-readable size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# --- CLI Interface ---

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AgenticToolset Metrics Collector")
    parser.add_argument("--path", default=".", help="Project root path")
    parser.add_argument("--metric", default="all",
                        choices=["all", "loc", "files", "functions", "tests", "git", "size"],
                        help="Type of metrics to collect")
    parser.add_argument("--output", default=None, help="Write result to JSON file")
    parser.add_argument("--session_id", default=None, help="Session ID for logging")

    args = parser.parse_args()
    session_id = args.session_id or "unset"

    start = time.time()
    result = collect_metrics(args.path, metric=args.metric)
    duration_ms = (time.time() - start) * 1000

    log_tool_invocation(
        session_id=session_id,
        tool_name="metrics_collector",
        params={"path": args.path, "metric": args.metric},
        result={"status": "error" if "error" in result else "success"},
        duration_ms=duration_ms
    )

    output_str = json.dumps(result, indent=2, default=str)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output_str, encoding="utf-8")
        print(f"Metrics written to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
