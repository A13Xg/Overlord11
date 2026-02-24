# Overlord11

**Provider-agnostic multi-agent LLM toolset**

Overlord11 is a structured multi-agent framework that coordinates six specialist AI agents across any LLM provider (Anthropic, Google Gemini, or OpenAI). Every request is routed through an Orchestrator that decomposes tasks, delegates to specialists, and synthesizes a reviewed final output.

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/your-org/Overlord11.git
cd Overlord11
cp .env.example .env
```

### 2. Set your API key

Edit `.env` and add the key for your chosen provider:

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# OR Google Gemini
GOOGLE_GEMINI_API_KEY=AIza...

# OR OpenAI
OPENAI_API_KEY=sk-...
```

### 3. Set the active provider

In `config.json`, set `providers.active` to `"anthropic"`, `"gemini"`, or `"openai"`:

```json
{
  "providers": {
    "active": "anthropic"
  }
}
```

### 4. Run a task

Pass your system prompt (the agent file) and user request to your LLM client:

```bash
# Example using a Python runner
python tools/python/session_manager.py --agent orchestrator --task "Research the top 5 Python testing frameworks and write a comparison report"
```

---

## Directory Structure

```
Overlord11/
├── agents/                  # 7 consolidated agent definitions
│   ├── orchestrator.md      # OVR_DIR_01 — master coordinator + output tier logic
│   ├── researcher.md        # OVR_RES_02 — research & info gathering
│   ├── coder.md             # OVR_COD_03 — code generation & debugging
│   ├── analyst.md           # OVR_ANL_04 — data analysis & summarization
│   ├── writer.md            # OVR_WRT_05 — writing & documentation (Tier 1)
│   ├── reviewer.md          # OVR_REV_06 — QA, review & validation
│   └── publisher.md         # OVR_PUB_07 — styled HTML report generation (Tier 2)
│
├── tools/
│   ├── defs/                # 15 provider-agnostic tool JSON schemas
│   │   ├── read_file.json
│   │   ├── write_file.json
│   │   ├── list_directory.json
│   │   ├── glob.json
│   │   ├── search_file_content.json
│   │   ├── replace.json
│   │   ├── run_shell_command.json
│   │   ├── web_fetch.json
│   │   ├── git_tool.json
│   │   ├── calculator.json
│   │   ├── save_memory.json
│   │   ├── web_scraper.json
│   │   ├── project_scanner.json
│   │   ├── code_analyzer.json
│   │   └── publisher_tool.json
│   └── python/              # Python implementations of all tools
│
├── config.json              # Unified config (providers + available_models, agents, tools)
├── Consciousness.md         # Shared cross-agent memory
├── ONBOARDING.md            # Universal LLM onboarding guide
├── .env.example             # Environment variable template
└── pre_commit_clean.py      # Git pre-commit hook utility
```

---

## Agents

| ID | Agent | Role |
|----|-------|------|
| OVR_DIR_01 | **Orchestrator** | Master coordinator. Receives all requests, assesses output tier, decomposes tasks, delegates to specialists, and synthesizes final output. Always the entry point. |
| OVR_RES_02 | **Researcher** | Gathers information from the web and local files. Fetches pages, extracts content, cross-references sources, and structures findings. Uses `analyze_content` for LLM-ready web context packages. |
| OVR_COD_03 | **Coder** | Writes, debugs, tests, and refactors code. Works in any language. Runs static analysis and tests before handoff. |
| OVR_ANL_04 | **Analyst** | Analyzes data, identifies patterns, computes metrics, and produces structured summaries with actionable recommendations. |
| OVR_WRT_05 | **Writer** | Produces all Markdown output: READMEs, reports, docs, changelogs, and technical specs. Used for Tier 1 (moderate-complexity) output. |
| OVR_REV_06 | **Reviewer** | Final quality gate. Reviews code and documents for correctness, security, style, and completeness before delivery. |
| OVR_PUB_07 | **Publisher** | Generates fully self-contained styled HTML reports for Tier 2 output. Chooses a visual theme (techno, classic, modern, editorial, etc.) based on content type and produces a single `.html` file with all CSS inline — no external dependencies. |

---

## Tools

### File System
| Tool | Description |
|------|-------------|
| `read_file` | Read any file's contents, with optional line range |
| `write_file` | Write or append content to a file |
| `list_directory` | List directory contents with metadata |
| `glob` | Find files by pattern (`**/*.py`, `src/**/*.ts`) |
| `search_file_content` | Ripgrep-powered content search with regex support |
| `replace` | Precise find-and-replace within files |

### Execution
| Tool | Description |
|------|-------------|
| `run_shell_command` | Execute shell commands, run tests, install packages |
| `git_tool` | Git operations: status, diff, commit, push, branch |
| `calculator` | Math expressions, statistics, unit conversions |

### Web
| Tool | Description |
|------|-------------|
| `web_fetch` | HTTP GET with HTML-to-Markdown conversion |
| `web_scraper` | Advanced article extraction, link following, structured data |

### Analysis & Memory
| Tool | Description |
|------|-------------|
| `code_analyzer` | Static analysis: bugs, security, complexity, style |
| `project_scanner` | Codebase structure, language detection, entry points |
| `save_memory` | Persist facts to `Consciousness.md` across sessions |
| `publisher_tool` | Generate themed self-contained HTML reports (9 visual themes) |

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

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | If using Anthropic | Claude API key from console.anthropic.com |
| `GOOGLE_GEMINI_API_KEY` | If using Gemini | Gemini API key from aistudio.google.com |
| `OPENAI_API_KEY` | If using OpenAI | OpenAI API key from platform.openai.com |

Only the key for your active provider is required.

---

## How to Use Agents

### Load as a system prompt

Each agent file in `agents/` is a complete system prompt. Load it directly:

```python
with open("agents/orchestrator.md") as f:
    system_prompt = f.read()
```

### Delegation pattern

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

---

## How to Use Tools (CLI Examples)

```bash
# Read a file
python tools/python/read_file.py --path config.json

# Search code
python tools/python/search_file_content.py --pattern "def run" --path tools/python/

# Fetch a web page as Markdown
python tools/python/web_fetch.py --url https://docs.python.org/3/

# Scrape and package for LLM analysis
python tools/python/web_scraper.py --action analyze_content --url https://example.com/article --analysis_goal "Extract key findings"

# Smart image download (content-relevant images only)
python tools/python/web_scraper.py --action download_images --url https://example.com --smart_images true --min_image_score 0.5

# Run static analysis
python tools/python/code_analyzer.py --path tools/python/

# Scan project structure
python tools/python/project_scanner.py --path .

# Generate a styled HTML report
python tools/python/publisher_tool.py --title "Q1 Analysis" --content report.md --theme modern

# Generate a report with auto theme detection
python tools/python/publisher_tool.py --title "Security Audit Results" --content audit.txt --output workspace/reports/audit.html

# Save a memory entry
python tools/python/save_memory_tool.py --key "project_goal" --value "Build provider-agnostic toolset"
```

---

## Extension Guide

### Add a new agent

1. Create `agents/my_agent.md` following the template in existing agent files
2. Add an entry to `agents` in `config.json` with a unique ID (e.g., `OVR_NEW_07`)
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

---

## Memory System

`Consciousness.md` is the shared memory for all agents. Agents write findings, decisions, and work-in-progress entries here using the `save_memory` tool. The memory system supports:

- **Cross-session continuity**: Facts persist between runs
- **Cross-agent communication**: One agent's output becomes another's input
- **Work deduplication**: Agents check WIP entries before starting tasks
- **Error broadcasting**: Critical errors visible to all agents
