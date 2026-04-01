# Changelog

All notable changes to Overlord11 are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [2.3.1] — 2026-04-01

### Added — Tool Registrations

- `tools/defs/session_manager.json` — provider-agnostic JSON schema for `session_manager.py` (previously orphaned)
- `tools/defs/log_manager.json` — provider-agnostic JSON schema for `log_manager.py` (previously orphaned)
- Both tools registered in `config.json` tools section; now agent-callable
- `response_formatter` added to Publisher agent's tool list in `config.json` (was documented in `agents/publisher.md` but missing from config)

### Added — UI/UX Premium Themes

- `publisher_tool.py`: Three premium HTML themes added — `ultraviolet` (deep purple AI aesthetic), `aurora` (dark gradient dashboard), `neobrutalism` (bold offset shadow)
- Premium themes receive 2× keyword weight in auto-detection; default no-match fallback changed from `modern` → `aurora`
- "CLASSIFIED" tag removed from tactical theme — now "INTEL"
- `tools/defs/publisher_tool.json`: Updated `theme` enum to include `ultraviolet`, `aurora`, `neobrutalism`
- `ui_design_system.py`: Style pool split into `_PREMIUM_STYLE_IDS` (aurora-gradient, glassmorphism, ultraviolet, neobrutalism, biomimetic), `_STANDARD_STYLE_IDS`, `_BASIC_STYLE_IDS`; `_default_style()` now draws exclusively from premium pool

### Added — WebUI: Provider Health, Model Picker, Gemini Fallback

- `webui/provider_health.py` — async health probes for Gemini/OpenAI/Anthropic at startup; TTL-cached (5 min); Gemini `429 RESOURCE_EXHAUSTED` detection with `retryDelay` extraction
- `webui/logging_config.py` — two rotating JSONL loggers: `logs/webui.jsonl` (HTTP, config, health) and `logs/agents.jsonl` (agent/tool work)
- Gemini progressive fallback chain: `gemini-2.5-pro → gemini-2.5-flash → gemini-2.5-flash-lite → gemini-2.0-flash → gemini-1.5-flash → gemini-1.5-pro`
- New API endpoints: `POST /api/jobs`, `GET/PUT/DELETE /api/config/selection`, `GET /api/providers/status?force=`, `GET /api/providers/gemini/fallback`
- WebUI header: 2-row layout with clickable provider pills, model picker panel, active model badge, activity log

### Changed — Fallback Order (corrected)

- `orchestration.fallback_provider_order` corrected from `["gemini", "anthropic", "openai"]` to `["gemini", "openai", "anthropic"]`
- All documentation updated to reflect Gemini → OpenAI → Anthropic order

### Changed — Agent Documentation

- `agents/researcher.md`: Added explicit `save_memory` tool documentation (was in config.json but undocumented in .md)
- `agents/analyst.md`: Added explicit `save_memory` tool documentation
- `agents/writer.md`: Added `glob` and `list_directory` tool documentation
- `agents/publisher.md`: Updated theme table to include premium themes; clarified `response_formatter` usage; removed "CLASSIFIED" language
- `agents/coder.md`: Strengthened UI/UX mandate — all providers must call `ui_design_system(persist=True)` before any UI work
- `agents/orchestrator.md`: Updated UI/UX routing with premium style requirement; updated reviewer checklist

### Changed — Documentation

- `ONBOARDING.md`: Updated v2.2.0 → v2.3.1; added WebUI section, `.env` row, updated tool tables (added session_manager, log_manager, consciousness_tool, error_handler, response_formatter, file_converter, vision_tool, computer_control); updated logging section with dual-log structure; added UI/UX premium pool description; added rule 19 (logging protocol); fixed fallback order
- `README.md`: Updated version badge (2.2.0 → 2.3.1), tests badge, tool count badge (28 → 30); updated features list; corrected provider order badge and active provider; added WebUI step to Quick Start; updated directory structure
- `docs/Providers.md`: Corrected fallback order from `anthropic→gemini→openai` to `gemini→openai→anthropic`; added Gemini rate-limit fallback section
- `docs/WebUI.md`: Added new API endpoints table; updated Settings Panel section with model picker docs; added Logs section
- `docs/Tools-Reference.md`: Added `tools/defs/` schema references to session_manager and log_manager entries; updated publisher_tool with premium themes; updated ui_design_system with premium/standard/basic tier table
- `docs/Agents-Reference.md`: Updated Publisher tools list to include `response_formatter`; updated Publisher theme table with premium themes
- `directives/CodingBehavior.md`: Added "UI/UX Design System — Mandatory Rules" section covering design-system check, premium style requirement, publisher_tool theme priority, and verbose-UI guidelines
- `config.json`: Version bumped to 2.3.1; added `ui_defaults` section (premium styles, no-generic-html policy); added `session_manager` and `log_manager` to tools section; added `response_formatter` to publisher agent tools

### Fixed

- `tests/test_webui.py`: Removed duplicate test functions (lines 411+); fixed stray `r.status_code` reference in `test_gemini_fallback_logic`; fixed `test_config_no_api_keys` to allow `api_key_env` (env var name is intentionally exposed — actual key value is not)

---

## [2.3.0] — 2026-06-15

### Added — Tactical WebUI

- `webui/` Python package — FastAPI backend for read-only job browsing
  - `webui/app.py` — FastAPI application with CORS, static file serving, and all API endpoints
  - `webui/models.py` — Pydantic models: `JobSummary`, `JobDetail`, `ArtifactInfo`, `ConfigInfo`, etc.
  - `webui/state_store.py` — reads `workspace/jobs/*/state.json` and `events.jsonl`; lists and serves artifacts with path-traversal protection
- `webui/static/index.html` — self-contained SPA (Vanilla JS + Tailwind CDN + Marked.js CDN)
  - Dark tactical aesthetic (GitHub dark palette — `#0d1117` bg, `#58a6ff` blue, `#3fb950` green)
  - Sidebar: job list with status dots, filters (All/Running/Done/Failed), search
  - Main panel: Overview / Events / Artifacts / ⭐ Finished Products tabs
  - Inline Markdown preview for `.md` artifacts
  - Auto-refresh: jobs list every 5 s, active running job detail every 3 s
  - Settings panel: provider/model dropdowns populated from `/api/config`
- `scripts/run_webui.py` — convenience launcher (`python scripts/run_webui.py`)
- `requirements-webui.txt` — FastAPI, uvicorn, pydantic ≥ 2, python-multipart
- `docs/WebUI.md` — comprehensive WebUI documentation
- `workspace/jobs/.gitkeep` — ensures jobs directory exists in the repo
- `tests/test_webui.py` — pytest suite for WebUI API (health, jobs CRUD, config, artifacts, path traversal)

### Changed — Provider Configuration

- `providers.active` switched from `"anthropic"` to `"gemini"`
- `providers.gemini.model` updated to `"gemini-3.1-flash-lite-preview"`
- `providers.gemini.available_models` expanded with Gemini 3.1 models:
  - `gemini-3.1-flash-lite-preview` (new default)
  - `gemini-3.1-flash-preview`
  - `gemini-3.1-pro-preview`
- `orchestration.fallback_provider_order` reordered to `["gemini", "anthropic", "openai"]`
- `docs/Providers.md` updated with Gemini 3.1 model table entries

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
