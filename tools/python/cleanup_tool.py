"""
Overlord11 - Cleanup & Sanity Check Tool
=============================================
Pre-deployment sanity checker and cleanup utility. Scans for sensitive information
(API keys, passwords, secrets, credentials), removes temporary files, validates
directory structure, and produces a readiness report.

Intended to run manually or by the AI at the END of tasking.

Usage:
    python cleanup_tool.py --action full_scan --target_dir /path/to/project
    python cleanup_tool.py --action scan_secrets --target_dir /path/to/project
    python cleanup_tool.py --action clean_temp --target_dir /path/to/project
    python cleanup_tool.py --action clean_temp --target_dir /path/to/project --dry_run false
    python cleanup_tool.py --action validate_structure --target_dir /path/to/project
    python cleanup_tool.py --action report --target_dir /path/to/project
"""

import io
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from log_manager import log_tool_invocation


def safe_str(val, max_len: int = 200) -> str:
    if val is None:
        return "(none)"
    s = str(val)
    if len(s) > max_len:
        s = s[:max_len] + "..."
    try:
        s.encode(sys.stdout.encoding or "utf-8")
        return s
    except (UnicodeEncodeError, LookupError):
        return s.encode("ascii", errors="backslashreplace").decode("ascii")


# --- Secret Detection Patterns ---

SECRET_PATTERNS = [
    # API keys (generic)
    (r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}['\"]?", "API key"),
    # Bearer tokens
    (r"(?i)bearer\s+[A-Za-z0-9_\-\.]{20,}", "Bearer token"),
    # AWS keys
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r"(?i)(aws[_-]?secret[_-]?access[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?", "AWS Secret Key"),
    # Anthropic keys
    (r"sk-ant-[A-Za-z0-9_\-]{40,}", "Anthropic API key"),
    # OpenAI keys
    (r"sk-[A-Za-z0-9]{32,}", "OpenAI API key"),
    # Google API keys
    (r"AIza[0-9A-Za-z_\-]{35}", "Google API key"),
    # Generic secrets
    (r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?[^\s'\"]{8,}['\"]?", "Password"),
    (r"(?i)(secret|token|credential)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}['\"]?", "Secret/Token"),
    # Private keys
    (r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----", "Private key file"),
    # Connection strings
    (r"(?i)(mongodb|postgres|mysql|redis)://[^\s]+:[^\s]+@", "Database connection string"),
    # .env patterns with values
    (r"(?i)^[A-Z_]*(KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL|AUTH)[A-Z_]*\s*=\s*[^\s].{8,}$", "Env variable with secret"),
]

# File extensions to scan for secrets (text-based files only)
SCANNABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".env", ".sh", ".bash", ".zsh",
    ".ps1", ".bat", ".cmd", ".md", ".txt", ".html", ".css", ".xml",
    ".csv", ".sql", ".rb", ".go", ".rs", ".java", ".kt", ".swift",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".php", ".pl", ".r",
}

# Directories to always skip
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".eggs", "*.egg-info",
}

# Temp file patterns to clean
TEMP_PATTERNS = [
    ".claude", ".claude-*", "tmpclaude-*", "*-cwd",
    "__pycache__", "*.pyc", "*.pyo", "*.pyd",
    ".DS_Store", "Thumbs.db", "desktop.ini",
    "*.tmp", "*.temp", "*.swp", "*.swo", "*~",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "claude_temp", "claude_*.tmp", "claude_*.log", "claude_*.cache",
    ".claude_state", ".claude_cache", ".claude_session", ".claude_history",
]


def _should_skip_dir(dirname: str) -> bool:
    if dirname in SKIP_DIRS:
        return True
    if dirname.endswith(".egg-info"):
        return True
    return False


def _is_scannable(path: Path) -> bool:
    return path.suffix.lower() in SCANNABLE_EXTENSIONS


def _match_temp_pattern(name: str) -> bool:
    """Check if a file/dir name matches any temp pattern."""
    import fnmatch
    for pattern in TEMP_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


# --- Scan Functions ---

def scan_secrets(target_dir: str) -> dict:
    """Scan all text files for potential secrets and credentials."""
    target = Path(target_dir).resolve()
    if not target.is_dir():
        return {"status": "error", "error": f"Not a directory: {target_dir}"}

    findings = []
    files_scanned = 0

    for root, dirs, files in os.walk(target):
        # Prune skippable directories
        dirs[:] = [d for d in dirs if not _should_skip_dir(d)]

        for fname in files:
            fpath = Path(root) / fname
            if not _is_scannable(fpath):
                continue

            files_scanned += 1
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except (OSError, PermissionError):
                continue

            for line_num, line in enumerate(content.split("\n"), 1):
                for pattern, label in SECRET_PATTERNS:
                    if re.search(pattern, line):
                        # Don't flag .example or template files with placeholders
                        if any(placeholder in line.lower() for placeholder in
                               ["your_", "xxx", "placeholder", "example", "changeme",
                                "insert_", "replace_", "<your", "TODO"]):
                            continue
                        findings.append({
                            "file": str(fpath.relative_to(target)),
                            "line": line_num,
                            "type": label,
                            "preview": safe_str(line.strip(), 120)
                        })
                        break  # One match per line is enough

    return {
        "status": "ok",
        "files_scanned": files_scanned,
        "findings_count": len(findings),
        "findings": findings,
        "clean": len(findings) == 0
    }


def find_temp_files(target_dir: str, extra_patterns: list = None) -> list:
    """Find all temp files/dirs matching cleanup patterns."""
    target = Path(target_dir).resolve()
    all_patterns = TEMP_PATTERNS + (extra_patterns or [])
    found = []

    for root, dirs, files in os.walk(target):
        # Don't descend into .git
        if ".git" in dirs:
            dirs.remove(".git")

        for d in list(dirs):
            if _match_temp_pattern(d):
                full_path = Path(root) / d
                found.append({
                    "path": str(full_path.relative_to(target)),
                    "type": "directory",
                    "size_bytes": sum(f.stat().st_size for f in full_path.rglob("*") if f.is_file())
                })
                dirs.remove(d)  # Don't descend into it

        for f in files:
            if _match_temp_pattern(f):
                full_path = Path(root) / f
                try:
                    size = full_path.stat().st_size
                except OSError:
                    size = 0
                found.append({
                    "path": str(full_path.relative_to(target)),
                    "type": "file",
                    "size_bytes": size
                })

    return found


def clean_temp(target_dir: str, dry_run: bool = True,
               extra_patterns: list = None) -> dict:
    """Remove temp files from the target directory."""
    target = Path(target_dir).resolve()
    found = find_temp_files(target_dir, extra_patterns)

    if dry_run:
        return {
            "status": "dry_run",
            "would_delete": len(found),
            "items": found,
            "message": "Run with --dry_run false to actually delete these files"
        }

    deleted = []
    errors = []
    import shutil

    for item in found:
        full_path = target / item["path"]
        try:
            if item["type"] == "directory":
                shutil.rmtree(full_path)
            else:
                full_path.unlink()
            deleted.append(item["path"])
        except (OSError, PermissionError) as e:
            errors.append({"path": item["path"], "error": str(e)})

    return {
        "status": "cleaned",
        "deleted_count": len(deleted),
        "deleted": deleted,
        "error_count": len(errors),
        "errors": errors
    }


def validate_structure(target_dir: str) -> dict:
    """Validate that the project directory has a sensible structure."""
    target = Path(target_dir).resolve()
    if not target.is_dir():
        return {"status": "error", "error": f"Not a directory: {target_dir}"}

    checks = []

    # Check for common project structure indicators
    has_readme = any(target.glob("README*"))
    has_gitignore = (target / ".gitignore").exists()
    has_git = (target / ".git").is_dir()

    checks.append({
        "check": "README exists",
        "passed": has_readme,
        "severity": "warning" if not has_readme else "ok"
    })
    checks.append({
        "check": ".gitignore exists",
        "passed": has_gitignore,
        "severity": "warning" if not has_gitignore else "ok"
    })
    checks.append({
        "check": "Git repository initialized",
        "passed": has_git,
        "severity": "info" if not has_git else "ok"
    })

    # Check for .env without .env.example
    has_env = (target / ".env").exists()
    has_env_example = (target / ".env.example").exists()
    if has_env and not has_env_example:
        checks.append({
            "check": ".env exists without .env.example template",
            "passed": False,
            "severity": "warning"
        })

    # Check for large files (>10MB)
    large_files = []
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            fpath = Path(root) / f
            try:
                if fpath.stat().st_size > 10 * 1024 * 1024:
                    large_files.append({
                        "file": str(fpath.relative_to(target)),
                        "size_mb": round(fpath.stat().st_size / (1024 * 1024), 1)
                    })
            except OSError:
                continue

    if large_files:
        checks.append({
            "check": f"Large files detected (>10MB): {len(large_files)} files",
            "passed": False,
            "severity": "warning",
            "details": large_files
        })

    # Check for sensitive file types that shouldn't be committed
    sensitive_patterns = ["*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore",
                          "id_rsa", "id_ed25519", "*.sqlite", "*.db"]
    sensitive_found = []
    for pattern in sensitive_patterns:
        for match in target.rglob(pattern):
            if ".git" not in match.parts:
                sensitive_found.append(str(match.relative_to(target)))

    if sensitive_found:
        checks.append({
            "check": f"Potentially sensitive files: {len(sensitive_found)} found",
            "passed": False,
            "severity": "critical",
            "details": sensitive_found
        })

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)

    return {
        "status": "ok",
        "checks_passed": passed,
        "checks_total": total,
        "all_passed": passed == total,
        "checks": checks
    }


def full_scan(target_dir: str, dry_run: bool = True,
              extra_patterns: list = None) -> dict:
    """Run all scans and produce a comprehensive report."""
    secrets = scan_secrets(target_dir)
    temp = find_temp_files(target_dir, extra_patterns)
    structure = validate_structure(target_dir)

    # Overall readiness
    is_ready = (
        secrets.get("clean", False) and
        len(temp) == 0 and
        structure.get("all_passed", False)
    )

    severity = "READY" if is_ready else "ISSUES_FOUND"
    if any(c.get("severity") == "critical" for c in structure.get("checks", [])):
        severity = "CRITICAL_ISSUES"
    if secrets.get("findings_count", 0) > 0:
        severity = "SECRETS_DETECTED"

    return {
        "status": severity,
        "timestamp": datetime.now().isoformat(),
        "target": str(Path(target_dir).resolve()),
        "secrets_scan": secrets,
        "temp_files": {"count": len(temp), "items": temp},
        "structure_validation": structure,
        "ready_for_deployment": is_ready,
        "summary": _generate_summary(secrets, temp, structure, is_ready)
    }


def _generate_summary(secrets: dict, temp: list, structure: dict,
                      is_ready: bool) -> str:
    lines = []
    if is_ready:
        lines.append("All checks passed. Project is clean and ready for deployment.")
    else:
        if secrets.get("findings_count", 0) > 0:
            lines.append(f"SECRETS: {secrets['findings_count']} potential secret(s) found in code. REVIEW IMMEDIATELY.")
        if len(temp) > 0:
            lines.append(f"TEMP FILES: {len(temp)} temporary file(s)/dir(s) should be cleaned.")
        failed = [c for c in structure.get("checks", []) if not c["passed"]]
        if failed:
            lines.append(f"STRUCTURE: {len(failed)} check(s) failed: {', '.join(c['check'] for c in failed)}")
    return " | ".join(lines)


def generate_report(target_dir: str, output_path: str = "",
                    dry_run: bool = True, extra_patterns: list = None) -> dict:
    """Generate a markdown cleanup report."""
    result = full_scan(target_dir, dry_run, extra_patterns)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    report = f"""# Cleanup & Sanity Check Report

**Target**: `{result['target']}`
**Timestamp**: {timestamp}
**Status**: {result['status']}

---

## Summary

{result['summary']}

---

## Secrets Scan

- **Files scanned**: {result['secrets_scan']['files_scanned']}
- **Findings**: {result['secrets_scan']['findings_count']}
"""

    if result['secrets_scan']['findings_count'] > 0:
        report += "\n| File | Line | Type | Preview |\n|---|---|---|---|\n"
        for f in result['secrets_scan']['findings']:
            report += f"| `{f['file']}` | {f['line']} | {f['type']} | `{f['preview'][:60]}` |\n"

    report += f"""
---

## Temporary Files

- **Found**: {result['temp_files']['count']}
"""

    if result['temp_files']['count'] > 0:
        report += "\n| Path | Type | Size |\n|---|---|---|\n"
        for t in result['temp_files']['items']:
            size = f"{t['size_bytes']} bytes" if t['size_bytes'] < 1024 else f"{t['size_bytes']/1024:.1f} KB"
            report += f"| `{t['path']}` | {t['type']} | {size} |\n"

    report += f"""
---

## Structure Validation

"""
    for check in result['structure_validation'].get('checks', []):
        icon = "pass" if check['passed'] else "FAIL"
        report += f"- [{icon}] {check['check']}\n"

    report += f"""
---

## Deployment Readiness

**{'READY' if result['ready_for_deployment'] else 'NOT READY'}**

---

*Generated by Overlord11 Cleanup Tool*
"""

    if output_path:
        Path(output_path).write_text(report, encoding="utf-8")

    result["report"] = report
    return result


# --- CLI Interface ---

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Overlord11 Cleanup & Sanity Check Tool")
    parser.add_argument("--action", required=True,
                        choices=["full_scan", "scan_secrets", "clean_temp",
                                 "validate_structure", "report"])
    parser.add_argument("--target_dir", required=True)
    parser.add_argument("--dry_run", default="true",
                        help="'true' or 'false' — whether to actually delete files")
    parser.add_argument("--output_report", default="")
    parser.add_argument("--extra_patterns", default="[]",
                        help="JSON array of additional glob patterns to clean")
    parser.add_argument("--session_id", default=None)

    args = parser.parse_args()
    dry_run = args.dry_run.lower() != "false"
    extra_patterns = json.loads(args.extra_patterns) if args.extra_patterns else []

    start = time.time()

    if args.action == "full_scan":
        result = full_scan(args.target_dir, dry_run, extra_patterns)
    elif args.action == "scan_secrets":
        result = scan_secrets(args.target_dir)
    elif args.action == "clean_temp":
        result = clean_temp(args.target_dir, dry_run, extra_patterns)
    elif args.action == "validate_structure":
        result = validate_structure(args.target_dir)
    elif args.action == "report":
        result = generate_report(args.target_dir, args.output_report,
                                 dry_run, extra_patterns)
    else:
        result = {"error": f"Unknown action: {args.action}"}

    duration_ms = (time.time() - start) * 1000

    if args.session_id:
        log_tool_invocation(
            session_id=args.session_id,
            tool_name="cleanup_tool",
            params={"action": args.action, "target_dir": args.target_dir, "dry_run": dry_run},
            result={"status": result.get("status", "unknown")},
            duration_ms=duration_ms
        )

    # Print without the full report text to keep output manageable
    output = {k: v for k, v in result.items() if k != "report"}
    print(json.dumps(output, indent=2, ensure_ascii=False))
    if "report" in result and args.output_report:
        print(f"\nReport written to: {args.output_report}")


if __name__ == "__main__":
    main()
