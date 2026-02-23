# AgenticToolset - Master Onboarding

> Portable AI development toolkit. Drop this directory into any project. Read this file first.

---

## Before You Start: Project Brief

Fill `PROJECT_BRIEF.md` at the root of this directory with concise, high-level context for the task before creating a session. Agents will read that brief first to speed onboarding and reduce clarifying questions. At minimum include: Project Name, Short Description, Primary Goal, Acceptance Criteria, Key Files, and any Constraints or Priorities.


## What This Is

AgenticToolset is a self-contained toolkit that gives you a structured system of **specialized sub-agents**, **Python tools**, and **centralized logging** to work on any codebase. When this directory exists in a project, follow the protocols below.

---

## Quick Start Protocol

When you first encounter this toolset in a project, execute these steps in order:

### 1. Create a Session
```bash
python AgenticToolset/tools/python/session_manager.py --action create --description "Brief task description"
```
Capture the `session_id` from the output. Use it for all subsequent tool calls.

### 2. Scan the Project
```bash
python AgenticToolset/tools/python/project_scanner.py --path . --session_id SESSION_ID
```
This gives you the full project profile: languages, frameworks, structure, entry points, dependencies.

### 3. Adopt the Orchestrator Role
Read `AgenticToolset/agents/orchestrator.md` and follow its workflow. The Orchestrator (AGNT_DIR_01) is always your starting role. It tells you how to decompose requests and delegate to specialists.

### 4. Execute the Task
Follow the Orchestrator's workflow phases: SCAN -> PLAN -> EXECUTE -> REVIEW -> DELIVER.

### 5. Close the Session
```bash
python AgenticToolset/tools/python/session_manager.py --action close --session_id SESSION_ID --description "Summary of work"
```

---

## Agent System

### How Agents Work

Each agent is a **role definition** stored as a markdown file in `AgenticToolset/agents/`. To "invoke" an agent, you read its file and adopt its persona, responsibilities, and output format for the sub-task at hand.

You can also delegate to agents using the **Task tool** with subagent_type:

```
Task tool:
  subagent_type: "general-purpose"
  prompt: "[Read the agent file content] + [The specific task]"
```

### Agent Registry

| Agent ID | Name | File | Use When |
|----------|------|------|----------|
| AGNT_DIR_01 | **Orchestrator** | `agents/orchestrator.md` | Always start here. Decomposes requests, delegates, manages workflow. |
| AGNT_ARC_02 | **Architect** | `agents/architect.md` | Designing solutions, creating implementation plans, analyzing architecture. |
| AGNT_COD_03 | **Implementer** | `agents/implementer.md` | Writing code, implementing features, making changes. |
| AGNT_REV_04 | **Reviewer** | `agents/reviewer.md` | Reviewing code quality, security, performance, correctness. |
| AGNT_DBG_05 | **Debugger** | `agents/debugger.md` | Diagnosing bugs, tracing errors, finding root causes. |
| AGNT_RES_06 | **Researcher** | `agents/researcher.md` | Gathering context, understanding codebases, researching approaches. |
| AGNT_TST_07 | **Tester** | `agents/tester.md` | Writing tests, running test suites, validating behavior. |
| AGNT_DOC_08 | **Doc Writer** | `agents/doc_writer.md` | Writing documentation, READMEs, API docs, comments. |
| AGNT_WEB_09 | **Web Researcher** | `agents/web_researcher.md` | Web search, RSS feed discovery, page scraping, online research. |

### Delegation Patterns

**Feature Request:**
```
Orchestrator -> Researcher (understand context)
             -> Architect (design solution)
             -> Implementer (write code)
             -> Tester (write/run tests)
             -> Reviewer (quality check)
             -> Doc Writer (if docs needed)
```

**Bug Fix:**
```
Orchestrator -> Debugger (diagnose root cause)
             -> Implementer (apply fix)
             -> Tester (regression tests)
             -> Reviewer (verify fix)
```

**Refactor:**
```
Orchestrator -> Researcher (understand current state)
             -> Architect (plan refactor)
             -> Reviewer (review current code)
             -> Implementer (execute refactor)
             -> Tester (verify no regressions)
```

**Code Review:**
```
Orchestrator -> Reviewer (full review)
```

**New Project:**
```
Orchestrator -> Architect (design structure)
             -> Implementer (scaffold + implement)
             -> Tester (write initial tests)
             -> Doc Writer (README + setup docs)
```

---

## Tool System

### Available Tools

All tools are Python scripts in `AgenticToolset/tools/python/`. Each has a corresponding JSON definition in `AgenticToolset/tools/defs/`. Run tools via Bash:

```bash
python AgenticToolset/tools/python/TOOL_NAME.py --help
```

### Tool Reference

#### 1. Project Scanner
**Purpose**: Deep scan of a project directory. Detects languages, frameworks, entry points, configs.
**When**: First thing when working on any project. Also useful when you need to understand project structure.
```bash
python AgenticToolset/tools/python/project_scanner.py --path . --session_id SESSION_ID
python AgenticToolset/tools/python/project_scanner.py --path . --depth 3 --output scan.json
```

#### 2. Dependency Analyzer
**Purpose**: Analyzes package manifests. Finds unpinned versions, security flags, missing lockfiles, conflicts.
**When**: Before adding dependencies, during security review, or when debugging dependency issues.
```bash
python AgenticToolset/tools/python/dependency_analyzer.py --path . --session_id SESSION_ID
python AgenticToolset/tools/python/dependency_analyzer.py --path . --check security
```

#### 3. Code Analyzer
**Purpose**: Static analysis. Complexity metrics, code smells, import analysis, function extraction.
**When**: During code review, before refactoring, or when assessing code quality.
```bash
python AgenticToolset/tools/python/code_analyzer.py --path . --session_id SESSION_ID
python AgenticToolset/tools/python/code_analyzer.py --file src/app.py --check complexity
python AgenticToolset/tools/python/code_analyzer.py --path . --language python --check smells
```

#### 4. Session Manager
**Purpose**: Tracks work sessions. Creates workspaces, logs changes, records agent/tool usage.
**When**: Start of every task (create), during work (log changes), end of task (close).
```bash
python AgenticToolset/tools/python/session_manager.py --action create --description "Task description"
python AgenticToolset/tools/python/session_manager.py --action log_change --session_id SESSION_ID \
    --data '{"file": "src/app.py", "action": "modified", "summary": "Added error handling"}'
python AgenticToolset/tools/python/session_manager.py --action close --session_id SESSION_ID
python AgenticToolset/tools/python/session_manager.py --action list
python AgenticToolset/tools/python/session_manager.py --action active
```

#### 5. Metrics Collector
**Purpose**: Comprehensive code metrics. LOC, file distributions, function counts, test ratios, git activity.
**When**: Project assessment, progress tracking, or when you need quantitative data about the codebase.
```bash
python AgenticToolset/tools/python/metrics_collector.py --path . --session_id SESSION_ID
python AgenticToolset/tools/python/metrics_collector.py --path . --metric loc
python AgenticToolset/tools/python/metrics_collector.py --path . --metric git
python AgenticToolset/tools/python/metrics_collector.py --path . --metric tests
```

#### 6. Scaffold Generator
**Purpose**: Generate project scaffolding from templates. Creates complete boilerplate.
**When**: Starting a new project or component. Templates: python_cli, python_api, node_api, react_app.
```bash
python AgenticToolset/tools/python/scaffold_generator.py --list-templates
python AgenticToolset/tools/python/scaffold_generator.py --template python_api --name my_api --output ./my_api
python AgenticToolset/tools/python/scaffold_generator.py --template python_cli --name my_tool --output ./my_tool \
    --description "A CLI tool for data processing"
```

#### 7. Log Manager
**Purpose**: Central logging for all activity. Query and summarize logs.
**When**: Automatically used by other tools. Directly call for queries and summaries.
```bash
python AgenticToolset/tools/python/log_manager.py --action log_decision --session_id SESSION_ID \
    --data '{"agent": "AGNT_ARC_02", "decision": "Use REST over GraphQL", "reasoning": "Project already uses Express"}'
python AgenticToolset/tools/python/log_manager.py --action query --session_id SESSION_ID --last_n 20
python AgenticToolset/tools/python/log_manager.py --action summary --session_id SESSION_ID
python AgenticToolset/tools/python/log_manager.py --action list_sessions
```

#### 8. Web Researcher
**Purpose**: Web search, RSS feed discovery and parsing, page scraping and text extraction.
**When**: Researching libraries, looking up documentation, monitoring news feeds, gathering online context.
```bash
python AgenticToolset/tools/python/web_researcher.py --action search --query "fastapi authentication" --session_id SESSION_ID
python AgenticToolset/tools/python/web_researcher.py --action extract --url https://example.com
python AgenticToolset/tools/python/web_researcher.py --action find_feeds --url https://example.com
python AgenticToolset/tools/python/web_researcher.py --action parse_feed --url https://example.com/feed.xml
python AgenticToolset/tools/python/web_researcher.py --action fetch --url https://example.com
```

---

## Logging Protocol

**Everything gets logged.** This is non-negotiable. The logging system provides auditability, session continuity, and debugging context.

### What to Log

| Event | How | When |
|-------|-----|------|
| Session start | `session_manager --action create` | Beginning of any task |
| Project scan | Automatic (project_scanner logs itself) | First interaction with codebase |
| Agent activation | `log_manager --action log_agent_switch` | Every time you switch agent roles |
| Key decisions | `log_manager --action log_decision` | Architecture choices, approach decisions |
| File changes | `session_manager --action log_change` | Every file create/modify/delete |
| Tool usage | Automatic (all tools log themselves) | Every tool invocation |
| Errors | `log_manager --action log_error` | Any error or unexpected outcome |
| Session end | `session_manager --action close` | Task completion |

### Log Location

- **Master log**: `AgenticToolset/logs/master.jsonl` (all activity, all sessions)
- **Session logs**: `AgenticToolset/logs/sessions/SESSION_ID.jsonl` (per-session activity)
- **Session manifests**: `AgenticToolset/workspace/SESSION_ID/session.json` (session metadata)

---

## Directory Structure

```
AgenticToolset/
├── ONBOARDING.md              # This file - read first
├── config.json                # Configuration (model settings, tool registry, quality standards)
├── memory.md                  # Persistent memory across sessions
│
├── agents/                    # Sub-agent role definitions
│   ├── orchestrator.md        # AGNT_DIR_01 - Master coordinator
│   ├── architect.md           # AGNT_ARC_02 - Solution design
│   ├── implementer.md         # AGNT_COD_03 - Code writing
│   ├── reviewer.md            # AGNT_REV_04 - Code review
│   ├── debugger.md            # AGNT_DBG_05 - Bug diagnosis
│   ├── researcher.md          # AGNT_RES_06 - Context gathering
│   ├── tester.md              # AGNT_TST_07 - Test engineering
│   ├── doc_writer.md          # AGNT_DOC_08 - Documentation
│   └── web_researcher.md      # AGNT_WEB_09 - Web research & scraping
│
├── tools/
│   ├── defs/                  # JSON tool definitions (schemas)
│   │   ├── project_scanner.json
│   │   ├── dependency_analyzer.json
│   │   ├── code_analyzer.json
│   │   ├── session_manager.json
│   │   ├── metrics_collector.json
│   │   ├── scaffold_generator.json
│   │   ├── log_manager.json
│   │   └── web_researcher.json
│   └── python/                # Python tool implementations
│       ├── project_scanner.py
│       ├── dependency_analyzer.py
│       ├── code_analyzer.py
│       ├── session_manager.py
│       ├── metrics_collector.py
│       ├── scaffold_generator.py
│       ├── log_manager.py
│       └── web_researcher.py
│
├── logs/                      # Log output directory
│   ├── master.jsonl           # Master log (auto-created)
│   └── sessions/              # Per-session logs (auto-created)
│
└── workspace/                 # Session workspaces
    └── SESSION_ID/            # Created per session
        ├── session.json       # Session manifest
        ├── output/            # Session output files
        └── temp/              # Session temp files
```

---

## Configuration

The `config.json` file contains:

- **model_config**: LLM provider and model settings
- **orchestration_logic**: Workflow phases, loop limits, fallback behavior
- **agent_registry**: All agents with file paths
- **tool_registry**: All tools with definition and implementation paths
- **logging**: Log file locations, rotation settings
- **quality_standards**: Min quality scores, review requirements, complexity limits
- **workspace**: Session directory settings

Modify `config.json` to customize behavior for specific projects.

---

## Memory System

`memory.md` persists across sessions. Use it to store:

- Project-specific context discovered during scans
- Architecture decisions made
- Known issues and their status
- Patterns specific to this codebase

Update memory when you learn something that would be valuable for future sessions.

---

## Integration with Overlord11

This toolkit is part of the Overlord11 framework. The parent project includes:

- **Analysis-Summarize**: Data analysis and report generation
- **Research-InfoGather**: Automated research and information synthesis
- **Writing-Literature**: Content writing and transformation
- **Code-ProjectGen**: Code generation with project scaffolding
- **GeminiToolset**: Parallel toolkit for Google Gemini
- **Consciousness.md**: Cross-agent shared memory system

The `Consciousness.md` file at the project root can be used for cross-system communication when multiple toolsets are active.

---

## Extending the Toolset

### Adding a New Tool
1. Create Python implementation in `tools/python/new_tool.py`
2. Import and use `log_manager` for automatic logging
3. Add CLI interface with argparse and `--session_id` parameter
4. Create JSON definition in `tools/defs/new_tool.json`
5. Register in `config.json` under `tool_registry`
6. Document in this file under Tool Reference

### Adding a New Agent
1. Create markdown file in `agents/new_agent.md`
2. Follow the pattern: Identity, Responsibilities, Workflow, Output Format, Quality Checklist
3. Assign agent ID following pattern: `AGNT_XXX_NN`
4. Register in `config.json` under `agent_registry`
5. Add to the Agent Registry table in this file
6. Update Orchestrator's delegation guide

---

## Rules

1. **Always create a session** before starting work
2. **Always scan the project** if this is the first interaction
3. **Always log** decisions, changes, and errors
4. **Always start as Orchestrator** and delegate to specialists
5. **Always review** code changes before considering them done
6. **Always close the session** when work is complete
7. **Follow existing patterns** in the target project - never impose new conventions
8. **Minimal changes** - do what was asked, nothing more

## Publishing & Cleanup

When preparing a project for public release or publication, run the publishing cleanup utility to ensure AI/model artifacts and secrets are excluded and documentation is finalized.

Dry-run (shows what would change):
```bash
python AgenticToolset/tools/python/publish_cleanup.py --path .
```

Apply changes (writes `.gitignore` additions and `RELEASE_CHECKLIST.md`):
```bash
python AgenticToolset/tools/python/publish_cleanup.py --path . --apply
```

After running, review and commit the changes, then follow the `RELEASE_CHECKLIST.md` steps.
