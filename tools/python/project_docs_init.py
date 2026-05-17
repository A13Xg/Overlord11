"""
Overlord11 - Project Docs Initializer
==========================================
Initializes the standardized documentation files within a sandboxed project directory:
  - ProjectOverview.md  — Comprehensive onboarding for fresh agents
  - Settings.md         — AI behavior configuration (human+AI readable)
  - TaskingLog.md       — Task tracking with checkboxes
  - AInotes.md          — Critical notes for agent continuity
  - ErrorLog.md         — Error tracking with severity and resolution

Usage:
    python project_docs_init.py --project_dir /path/to/task --project_name "My App"
    python project_docs_init.py --project_dir /path/to/task --project_name "My App" --language python
"""

import io
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from log_manager import log_tool_invocation
from task_workspace import env_task_dir


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def init_project_overview(project_dir: str, project_name: str = "Untitled Project",
                          language: str = "", description: str = "") -> str:
    content = f"""# ProjectOverview

> Comprehensive onboarding document for AI agents and human developers.
> Read this file FIRST when joining the project.

---

## Project Identity

| Field | Value |
|-------|-------|
| **Name** | {project_name} |
| **Language/Stack** | {language or '_(to be determined)_'} |
| **Description** | {description or '_(to be filled by the agent or human)_'} |
| **Created** | {_timestamp()} |
| **Last Updated** | {_timestamp()} |

---

## Purpose & Goals

> What does this project do? What problem does it solve?

_(To be filled: describe the project's core purpose, target users, and key value proposition.)_

---

## Architecture & Design

> How is the project structured? What are the major components?

### Directory Structure
```
task-root/
  ProjectOverview.md    # agent context (this file)
  Settings.md           # AI behavior config
  TaskingLog.md         # task tracking
  AInotes.md            # critical agent notes
  ErrorLog.md           # error tracking
  final_output.md       # session deliverable
  artifacts/
    app/                # software project source, if applicable
    agent/              # system profile, agent traces
    tools/              # web scrapes, vision outputs, tool cache
    logs/               # session manifest, events, trace index
```

### Key Components
_(List and describe the major modules, services, or components.)_

### Data Flow
_(Describe how data moves through the system.)_

---

## Technical Stack

| Category | Technology | Notes |
|----------|-----------|-------|
| Language | {language or 'TBD'} | |
| Framework | TBD | |
| Database | TBD | |
| Testing | TBD | |
| Build | TBD | |
| Deployment | TBD | |

---

## Design Constraints & Requirements

### Functional Requirements
_(Numbered list of what the project must do.)_

### Non-Functional Requirements
_(Performance, security, scalability, accessibility requirements.)_

### Design Constraints
_(Technical limitations, compatibility requirements, platform targets.)_

---

## UI/UX Design

> Visual identity and user experience guidelines.

| Property | Value |
|----------|-------|
| **Style** | _(e.g., modern, minimal, material, etc.)_ |
| **Primary Color** | _(e.g., #1a73e8)_ |
| **Secondary Color** | _(e.g., #34a853)_ |
| **Accent Color** | _(e.g., #ea4335)_ |
| **Background** | _(e.g., #ffffff / #121212 for dark mode)_ |
| **Font - Headings** | _(e.g., Inter, Roboto)_ |
| **Font - Body** | _(e.g., system-ui, sans-serif)_ |
| **Border Radius** | _(e.g., 8px)_ |
| **Spacing Unit** | _(e.g., 4px base)_ |
| **Dark Mode** | _(yes/no/auto)_ |
| **Responsive** | _(yes/no, breakpoints)_ |
| **Accessibility** | _(WCAG level, screen reader support)_ |

### Component Guidelines
_(Describe button styles, form inputs, cards, modals, navigation patterns, etc.)_

---

## API & Integration Points

_(Describe any APIs consumed or exposed, webhook endpoints, third-party integrations.)_

---

## Environment & Configuration

| Variable | Purpose | Required |
|----------|---------|----------|
| _(e.g., DATABASE_URL)_ | _(DB connection)_ | yes |

---

## Getting Started (for agents)

1. Read this file completely
2. Read `Settings.md` for AI behavior configuration
3. Check `TaskingLog.md` for current and completed tasks
4. Check `AInotes.md` for critical notes from previous agents
5. Check `ErrorLog.md` for any open errors
6. Begin your assigned task

---

*Last updated: {_timestamp()}*
"""
    return content


def init_settings(project_dir: str) -> str:
    content = f"""# Settings

> AI behavior configuration for this project. Human+AI readable.
> Format: `option = value` with allowed values listed.
> Agents: read this file at session start and respect all settings.

---

## Agent Behavior

```ini
# --- Thinking & Reasoning ---
# How deeply the AI should analyze before acting
thinking_depth = moderate
# Allowed: minimal | moderate | thorough | exhaustive

# How verbose AI responses should be after completing tasks
response_verbosity = concise
# Allowed: minimal | concise | detailed | comprehensive

# Whether to explain reasoning or just show results
show_reasoning = true
# Allowed: true | false

# --- Verification & Testing ---
# How much effort to spend verifying and testing work
verification_level = standard
# Allowed: skip | quick | standard | thorough | exhaustive

# Run tests automatically after code changes
auto_run_tests = true
# Allowed: true | false

# Run static analysis (code_analyzer) after code changes
auto_static_analysis = true
# Allowed: true | false

# --- Error Handling ---
# What to do when a task fails
error_response = try_fix_then_ask
# Allowed: try_fix_self | try_fix_then_ask | suggest_and_wait | halt_and_wait | error_workflow

# Maximum retry attempts before escalating
max_retry_loops = 3
# Allowed: 1-10 (integer)

# When error_response = error_workflow, run this sequence:
# 1. Log to ErrorLog.md
# 2. Analyze error and generate ranked solutions
# 3. Attempt solutions in order (up to max_retry_loops)
# 4. If all fail, halt and report to human
error_workflow_enabled = true
# Allowed: true | false

# --- Task Management ---
# Automatically update TaskingLog.md when starting/completing tasks
auto_update_tasking_log = true
# Allowed: true | false

# Automatically update AInotes.md with significant findings
auto_update_ai_notes = true
# Allowed: true | false

# Check TaskingLog.md before starting work to avoid duplicates
check_for_duplicates = true
# Allowed: true | false

# --- Code Style ---
# Add docstrings to new functions/classes
require_docstrings = true
# Allowed: true | false

# Add type hints to function signatures (Python)
require_type_hints = true
# Allowed: true | false

# Maximum function complexity (cyclomatic) before suggesting refactor
max_function_complexity = 10
# Allowed: 5-25 (integer)

# --- Safety ---
# Run cleanup_tool scan before any deployment/push
pre_deploy_scan = true
# Allowed: true | false

# Block commits containing detected secrets
block_secrets_in_commits = true
# Allowed: true | false

# --- Output ---
# Default output tier (can be overridden per task)
default_output_tier = 1
# Allowed: 0 | 1 | 2

# Where to save final deliverables
output_dir = ./
# Allowed: any valid relative path within the task root
```

---

## Project-Specific Overrides

> Add any project-specific setting overrides below.
> These take precedence over the defaults above.

```ini
# (add overrides here)
```

---

*Last updated: {_timestamp()}*
"""
    return content


def init_tasking_log(project_dir: str) -> str:
    content = f"""# TaskingLog

> Standardized task tracking for AI agents and humans.
> **Format**: Tasks are numbered sequentially. Subtasks are indented under their parent.
> **Status Icons**: `[ ]` = pending, `[~]` = in progress, `[x]` = completed, `[!]` = blocked, `[-]` = skipped

---

## Active Tasks

*(No tasks yet)*

---

## Completed Tasks

*(No completed tasks yet)*

---

*Last updated: {_timestamp()}*
"""
    return content


def init_ai_notes(project_dir: str) -> str:
    content = f"""# AInotes

> Critical notes from AI agents for all future agents working on this project.
> Only write here if the information is SIGNIFICANTLY important.
> This file is read by every agent at session start.

---

## Format

Each note follows this format:
- **Date**: When the note was written
- **Agent**: Which agent wrote it
- **Category**: One of `BLOCKER`, `GOTCHA`, `REQUIREMENT`, `ARCHITECTURE`, `WARNING`
- **Content**: The actual note

---

## Notes

*(No notes yet)*

---

*Last updated: {_timestamp()}*
"""
    return content


def init_error_log(project_dir: str) -> str:
    content = f"""# ErrorLog

> Standardized error tracking for AI agents and humans.
> Errors are logged with severity, context, attempted fixes, and resolution.
> **Severity**: `CRITICAL` = blocks all work | `MAJOR` = blocks current task | `MINOR` = workaround exists | `WARNING` = potential issue

---

## Open Errors

*(No open errors)*

---

## Resolved Errors

*(No resolved errors)*

---

*Last updated: {_timestamp()}*
"""
    return content


def init_all(project_dir: str, project_name: str = "Untitled Project",
             language: str = "", description: str = "") -> dict:
    """Initialize all standardized project docs."""
    pdir = Path(project_dir).resolve()
    pdir.mkdir(parents=True, exist_ok=True)

    files_created = []
    files_skipped = []

    docs = {
        "ProjectOverview.md": init_project_overview(project_dir, project_name, language, description),
        "Settings.md": init_settings(project_dir),
        "TaskingLog.md": init_tasking_log(project_dir),
        "AInotes.md": init_ai_notes(project_dir),
        "ErrorLog.md": init_error_log(project_dir),
    }

    for filename, content in docs.items():
        filepath = pdir / filename
        if filepath.exists():
            files_skipped.append(filename)
        else:
            filepath.write_text(content, encoding="utf-8")
            files_created.append(filename)

    return {
        "status": "ok",
        "project_dir": str(pdir),
        "created": files_created,
        "skipped_existing": files_skipped,
        "total_files": len(docs)
    }


# --- CLI Interface ---

def main():
    import argparse, io

    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


    parser = argparse.ArgumentParser(description="Overlord11 Project Docs Initializer")
    parser.add_argument("--project_dir", default=None, help="Path to task directory")
    parser.add_argument("--task_dir", default=None, help="Alias for --project_dir")
    parser.add_argument("--project_name", default="Untitled Project", help="Project name")
    parser.add_argument("--language", default="", help="Primary language/stack")
    parser.add_argument("--description", default="", help="Short project description")
    parser.add_argument("--session_id", default=None, help="Session ID for logging")

    args = parser.parse_args()
    start = time.time()

    project_dir = args.task_dir or args.project_dir or (str(env_task_dir()) if env_task_dir() else None)
    if not project_dir:
        parser.error("--project_dir is required when no task workspace is active")

    result = init_all(
        project_dir=project_dir,
        project_name=args.project_name,
        language=args.language,
        description=args.description
    )

    duration_ms = (time.time() - start) * 1000

    if args.session_id:
        log_tool_invocation(
            session_id=args.session_id,
            tool_name="project_docs_init",
            params={"project_dir": project_dir, "project_name": args.project_name},
            result={"status": result.get("status", "unknown")},
            duration_ms=duration_ms
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
