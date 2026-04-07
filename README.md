# Overlord11

> **Provider-agnostic multi-agent LLM orchestration framework with Tactical WebUI**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-2.3.0-22c55e)](config.json)
[![Tools](https://img.shields.io/badge/tools-43%20built--in-6366f1)](tools/python/)
[![Agents](https://img.shields.io/badge/agents-8%20specialists-f59e0b)](agents/)
[![Providers](https://img.shields.io/badge/providers-Anthropic%20%7C%20Gemini%20%7C%20OpenAI-0ea5e9)](docs/Providers.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-64748b)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-64748b)](https://github.com/A13Xg/Overlord11)

Overlord11 is a structured multi-agent framework that coordinates **eight specialist AI agents** across any LLM provider (Anthropic Claude, Google Gemini, or OpenAI GPT). Every request is routed through an **Orchestrator** that decomposes tasks, delegates to specialists, and synthesizes a reviewed final output — without any provider-specific code in the agent definitions or tool schemas.

It ships with a **Tactical WebUI** — a cold-war Soviet control-panel interface for dispatching jobs, watching live agent execution, and inspecting all output artifacts — alongside a classic **CLI mode** for direct terminal use.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
  - [WebUI (recommended)](#webui-recommended)
  - [CLI Mode](#cli-mode)
- [Directory Structure](#directory-structure)
- [Agents](#agents)
- [Tools](#tools)
- [Output Tiers](#output-tiers)
- [Provider Configuration](#provider-configuration)
- [Rate Limiting](#rate-limiting)
- [Environment Variables](#environment-variables)
- [Testing](#testing)
- [Extension Guide](#extension-guide)
- [Memory System](#memory-system)
- [Wiki](#wiki)

---

## Features

- 🌐 **Tactical WebUI** — browser-based control panel: create jobs, watch live token streaming, inspect artifacts in split-panel file explorer, rate-limit countdown banners, provider health dashboard
- 🔀 **Provider-agnostic** — switch between Anthropic, Gemini, or OpenAI by changing one line in `config.json`; automatic per-model fallback within each provider
- 🤖 **8 specialist agents** — Orchestrator, Researcher, Coder, Analyst, Writer, Reviewer, Publisher, Cleanup
- 🛠️ **43 built-in tools** — file I/O, web fetch/scrape, shell execution, Git, code analysis, project scanning, UI design system, scaffolding, task management, data visualization, notifications, and more
- ⚡ **Parallel tool execution** — dependency-aware wave scheduling runs independent tool calls concurrently; configurable thread pool
- 🔁 **Rate-limit resilience** — three configurable actions when all providers return 429: `pause` (exponential backoff, default), `stop`, or `try_different_model`; interruptible waits with live countdown in the UI
- 📡 **Live streaming** — token-by-token SSE streaming from every provider with automatic non-streaming fallback
- 🎨 **UI/UX design system skill** — 10 curated styles × 10 color palettes; Coder generates a persistent spec before any UI work; Reviewer validates against it
- 🔍 **Dual-engine search** — ripgrep when available, pure-Python fallback producing identical JSON output
- 📊 **3 output tiers** — inline text, Markdown docs, or styled self-contained HTML reports
- 🖼️ **9 HTML themes** — techno, classic, modern, editorial, and more — auto-selected by content type
- 🔒 **Tool result caching** — SHA-256 keyed LRU cache with configurable TTL; side-effect tools excluded by default
- 🧠 **Shared memory** — `Consciousness.md` enables cross-agent, cross-session context
- 🔐 **Authentication** — session-token auth with SHA-256 password hashing; optional dev bypass
- ✅ **Fully tested** — test suite covering all tool modules, ripgrep/Python fallback, Unicode, encoding edge-cases
- 🔌 **Extensible** — add agents, tools, or LLM providers without touching the framework core

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Request                            │
│              (WebUI job  OR  CLI prompt)                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    EngineBridge
                  (async worker pool)
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│               Orchestrator  (OVR_DIR_01)                    │
│  1.Intake → 2.Classify → 3.Tier → 4.Decompose → 5.Plan     │
│  6.Delegate → 7.Monitor → 8.Retry (loop) → 9.Synthesize    │
│  10.Review → 11.Publish [Tier 2 only] → 12.Log             │
└──────┬───────────────┬──────────────┬──────────────┬────────┘
       │               │              │              │
       ▼               ▼              ▼              ▼
 Researcher         Coder          Analyst        Writer
(OVR_RES_02)   (OVR_COD_03)   (OVR_ANL_04)  (OVR_WRT_05)
       │               │              │              │
       └───────────────┴──────────────┴──────┬───────┘
                                             │
                                    Reviewer (OVR_REV_06)
                                    Publisher (OVR_PUB_07)
                                    Cleanup (OVR_CLN_08)
                                    ┌────────┴────────┐
                                    │  Tier 1: .md    │
                                    │  Tier 2: .html  │
                                    └─────────────────┘
```

**Engine layer** (`engine/`): pure Python, stdlib-only. Handles the agent loop, provider calls (streaming + non-streaming), parallel tool execution, tool result caching, rate-limit auto-retry, and session logging.

**Backend** (`backend/`): FastAPI server wrapping the engine. Serves the WebUI, exposes REST + SSE APIs, enforces auth.

**Frontend** (`frontend/`): single-file SPA served by the backend. No build step required.

---

## Quick Start

### WebUI (recommended)

#### 1. Clone

```bash
git clone https://github.com/A13Xg/Overlord11.git
cd Overlord11
```

#### 2. Install WebUI dependencies

```bash
pip install -r requirements-webui.txt
```

#### 3. Start the server

```bash
python scripts/run_webui.py
# Opens on http://localhost:7900
```

#### 4. First-run setup wizard

On first load the setup wizard guides you through:
- Entering your API key(s) for Anthropic / Gemini / OpenAI
- Selecting the active provider and default model
- Keys are saved to `.env` and loaded on every subsequent start automatically

#### 5. Create a job

Click **+ NEW JOB**, enter a title and prompt, and hit **START**. Watch the agent execution tree in real time.

> Default login: **admin / overlord11** — change in `backend/auth/users.json`

---

### CLI Mode

No server required — runs the engine directly in your terminal.

#### 1. Set API key

```bash
# Copy and fill in your key(s)
cp .env.example .env
# Edit .env: ANTHROPIC_API_KEY=sk-ant-...
```

#### 2. Run

```bash
python run_engine.py
```

The interactive menu lets you start new sessions, resume existing ones, and switch providers/models.

---

## Directory Structure

```
Overlord11/
├── agents/                  # 8 agent definitions (system prompts)
│   ├── orchestrator.md      # OVR_DIR_01 — master coordinator
│   ├── researcher.md        # OVR_RES_02 — web & local research
│   ├── coder.md             # OVR_COD_03 — code generation & debugging
│   ├── analyst.md           # OVR_ANL_04 — data analysis & summarization
│   ├── writer.md            # OVR_WRT_05 — Markdown output (Tier 1)
│   ├── reviewer.md          # OVR_REV_06 — QA, review & validation
│   ├── publisher.md         # OVR_PUB_07 — styled HTML reports (Tier 2)
│   └── cleanup.md           # OVR_CLN_08 — pre-deployment sanity check
│
├── engine/                  # Core execution engine (stdlib-only)
│   ├── runner.py            # EngineRunner — main agent loop
│   ├── orchestrator_bridge.py  # LLM provider calls (stream + non-stream)
│   ├── tool_executor.py     # Tool call parsing + Python/subprocess execution
│   ├── parallel_executor.py # Wave-based parallel tool scheduling
│   ├── dependency_analyzer.py  # Conflict detection for parallelism
│   ├── session_manager.py   # Session lifecycle + workspace management
│   ├── event_stream.py      # Typed event emission with thread-safe callbacks
│   ├── tool_cache.py        # SHA-256 LRU tool result cache
│   ├── rate_limit.py        # 429 exception hierarchy + Retry-After parsing
│   └── self_healing.py      # Error classification + retry report injection
│
├── backend/                 # FastAPI server
│   ├── main.py              # App entry point, lifespan, .env loader
│   ├── api/
│   │   ├── jobs.py          # Job CRUD + start/stop/pause/resume/restart
│   │   ├── artifacts.py     # Artifact listing, serving, screenshot, zip
│   │   ├── events.py        # SSE endpoints (per-job and global)
│   │   ├── auth.py          # Login/logout/verify endpoints
│   │   ├── health.py        # Provider health checks (cached 5 min)
│   │   ├── providers.py     # Provider + model management
│   │   ├── setup.py         # First-run setup wizard API
│   │   └── templates.py     # Job templates API
│   ├── core/
│   │   ├── engine_bridge.py # Async worker pool + job execution + dep gating
│   │   ├── session_store.py # In-memory + file-persisted job store
│   │   └── event_stream.py  # SSE broadcaster with heartbeat
│   └── auth/
│       ├── auth.py          # AuthManager + require_auth FastAPI dependency
│       └── users.json       # User table (username, salt, sha256 hash, role)
│
├── frontend/
│   ├── index.html           # Single-file SPA (no build step)
│   └── login.html           # Login page
│
├── tools/
│   ├── defs/                # 43 provider-agnostic tool JSON schemas
│   └── python/              # Python implementations of all tools
│
├── skills/
│   └── uiux/                # UI/UX design system datasets
│       ├── styles.json      # 10 curated UI styles
│       └── palettes.json    # 10 color palettes with semantic tokens
│
├── docs/                    # Full wiki documentation
│
├── directives/              # Behavioral instruction files for AI sessions
│
├── tests/
│   ├── test.py              # Test suite covering all tool modules
│   └── test_results.json    # Machine-readable results (auto-generated)
│
├── scripts/
│   └── run_webui.py         # WebUI launcher (port 7900)
│
├── run_engine.py            # CLI entry point (interactive menu)
├── config.json              # Unified config (providers, agents, tools)
├── Consciousness.md         # Shared cross-agent memory
├── ONBOARDING.md            # Universal LLM onboarding guide
├── requirements-webui.txt   # FastAPI + uvicorn + python-multipart + playwright
├── requirements-engine.txt  # Stdlib-only; optional extras documented
└── .env.example             # Environment variable template
```

---

## Agents

| ID | Agent | Role |
|----|-------|------|
| OVR_DIR_01 | **Orchestrator** | Master coordinator. Receives all requests, assesses output tier, decomposes tasks, delegates to specialists, and synthesizes final output. Always the entry point. |
| OVR_RES_02 | **Researcher** | Gathers information from the web and local files. Fetches pages, extracts content, cross-references sources, and structures findings for downstream agents. |
| OVR_COD_03 | **Coder** | Writes, debugs, tests, and refactors code. Works in any language. Runs static analysis and tests before handoff. |
| OVR_ANL_04 | **Analyst** | Analyzes data, identifies patterns, computes metrics, and produces structured summaries with actionable recommendations. |
| OVR_WRT_05 | **Writer** | Produces all Markdown output: READMEs, reports, docs, changelogs, and technical specs. Used for Tier 1 output. |
| OVR_REV_06 | **Reviewer** | Final quality gate. Reviews code and documents for correctness, security, style, and completeness before delivery. |
| OVR_PUB_07 | **Publisher** | Generates fully self-contained styled HTML reports (Tier 2). Chooses a visual theme based on content type and produces a single `.html` file with all CSS inline. |
| OVR_CLN_08 | **Cleanup** | Pre-deployment sanity check. Scans for hardcoded secrets, removes temp files, validates project structure before delivery. |

> Full agent documentation: [`docs/Agents-Reference.md`](docs/Agents-Reference.md)

---

## Tools

### File System
| Tool | Description |
|------|-------------|
| `read_file` | Read any file's contents, with optional line range |
| `write_file` | Write or append content to a file (auto-creates directories) |
| `list_directory` | List directory contents with metadata |
| `glob` | Find files by pattern (`**/*.py`, `src/**/*.ts`) |
| `search_file_content` | Ripgrep-powered content search with regex support; pure-Python fallback |
| `replace` | Precise find-and-replace within files |
| `diff_tool` | Unified diff between two files or strings |

### Execution
| Tool | Description |
|------|-------------|
| `run_shell_command` | Execute shell commands, run tests, install packages |
| `execute_python` | Sandboxed Python code execution with AST-based safety checks |
| `git_tool` | Git operations: status, diff, commit, push, branch |
| `calculator` | Math expressions: arithmetic, trig, logarithms, sqrt, power |
| `scaffold_generator` | Generate project scaffolding from templates |
| `launcher_generator` | Generate `run.py` + `run.bat` + `run.command` for Python projects |

### Web
| Tool | Description |
|------|-------------|
| `web_fetch` | HTTP GET with HTML-to-Markdown conversion |
| `web_scraper` | Advanced article extraction, RSS/Atom discovery, DuckDuckGo search |
| `http_request` | Raw HTTP requests (GET/POST/PUT/DELETE) with full header control |

### Analysis & Memory
| Tool | Description |
|------|-------------|
| `code_analyzer` | Static analysis: function detection, cyclomatic complexity, code smells |
| `project_scanner` | Codebase structure, language detection, entry points, git metadata |
| `save_memory` | Persist facts to `Consciousness.md` with timestamps across sessions |
| `consciousness_tool` | Read, query, and manage entries in `Consciousness.md` programmatically |
| `publisher_tool` | Generate themed self-contained HTML reports (9 visual themes) |
| `ui_design_system` | Generate a complete UI/UX design system (10 styles × 10 palettes) |
| `response_formatter` | Format agent responses into structured output (sections, tables) |
| `file_converter` | Convert files between formats (JSON, CSV, YAML, Markdown) |
| `data_visualizer` | Generate charts and visual data summaries |

### Data & Utilities
| Tool | Description |
|------|-------------|
| `json_tool` | JSON query, transform, validate, and format |
| `regex_tool` | Regex match, extract, replace operations |
| `hash_tool` | Compute file/string hashes (MD5, SHA-256, SHA-512) |
| `zip_tool` | Create, extract, and inspect ZIP archives |
| `env_tool` | Read and write environment variables |
| `datetime_tool` | Date/time formatting, arithmetic, timezone conversion |
| `database_tool` | SQLite query execution and schema inspection |

### Project Management
| Tool | Description |
|------|-------------|
| `task_manager` | Manage `TaskingLog.md` — create, update, and track tasks with T-NNN IDs |
| `error_logger` | Log errors to `ErrorLog.md` with severity, attempts, and resolution tracking |
| `project_docs_init` | Initialize the 5 standardized project files |
| `cleanup_tool` | Pre-deployment scan: detect secrets, remove temp files, validate structure |
| `session_manager` | Session lifecycle management and workspace operations |
| `session_clean` | Clean up old session workspaces and temporary files |
| `log_manager` | Structured JSON logging to `logs/master.jsonl` |

### Automation & Vision
| Tool | Description |
|------|-------------|
| `notification_tool` | Push browser toast notifications to the WebUI operator |
| `error_handler` | Catch, classify, and recover from tool execution errors |
| `computer_control` | Desktop automation: mouse, keyboard, window management, screenshots |
| `vision_tool` | Image analysis: OCR, object detection, screenshot interpretation |

> Full tool documentation: [`docs/Tools-Reference.md`](docs/Tools-Reference.md)

---

## Output Tiers

The Orchestrator automatically determines the right output format:

| Tier | Condition | Output |
|------|-----------|--------|
| **0** | Simple Q&A, one-liners | Inline text — no file |
| **1** | Moderate complexity: docs, guides, summaries | Markdown `.md` via Writer |
| **2** | Detailed reports, infographics, dashboards | Self-contained HTML `.html` via Publisher |

### Publisher HTML Themes

| Theme | Best For |
|-------|----------|
| `techno` | Code, engineering, APIs, DevOps |
| `classic` | Business, finance, executive reports |
| `informative` | Research, academia, data science |
| `contemporary` | Health, science, environment |
| `abstract` | Arts, creative, culture |
| `modern` | Startups, product, marketing |
| `colorful` | Education, children's content |
| `tactical` | Security, defense, risk |
| `editorial` | Journalism, history, narrative |

> Full output tier documentation: [`docs/Output-Tiers.md`](docs/Output-Tiers.md)

---

## Provider Configuration

Switch providers by changing `providers.active` in `config.json`:

```json
{
  "providers": {
    "active": "gemini",
    "anthropic": {
      "model": "claude-opus-4-5",
      "api_key_env": "ANTHROPIC_API_KEY"
    },
    "gemini": {
      "model": "gemini-2.5-pro",
      "api_key_env": "GOOGLE_GEMINI_API_KEY"
    },
    "openai": {
      "model": "gpt-4o",
      "api_key_env": "OPENAI_API_KEY"
    }
  }
}
```

Each provider also supports an `available_models` map for automatic per-model fallback — if the primary model is rate limited, the engine tries the next model before moving to the next provider.

> Full provider guide: [`docs/Providers.md`](docs/Providers.md)

---

## Rate Limiting

When all configured providers return HTTP 429, the engine applies one of three configurable actions:

| Action | Behaviour |
|--------|-----------|
| `pause` *(default)* | Exponential backoff starting at 5 min, doubling on each hit, capped at 8 hours. Adds ±20% jitter to prevent thundering-herd. |
| `stop` | Fail the job immediately with a `rate_limited` status. |
| `try_different_model` | Wait only as long as the shortest Retry-After header, then retry. |

Configure the default in `config.json`:

```json
"orchestration": {
  "rate_limit": {
    "action": "pause",
    "initial_wait_s": 300,
    "max_wait_s": 28800
  }
}
```

Or set a per-job override in the **New Job** modal in the WebUI. A live countdown banner appears in the job list while a job is waiting.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | If using Anthropic | Claude API key from [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| `GOOGLE_GEMINI_API_KEY` | If using Gemini | Gemini API key from [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| `OPENAI_API_KEY` | If using OpenAI | OpenAI API key from [platform.openai.com](https://platform.openai.com/api-keys) |
| `PORT` | No (default 7900) | WebUI server port |
| `OVERLORD11_AUTH_DISABLED` | No | Set to `1` to bypass authentication (dev/local use only) |
| `OVERLORD11_SESSION_TTL` | No (default 28800) | Session token TTL in seconds (8 hours default) |
| `NO_COLOR` | No | Set to `1` to disable ANSI colour output |

Keys written via the setup wizard are saved to `.env` and loaded automatically on every start.

---

## Testing

The test suite covers all **43 tool modules** — encoding edge-cases (UTF-8, CJK, emoji), ripgrep/Python-fallback compatibility, live web calls, and all 9 publisher themes.

```bash
# Skip internet-dependent tests (fast, <5s)
python tests/test.py --skip-web

# Full suite (includes live web calls)
python tests/test.py

# Single tool
python tests/test.py --tool calculator

# Summary only — ideal for CI
python tests/test.py --quiet --no-color

# Stop on first failure
python tests/test.py --fail-fast
```

---

## Extension Guide

### Add a new agent

1. Create `agents/my_agent.md` following the template in existing agent files
2. Add an entry to `agents` in `config.json` with a unique ID (`OVR_NEW_09`)
3. List the tools the agent needs in its `tools` array
4. Update the Orchestrator's `can_delegate_to` list

### Add a new tool

1. Create `tools/defs/my_tool.json` with the JSON Schema definition
2. Implement `tools/python/my_tool.py` with a `main(**kwargs)` function
3. Add an entry to `tools` in `config.json`
4. Reference the tool in any agent definitions that need it

### Add a new provider

1. Add a new entry under `providers` in `config.json` with `model`, `api_key_env`, `api_base`, `max_tokens`, `temperature`
2. Implement the provider dispatch in `engine/orchestrator_bridge.py` (`_call_<provider>`, `_call_<provider>_streaming`)
3. Add the API key variable to `.env.example`

> Full extension guide: [`docs/Extension-Guide.md`](docs/Extension-Guide.md)

---

## Memory System

`Consciousness.md` is the shared memory for all agents. Agents write findings, decisions, and work-in-progress entries here using the `save_memory` tool. Supports:

- **Cross-session continuity** — facts persist between runs
- **Cross-agent communication** — one agent's output becomes another's input
- **Work deduplication** — agents check WIP entries before starting tasks
- **Error broadcasting** — critical errors visible to all agents

> Full memory system guide: [`docs/Memory-System.md`](docs/Memory-System.md)

---

## Wiki

Complete documentation is available in the [`docs/`](docs/) directory:

| Document | Description |
|----------|-------------|
| [Home](docs/Home.md) | Overview, index, and quick navigation |
| [Getting Started](docs/Getting-Started.md) | Installation, setup, and first run |
| [Architecture](docs/Architecture.md) | System design, data flow, and component interactions |
| [Agents Reference](docs/Agents-Reference.md) | All 8 agents — identities, workflows, and quality checklists |
| [Tools Reference](docs/Tools-Reference.md) | All 43 tools — parameters, examples, and return values |
| [Configuration Reference](docs/Configuration-Reference.md) | Complete `config.json` field reference |
| [Providers](docs/Providers.md) | LLM provider guide: models, switching, rate limiting, and fallbacks |
| [Memory System](docs/Memory-System.md) | `Consciousness.md` format, rules, and best practices |
| [Output Tiers](docs/Output-Tiers.md) | Tier 0/1/2 decision logic and all 9 HTML themes |
| [Extension Guide](docs/Extension-Guide.md) | Adding agents, tools, and providers |
| [Development](docs/Development.md) | Contributing, testing, and dev setup |
| [Troubleshooting](docs/Troubleshooting.md) | FAQ and common error fixes |
| [UI/UX Design System](docs/UI-UX-Design-System.md) | Design system skill: styles, palettes, usage |
