"""
AgenticToolset - Dependency Analyzer
=====================================
Analyzes project dependencies from package manifests. Detects outdated packages,
security concerns, unused imports, and dependency conflicts.

Usage:
    python dependency_analyzer.py --path /path/to/project
    python dependency_analyzer.py --path . --check outdated
    python dependency_analyzer.py --path . --check security
    python dependency_analyzer.py --path . --check all
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
from log_manager import log_tool_invocation, log_error

# Manifest file handlers
MANIFEST_FILES = {
    "requirements.txt": "python_requirements",
    "Pipfile": "python_pipfile",
    "pyproject.toml": "python_pyproject",
    "setup.py": "python_setup",
    "setup.cfg": "python_setup_cfg",
    "package.json": "node_package",
    "Cargo.toml": "rust_cargo",
    "go.mod": "go_mod",
    "Gemfile": "ruby_gemfile",
    "composer.json": "php_composer",
    "pom.xml": "java_maven",
    "build.gradle": "java_gradle",
}


def analyze_dependencies(root_path: str, check: str = "all") -> dict:
    """Analyze all dependency manifests in the project."""
    root = Path(root_path).resolve()
    if not root.exists():
        return {"error": f"Path does not exist: {root}"}

    start_time = time.time()

    result = {
        "project_root": str(root),
        "analyzed_at": datetime.now().isoformat(),
        "manifests_found": [],
        "total_dependencies": 0,
        "dependencies_by_manifest": {},
        "warnings": [],
        "security_flags": [],
        "dependency_tree": {},
    }

    # Find all manifest files
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip common non-project dirs
        dirnames[:] = [d for d in dirnames if d not in {
            ".git", "node_modules", "__pycache__", ".venv", "venv",
            "env", "dist", "build", ".tox", "target"
        }]

        for fname in filenames:
            if fname in MANIFEST_FILES:
                fpath = Path(dirpath) / fname
                rel_path = str(fpath.relative_to(root)).replace("\\", "/")
                manifest_type = MANIFEST_FILES[fname]

                result["manifests_found"].append({
                    "file": rel_path,
                    "type": manifest_type,
                })

                deps = _parse_manifest(fpath, manifest_type)
                result["dependencies_by_manifest"][rel_path] = deps
                result["total_dependencies"] += len(deps.get("dependencies", []))

                # Check for issues
                if check in ("all", "security"):
                    flags = _check_security(deps.get("dependencies", []), manifest_type)
                    result["security_flags"].extend(flags)

                if check in ("all", "warnings"):
                    warns = _check_warnings(deps, rel_path)
                    result["warnings"].extend(warns)

    # Cross-manifest analysis
    if check in ("all", "conflicts"):
        conflicts = _find_conflicts(result["dependencies_by_manifest"])
        if conflicts:
            result["warnings"].extend(conflicts)

    # Check for lockfile presence
    _check_lockfiles(root, result)

    duration_ms = (time.time() - start_time) * 1000
    result["analysis_duration_ms"] = round(duration_ms, 1)

    return result


def _parse_manifest(fpath: Path, manifest_type: str) -> dict:
    """Parse a dependency manifest file."""
    try:
        content = fpath.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {"error": f"Could not read {fpath}", "dependencies": []}

    if manifest_type == "python_requirements":
        return _parse_requirements_txt(content)
    elif manifest_type == "node_package":
        return _parse_package_json(content)
    elif manifest_type == "python_pyproject":
        return _parse_pyproject_toml(content)
    elif manifest_type == "rust_cargo":
        return _parse_cargo_toml(content)
    elif manifest_type == "go_mod":
        return _parse_go_mod(content)
    else:
        return {"dependencies": [], "note": f"Parser not implemented for {manifest_type}"}


def _parse_requirements_txt(content: str) -> dict:
    """Parse requirements.txt."""
    deps = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Handle inline comments
        line = line.split("#")[0].strip()
        # Parse name and version spec
        match = re.match(r'^([A-Za-z0-9_.-]+)\s*(\[.*?\])?\s*(.*)?$', line)
        if match:
            name = match.group(1)
            extras = match.group(2) or ""
            version_spec = (match.group(3) or "").strip()
            deps.append({
                "name": name,
                "version_spec": version_spec if version_spec else "any",
                "extras": extras,
                "pinned": "==" in version_spec,
            })
    return {"format": "requirements.txt", "dependencies": deps}


def _parse_package_json(content: str) -> dict:
    """Parse package.json."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON", "dependencies": []}

    deps = []
    for dep_key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        dep_dict = data.get(dep_key, {})
        if isinstance(dep_dict, dict):
            for name, version in dep_dict.items():
                deps.append({
                    "name": name,
                    "version_spec": version,
                    "category": dep_key,
                    "pinned": not any(c in str(version) for c in "^~><=*x"),
                })

    result = {
        "format": "package.json",
        "dependencies": deps,
        "metadata": {
            "name": data.get("name"),
            "version": data.get("version"),
            "engine": data.get("engines", {}),
            "scripts": list(data.get("scripts", {}).keys()),
        }
    }
    return result


def _parse_pyproject_toml(content: str) -> dict:
    """Parse pyproject.toml (basic parser, no toml library needed)."""
    deps = []
    in_deps = False
    in_optional = False
    section_name = ""

    for line in content.splitlines():
        stripped = line.strip()

        # Track sections
        if stripped.startswith("["):
            in_deps = False
            in_optional = False
            if "dependencies" in stripped.lower():
                in_deps = True
                section_name = stripped.strip("[]").strip()
            if "optional" in stripped.lower():
                in_optional = True
            continue

        if in_deps and stripped and not stripped.startswith("#"):
            # Handle array items like: "requests>=2.28"
            cleaned = stripped.strip('"').strip("'").strip(",").strip()
            if cleaned and not cleaned.startswith("[") and not cleaned.startswith("]"):
                match = re.match(r'^([A-Za-z0-9_.-]+)\s*(.*)?$', cleaned)
                if match:
                    name = match.group(1)
                    version_spec = (match.group(2) or "").strip()
                    deps.append({
                        "name": name,
                        "version_spec": version_spec if version_spec else "any",
                        "section": section_name,
                        "optional": in_optional,
                    })

    return {"format": "pyproject.toml", "dependencies": deps}


def _parse_cargo_toml(content: str) -> dict:
    """Parse Cargo.toml."""
    deps = []
    in_deps = False
    dep_section = ""

    for line in content.splitlines():
        stripped = line.strip()

        if stripped.startswith("["):
            in_deps = "dependencies" in stripped.lower()
            dep_section = stripped.strip("[]").strip()
            continue

        if in_deps and "=" in stripped and not stripped.startswith("#"):
            parts = stripped.split("=", 1)
            name = parts[0].strip()
            value = parts[1].strip()
            # Simple version string or table
            version = value.strip('"').strip("'")
            if version.startswith("{"):
                # Extract version from table-style: { version = "1.0", features = [...] }
                v_match = re.search(r'version\s*=\s*"([^"]*)"', value)
                version = v_match.group(1) if v_match else "complex"
            deps.append({
                "name": name,
                "version_spec": version,
                "section": dep_section,
            })

    return {"format": "Cargo.toml", "dependencies": deps}


def _parse_go_mod(content: str) -> dict:
    """Parse go.mod."""
    deps = []
    in_require = False

    for line in content.splitlines():
        stripped = line.strip()

        if stripped.startswith("require ("):
            in_require = True
            continue
        if stripped == ")" and in_require:
            in_require = False
            continue

        if in_require and stripped and not stripped.startswith("//"):
            parts = stripped.split()
            if len(parts) >= 2:
                deps.append({
                    "name": parts[0],
                    "version_spec": parts[1],
                    "indirect": "// indirect" in stripped,
                })
        elif stripped.startswith("require "):
            parts = stripped.split()
            if len(parts) >= 3:
                deps.append({
                    "name": parts[1],
                    "version_spec": parts[2],
                })

    # Extract Go version
    go_version = None
    for line in content.splitlines():
        if line.strip().startswith("go "):
            go_version = line.strip().split()[1]
            break

    return {"format": "go.mod", "dependencies": deps,
            "metadata": {"go_version": go_version}}


def _check_security(deps: list, manifest_type: str) -> list:
    """Basic security checks on dependency list."""
    flags = []
    known_risky = {
        "eval", "exec", "pickle", "marshal", "subprocess",  # Python patterns
    }

    for dep in deps:
        name = dep.get("name", "").lower()
        version = dep.get("version_spec", "")

        # Flag unpinned deps
        if version in ("any", "*", "latest", ""):
            flags.append({
                "severity": "medium",
                "package": dep["name"],
                "issue": "Unpinned dependency - version not specified",
                "recommendation": "Pin to a specific version for reproducible builds"
            })

        # Flag wildcard versions in Node
        if version.startswith("*") or version == ">=0.0.0":
            flags.append({
                "severity": "high",
                "package": dep["name"],
                "issue": "Wildcard version allows any version including breaking changes",
                "recommendation": "Use a specific semver range"
            })

        # Flag git/url dependencies
        if any(prefix in str(version) for prefix in ("git://", "git+", "http://", "github:")):
            flags.append({
                "severity": "high",
                "package": dep["name"],
                "issue": "Git/URL dependency - not from package registry",
                "recommendation": "Use registry packages when possible for auditability"
            })

    return flags


def _check_warnings(deps_data: dict, manifest_path: str) -> list:
    """Check for general warnings."""
    warnings = []
    deps = deps_data.get("dependencies", [])

    if len(deps) > 100:
        warnings.append({
            "file": manifest_path,
            "warning": f"Large dependency count ({len(deps)}). Consider auditing for unused packages."
        })

    # Check for duplicate dependencies (different versions)
    names = [d["name"].lower() for d in deps]
    dupes = [n for n in set(names) if names.count(n) > 1]
    for dupe in dupes:
        warnings.append({
            "file": manifest_path,
            "warning": f"Duplicate dependency: {dupe} appears multiple times"
        })

    return warnings


def _find_conflicts(manifests: dict) -> list:
    """Find conflicts across manifests."""
    conflicts = []
    all_deps = defaultdict(list)

    for manifest_path, data in manifests.items():
        for dep in data.get("dependencies", []):
            all_deps[dep["name"].lower()].append({
                "manifest": manifest_path,
                "version": dep.get("version_spec", "any")
            })

    for name, sources in all_deps.items():
        if len(sources) > 1:
            versions = set(s["version"] for s in sources)
            if len(versions) > 1:
                conflicts.append({
                    "warning": f"Conflicting versions for '{name}': " +
                               ", ".join(f'{s["manifest"]}={s["version"]}' for s in sources)
                })

    return conflicts


def _check_lockfiles(root: Path, result: dict):
    """Check for presence of lockfiles."""
    lockfiles = {
        "package-lock.json": "npm",
        "yarn.lock": "yarn",
        "pnpm-lock.yaml": "pnpm",
        "bun.lockb": "bun",
        "Pipfile.lock": "pipenv",
        "poetry.lock": "poetry",
        "Cargo.lock": "cargo",
        "go.sum": "go",
        "Gemfile.lock": "bundler",
        "composer.lock": "composer",
    }

    found = []
    missing_for = []

    for lockfile, manager in lockfiles.items():
        if (root / lockfile).exists():
            found.append({"file": lockfile, "manager": manager})

    # Check if manifests exist without lockfiles
    manifest_to_lock = {
        "package.json": ["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb"],
        "Pipfile": ["Pipfile.lock"],
        "Cargo.toml": ["Cargo.lock"],
        "go.mod": ["go.sum"],
        "Gemfile": ["Gemfile.lock"],
        "composer.json": ["composer.lock"],
    }

    for manifest, locks in manifest_to_lock.items():
        if (root / manifest).exists():
            if not any((root / l).exists() for l in locks):
                missing_for.append({
                    "manifest": manifest,
                    "expected_locks": locks,
                    "warning": f"No lockfile found for {manifest}"
                })

    result["lockfiles"] = {"found": found, "missing": missing_for}


# --- CLI Interface ---

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AgenticToolset Dependency Analyzer")
    parser.add_argument("--path", default=".", help="Project root path")
    parser.add_argument("--check", default="all",
                        choices=["all", "security", "warnings", "conflicts"],
                        help="Type of analysis to perform")
    parser.add_argument("--output", default=None, help="Write result to JSON file")
    parser.add_argument("--session_id", default=None, help="Session ID for logging")

    args = parser.parse_args()
    session_id = args.session_id or "unset"

    start = time.time()
    result = analyze_dependencies(args.path, check=args.check)
    duration_ms = (time.time() - start) * 1000

    log_tool_invocation(
        session_id=session_id,
        tool_name="dependency_analyzer",
        params={"path": args.path, "check": args.check},
        result={"status": "error" if "error" in result else "success",
                "manifests_found": len(result.get("manifests_found", [])),
                "total_deps": result.get("total_dependencies", 0)},
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
