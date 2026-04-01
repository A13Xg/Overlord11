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

Open `config.json` and set `providers.active` to your provider. The default is `"gemini"`:

```json
{
  "providers": {
    "active": "gemini"
  }
}
```

Valid values: `"gemini"`, `"openai"`, `"anthropic"`.

The fallback order (used when the active provider fails) is `gemini → openai → anthropic`. Edit `orchestration.fallback_provider_order` to change it.

To also change the model within a provider, update the `model` field:

```json
"gemini": {
  "model": "gemini-3.1-flash-lite-preview"
}
```

See [Providers](Providers.md) for a full model list and cost comparison.

---

## Step 5 — (Optional) Launch the Tactical WebUI

The Tactical WebUI provides a browser dashboard to monitor jobs, browse artifacts, and configure provider/model selection.

```bash
# Install WebUI dependencies
pip install -r requirements-webui.txt

# Start the server
python scripts/run_webui.py
```

Open **http://127.0.0.1:8844** in your browser. The interactive API docs are at **http://127.0.0.1:8844/docs**.

Features:
- Live provider health indicators — green/yellow/red status per provider
- Clickable model picker — select any available model for the next job
- Gemini rate-limit fallback — auto-degrades through lighter models on `429 RESOURCE_EXHAUSTED`
- Job list, events log, artifact browser with inline Markdown preview
- Structured JSONL logs: `logs/webui.jsonl` and `logs/agents.jsonl`

---

## Step 6 — Verify Your Setup

Run the WebUI test suite to confirm all endpoints are working:

```bash
python -m pytest tests/test_webui.py -v
```

Or run the core tool test suite:

```bash
# Skip internet-dependent tests (fast, offline-safe)
python tests/test.py --skip-web --quiet
```

---

## Step 7 — Load an Agent as a System Prompt

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

## Step 8 — Run a Task End-to-End

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
