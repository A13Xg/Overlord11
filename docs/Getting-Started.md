# Getting Started

This guide walks you through installing, configuring, and running Overlord11 for the first time.

---

## Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.8+ | Required |
| pip | Latest | Required |
| requests | Any | For `web_fetch`, `web_scraper` |
| beautifulsoup4 | Any | For HTML parsing in `web_scraper` |
| ddgs | Any | For DuckDuckGo search in `web_scraper` |
| Pillow | Any | Optional — for smart image scoring |
| selenium | 4.x | Optional — for JS-rendered pages |

---

## Step 1 — Clone the Repository

```bash
git clone https://github.com/A13Xg/Overlord11.git
cd Overlord11
```

---

## Step 2 — Install Dependencies

```bash
# Core dependencies
pip install requests beautifulsoup4 ddgs

# Optional: for smart image download scoring
pip install pillow

# Optional: for JavaScript-rendered pages
pip install selenium
```

> **Note:** All tool implementations are in `tools/python/`. They are plain Python scripts with no framework dependencies beyond the optional packages above.

---

## Step 3 — Configure Your API Key

Copy the environment template and add your key:

```bash
cp .env.example .env
```

Open `.env` and fill in the key for your chosen provider:

```bash
# Anthropic (Claude)
ANTHROPIC_API_KEY=sk-ant-...

# OR Google Gemini
GOOGLE_GEMINI_API_KEY=AIza...

# OR OpenAI
OPENAI_API_KEY=sk-...
```

You only need **one key** — the one for your active provider.

| Provider | Where to get a key |
|----------|--------------------|
| Anthropic | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) |
| Google Gemini | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |
| OpenAI | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |

---

## Step 4 — Set the Active Provider

Open `config.json` and set `providers.active` to your provider:

```json
{
  "providers": {
    "active": "anthropic"
  }
}
```

Valid values: `"anthropic"`, `"gemini"`, `"openai"`.

To also change the model within a provider, update the `model` field:

```json
"anthropic": {
  "model": "claude-opus-4-5"
}
```

See [Providers](Providers.md) for a full model list and cost comparison.

---

## Step 5 — Verify Your Setup

Run the test suite to confirm all tools are working:

```bash
# Full suite (requires internet for web tests)
python tests/test.py

# Skip internet-dependent tests (fast, offline-safe)
python tests/test.py --skip-web

# Summary output only — ideal for a quick pass/fail check
python tests/test.py --skip-web --quiet
```

Expected output when all 81 tests pass:

```
  Overlord11 Tool Test Suite
  Session: 20260224_213345_test
  Workspace: tests\test_workspace

  Running: read_file ... 7/7
  Running: write_file ... 6/6
  Running: list_directory ... 3/3
  Running: glob ... 4/4
  Running: search_file_content ... 7/7
  ...

  SUMMARY:  81/81 tests passed  |  16 tools tested  |  Total time: 4823ms
```

| Mode | Tests | Use When |
|------|-------|----------|
| Full suite | **81** | Final verification, CI pipelines with internet |
| `--skip-web` | **72** | Offline development, fast local checks |

### Test CLI Flags

| Flag | Description |
|------|-------------|
| `--skip-web` | Skip internet-dependent tests |
| `--tool NAME` | Run tests for one tool only (e.g. `--tool calculator`) |
| `--tool A,B,C` | Run tests for multiple tools (comma-separated) |
| `--quiet` / `-q` | Summary and failures only — LLM/CI friendly |
| `--no-color` | Disable ANSI colour codes (also: `NO_COLOR=1`) |
| `--output PATH` | Write JSON results to a custom file path |
| `--list` | Print all testable tool names and exit |
| `--fail-fast` | Stop immediately on the first failure |

---

## Step 6 — Load an Agent as a System Prompt

Each file in `agents/` is a complete system prompt. Load it in your LLM client:

```python
import anthropic

with open("agents/orchestrator.md", encoding="utf-8") as f:
    system_prompt = f.read()

client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=8192,
    system=system_prompt,
    messages=[{"role": "user", "content": "Research the top 5 Python testing frameworks and write a comparison report"}]
)
print(response.content[0].text)
```

---

## Step 7 — Run a Task End-to-End

The typical flow is:

1. Load `agents/orchestrator.md` as your system prompt
2. Send your request as a user message
3. The Orchestrator parses, classifies, and delegates the task
4. Specialists complete their subtasks using the available tools
5. The Reviewer validates the output
6. The Orchestrator synthesizes and returns the final result

For CLI tool usage without an LLM, see individual tool examples in [Tools Reference](Tools-Reference.md).

---

## Common First Tasks

### Scan a project structure

```bash
python tools/python/project_scanner.py --path .
```

### Search code for a pattern

```bash
python tools/python/search_file_content.py --pattern "def main" --path tools/python/
```

### Generate an HTML report

```bash
python tools/python/publisher_tool.py --title "My First Report" --content README.md --theme modern
```

### Fetch a web page as Markdown

```bash
python tools/python/web_fetch.py --url https://docs.python.org/3/
```

### DuckDuckGo web search

```bash
python tools/python/web_scraper.py --action search --query "Python async patterns" --max_results 5
```

---

## Workspace and Logs

- **Workspace**: session files are created under `workspace/` (auto-created, excluded from git)
- **Logs**: structured JSONL logs are written to `logs/` (auto-created, excluded from git)
- **Memory**: agents read/write `Consciousness.md` in the project root
- **Test results**: `tests/test_results.json` is written after every test run with a full environment block (Python version, platform, ripgrep availability, package status)

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | If using Anthropic | API key from console.anthropic.com |
| `GOOGLE_GEMINI_API_KEY` | If using Gemini | API key from aistudio.google.com |
| `OPENAI_API_KEY` | If using OpenAI | API key from platform.openai.com |
| `NO_COLOR` | No | Set to `1` to disable ANSI colour in the test suite |

---

## Next Steps

- [Architecture](Architecture.md) — understand how the components fit together
- [Agents Reference](Agents-Reference.md) — deep dive into each agent
- [Tools Reference](Tools-Reference.md) — complete tool parameter reference
- [Providers](Providers.md) — model selection and provider switching
- [Development](Development.md) — contributing, testing, and dev setup

---

## Optional: Run the Internal Engine (no external CLI)

Overlord11 v2.3.0 includes an internal Python execution engine that runs agents directly — no external CLI tool (Claude CLI, Gemini CLI, etc.) needed.

### Prerequisites

The engine uses only Python standard library — no additional packages needed.

### Launch the Engine CLI

```bash
python run_engine.py
```

This opens an interactive terminal interface:

```
  OVERLORD11 ENGINE  v2.3.0

MENU  (provider: anthropic  model: claude-opus-4-5)
  1. Start new session
  2. Resume existing session
  3. Select provider
  4. Select model
  5. Exit
```

- **Start new session**: enter any prompt; the engine runs the Orchestrator agent and streams events live
- **Resume existing session**: pick from the 10 most recent sessions
- **Select provider / Select model**: change the active provider or model (writes to `config.json`)

---

## Optional: Run the Tactical WebUI

A self-hosted web application providing a full visual interface over the engine.

### Install WebUI Dependencies

```bash
pip install -r requirements-webui.txt
```

### Launch the WebUI

```bash
python scripts/run_webui.py
```

Then open [http://localhost:7900](http://localhost:7900) in your browser.

> **PORT override:** `PORT=8080 python scripts/run_webui.py`

### WebUI Features

- **Job queue** — create, start, pause, resume, stop, restart, and delete jobs
- **Real-time event stream** — live agent/tool events via Server-Sent Events
- **Artifacts browser** — browse and preview output files per job
- **Provider selector** — switch provider and model from the top bar
- **Job state indicators** — 🟢 complete · 🟠 queued · 🔵 running · 🔴 failed · ⏸ paused

### API Reference

The FastAPI backend exposes auto-generated docs at [http://localhost:7900/api/docs](http://localhost:7900/api/docs).
