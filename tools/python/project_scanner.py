"""
Overlord11 - Project Scanner
================================
Deep project analysis tool. Scans a directory to detect framework, language,
structure, dependencies, entry points, config files, and produces a comprehensive
JSON profile of the project.

Usage:
    python project_scanner.py --path /path/to/project
    python project_scanner.py --path . --depth 3
    python project_scanner.py --path . --output scan_result.json
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# Add parent to path for log_manager import
sys.path.insert(0, str(Path(__file__).parent))
from log_manager import log_tool_invocation, log_error

# --- Language Detection ---

LANGUAGE_EXTENSIONS = {
    ".py": "Python", ".pyw": "Python",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".jsx": "JavaScript (JSX)",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".cs": "C#", ".csx": "C#",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++", ".h": "C/C++",
    ".c": "C",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin", ".kts": "Kotlin",
    ".scala": "Scala",
    ".r": "R", ".R": "R",
    ".lua": "Lua",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".sql": "SQL",
    ".html": "HTML", ".htm": "HTML",
    ".css": "CSS", ".scss": "SCSS", ".sass": "Sass", ".less": "Less",
    ".md": "Markdown", ".mdx": "MDX",
    ".json": "JSON",
    ".yaml": "YAML", ".yml": "YAML",
    ".toml": "TOML",
    ".xml": "XML",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".dart": "Dart",
    ".zig": "Zig",
    ".ex": "Elixir", ".exs": "Elixir",
    ".erl": "Erlang",
    ".hs": "Haskell",
    ".ml": "OCaml",
    ".tf": "Terraform",
    ".proto": "Protocol Buffers",
}

SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".env", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", ".next", ".nuxt", "target", "bin", "obj",
    ".idea", ".vscode", ".vs", "coverage", ".nyc_output", ".cache",
    ".terraform", ".gradle", ".cargo",
}

# --- Framework Detection ---

FRAMEWORK_SIGNATURES = {
    # Python
    "Django": {"files": ["manage.py", "settings.py"], "deps": ["django"]},
    "Flask": {"files": ["app.py"], "deps": ["flask"]},
    "FastAPI": {"deps": ["fastapi"]},
    "Streamlit": {"deps": ["streamlit"]},
    "Celery": {"deps": ["celery"]},
    "Pytest": {"files": ["conftest.py", "pytest.ini"], "deps": ["pytest"]},
    "SQLAlchemy": {"deps": ["sqlalchemy"]},
    "Pydantic": {"deps": ["pydantic"]},

    # JavaScript / TypeScript
    "React": {"files": [], "deps": ["react"]},
    "Next.js": {"files": ["next.config.js", "next.config.mjs", "next.config.ts"], "deps": ["next"]},
    "Vue.js": {"deps": ["vue"]},
    "Nuxt": {"files": ["nuxt.config.js", "nuxt.config.ts"], "deps": ["nuxt"]},
    "Angular": {"files": ["angular.json"], "deps": ["@angular/core"]},
    "Svelte": {"deps": ["svelte"]},
    "Express": {"deps": ["express"]},
    "NestJS": {"deps": ["@nestjs/core"]},
    "Vite": {"files": ["vite.config.js", "vite.config.ts"], "deps": ["vite"]},
    "Webpack": {"files": ["webpack.config.js"], "deps": ["webpack"]},
    "Tailwind CSS": {"files": ["tailwind.config.js", "tailwind.config.ts"], "deps": ["tailwindcss"]},
    "Jest": {"deps": ["jest"]},
    "Vitest": {"deps": ["vitest"]},
    "ESLint": {"files": [".eslintrc.js", ".eslintrc.json", ".eslintrc.yml"], "deps": ["eslint"]},
    "Prettier": {"files": [".prettierrc", ".prettierrc.json"], "deps": ["prettier"]},

    # Rust
    "Tokio": {"deps": ["tokio"]},
    "Actix": {"deps": ["actix-web"]},
    "Axum": {"deps": ["axum"]},

    # Go
    "Gin": {"deps": ["github.com/gin-gonic/gin"]},
    "Echo": {"deps": ["github.com/labstack/echo"]},

    # Infrastructure
    "Docker": {"files": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"]},
    "Kubernetes": {"files": ["k8s/", "kubernetes/"]},
    "Terraform": {"files": ["main.tf"]},
    "GitHub Actions": {"files": [".github/workflows/"]},
}

ENTRY_POINT_PATTERNS = [
    "main.py", "app.py", "server.py", "index.py", "run.py", "cli.py",
    "main.js", "index.js", "server.js", "app.js",
    "main.ts", "index.ts", "server.ts", "app.ts",
    "main.go", "main.rs", "Main.java",
    "Program.cs", "Startup.cs",
    "manage.py",
]

CONFIG_FILE_PATTERNS = [
    "package.json", "tsconfig.json", "jsconfig.json",
    "requirements.txt", "Pipfile", "pyproject.toml", "setup.py", "setup.cfg",
    "Cargo.toml", "go.mod", "go.sum",
    "Gemfile", "composer.json", "pom.xml", "build.gradle",
    ".env", ".env.example", ".env.local",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "Makefile", "CMakeLists.txt",
    ".gitignore", ".dockerignore", ".editorconfig",
    "LICENSE", "README.md",
]


def scan_project(root_path: str, max_depth: int = 5) -> dict:
    """Perform a deep scan of a project directory."""
    root = Path(root_path).resolve()
    if not root.exists():
        return {
            "status": "error",
            "error": f"Path does not exist: {root}",
            "hint": "Verify the path with list_directory or provide an absolute path.",
        }

    start_time = time.time()

    result = {
        "project_root": str(root),
        "project_name": root.name,
        "scanned_at": datetime.now().isoformat(),
        "languages": {},
        "frameworks_detected": [],
        "entry_points": [],
        "config_files": [],
        "directory_structure": {},
        "file_stats": {
            "total_files": 0,
            "total_dirs": 0,
            "total_lines": 0,
            "total_size_bytes": 0,
        },
        "top_level_contents": [],
        "dependency_files": [],
        "test_directories": [],
        "has_git": False,
        "has_ci": False,
        "has_docker": False,
        "has_tests": False,
    }

    lang_lines = defaultdict(int)
    lang_files = defaultdict(int)
    all_filenames = set()
    all_dep_names = set()

    # Walk the directory tree
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        depth = len(rel_dir.parts)

        # Skip excluded directories
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        if depth > max_depth:
            dirnames.clear()
            continue

        result["file_stats"]["total_dirs"] += 1

        # Top-level contents
        if depth == 0:
            for d in sorted(dirnames):
                result["top_level_contents"].append({"name": d, "type": "directory"})
            for f in sorted(filenames):
                result["top_level_contents"].append({"name": f, "type": "file"})

        for fname in filenames:
            fpath = Path(dirpath) / fname
            rel_path = str(fpath.relative_to(root)).replace("\\", "/")
            all_filenames.add(fname)
            result["file_stats"]["total_files"] += 1

            try:
                fsize = fpath.stat().st_size
                result["file_stats"]["total_size_bytes"] += fsize
            except OSError:
                fsize = 0

            ext = fpath.suffix.lower()

            # Language stats
            if ext in LANGUAGE_EXTENSIONS:
                lang = LANGUAGE_EXTENSIONS[ext]
                lang_files[lang] += 1
                # Count lines for source files (skip huge files)
                if fsize < 2_000_000:
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            line_count = sum(1 for _ in f)
                        lang_lines[lang] += line_count
                        result["file_stats"]["total_lines"] += line_count
                    except (OSError, UnicodeDecodeError):
                        pass

            # Entry points
            if fname in ENTRY_POINT_PATTERNS:
                result["entry_points"].append(rel_path)

            # Config files
            if fname in CONFIG_FILE_PATTERNS:
                result["config_files"].append(rel_path)

            # Dependency files
            if fname in ("package.json", "requirements.txt", "Pipfile",
                         "pyproject.toml", "Cargo.toml", "go.mod", "Gemfile",
                         "composer.json", "pom.xml", "build.gradle"):
                result["dependency_files"].append(rel_path)
                # Extract dep names for framework detection
                _extract_deps(fpath, fname, all_dep_names)

        # Test directories
        dir_name = Path(dirpath).name.lower()
        if dir_name in ("test", "tests", "__tests__", "spec", "specs", "test_"):
            result["test_directories"].append(
                str(Path(dirpath).relative_to(root)).replace("\\", "/")
            )
            result["has_tests"] = True

    # Check special directories/files
    result["has_git"] = (root / ".git").exists()
    result["has_ci"] = (root / ".github" / "workflows").exists() or \
                       (root / ".gitlab-ci.yml").exists() or \
                       (root / "Jenkinsfile").exists()
    result["has_docker"] = any(f in all_filenames for f in
                               ("Dockerfile", "docker-compose.yml", "docker-compose.yaml"))

    # Build language summary
    for lang in sorted(lang_files, key=lambda l: lang_lines[l], reverse=True):
        result["languages"][lang] = {
            "files": lang_files[lang],
            "lines": lang_lines[lang]
        }

    # Detect frameworks
    for fw_name, sigs in FRAMEWORK_SIGNATURES.items():
        detected = False
        # Check files
        for sig_file in sigs.get("files", []):
            if sig_file in all_filenames or (root / sig_file).exists():
                detected = True
                break
        # Check deps
        if not detected:
            for dep in sigs.get("deps", []):
                if dep in all_dep_names:
                    detected = True
                    break
        if detected:
            result["frameworks_detected"].append(fw_name)

    # Build directory structure (top 2 levels)
    result["directory_structure"] = _build_tree(root, max_depth=2)

    duration_ms = (time.time() - start_time) * 1000
    result["scan_duration_ms"] = round(duration_ms, 1)

    return result


def _extract_deps(fpath: Path, fname: str, dep_set: set):
    """Extract dependency names from common dependency files."""
    try:
        content = fpath.read_text(encoding="utf-8", errors="ignore")

        if fname == "package.json":
            data = json.loads(content)
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                if key in data and isinstance(data[key], dict):
                    dep_set.update(data[key].keys())

        elif fname == "requirements.txt":
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    name = line.split("==")[0].split(">=")[0].split("<=")[0] \
                              .split("~=")[0].split("!=")[0].split("[")[0].strip()
                    if name:
                        dep_set.add(name.lower())

        elif fname == "pyproject.toml":
            # Simple extraction - look for dependency lines
            for line in content.splitlines():
                line = line.strip().strip('"').strip("'").strip(",")
                if ">=" in line or "==" in line or "<" in line:
                    name = line.split(">=")[0].split("==")[0].split("<")[0] \
                              .split("[")[0].strip().strip('"').strip("'")
                    if name and not name.startswith("[") and not name.startswith("#"):
                        dep_set.add(name.lower())

        elif fname == "Cargo.toml":
            in_deps = False
            for line in content.splitlines():
                if line.strip().startswith("[") and "dependencies" in line.lower():
                    in_deps = True
                    continue
                elif line.strip().startswith("["):
                    in_deps = False
                if in_deps and "=" in line:
                    name = line.split("=")[0].strip()
                    if name:
                        dep_set.add(name)

        elif fname == "go.mod":
            for line in content.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and "/" in parts[0]:
                    dep_set.add(parts[0])

    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass


def _build_tree(root: Path, max_depth: int = 2, current_depth: int = 0) -> dict:
    """Build a directory tree representation."""
    tree = {}
    if current_depth > max_depth:
        return tree
    try:
        entries = sorted(root.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        for entry in entries:
            if entry.name in SKIP_DIRS:
                continue
            if entry.is_dir():
                tree[entry.name + "/"] = _build_tree(entry, max_depth, current_depth + 1)
            else:
                tree[entry.name] = None
    except PermissionError:
        tree["[permission denied]"] = None
    return tree


# --- CLI Interface ---

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Overlord11 Project Scanner")
    parser.add_argument("--path", default=".", help="Project root path to scan")
    parser.add_argument("--max_depth", type=int, default=5, help="Max directory depth")
    parser.add_argument("--output", default=None, help="Write result to JSON file")
    parser.add_argument("--session_id", default=None, help="Session ID for logging")
    parser.add_argument("--compact", action="store_true", help="Compact JSON output")

    args = parser.parse_args()
    session_id = args.session_id or "unset"

    start = time.time()
    result = scan_project(args.path, max_depth=args.max_depth)
    duration_ms = (time.time() - start) * 1000

    # Log the invocation
    log_tool_invocation(
        session_id=session_id,
        tool_name="project_scanner",
        params={"path": args.path, "max_depth": args.max_depth},
        result={"status": "error" if "error" in result else "success",
                "files_scanned": result.get("file_stats", {}).get("total_files", 0)},
        duration_ms=duration_ms
    )

    indent = None if args.compact else 2
    output_str = json.dumps(result, indent=indent, default=str)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_str, encoding="utf-8")
        print(f"Scan result written to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
