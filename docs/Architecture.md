# Architecture

This document describes the Overlord11 system design: how components fit together, how data flows through the system, and the design decisions behind the framework.

---

## Overview

Overlord11 is built around three pillars:

1. **Agents** — LLM system prompts that define specialist roles and workflows
2. **Tools** — Python implementations and JSON schemas that give agents real-world capabilities
3. **Shared memory** — `Consciousness.md`, a Markdown file that provides persistent cross-agent context

All three components are **provider-agnostic**: none of them contain Anthropic, Gemini, or OpenAI specific code. The only provider-specific configuration lives in `config.json`.

---

## Component Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                          LLM Provider                                │
│              (Anthropic / Gemini / OpenAI — set in config.json)      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │  API calls
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        Agent Layer                                   │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │               Orchestrator  (OVR_DIR_01)                       │  │
│  │  • Classifies request type                                     │  │
│  │  • Decides output tier (0 / 1 / 2)                            │  │
│  │  • Writes delegation plan                                      │  │
│  │  • Sequences specialist agents                                 │  │
│  │  • Synthesizes final output                                    │  │
│  └─────┬──────────┬──────────┬──────────┬──────────┬─────────────┘  │
│        │          │          │          │          │                 │
│        ▼          ▼          ▼          ▼          ▼                 │
│  Researcher    Coder      Analyst    Writer    Reviewer              │
│  (RES_02)     (COD_03)   (ANL_04)   (WRT_05)  (REV_06)              │
│                                                    │                 │
│                                                    ▼                 │
│                                               Publisher              │
│                                               (PUB_07)               │
│                                                    │                 │
│                                                    ▼                 │
│                                               Cleanup                │
│                                               (CLN_08)               │
└──────────────────────────────────────────────────────────────────────┘
                               │  tool calls
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         Tool Layer                                   │
│                                                                      │
│  File I/O        Web          Execution      Analysis & Memory       │
│  ─────────       ───          ─────────      ────────────────────    │
│  read_file       web_fetch    run_shell      code_analyzer           │
│  write_file      web_scraper  git_tool       project_scanner         │
│  list_directory               calculator     save_memory             │
│  glob                         scaffold_gen   publisher_tool          │
│  search_file                                 consciousness_tool      │
│  replace                                     response_formatter      │
│                                              file_converter          │
│                                                                      │
│  Project Mgmt    Automation                                          │
│  ────────────    ──────────                                          │
│  task_manager    error_handler    computer_control                   │
│  error_logger    vision_tool                                         │
│  cleanup_tool    ui_design_system                                    │
│  project_docs                                                        │
│  launcher_gen                                                        │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  tools/defs/*.json   ←  JSON Schema (provider-agnostic)      │    │
│  │  tools/python/*.py   ←  Python implementations               │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
                               │  read / write
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       Shared Memory Layer                            │
│                                                                      │
│  Consciousness.md  (project root)                                    │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │  Cross-Agent Signals   │  WIP Entries   │  Pending Handoffs   │   │
│  │  Error States          │  Shared Context│  Archive            │   │
│  └───────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Standard Request Flow

```
1. User sends request to Orchestrator (via system prompt + user message)
2. Orchestrator reads Consciousness.md  →  checks for blockers / WIP
3. Orchestrator classifies request      →  task type + output tier
4. Orchestrator writes delegation plan  →  numbered subtask list
5. Orchestrator invokes Researcher      →  gather context
6.   Researcher uses web_fetch / web_scraper / read_file
7.   Researcher saves key findings to Consciousness.md
8. Orchestrator invokes Coder / Analyst (parallel if no dependency)
9.   Coder / Analyst use their tool sets to perform work
10.  Coder / Analyst write WIP entries to Consciousness.md
11. Orchestrator invokes Writer (Tier 1) or skips (Tier 2)
12. Orchestrator always invokes Reviewer
13.  Reviewer validates output; requests changes if needed
14. If Tier 2: Orchestrator invokes Publisher
15.  Publisher generates self-contained HTML with publisher_tool
16. Orchestrator synthesizes final output
17. Orchestrator writes session summary to Consciousness.md
18. Final output delivered to user
```

### Output Tier Decision

```
Is the request a simple Q&A or one-liner?
  YES → Tier 0: Answer inline, no file
  NO  ↓
Does the output need visual richness, charts, or publication quality?
  YES → Tier 2: Publisher → .html
  NO  → Tier 1: Writer → .md
```

---

## Design Principles

### 1. Provider Agnosticism

Agent definitions (`.md` files) contain zero provider-specific syntax. Tool schemas (`.json` files) use standard JSON Schema. The LLM provider is a runtime concern configured in `config.json` — swapping providers requires no code changes.

### 2. Separation of Concerns

Each agent has exactly one primary responsibility. The Orchestrator never does specialist work. Specialists never orchestrate. This makes agents independently testable and replaceable.

### 3. Fail-Safe Quality Gate

The Reviewer agent is **always** the last step before output delivery. The Orchestrator's quality checklist explicitly requires Reviewer invocation. This prevents unvalidated output from reaching users.

### 4. Shared Memory Over Direct Coupling

Agents communicate through `Consciousness.md` rather than direct API calls to each other. This enables:
- Asynchronous workflows (one agent's output persists even if the session ends)
- Transparent state (any agent can see what others have done)
- Auditability (the memory file is a readable change log)

### 5. Tool-First Execution

Agents are instructed to use tools (e.g., `read_file`) rather than recall from memory. This prevents hallucination of file contents and keeps behavior grounded in real data.

---

## Configuration Architecture

`config.json` is the single source of truth for:

- **Provider settings** — active provider, models, API endpoints, token limits
- **Agent definitions** — IDs, file paths, delegation permissions, tool access lists
- **Tool registry** — schema paths and implementation paths for all tools
- **Orchestration policy** — loop limits, retry counts, fallback order, phases
- **Quality policy** — test coverage, complexity limits, security scan settings
- **Workspace / logging** — paths, session ID format, log rotation

See [Configuration Reference](Configuration-Reference.md) for every field.

---

## Session Lifecycle

Each agent run produces a **session**:

1. `session_manager.py` creates exactly one task directory under `workspace/YYYYMMDD_HHMMSS/`
2. Each tool call is logged to `logs/sessions/` (JSONL format)
3. Task-local agent/tool/runtime data is written under `agent/`, `tools/`, and `logs/` inside that task directory
4. Final deliverables are written at the task-root level; software project files live in `app/` when applicable
5. Session metadata is written to `workspace/YYYYMMDD_HHMMSS/logs/session.json`
6. Key findings are persisted to `Consciousness.md`

Sessions are retained for up to 50 runs (configurable via `workspace.max_sessions_retained`).

---

## File Ownership

| Path | Owner | Notes |
|------|-------|-------|
| `agents/*.md` | Framework developers | System prompts — edit carefully |
| `tools/defs/*.json` | Framework developers | JSON Schema tool definitions |
| `tools/python/*.py` | Framework developers | Tool implementations |
| `engine/` | Framework developers | Internal execution engine |
| `backend/` | Framework developers | Tactical WebUI FastAPI backend |
| `frontend/` | Framework developers | Tactical WebUI single-page app |
| `config.json` | Operators | Runtime configuration |
| `Consciousness.md` | All agents | Shared memory — agents write here |
| `.env` | Operators | API keys — never commit |
| `workspace/` | Runtime | Auto-created, gitignored |
| `logs/` | Runtime | Auto-created, gitignored |

---

## Internal Execution Engine (`engine/`)

Overlord11 v2.3.0 introduces an **internal Python execution engine** that lets agents run without any external CLI (Claude CLI, Gemini CLI, etc.). The framework supports two modes:

### Mode A — External CLI (existing behavior)
- User loads an agent `.md` file as a system prompt in their LLM client
- Agent reads `ONBOARDING.md` and operates using tool schemas
- No code changes required

### Mode B — Internal Engine
- `run_engine.py` launches an interactive terminal interface
- `EngineRunner` manages the full agent loop: prompt → LLM call → tool detection → tool execution → re-injection → repeat
- `OrchestratorBridge` handles provider API calls (Anthropic, Gemini, OpenAI) with automatic fallback
- `ToolExecutor` parses tool calls from three text formats and dispatches to `tools/python/` implementations
- `EventStream` emits structured events at every step (agent start/complete, tool call/result, session start/end)
- `SelfHealingEngine` classifies errors and builds retry hints for re-injection into the agent context

```
engine/
  runner.py             ← Core agent execution loop
  orchestrator_bridge.py← Provider-agnostic LLM API caller (stdlib urllib)
  tool_executor.py      ← Tool call parser + Python/subprocess dispatcher
  session_manager.py    ← EngineSession wrapper over tools/python/session_manager.py
  event_stream.py       ← EventType enum + EventStream with callbacks
  self_healing.py       ← Error classification, retry logic, failure logging
```

### Engine Data Flow

```
run_engine.py / WebUI job
       │
       ▼
 EngineRunner.run(user_input)
       │
       ├─► OrchestratorBridge.build_system_prompt()  ← reads ONBOARDING.md + agent .md
       │
       └─► Loop (max_loops):
              │
              ├─► OrchestratorBridge.call_provider()   ← REST call with fallback
              │         │
              │         └─► response text
              │
              ├─► extract_tool_calls(response)          ← 3-format parser
              │
              ├─► ToolExecutor.execute(tool_call)       ← import + call main(), or subprocess
              │
              ├─► EventStream.emit(...)                 ← TOOL_CALL / TOOL_RESULT events
              │
              └─► OrchestratorBridge.build_context()   ← append tool results as user messages
```

---

## Tactical WebUI (`backend/` + `frontend/`)

A self-hosted web application providing a visual interface over the engine.

### Backend (`backend/`)

Built with FastAPI + async WebSockets (SSE). Entry point: `scripts/run_webui.py` (port 7900).

```
backend/
  main.py                ← FastAPI app, lifespan, CORS, routers
  api/
    jobs.py              ← Job CRUD + start/stop/pause/resume/restart
    providers.py         ← Provider/model listing + selection
    artifacts.py         ← Artifact listing + secure file serving
    events.py            ← SSE endpoints (/api/events, /api/events/{job_id})
  core/
    session_store.py     ← Job dataclass + SessionStore (file-persisted)
    engine_bridge.py     ← Async engine driver + sequential job queue worker
    event_stream.py      ← EventBroadcaster with SSE fan-out + heartbeat
```

### Job State Machine

```
QUEUED → RUNNING → COMPLETED
                 → FAILED
         PAUSED (from RUNNING) → RUNNING (on resume)
         (stop) → FAILED
```

Jobs run **sequentially** via `asyncio.Queue`. The engine runs in a thread-pool executor so the async event loop stays responsive.

### Frontend (`frontend/index.html`)

Self-contained single-page application (no build step). Cold-war Soviet control panel aesthetic with CRT scanlines, radar animation, and matrix-green palette. Connects to the backend via REST + SSE.
