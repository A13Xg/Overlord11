# Memory

> Permanent preferences, behavioral rules, and standing decisions that persist indefinitely across all sessions.
> 
> This file is **NOT** cleared by `session_clean`. It survives workspace purges and Consciousness.md resets.
> 
> Update this file when the user establishes a lasting preference, a project-level rule, or a standing decision that should apply to all future sessions.

---

## How to Use This File

- **Agents**: Read `Memory.md` at session start alongside `Consciousness.md`.
- **When to write**: When a user establishes a rule, preference, or decision that should apply permanently (not just for the current task).
- **When NOT to write**: Ephemeral task context, session-specific findings, or anything that expires — those belong in `Consciousness.md`.
- **Format**: Use the entry format below. Group entries under appropriate headings.

### Entry Format

```markdown
### [RULE|PREFERENCE|DECISION] Title
- **Established**: YYYY-MM-DD
- **Source**: Who established this (user, Orchestrator, etc.)
- **Applies to**: Which agents or contexts this affects
- **Rule**: The actual preference or rule
- **Why**: Rationale (optional but recommended)
```

---

## Behavioral Rules

<!-- Standing rules that govern how all agents behave in every session. -->

### [RULE] Encoding Safety is Mandatory
- **Established**: 2026-01-12
- **Source**: System (coder.md)
- **Applies to**: OVR_COD_03 (all file I/O), all agents that write files
- **Rule**: Every `open()` call must specify `encoding="utf-8"`. Every `json.dumps()` must use `ensure_ascii=False`. Every subprocess output must be decoded with `.decode("utf-8", errors="replace")`. Every module that prints must have a `safe_str()` helper.
- **Why**: Silent encoding failures on Windows (cp1252/cp437) are hard to debug and cause cross-platform crashes.

### [RULE] Never Skip the Reviewer
- **Established**: 2026-01-12
- **Source**: System (orchestrator.md)
- **Applies to**: OVR_DIR_01
- **Rule**: All final outputs must pass through OVR_REV_06 before delivery. No exceptions, regardless of task size.
- **Why**: Prevents defective or incomplete outputs from reaching the user.

### [RULE] Always Initialize Project Docs
- **Established**: 2026-01-12
- **Source**: System (orchestrator.md)
- **Applies to**: OVR_DIR_01
- **Rule**: Before any work begins in a sandboxed project directory, ensure the 5 standardized files exist (ProjectOverview.md, Settings.md, TaskingLog.md, AInotes.md, ErrorLog.md). Use `project_docs_init` if missing.
- **Why**: Prevents agents from working without context, which leads to duplicate work and missed requirements.

### [RULE] UI Code Must Use Design System
- **Established**: 2026-01-12
- **Source**: System (coder.md, reviewer.md)
- **Applies to**: OVR_COD_03, OVR_REV_06
- **Rule**: Before writing any UI code, check for `design-system/MASTER.md`. If missing, call `ui_design_system` with `persist=true`. Never hardcode hex colors or invent styles — always use design system tokens.
- **Why**: Ensures visual consistency across all generated UI; prevents style drift between sessions.

### [RULE] Every New Python Project Gets a Launcher
- **Established**: 2026-01-12
- **Source**: System (coder.md)
- **Applies to**: OVR_COD_03
- **Rule**: Generate `run.py` (ASCII title, color menu, concurrent mode) + `run.bat` + `run.command` for every new Python project using `launcher_generator`.
- **Why**: Provides a consistent, user-friendly entry point for every project.

---

## Output Preferences

<!-- User preferences for how results are presented. -->

### [PREFERENCE] Output Tier Defaults
- **Established**: 2026-01-12
- **Source**: System (publisher.md)
- **Applies to**: OVR_DIR_01, OVR_PUB_07
- **Rule**: Default to Tier 1 (Markdown) unless the request explicitly or implicitly calls for visual/publication-quality output. Escalate to Tier 2 (HTML) only when content richness clearly warrants it.
- **Why**: Avoids unnecessary complexity for simple outputs.

---

## Provider Preferences

<!-- Standing choices about LLM providers and models. -->

### [PREFERENCE] Active Provider
- **Established**: 2026-01-12
- **Source**: config.json
- **Applies to**: All agents
- **Rule**: Active provider is set in `config.json` under `providers.active`. Do not hardcode provider or model names in agent definitions or tool implementations. Change provider by editing `config.json` only.
- **Why**: Provider agnosticism is a core design principle.

---

## Workspace Conventions

<!-- How workspace and sessions are organized. -->

### [RULE] One Workspace Per Session
- **Established**: 2026-01-12
- **Source**: System (runner.py, ONBOARDING.md)
- **Applies to**: All agents, engine runner
- **Rule**: Every engine session creates an isolated folder at `workspace/YYYYMMDD_HHMMSS/`. All agent-written files, research data, scaffolding, and program files go inside this folder. The session folder contains everything needed to reproduce or resume the task.
- **Why**: Isolation prevents cross-session contamination; enables clean resume and audit.

### [RULE] Logging Goes Through log_manager
- **Established**: 2026-04-06
- **Source**: System
- **Applies to**: All agents and tools
- **Rule**: All tool invocations and significant agent decisions should be logged to `logs/master.jsonl` via `log_manager`. Use `session_id` from the active session for all log entries.
- **Why**: A single log file provides a complete audit trail and enables session replays.

### [RULE] Session Clean Preserves Memory and Logs
- **Established**: 2026-04-06
- **Source**: System (session_clean.py)
- **Applies to**: OVR_CLN_08, session_clean tool
- **Rule**: `session_clean` always preserves `Memory.md` and `logs/`. It purges `workspace/SESSION_ID/` folders and clears ephemeral sections of `Consciousness.md`. Permanent context (Shared Context, Agent Registry) in `Consciousness.md` is never cleared.
- **Why**: Memories and logs are permanent records; workspace files are ephemeral task artifacts.

---

## Standing Decisions

<!-- Architecture or design decisions that should not be revisited without user instruction. -->

### [DECISION] Provider-Agnostic Tool Schemas
- **Established**: 2026-01-12
- **Source**: System
- **Applies to**: All tool definitions in `tools/defs/`
- **Rule**: Tool JSON schemas must contain zero provider-specific syntax. Provider is a runtime concern resolved from `config.json`.
- **Why**: Allows the entire tool library to work identically on Anthropic, Gemini, and OpenAI.

### [DECISION] Single Consciousness File for Cross-Agent Memory
- **Established**: 2026-01-12
- **Source**: System
- **Applies to**: All agents
- **Rule**: `Consciousness.md` at the project root is the single shared memory space for cross-agent communication. It is NOT project-specific — it serves all projects and all sessions simultaneously.
- **Why**: Decouples agents; enables asynchronous multi-agent workflows without direct coupling.
