# Changelog

All notable changes to Overlord11 are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [3.0.0] — 2026-04-04

### Added — Internal Execution Engine (`engine/`)

- `engine/runner.py` — Main agent execution loop with tool detection and dispatch
- `engine/orchestrator_bridge.py` — Provider adapter (Anthropic, Gemini, OpenAI) with fallback chain
- `engine/tool_executor.py` — Parse tool calls from agent output (JSON fenced, XML tag, Anthropic format); dynamic tool loader
- `engine/session_manager.py` — Session lifecycle management (queued → running → completed/failed)
- `engine/event_stream.py` — Async event bus emitting typed events (`agent_start`, `tool_call`, `tool_result`, `log`, `complete`, `error`, `healing`)
- `engine/self_healing.py` — Error classification, retry with backoff, remediation message injection

### Added — Self-Healing System

- Error classification: `tool_error`, `api_error`, `parse_error`, `runtime_error`, `loop_limit`
- Exponential backoff retry (configurable max_retries, retry_delay)
- Remediation context injected back into agent conversation loop

### Added — Python Execution Tool

- `tools/python/execute_python.py` — Execute arbitrary Python in subprocess sandbox (timeout, env, working_dir)
- `tools/defs/execute_python.json` — Tool definition registered in config.json

### Added — Backend API (`backend/`)

- `backend/main.py` — FastAPI application (port 8080), CORS, static frontend serving
- `backend/core/session_store.py` — Thread-safe job registry with disk persistence
- `backend/core/engine_bridge.py` — Async bridge from FastAPI to engine runner
- `backend/core/event_stream.py` — SSE/WebSocket event bus (`BackendEventBus`)
- `backend/api/jobs.py` — Full job CRUD + state transitions + bulk controls (start all / pause all / stop all)
- `backend/api/events.py` — SSE (`/api/events/{session_id}`) + WebSocket (`/ws/{session_id}`)
- `backend/api/models_api.py` — Model listing, provider status (green/red), config read/write
- `backend/api/artifacts.py` — Artifact listing, download, delete with path-injection protection
- `requirements-backend.txt` — FastAPI, uvicorn, pydantic, websockets, provider SDKs
- `scripts/run_backend.py` — Backend launch script with auto-install

### Added — Frontend WebUI (`frontend/`)

- Next.js 15 + TypeScript + Tailwind CSS
- Ultra-modern retro military / cold-war control panel theme (phosphor green, radar animations, waveform)
- **Top Bar** — branding, provider status indicators (green/red), global controls
- **Job Queue** — left panel with per-job controls (start/pause/resume/stop/restart/delete)
- **Main View** — tabbed: Execution | Artifacts | Product
- **Event Feed** — real-time SSE event stream with typed color coding
- **System Log** — collapsible bottom panel with auto-scroll
- **New Job Modal** — task, agent, provider selection
- **File Preview Modal** — text/image rendering, download option
- `src/lib/api.ts` — Full API client
- `src/hooks/useJobs.ts` — Job list with polling
- `src/hooks/useEvents.ts` — SSE subscription hook

### Added — Tests

- `tests/test_engine.py` — 35 unit tests covering EventStream, SessionManager, ToolExecutor, SelfHealingSystem, execute_python

### Changed

- `config.json` version bumped to 3.0.0
- `config.json` description updated
- `config.json` `execute_python` tool registered
- `config.json` new `engine` section with port/retry/store config

---

## [2.2.0] — 2026-03-22


### Added — Cleanup Agent (OVR_CLN_08)

- `agents/cleanup.md` — Pre-deployment sanity check agent
- Scans for hardcoded secrets, removes temp files, validates project structure
- Added to Orchestrator's `can_delegate_to` list in `config.json`

### Added — Project Management Tools

- `cleanup_tool` — secrets scan, temp cleanup, structure validation (`tools/defs/cleanup_tool.json` + `tools/python/cleanup_tool.py`)
- `task_manager` — manage `TaskingLog.md` with T-NNN IDs and subtasks
- `error_logger` — log errors to `ErrorLog.md` with severity and resolution tracking
- `project_docs_init` — initialize 5 standardized project files (ProjectOverview, Settings, TaskingLog, AInotes, ErrorLog)
- `launcher_generator` — generate `run.py` (ASCII title, color menu, concurrent mode) + `run.bat` + `run.command`
- `replace` tool now has a Python implementation (`tools/python/replace_tool.py`)
- `scaffold_generator` now has a JSON schema definition

### Added — Utility Tools (registered in config.json)

- `consciousness_tool` — programmatic read/query/manage of `Consciousness.md`
- `error_handler` — catch, classify, and recover from tool execution errors
- `response_formatter` — format agent responses into structured output
- `file_converter` — convert files between JSON, CSV, YAML, and Markdown
- `computer_control` — desktop automation (mouse, keyboard, screenshots)
- `vision_tool` — image analysis, OCR, screenshot interpretation

### Added — Behavioral Directives (`directives/`)

- `Personality.md` — tone, voice, 5 personality types (ChildFriendly, Assistant, Cautious, Quick, Mentor)
- `CustomBehavior.md` — decision-making, autonomy, transparency mode, contradiction resolution
- `OutputFormat.md` — 5-section standard response structure, verbosity rules
- `CodingBehavior.md` — CheckMode/GoMode, `.ai/` context directory, implementation cycle, testing
- `WritingBehavior.md` — writing rules, document templates, revision cycles
- `GeneralBehavior.md` — research, analysis, multi-part requests, when to push back
- `README.md` — directive layering guide and quick-start combos

### Added — Standardized Project Files

- Every sandboxed project directory gets 5 files via `project_docs_init`: `ProjectOverview.md`, `Settings.md`, `TaskingLog.md`, `AInotes.md`, `ErrorLog.md`

### Added — Launcher System

- Every Python project gets `run.py`, `run.bat`, `run.command` via `launcher_generator`
- Scaffold templates include basic launchers; `launcher_generator` creates full-featured ones

### Added — UI/UX Design System Skill

A native Overlord11 UI/UX design system skill that gives agents a consistent,
reusable visual specification before any UI implementation begins.

#### Datasets (`skills/uiux/`)
- `skills/uiux/styles.json` — 10 vastly different UI styles with full layout,
  typography, shape, interaction, and Do/Don't guidance:
  `brutalist`, `glassmorphism`, `neobrutalism`, `editorial`, `minimal-zen`,
  `data-dense`, `soft-ui`, `retro-terminal`, `biomimetic`, `aurora-gradient`
- `skills/uiux/palettes.json` — 10 color palettes (light + dark modes) with
  14 semantic token hex values each and WCAG contrast notes:
  `midnight-ink`, `chalk-board`, `neon-city`, `nordic-frost`, `terracotta-sun`,
  `deep-forest`, `sakura-bloom`, `volcanic-night`, `arctic-monochrome`, `ultraviolet`

#### New Tool (`ui_design_system`)
- `tools/defs/ui_design_system.json` — provider-agnostic tool schema
- `tools/python/ui_design_system.py` — Python implementation
- Accepts: `style_id`, `palette_id`, `stack` (html-tailwind/html-css/react/nextjs/vue/svelte),
  `page`, `project_name`, `output_format` (md/json), `persist` (bool)
- Outputs: complete design spec (tokens, layout rules, typography, shapes, motion, Do/Don't,
  stack implementation code, Reviewer checklist)
- When `persist=true`: writes `design-system/MASTER.md` and optional per-page override
- Deterministic default selection: same project name always produces the same style+palette
- Style-palette affinity tables guide sensible default pairings

#### Agent Updates
- **Orchestrator** (`agents/orchestrator.md`): Added "UI/UX Feature Request" delegation
  pattern; Coder is instructed to generate/consult design system before UI work
- **Coder** (`agents/coder.md`): Added step 3 "UI/UX Check" — read `design-system/MASTER.md`
  or call `ui_design_system` with `persist=true` if missing; added UI token compliance to
  quality checklist; `ui_design_system` added to tool list
- **Reviewer** (`agents/reviewer.md`): Added "UI Design System Audit" workflow step;
  added full "UI Design System Checklist" section; added `ui_design_system` to tool list

#### Config Updates
- `config.json`: `ui_design_system` registered in `tools` section; added to Coder and
  Reviewer agent tool lists

#### Documentation
- `docs/UI-UX-Design-System.md` — comprehensive documentation: what the skill is,
  dataset structure, tool reference, CLI usage, persist/reuse patterns, style+palette
  combination guide, extending the skill, and troubleshooting
- `ONBOARDING.md`: Added "UI/UX Design System Skill" section with quick-start CLI
  examples and tool reference; added `ui_design_system` to tool table; added rule 15
  ("Use the design system for UI"); updated delegation patterns
- `README.md`: Added `🎨 UI/UX design system skill` feature bullet; updated tool count
  badge to 16; added `skills/uiux/` to directory structure; added `ui_design_system`
  to Analysis & Memory tools table; added `docs/UI-UX-Design-System.md` to docs listing

#### Tests
- `tests/test.py`: Added `test_ui_design_system` function with 6 tests covering:
  Markdown output, JSON output, default selection, persist to disk, invalid IDs,
  and error handling for missing data

---

### Added — Test Suite (`tests/test.py`)

A comprehensive test suite for all 16 Overlord11 modules was built and
hardened across multiple iterations. It is designed to be usable directly
by LLM agents as well as humans.

#### Coverage
- **81 tests** across 28 modules: read_file, write_file, list_directory,
  glob, search_file_content, run_shell_command, web_fetch, web_scraper,
  git_tool, calculator, save_memory, code_analyzer, project_scanner,
  publisher_tool, log_manager, session_manager
- Encoding edge-cases: UTF-8, CJK (Chinese/Japanese/Korean), emoji, empty
  files — all verified via roundtrip write/read
- Ripgrep + pure-Python fallback compatibility: JSON output format
  differences (`"type":"match"` vs `"type": "match"`) handled in all tests
- Web scraper tests call the actual `act_*` API (`act_validate_url`,
  `act_search`, `act_detect_type`, `act_extract_text`, `act_analyze_structure`,
  `act_find_feeds`) — no more SKIP returns

#### CLI flags
| Flag | Description |
|------|-------------|
| `--skip-web` | Skip internet-dependent tests |
| `--tool X[,Y,Z]` | Run one or more tools (comma-separated) |
| `--quiet` / `-q` | Summary + failures only — LLM/CI friendly |
| `--no-color` | Strip all ANSI codes; auto-applied when stdout is not a TTY |
| `--output PATH` | Write JSON results to a custom path |
| `--list` | Print available tool names and exit |
| `--fail-fast` | Abort on first failure |

#### Machine-readable JSON output (`tests/test_results.json`)
Every run emits a JSON file with a full `environment` block:
```json
{
  "environment": {
    "python_version": "3.x",
    "platform": "win32 | linux | darwin",
    "ripgrep": true,
    "packages": { "bs4": true, "requests": true, "ddgs": true, ... }
  }
}
```

#### `NO_COLOR` environment variable
Honoured at process startup (POSIX standard). Equivalent to `--no-color`.

### Fixed — `tools/python/search_file_content.py`
- Added `_find_rg()` — probes `rg` on `PATH` then common Windows install
  paths (Scoop, WinGet, Chocolatey, Cargo) before giving up
- Added `_python_search()` — pure-Python regex fallback producing
  ripgrep-compatible JSON-lines (`{"type":"begin",...}` / `{"type":"match",...}` /
  `{"type":"summary",...}`)
- `_RG_BIN` module-level cache — binary discovery happens once at import,
  not per call

### Fixed — `tools/python/publisher_tool.py`
- `log_tool_invocation(tool=...)` → `log_tool_invocation(tool_name=...)`
  (wrong keyword argument caused every publisher call to log an exception)
- `log_error(tool=...)` → `log_error(source=...)` (same root cause)

### Fixed — Windows console encoding (`tests/test.py`)
- Wrap `sys.stdout` / `sys.stderr` in `io.TextIOWrapper(..., encoding="utf-8")`
  at startup on `win32` to avoid `UnicodeEncodeError` on cp1252 consoles
- `safe_str()` helper encodes all output values through
  `encode("ascii", errors="backslashreplace")` as a final fallback

---

## [2.1.0] — README & Wiki Overhaul

### Added
- 12-page Wiki in `docs/`: Home, Getting Started, Architecture, Agents
  Reference, Tools Reference, Configuration Reference, Providers, Memory
  System, Output Tiers, Extension Guide, Development, Troubleshooting
- Publisher agent (`OVR_PUB_07`) — generates fully self-contained styled
  HTML reports with inline CSS and 9 visual themes
- Web scraper: LLM analysis action, smart image scoring, RSS/Atom feed
  discovery, DuckDuckGo search via `ddgs`
### Changed
- README completely rewritten: architecture diagram, full tool tables,
  output-tier guide, provider switching reference
- Branding unified: "AgenticToolset" → "Overlord11" throughout all files

### Fixed
- `write_file.py`: `mode` parameter (`overwrite`/`append`) and `encoding`
  parameters now correctly implemented from JSON schema

---

## [2.0.0] — Provider-Agnostic Restructure

### Changed
- Restructured from scattered subsystems into a unified, provider-agnostic
  LLM toolset
- All agent definitions and tool schemas made provider-neutral
- `config.json` unified configuration: providers, agents, tools
- Fallback provider order configurable via `orchestration.fallback_provider_order`

### Added
- Provider support: Anthropic Claude, Google Gemini, OpenAI GPT
- 7 specialist agents with unique IDs (`OVR_DIR_01` … `OVR_PUB_07`)
- 15 tool implementations in `tools/python/`
- 15 provider-agnostic tool JSON schemas in `tools/defs/`
- `Consciousness.md` shared memory system
- `ONBOARDING.md` universal LLM onboarding guide
- `.env.example` environment variable template

---

## [1.x] — Early Development

### Added
- Gemini multi-bot support
- Sandboxing infrastructure
- AgenticToolset initial toolkit with agents and tools (`web_researcher`,
  later renamed `web_scraper`)
- Linux hardening guide (later removed from repo)
- Requirements file
- Initial agent configurations

---

*For the full commit history see `git log --oneline`.*
