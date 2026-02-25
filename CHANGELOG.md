# Changelog

All notable changes to Overlord11 are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added — Test Suite (`tests/test.py`)

A comprehensive test suite for all 16 Overlord11 modules was built and
hardened across multiple iterations. It is designed to be usable directly
by LLM agents as well as humans.

#### Coverage
- **81 tests** across 16 modules: read_file, write_file, list_directory,
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
- `pre_commit_clean.py` — pre-commit hook runner + test gate

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
