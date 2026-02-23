#!/usr/bin/env python3
"""publish_cleanup.py

Utility to prepare a repository for final publication:
- Adds common AI/model/secret-related patterns to `.gitignore`
- Creates a `RELEASE_CHECKLIST.md` with finalization steps

Usage:
  python AgenticToolset/tools/python/publish_cleanup.py --path /repo/root --apply

By default this runs as a dry-run. Use `--apply` to write changes.
"""
import argparse
import os
import shutil
import datetime


DEFAULT_PATTERNS = [
    "# AI / model / secrets",
    ".env",
    ".env.local",
    ".env.*",
    "secrets.env",
    "tokens.json",
    ".claude/",
    "AgenticToolset/",
    "models/",
    "*.ckpt",
    "*.safetensors",
    "*.pth",
    "*.bin",
    ".openai/",
    ".huggingface/",
    "__pycache__/",
    ".cache/",
    ".idea/",
    ".vscode/",
]


RELEASE_CHECKLIST = """
# Release / Publication Checklist

Fill and verify each item before publishing a public release.

- [ ] Confirm `.gitignore` contains AI, model, and secret patterns
- [ ] Remove or rotate any plaintext secrets from the repository
- [ ] Ensure `PROJECT_BRIEF.md` and `ONBOARDING.md` do not contain sensitive info
- [ ] Run full test suite: `pytest` (or project-specific test command)
- [ ] Update `CHANGELOG.md` with release notes
- [ ] Ensure `LICENSE` is present and correct
- [ ] Bump version (if applicable) and tag the release
- [ ] Build release artifacts and smoke-test them
- [ ] Create release PR and ensure CI passes
- [ ] Create archival backup if required

Notes:
- This checklist is a starting point — adapt to your project's requirements.
"""


def read_gitignore(path):
    gi_path = os.path.join(path, ".gitignore")
    if not os.path.exists(gi_path):
        return []
    with open(gi_path, "r", encoding="utf-8") as f:
        return [line.rstrip("\n") for line in f]


def write_gitignore(path, lines, apply):
    gi_path = os.path.join(path, ".gitignore")
    if apply:
        # backup
        if os.path.exists(gi_path):
            stamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            shutil.copyfile(gi_path, gi_path + ".bak." + stamp)
        with open(gi_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Updated .gitignore at: {gi_path}")
    else:
        print("Dry-run: would write the following .gitignore content:\n")
        print("\n".join(lines))


def ensure_release_checklist(path, apply):
    rc_path = os.path.join(path, "RELEASE_CHECKLIST.md")
    if os.path.exists(rc_path):
        print(f"RELEASE_CHECKLIST.md already exists at {rc_path}")
        return
    if apply:
        with open(rc_path, "w", encoding="utf-8") as f:
            f.write(RELEASE_CHECKLIST)
        print(f"Created RELEASE_CHECKLIST.md at {rc_path}")
    else:
        print("Dry-run: would create RELEASE_CHECKLIST.md with the standard checklist.")


def scan_for_sensitive_files(path):
    findings = []
    for root, dirs, files in os.walk(path):
        for name in files:
            if name.lower() in (".env", "secrets.env", "tokens.json"):
                findings.append(os.path.join(root, name))
    return findings


def main():
    parser = argparse.ArgumentParser(description="Prepare repo for publication")
    parser.add_argument("--path", default=".", help="Path to repository root")
    parser.add_argument("--apply", action="store_true", help="Apply changes (write files)")
    parser.add_argument("--extra", help="Comma-separated extra gitignore patterns to add")
    args = parser.parse_args()

    repo_root = os.path.abspath(args.path)
    print(f"Repository root: {repo_root}")

    existing = read_gitignore(repo_root)
    new_lines = list(existing)

    # Add default header if .gitignore empty
    if not any(line.strip() for line in existing):
        new_lines = []

    # flatten existing for comparison
    existing_set = set(line.strip() for line in existing if line.strip())

    additions = []
    for p in DEFAULT_PATTERNS:
        if p not in existing_set:
            additions.append(p)
            new_lines.append(p)

    if args.extra:
        for p in [x.strip() for x in args.extra.split(",") if x.strip()]:
            if p not in existing_set:
                additions.append(p)
                new_lines.append(p)

    if additions:
        print("The following patterns will be added to .gitignore:")
        for a in additions:
            print(f" - {a}")
    else:
        print("No new gitignore patterns needed.")

    write_gitignore(repo_root, new_lines, args.apply)

    # Create or verify release checklist
    ensure_release_checklist(repo_root, args.apply)

    # Scan repo for obvious sensitive files
    findings = scan_for_sensitive_files(repo_root)
    if findings:
        print("Potential sensitive files found:")
        for f in findings:
            print(f" - {f}")
        print("Please remove or rotate these before publishing, or ensure they're excluded by .gitignore.")
    else:
        print("No obvious sensitive files found by quick scan.")

    print("Done. Review the created/updated files and commit them to your repository when ready.")


if __name__ == "__main__":
    main()
