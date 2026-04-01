# Configuration Reference

Complete reference for every field in `config.json`.

---

## Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `version` | string | Framework version (e.g., `"2.3.1"`) |
| `name` | string | Framework name (`"Overlord11"`) |
| `description` | string | One-line description |
| `providers` | object | LLM provider configuration |
| `agents` | object | Agent definitions and tool access |
| `tools` | object | Tool registry (schema + implementation paths) |
| `orchestration` | object | Runtime orchestration policy |
| `quality` | object | Code and output quality thresholds |
| `workspace` | object | Session workspace settings |
| `logging` | object | Log output settings |
| `ui_defaults` | object | UI/UX output quality controls (applies to all AI providers) |

---

## `providers`

### `providers.active`

```json
"active": "gemini"
```

Sets the currently active LLM provider. Valid values: `"gemini"`, `"openai"`, `"anthropic"`. Default is `"gemini"`.

### Per-Provider Fields

Each provider entry (`anthropic`, `gemini`, `openai`) has the same structure:

| Field | Type | Description |
|-------|------|-------------|
| `model` | string | Default model ID to use for this provider |
| `available_models` | object | Map of model ID → description (informational only) |
| `api_key_env` | string | Name of the environment variable holding the API key |
| `max_tokens` | integer | Maximum tokens to generate per request |
| `temperature` | number | Sampling temperature (0.0–1.0; default: 0.7) |
| `top_p` | number | Nucleus sampling parameter (default: 1.0) |
| `api_base` | string | Base URL for the provider's API |

**Example:**

```json
"anthropic": {
  "model": "claude-sonnet-4-5",
  "api_key_env": "ANTHROPIC_API_KEY",
  "max_tokens": 8192,
  "temperature": 0.7,
  "top_p": 1.0,
  "api_base": "https://api.anthropic.com/v1"
}
```

### Available Models

#### Anthropic

| Model ID | Description |
|----------|-------------|
| `claude-opus-4-5` | Most capable — complex reasoning, long-form generation |
| `claude-opus-4-0` | Previous Opus generation — strong capability, lower cost |
| `claude-sonnet-4-5` | Balanced speed + capability — **recommended default** |
| `claude-sonnet-3-7` | Extended thinking variant — step-by-step reasoning |
| `claude-haiku-3-5` | Fast and lightweight — Q&A, classification |
| `claude-haiku-3-0` | Smallest / cheapest — high-throughput workloads |

#### Google Gemini

| Model ID | Description |
|----------|-------------|
| `gemini-2.5-pro` | Most capable — 1M token context, multimodal |
| `gemini-2.5-flash` | Fast + capable — **recommended for most tasks** |
| `gemini-2.5-flash-lite` | Ultra-fast — high-volume workloads |
| `gemini-2.0-pro` | Previous Pro — strong reasoning |
| `gemini-2.0-flash` | Previous Flash — reliable, widely supported |
| `gemini-1.5-pro` | Legacy — 2M token window, document-heavy tasks |
| `gemini-1.5-flash` | Legacy fast — cost-effective |

#### OpenAI

| Model ID | Description |
|----------|-------------|
| `gpt-4o` | Most capable GPT-4 class — vision, tool use |
| `gpt-4o-mini` | Fast and cheap — **recommended for everyday tasks** |
| `gpt-4-turbo` | Previous flagship — 128k context |
| `o3` | Reasoning model — multi-step logic and math |
| `o3-mini` | Lightweight reasoning — fast chain-of-thought |
| `o4-mini` | Latest reasoning mini — coding and math |
| `gpt-3.5-turbo` | Legacy — cheapest for simple completions |

---

## `agents`

Each agent entry has this structure:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Agent identifier (e.g., `"OVR_DIR_01"`) |
| `name` | string | Display name |
| `file` | string | Path to the agent's system prompt Markdown file |
| `description` | string | One-line role description |
| `entry_point` | boolean | `true` only for the Orchestrator |
| `can_delegate_to` | array | (Orchestrator only) List of agent keys it can invoke |
| `tools` | array | Tool keys this agent has access to |

**Example:**

```json
"researcher": {
  "id": "OVR_RES_02",
  "name": "Researcher",
  "file": "agents/researcher.md",
  "description": "Web research, information gathering, source verification",
  "entry_point": false,
  "tools": ["web_fetch", "web_scraper", "read_file", "list_directory", "glob",
            "search_file_content", "save_memory", "project_scanner"]
}
```

---

## `tools`

Each tool entry maps a tool name to its schema and implementation:

| Field | Type | Description |
|-------|------|-------------|
| `def` | string \| null | Path to the JSON Schema file, or `null` if schema-only |
| `impl` | string \| null | Path to the Python implementation, or `null` if agent-inline |

**Example:**

```json
"web_fetch": {
  "def": "tools/defs/web_fetch.json",
  "impl": "tools/python/web_fetch.py"
}
```

> Tools with `"impl": null` (like `replace`) are implemented directly by the LLM agent, not as standalone Python scripts.

The framework currently registers **30 tools**. All entries use the `def`/`impl` format. The two utility tools (`session_manager`, `log_manager`) follow the same format:

```json
"session_manager": {
  "def": "tools/defs/session_manager.json",
  "impl": "tools/python/session_manager.py"
},
"log_manager": {
  "def": "tools/defs/log_manager.json",
  "impl": "tools/python/log_manager.py"
}
```

---

## `orchestration`

| Field | Type | Description |
|-------|------|-------------|
| `max_loops` | integer | Maximum delegation loops before halting (default: 10) |
| `max_retries_per_agent` | integer | Retry count if an agent produces insufficient output (default: 3) |
| `retry_on_empty_output` | boolean | Retry automatically if an agent returns empty output (default: `true`) |
| `always_review_before_delivery` | boolean | Always invoke Reviewer before final output (default: `true`) |
| `fallback_provider_order` | array | Provider fallback chain on API failure — default: `["gemini", "openai", "anthropic"]` |
| `phases` | array | Ordered workflow phases: `["intake", "research", "planning", "execution", "review", "delivery"]` |
| `memory_file` | string | Path to shared memory file (default: `"Consciousness.md"`) |
| `log_sessions` | boolean | Enable session logging (default: `true`) |
| `log_dir` | string | Directory for log files (default: `"logs/"`) |

---

## `quality`

| Field | Type | Description |
|-------|------|-------------|
| `min_test_coverage` | integer | Minimum required test coverage % (default: 80) |
| `require_tests_for_new_code` | boolean | Block handoff if tests are missing for new code (default: `true`) |
| `require_reviewer_approval` | boolean | Require Reviewer sign-off before delivery (default: `true`) |
| `max_complexity_per_function` | integer | Cyclomatic complexity threshold (default: 10) |
| `security_scan_enabled` | boolean | Run security checks in `code_analyzer` (default: `true`) |
| `require_docstrings` | boolean | Require docstrings for new public functions (default: `true`) |

---

## `workspace`

| Field | Type | Description |
|-------|------|-------------|
| `root` | string | Workspace root directory (default: `"workspace/"`) |
| `session_id_format` | string | Format for session IDs (default: `"YYYYMMDD_HHmmss"`) |
| `max_sessions_retained` | integer | Maximum number of sessions to keep before cleanup (default: 50) |
| `auto_cleanup_days` | integer | Purge sessions older than this many days (default: 30) |

---

## `logging`

| Field | Type | Description |
|-------|------|-------------|
| `level` | string | Log level: `debug`, `info`, `warning`, `error` (default: `"info"`) |
| `log_dir` | string | Log output directory (default: `"logs/"`) |
| `log_format` | string | `"json"` (structured JSONL) or `"text"` (default: `"json"`) |
| `include_tool_calls` | boolean | Log all tool inputs and outputs (default: `true`) |
| `include_agent_outputs` | boolean | Log full agent output text (default: `true`) |
| `rotate_daily` | boolean | Rotate log files daily (default: `true`) |
| `max_log_files` | integer | Number of log files to retain (default: 30) |

The WebUI produces two separate log streams:

| File | Content |
|------|---------|
| `logs/webui.jsonl` | HTTP requests, provider health probes, config changes |
| `logs/agents.jsonl` | Tool invocations, LLM decisions, agent switches, job events |

---

## `ui_defaults`

Controls UI/UX output quality. Applies to **all AI providers** (Gemini, OpenAI, Anthropic).

| Field | Type | Description |
|-------|------|-------------|
| `design_system_required` | boolean | Coder must call `ui_design_system` before any HTML/CSS work (default: `true`) |
| `preferred_styles` | array | Premium style pool — auto-selection draws exclusively from these: `aurora-gradient`, `glassmorphism`, `ultraviolet`, `neobrutalism`, `biomimetic` |
| `fallback_styles` | array | Standard and basic styles available via explicit `style_id` parameter |
| `publisher_preferred_themes` | array | Publisher `publisher_tool` premium themes: `aurora`, `ultraviolet`, `neobrutalism` |
| `no_basic_generic_html` | boolean | Block plain/generic HTML output — styled design system required (default: `true`) |
| `verbose_ui_required` | boolean | Require rich, verbose HTML layouts with multiple sections, metrics, and visual hierarchy (default: `true`) |

**Example:**

```json
"ui_defaults": {
  "design_system_required": true,
  "preferred_styles": ["aurora-gradient", "glassmorphism", "ultraviolet", "neobrutalism", "biomimetic"],
  "fallback_styles": ["minimal-zen", "data-dense", "soft-ui", "editorial", "brutalist", "retro-terminal"],
  "publisher_preferred_themes": ["aurora", "ultraviolet", "neobrutalism"],
  "no_basic_generic_html": true,
  "verbose_ui_required": true
}
```

---

## Full Default Configuration

For the full `config.json` with all defaults, see [`config.json`](../config.json).
