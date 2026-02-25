# Overlord11

> **Provider-agnostic multi-agent LLM orchestration framework**

[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-3776ab?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-2.1.0-22c55e)](config.json)
[![Tests](https://img.shields.io/badge/tests-81%20passing-22c55e?logo=pytest&logoColor=white)](tests/test.py)
[![Tools](https://img.shields.io/badge/tools-15%20built--in-6366f1)](tools/python/)
[![Agents](https://img.shields.io/badge/agents-7%20specialists-f59e0b)](agents/)
[![Providers](https://img.shields.io/badge/providers-Anthropic%20%7C%20Gemini%20%7C%20OpenAI-0ea5e9)](docs/Providers.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-64748b)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-64748b)](https://github.com/A13Xg/Overlord11)

Overlord11 is a structured multi-agent framework that coordinates **seven specialist AI agents** across any LLM provider (Anthropic Claude, Google Gemini, or OpenAI GPT). Every request is routed through an **Orchestrator** that decomposes tasks, delegates to specialists, and synthesizes a reviewed final output — without any provider-specific code in the agent definitions or tool schemas.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Agents](#agents)
- [Tools](#tools)
- [Output Tiers](#output-tiers)
- [Provider Configuration](#provider-configuration)
- [Environment Variables](#environment-variables)
- [How to Use](#how-to-use)
- [Testing](#testing)
- [Extension Guide](#extension-guide)
- [Memory System](#memory-system)
- [Wiki](#wiki)

---

## Features

- 🔀 **Provider-agnostic** — switch between Anthropic, Gemini, or OpenAI by changing one line in `config.json`
- 🤖 **7 specialist agents** — Orchestrator, Researcher, Coder, Analyst, Writer, Reviewer, Publisher
- 🛠️ **15 built-in tools** — file I/O, web fetch/scrape, shell execution, Git, code analysis, project scanning, and more
- 🔍 **Dual-engine search** — ripgrep when available, pure-Python fallback producing identical JSON output
- 📊 **3 output tiers** — inline text, Markdown docs, or styled self-contained HTML reports
- 🎨 **9 HTML themes** — techno, classic, modern, editorial, and more — auto-selected by content type
- 🧠 **Shared memory** — `Consciousness.md` enables cross-agent, cross-session context
- 🔒 **Security-first** — Reviewer agent blocks hardcoded secrets; no credentials in agent definitions
- ✅ **Fully tested** — 81-test suite covering all 16 modules, ripgrep/Python fallback, Unicode, encoding edge-cases
- 🔌 **Extensible** — add new agents, tools, or LLM providers without touching the framework core

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        User Request                         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│               Orchestrator  (OVR_DIR_01)                    │
│  ┌───────────┐  ┌───────┐  ┌──────────┐  ┌──────────────┐  │
│  │ 1. Intake │→ │2.Tier │→ │3.Delegate│→ │ 4.Synthesize │  │
│  └───────────┘  └───────┘  └──────────┘  └──────────────┘  │
└──────┬───────────────┬──────────────┬──────────────┬────────┘
       │               │              │              │
       ▼               ▼              ▼              ▼
 Researcher         Coder          Analyst        Writer
(OVR_RES_02)   (OVR_COD_03)   (OVR_ANL_04)  (OVR_WRT_05)
       │               │              │              │
       └───────────────┴──────────────┴──────┬───────┘
                                             │
                                             ▼
                                    Reviewer (OVR_REV_06)
                                             │
                                    ┌────────┴────────┐
                                    │  Tier 1: .md    │
                                    │  Tier 2: .html  │
                                    │  (Publisher)    │
                                    └─────────────────┘
```

All agents read from and write to **`Consciousness.md`** (shared memory) and use the same **tool set** — the only difference is which tools each agent has access to.

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/A13Xg/Overlord11.git
cd Overlord11
cp .env.example .env
```

### 2. Install dependencies

```bash
pip install requests beautifulsoup4 pillow ddgs
# Optional for JS-rendered pages:
pip install selenium
```

### 3. Set your API key

Edit `.env` and add the key for your chosen provider:

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# OR Google Gemini
GOOGLE_GEMINI_API_KEY=AIza...

# OR OpenAI
OPENAI_API_KEY=sk-...
```

### 4. Set the active provider

In `config.json`, set `providers.active` to `"anthropic"`, `"gemini"`, or `"openai"`:

```json
{
  "providers": {
    "active": "anthropic"
  }
}
```

### 5. Run a task

Load `agents/orchestrator.md` as your system prompt in your LLM client, then send your request. For CLI usage:

```bash
# Example: scan the project
python tools/python/project_scanner.py --path .

# Example: generate a styled HTML report
python tools/python/publisher_tool.py --title "Q1 Analysis" --content report.md --theme modern
```

### 6. Verify your setup

```bash
python tests/test.py --skip-web --quiet
```

---

## Directory Structure

```
Overlord11/
├── agents/                  # 7 agent definitions (system prompts)
│   ├── orchestrator.md      # OVR_DIR_01 — master coordinator
│   ├── researcher.md        # OVR_RES_02 — web & local research
│   ├── coder.md             # OVR_COD_03 — code generation & debugging
│   ├── analyst.md           # OVR_ANL_04 — data analysis & summarization
│   ├── writer.md            # OVR_WRT_05 — Markdown output (Tier 1)
│   ├── reviewer.md          # OVR_REV_06 — QA, review & validation
│   └── publisher.md         # OVR_PUB_07 — styled HTML reports (Tier 2)
│
├── tools/
│   ├── defs/                # 15 provider-agnostic tool JSON schemas
│   └── python/              # Python implementations of all tools
│
├── docs/                    # Full Wiki documentation
│   ├── Home.md
│   ├── Getting-Started.md
│   ├── Architecture.md
│   ├── Agents-Reference.md
│   ├── Tools-Reference.md
│   ├── Configuration-Reference.md
│   ├── Providers.md
│   ├── Memory-System.md
│   ├── Output-Tiers.md
│   ├── Extension-Guide.md
│   ├── Development.md
│   └── Troubleshooting.md
│
├── tests/
│   ├── test.py              # 81-test suite covering all 16 modules
│   └── test_results.json    # Machine-readable results (auto-generated)
│
├── config.json              # Unified config (providers, agents, tools)
├── Consciousness.md         # Shared cross-agent memory
├── ONBOARDING.md            # Universal LLM onboarding guide
├── CHANGELOG.md             # Release history
├── .env.example             # Environment variable template
└── pre_commit_clean.py      # Pre-commit cleanup + test runner
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
| `search_file_content` | Ripgrep-powered content search with regex support; pure-Python fallback when `rg` is unavailable |
| `replace` | Precise find-and-replace within files |

### Execution
| Tool | Description |
|------|-------------|
| `run_shell_command` | Execute shell commands, run tests, install packages |
| `git_tool` | Git operations: status, diff, commit, push, branch |
| `calculator` | Math expressions: arithmetic, trig, logarithms, sqrt, power |
| `scaffold_generator` | Generate project scaffolding from templates |

### Web
| Tool | Description |
|------|-------------|
| `web_fetch` | HTTP GET with HTML-to-Markdown conversion |
| `web_scraper` | Advanced article extraction, page structure analysis, RSS/Atom feed discovery, DuckDuckGo search, smart image download |

### Analysis & Memory
| Tool | Description |
|------|-------------|
| `code_analyzer` | Static analysis: function detection, cyclomatic complexity, code smells, import structure |
| `project_scanner` | Codebase structure, language detection, entry points, git metadata |
| `save_memory` | Persist facts to `Consciousness.md` with timestamps across sessions |
| `publisher_tool` | Generate themed self-contained HTML reports (9 visual themes, auto-detection) |

> Full tool documentation: [`docs/Tools-Reference.md`](docs/Tools-Reference.md)

---

## Output Tiers

The Orchestrator automatically determines the right output format:

| Tier | Condition | Output |
|------|-----------|--------|
| **0** | Simple Q&A, one-liners | Inline text — no file |
| **1** | Moderate complexity: docs, guides, summaries | Markdown `.md` via Writer |
| **2** | Detailed reports, infographics, dashboards, comprehensive analyses | Self-contained HTML `.html` via Publisher |

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

Fallback order (if primary provider fails): configured in `orchestration.fallback_provider_order`.

> Full provider guide: [`docs/Providers.md`](docs/Providers.md)

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | If using Anthropic | Claude API key from [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| `GOOGLE_GEMINI_API_KEY` | If using Gemini | Gemini API key from [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| `OPENAI_API_KEY` | If using OpenAI | OpenAI API key from [platform.openai.com](https://platform.openai.com/api-keys) |
| `NO_COLOR` | No | Set to `1` to disable ANSI colour output in the test suite |

Only the key for your active provider is required.

---

## How to Use

### Load an agent as a system prompt

Each agent file in `agents/` is a complete system prompt. Load it directly:

```python
with open("agents/orchestrator.md") as f:
    system_prompt = f.read()
```

### Delegation flow

The Orchestrator always receives requests first and delegates:

```
User Request
    → Orchestrator (OVR_DIR_01)
        → Researcher  (gather context)
        → Coder       (implement)
        → Reviewer    (validate)
    → Final Output
```

### Direct agent invocation

For focused tasks, invoke a specialist directly:

```bash
# Use the Coder for a pure coding task
# Load agents/coder.md as your system prompt, then send your request

# Use the Researcher for a research task
# Load agents/researcher.md as your system prompt, then send your request
```

### CLI tool usage

```bash
# Read a file
python tools/python/read_file.py --path config.json

# Search code (uses ripgrep if available, Python fallback otherwise)
python tools/python/search_file_content.py --pattern "def run" --path tools/python/

# Fetch a web page as Markdown
python tools/python/web_fetch.py --url https://docs.python.org/3/

# Scrape and package for LLM analysis
python tools/python/web_scraper.py --action analyze_content \
  --url https://example.com/article \
  --analysis_goal "Extract key findings"

# DuckDuckGo web search
python tools/python/web_scraper.py --action search \
  --query "Python async patterns" --max_results 5

# Run static analysis
python tools/python/code_analyzer.py --path tools/python/

# Scan project structure
python tools/python/project_scanner.py --path .

# Generate a styled HTML report
python tools/python/publisher_tool.py \
  --title "Q1 Analysis" --content report.md --theme modern

# Save a memory entry
python tools/python/save_memory_tool.py \
  --key "project_goal" --value "Build provider-agnostic toolset"
```

---

## Testing

The test suite at `tests/test.py` covers all **16 modules** across **81 tests** — including encoding edge-cases (UTF-8, CJK, emoji), ripgrep/Python-fallback compatibility, live web calls, and all 9 publisher themes.

### Run the tests

```bash
# Full suite (includes live web calls)
python tests/test.py

# Skip internet-dependent tests (fast, ~1s)
python tests/test.py --skip-web

# Single tool
python tests/test.py --tool calculator

# Multiple tools (comma-separated)
python tests/test.py --tool calculator,git_tool,web_scraper

# Summary only — ideal for LLM agents or CI pipelines
python tests/test.py --quiet

# Plain text output — no ANSI codes (also: set NO_COLOR=1)
python tests/test.py --no-color

# Save JSON results to a custom path
python tests/test.py --output /path/to/results.json

# List all testable tools and exit
python tests/test.py --list

# Stop immediately on first failure
python tests/test.py --fail-fast

# Combined (typical CI invocation)
python tests/test.py --skip-web --quiet --no-color --output ci_results.json
```

### Test matrix

| Mode | Tests | Coverage |
|------|-------|----------|
| `--skip-web` | 72 | All local tools, encoding, file I/O, git, shell, analysis |
| Full (web) | **81** | All of the above + web fetch, DuckDuckGo search, scraper |

### JSON results

Every run writes `tests/test_results.json`. It includes an `environment` block with Python version, platform, ripgrep availability, and optional package status — so an LLM reading the output can reason about why a test passed or failed:

```json
{
  "session_id": "20260224_213345_test",
  "run_at": "2026-02-24T21:33:45",
  "total_tests": 81,
  "passed": 81,
  "failed": 0,
  "environment": {
    "python_version": "3.14.2",
    "platform": "win32",
    "ripgrep": true,
    "packages": {
      "bs4": true,
      "requests": true,
      "ddgs": true,
      "selenium": true
    }
  },
  "results": [...]
}
```

> See [`tests/test.py`](tests/test.py) for the full test implementation.

---

## Extension Guide

### Add a new agent

1. Create `agents/my_agent.md` following the template in existing agent files
2. Add an entry to `agents` in `config.json` with a unique ID (e.g., `OVR_NEW_08`)
3. List the tools the agent needs in its `tools` array
4. Update the Orchestrator's `can_delegate_to` list

### Add a new tool

1. Create `tools/defs/my_tool.json` with the JSON Schema definition
2. Implement `tools/python/my_tool.py`
3. Add an entry to `tools` in `config.json`
4. Reference the tool in any agent definitions that need it

### Add a new provider

1. Add a new entry under `providers` in `config.json` with `model`, `api_key_env`, `api_base`, `max_tokens`, and `temperature`
2. Add the API key variable to `.env.example`
3. Implement the provider adapter in your runner

> Full extension guide: [`docs/Extension-Guide.md`](docs/Extension-Guide.md)

---

## Memory System

`Consciousness.md` is the shared memory for all agents. Agents write findings, decisions, and work-in-progress entries here using the `save_memory` tool. The memory system supports:

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
| [Agents Reference](docs/Agents-Reference.md) | All 7 agents — identities, workflows, and quality checklists |
| [Tools Reference](docs/Tools-Reference.md) | All 15 tools — parameters, examples, and return values |
| [Configuration Reference](docs/Configuration-Reference.md) | Complete `config.json` field reference |
| [Providers](docs/Providers.md) | LLM provider guide: models, costs, switching, and fallbacks |
| [Memory System](docs/Memory-System.md) | `Consciousness.md` format, rules, and best practices |
| [Output Tiers](docs/Output-Tiers.md) | Tier 0/1/2 decision logic and all 9 HTML themes |
| [Extension Guide](docs/Extension-Guide.md) | Adding agents, tools, and providers |
| [Development](docs/Development.md) | Contributing, testing, and dev setup |
| [Troubleshooting](docs/Troubleshooting.md) | FAQ and common error fixes |
