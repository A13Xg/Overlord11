# Architecture

This document describes the Overlord11 system design: how components fit together, how data flows through the system, and the design decisions behind the framework.

---

## Overview

Overlord11 is built around four pillars:

1. **Agents** — LLM system prompts that define specialist roles and workflows
2. **Tools** — Python implementations and JSON schemas that give agents real-world capabilities
3. **Shared memory** — `Consciousness.md`, a Markdown file that provides persistent cross-agent context
4. **Execution engine + WebUI** — internal Python engine (`engine/`), REST API (`backend/`), and tactical frontend (`frontend/`) added in v3.0.0

All four components are **provider-agnostic**: none contain Anthropic, Gemini, or OpenAI specific code. The only provider-specific configuration lives in `config.json`.

---

## v3.0.0 System Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                           │
│         http://localhost:3000  —  Tactical Command Interface         │
│  JobQueue │ EventFeed │ Artifacts │ Product │ SystemLog │ Controls   │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ HTTP / SSE / WebSocket
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Backend API (FastAPI, port 8080)                   │
│                                                                      │
│  /api/jobs   /api/events  /ws   /api/models  /api/artifacts          │
│  /api/providers/status    /api/config        /health                 │
│                                                                      │
│  SessionStore (job registry + disk persistence)                      │
│  BackendEventBus (SSE/WS bridge per session_id)                      │
│  EngineBridge  ─── pause/resume/stop propagated to engine session    │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ asyncio.run_in_executor (thread pool)
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   Internal Engine  (engine/)                         │
│                                                                      │
│  EngineRunner ──── execution loop (provider call → tool dispatch)    │
│  OrchestratorBridge ── Anthropic / Gemini / OpenAI adapters          │
│  ToolExecutor ────── parses tool calls, dynamically loads tools      │
│  SelfHealingSystem ─ error classification + exponential backoff      │
│  SessionManager ──── session lifecycle (queued→running→done/failed)  │
│  EventStream ─────── per-session async event bus                     │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ reads agent .md files (system prompts)
                             │ dispatches to tools/python/*.py
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                          LLM Provider                                │
│              (Anthropic / Gemini / OpenAI — set in config.json)      │
└──────────────────────────────────────────────────────────────────────┘
```


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

1. `session_manager.py` creates a session directory under `workspace/YYYYMMDD_HHMMSS/`
2. Each tool call is logged to `logs/sessions/` (JSONL format)
3. Agent outputs are written to `workspace/YYYYMMDD_HHMMSS/output/`
4. Session is closed with a summary written to `workspace/YYYYMMDD_HHMMSS/session.json`
5. Key findings are persisted to `Consciousness.md`

Sessions are retained for up to 50 runs (configurable via `workspace.max_sessions_retained`).

---

## File Ownership

| Path | Owner | Notes |
|------|-------|-------|
| `agents/*.md` | Framework developers | System prompts — edit carefully |
| `tools/defs/*.json` | Framework developers | JSON Schema tool definitions |
| `tools/python/*.py` | Framework developers | Tool implementations |
| `engine/` | Framework developers | Internal execution engine |
| `backend/` | Framework developers | FastAPI backend + job system |
| `frontend/` | Framework developers | Next.js tactical WebUI |
| `config.json` | Operators | Runtime configuration |
| `Consciousness.md` | All agents | Shared memory — agents write here |
| `.env` | Operators | API keys — never commit |
| `workspace/` | Runtime | Auto-created, gitignored |
| `logs/` | Runtime | Auto-created, gitignored |
