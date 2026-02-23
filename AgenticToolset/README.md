# AgenticToolset

Portable AI development toolkit. Drop this directory into any project to enable structured multi-agent workflows, automated analysis, and comprehensive logging.

Part of the [Overlord11](https://github.com/A13Xg/Overlord11) multi-agent orchestration framework.

## Setup

### 1. Environment Variables

Copy the example env file and add your API keys:

```bash
cp .env.example .env
```

Then edit `.env` with your keys:

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for Anthropic models |
| `GOOGLE_GEMINI_API_KEY` | Yes | Google API key for Gemini models |

The active provider is controlled by `config.json` under `model_config.provider` (default: `anthropic`).

### 2. Python

All tools require Python 3.11+. No external dependencies needed -- the toolset uses only the Python standard library.

## Quick Start

```bash
# 1. Create a session
python tools/python/session_manager.py --action create --description "My task"

# 2. Scan the project
python tools/python/project_scanner.py --path . --session_id SESSION_ID

# 3. Work using the agent system (see ONBOARDING.md)

# 4. Close the session
python tools/python/session_manager.py --action close --session_id SESSION_ID
```

For full usage details, read [ONBOARDING.md](ONBOARDING.md).

## Directory Structure

```
AgenticToolset/
├── .env.example           # Environment variable template
├── config.json            # Model, agent, tool, and quality configuration
├── memory.md              # Persistent memory across sessions
├── ONBOARDING.md          # Full onboarding guide (read first)
├── README.md              # This file
│
├── agents/                # Sub-agent role definitions (Markdown)
│   ├── orchestrator.md    # AGNT_DIR_01 - Master coordinator
│   ├── architect.md       # AGNT_ARC_02 - Solution design
│   ├── implementer.md     # AGNT_COD_03 - Code writing
│   ├── reviewer.md        # AGNT_REV_04 - Code review
│   ├── debugger.md        # AGNT_DBG_05 - Bug diagnosis
│   ├── researcher.md      # AGNT_RES_06 - Context gathering
│   ├── tester.md          # AGNT_TST_07 - Test engineering
│   ├── doc_writer.md      # AGNT_DOC_08 - Documentation
│   └── web_researcher.md  # AGNT_WEB_09 - Web research
│
├── tools/
│   ├── defs/              # JSON tool schemas
│   └── python/            # Python tool implementations
│       ├── project_scanner.py
│       ├── dependency_analyzer.py
│       ├── code_analyzer.py
│       ├── session_manager.py
│       ├── metrics_collector.py
│       ├── scaffold_generator.py
│       ├── log_manager.py
│       └── web_researcher.py
│
├── logs/                  # Runtime logs (auto-created, gitignored)
└── workspace/             # Session workspaces (auto-created, gitignored)
```

## Agents

| ID | Name | Purpose |
|----|------|---------|
| AGNT_DIR_01 | Orchestrator | Decomposes requests, delegates to specialists, manages workflow |
| AGNT_ARC_02 | Architect | Designs solutions and implementation plans |
| AGNT_COD_03 | Implementer | Writes code and implements features |
| AGNT_REV_04 | Reviewer | Reviews code quality, security, and performance |
| AGNT_DBG_05 | Debugger | Diagnoses bugs and traces errors |
| AGNT_RES_06 | Researcher | Gathers context and researches approaches |
| AGNT_TST_07 | Tester | Writes and runs tests |
| AGNT_DOC_08 | Doc Writer | Writes documentation and API docs |
| AGNT_WEB_09 | Web Researcher | Web search, RSS feeds, page scraping |

## Tools

| Tool | Purpose |
|------|---------|
| `project_scanner` | Deep scan of project structure, languages, frameworks |
| `dependency_analyzer` | Analyzes package manifests for issues and conflicts |
| `code_analyzer` | Static analysis: complexity, smells, imports |
| `session_manager` | Tracks work sessions, changes, and agent usage |
| `metrics_collector` | LOC, file stats, function counts, git activity |
| `scaffold_generator` | Generates project boilerplate from templates |
| `log_manager` | Central structured logging and log queries |
| `web_researcher` | Web search, RSS feed discovery, page scraping |

All tools are standalone Python CLI scripts. Run any tool with `--help` for usage:

```bash
python tools/python/<tool_name>.py --help
```

All tools accept `--session_id` for automatic logging to the master log.

## Configuration

Edit `config.json` to customize:

- **model_config** -- LLM provider (`anthropic` or `gemini`), model name, token limits
- **orchestration_logic** -- Workflow phases, loop limits, fallback behavior
- **quality_standards** -- Min quality scores, complexity limits, review requirements
- **logging** -- Log paths, rotation, verbosity

## Extending

### Add a new tool

1. Create `tools/python/new_tool.py` with CLI interface and `--session_id` param
2. Create `tools/defs/new_tool.json` with the JSON schema
3. Register in `config.json` under `tool_registry`

### Add a new agent

1. Create `agents/new_agent.md` following the existing pattern
2. Assign ID using format `AGNT_XXX_NN`
3. Register in `config.json` under `agent_registry`
