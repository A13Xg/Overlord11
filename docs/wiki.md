# Overlord11 — Developer Wiki

**Version:** 2.4.0  
**Stack:** Python 3.14, FastAPI, Pydantic v2, Uvicorn

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Getting Started](#2-getting-started)
3. [Authentication](#3-authentication)
4. [Job Lifecycle](#4-job-lifecycle)
5. [Tool Gateway Pipeline](#5-tool-gateway-pipeline)
6. [Tool Reference (23 Tools)](#6-tool-reference)
7. [Agent System](#7-agent-system)
8. [Engine Internals](#8-engine-internals)
9. [Backend API Reference](#9-backend-api-reference)
10. [Adding a New Tool](#10-adding-a-new-tool)
11. [Testing](#11-testing)
12. [Configuration](#12-configuration)
13. [Frontend UI Guide](#13-frontend-ui-guide)
14. [Scripts Reference](#14-scripts-reference)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (frontend/)                                           │
│  login.html · index.html                                        │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────────────────┐
│  Backend (backend/)                                             │
│  FastAPI  ·  10 routers  ·  JWT-style session tokens           │
│  auth · jobs · providers · artifacts · events · health ·       │
│  setup · templates · tools · stats                             │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│  Engine (engine/)                                               │
│  runner.py  ─  EngineRunner (main orchestration loop)          │
│  parallel_executor.py  ─  concurrent tool dispatch (≤4 tasks)  │
│  session_manager.py  ─  workspace I/O + artifact logging       │
│  self_healing.py  ─  auto-retry on transient errors            │
│  rate_limit.py  ─  per-provider rate limit handling            │
│  dependency_analyzer.py · tool_cache.py · event_stream.py      │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│  Tool Gateway (tool_gateway/)                                   │
│  parse → normalize → validate → execute → envelope             │
│  registry · parser · normalizer · validator · executor          │
│  results · errors · models · logging_config                    │
│                                                                 │
│  tools/ (23 tools)                                              │
│  write_file · read_file · calculator · json_transform          │
│  image_scraper · html_report_generator · web_search            │
│  web_fetch · web_extract_text · web_extract_images             │
│  web_image_grabber · rss_read · dynamic_browser                │
│  intelligent_theme_scraper · web_code_scraper                  │
│  semantic_content_extractor · search_and_extract_pipeline      │
│  shell_runner · csv_processor · url_checker · text_diff        │
│  base64_tool · json_schema_validator                           │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Principles

- **Workspace isolation** — every job gets `workspace/<job_id>/`; all tool I/O stays inside it via `OVERLORD11_TASK_DIR`.
- **Result envelope** — every tool call returns `{ok, tool_name, data, warnings, errors, metadata}`.
- **Pydantic v2 strict validation** — tool inputs are validated before execution; unknown keys are rejected.
- **Partial success** — tools return `ok=True` with populated `_warnings` rather than throwing when non-critical sub-steps fail.
- **Self-healing** — the engine catches transient errors and retries with configurable back-off.

---

## 2. Getting Started

### Prerequisites

```
Python 3.14+
pip install -r requirements.txt
```

### Environment

```bash
cp .env.example .env
# Edit .env — add at least one provider API key:
# GEMINI_API_KEY=...
# ANTHROPIC_API_KEY=...
# OPENAI_API_KEY=...
```

### Run the server

```bash
python scripts/run_webui.py
# Starts on http://localhost:7900
```

### Default credentials

| Username | Password |
|----------|----------|
| admin    | admin    |

### Disable auth (dev only)

```bash
OVERLORD11_AUTH_DISABLED=1 python scripts/run_webui.py
```

---

## 3. Authentication

The backend uses session tokens (32-byte random hex, 8-hour TTL). Passwords are stored as SHA-256 with per-user salt.

### Login

```http
POST /api/auth/login
Content-Type: application/json

{"username": "admin", "password": "admin"}
```

Response:
```json
{"token": "abc123...", "expires_in": 28800}
```

### Use the token

All protected endpoints require:
```
Authorization: Bearer <token>
```

### Brute-force protection

The login endpoint enforces per-IP rate limiting:
- **5 failed attempts** within a 15-minute window trigger HTTP `429 Too Many Requests`
- The failure counter resets automatically on a successful login
- Locked IPs must wait until the oldest failure ages out of the 900-second window

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/auth/login` | Acquire session token |
| `POST` | `/api/auth/logout` | Revoke all sessions for user |
| `GET`  | `/api/auth/verify` | Check token validity (no auth) |
| `GET`  | `/api/auth/me` | Current user info |
| `GET`  | `/api/auth/status` | Admin: user list + session counts |

---

## 4. Job Lifecycle

### Create and auto-start a job

```http
POST /api/jobs
Authorization: Bearer <token>
Content-Type: application/json

{
  "title": "Research Python 3.14",
  "prompt": "Search for Python 3.14 release notes and save a summary to final_output.md",
  "auto_start": true
}
```

Response includes `job_id`. Poll until `status` is terminal:

```http
GET /api/jobs/{job_id}
```

### Job states

| State | Description |
|-------|-------------|
| `QUEUED` | Waiting for engine worker |
| `RUNNING` | Engine loop active |
| `PAUSED` | Manually paused or awaiting rate-limit recovery |
| `RATE_LIMITED` | Provider rate limit hit; waiting to retry |
| `COMPLETED` | Finished successfully |
| `FAILED` | Unrecoverable error |

### Completion modes

| Mode | Meaning |
|------|---------|
| `tool_driven` | Agent used tools and called `write_file` — output in `workspace/<job_id>/final_output.md` |
| `direct_answer` | Agent responded with prose only (no file write) |
| `empty_response_fail` | LLM returned empty content after retries |
| `no_effect_fail` | LLM claimed to save a file but `write_file` was never actually called |

### Workspace layout

```
workspace/
  <job_id>/
    final_output.md        # tool-written content (write_file)
    final_response.md      # LLM prose (if final_output.md already existed)
    artifacts/
      logs/
        agents/            # per-loop LLM messages
        tools/             # per-tool-call inputs + results
```

### Job control endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/jobs/{job_id}/start` | Start/resume queued job |
| `POST` | `/api/jobs/{job_id}/stop` | Stop running job |
| `POST` | `/api/jobs/{job_id}/pause` | Pause job |
| `POST` | `/api/jobs/{job_id}/resume` | Resume paused job |
| `POST` | `/api/jobs/{job_id}/restart` | Re-queue completed/failed job |
| `DELETE` | `/api/jobs/{job_id}` | Archive and delete job |

### CreateJobRequest fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | `str` | required | Human-readable name |
| `prompt` | `str` | required | Task instruction for the agent |
| `rate_limit_action` | `str` | `"try_different_model"` | What to do on rate limit: `pause`, `stop`, `try_different_model` |
| `auto_start` | `bool` | `true` | Start immediately after creation |
| `depends_on` | `list[str]` | `[]` | Job IDs that must complete first |
| `priority` | `int` | `0` | `−1`=high, `0`=normal, `1`=low |

---

## 5. Tool Gateway Pipeline

Every tool call passes through five sequential stages:

```
raw JSON from LLM
       │
  ┌────▼────┐
  │  Parse  │  parser.py — extract tool_name + arguments from LLM output
  └────┬────┘
       │
  ┌────▼──────────┐
  │  Normalize    │  normalizer.py — alias expansion, type coercion, default injection
  └────┬──────────┘
       │
  ┌────▼──────────┐
  │  Validate     │  validator.py — Pydantic model validation, enum checks
  └────┬──────────┘
       │
  ┌────▼──────────┐
  │  Execute      │  executor.py → tool.execute(args) → raw dict
  └────┬──────────┘
       │
  ┌────▼──────────┐
  │  Envelope     │  results.py — wrap in standard {ok, tool_name, data, ...}
  └───────────────┘
```

### Result envelope schema

```json
{
  "ok": true,
  "tool_name": "web_search",
  "data": { ... },
  "warnings": [],
  "errors": [],
  "metadata": {
    "request_id": "...",
    "duration_seconds": 1.23,
    "normalization": { ... }
  }
}
```

### Error handling

| Error class | Meaning | Recoverable |
|-------------|---------|-------------|
| `ParseError` | Malformed JSON / missing tool_name | Yes |
| `UnknownToolError` | Tool name not in registry | Yes |
| `ValidationError` | Bad argument types/values | Yes — retry hint included |
| `ExecutionError` | Tool raised an exception | Depends on tool |

Recoverable errors include a `retry_hint` field so the LLM can self-correct on the next loop turn.

---

## 6. Tool Reference

All 23 registered tools are documented below. Unless noted otherwise:
- `strict=True`, `extra="forbid"` on all input models
- Risk level `low` unless stated
- Output stays inside `workspace/<job_id>/` (enforced by `resolve_workspace_path`)

---

### write_file

Write UTF-8 text to a file inside the job workspace.

---

### read_file

Read a file from the job workspace. Companion to `write_file`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `path` | `str` | required | File path (relative to workspace root) |
| `encoding` | `str` | `"utf-8"` | Character encoding |
| `max_bytes` | `int` | `1048576` | Max bytes to read (1–10485760) |
| `include_line_count` | `bool` | `false` | Count lines in returned content |

Returns: `content`, `size_bytes`, `bytes_read`, `truncated`, `line_count`.

**Risk:** low

**Examples:**
```json
{"path": "final_output.md"}
{"path": "data.csv", "max_bytes": 65536, "include_line_count": true}
```

---

### csv_processor

Read, filter, sort, and summarize CSV data. Input can be a raw CSV string or a `.csv` file path in the workspace.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `data` | `str` | required | CSV string or workspace-relative `.csv` path |
| `filter_column` | `str \| None` | `null` | Column to filter on |
| `filter_value` | `str \| None` | `null` | Value to match (substring) |
| `sort_column` | `str \| None` | `null` | Column to sort by |
| `sort_order` | `Literal` | `"asc"` | `asc` · `desc` |
| `columns` | `list[str]` | `[]` | Select only these columns |
| `max_rows` | `int` | `500` | Max rows returned (1–10000) |
| `operation` | `Literal` | `"select"` | `select` · `summary` · `unique` |

**Operations:** `select` returns filtered rows; `summary` returns per-column statistics (count, min, max, mean, nulls); `unique` returns distinct values per column.

**Risk:** low

**Examples:**
```json
{"data": "name,age\nAlice,30\nBob,25", "operation": "summary"}
{"data": "data.csv", "filter_column": "status", "filter_value": "active", "sort_column": "name"}
```

---

### url_checker

Bulk URL availability checker. Performs HEAD (or GET) requests and reports status, latency, and SSL validity.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `urls` | `list[str]` | required | URLs to check (max 50) |
| `timeout_seconds` | `float` | `10.0` | Per-URL timeout (1–60) |
| `follow_redirects` | `bool` | `true` | Follow HTTP redirects |
| `check_ssl` | `bool` | `true` | Verify SSL certificates |
| `method` | `Literal` | `"HEAD"` | `HEAD` · `GET` |

Returns per-URL: `ok`, `status_code`, `latency_ms`, `final_url`, `content_type`, `error`.

**Risk:** low

**Examples:**
```json
{"urls": ["https://example.com", "https://httpbin.org/status/404"]}
{"urls": ["https://example.com"], "method": "GET", "timeout_seconds": 5}
```

---

### text_diff

Generate a unified diff between two text strings.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `text_a` | `str` | required | Original text |
| `text_b` | `str` | required | Modified text |
| `label_a` | `str` | `"original"` | Label for left side |
| `label_b` | `str` | `"modified"` | Label for right side |
| `context_lines` | `int` | `3` | Lines of context around changes (0–10) |
| `format` | `Literal` | `"unified"` | `unified` · `summary` · `side_by_side` |

Returns: `diff`, `lines_added`, `lines_removed`, `identical`.

**Risk:** low

**Examples:**
```json
{"text_a": "hello world", "text_b": "hello there"}
{"text_a": "v1 content", "text_b": "v2 content", "format": "summary", "label_a": "v1", "label_b": "v2"}
```

---

### base64_tool

Encode or decode Base64 data (standard and URL-safe variants).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `operation` | `Literal` | required | `encode` · `decode` |
| `data` | `str` | required | Input data |
| `variant` | `Literal` | `"standard"` | `standard` · `urlsafe` |
| `encoding` | `str` | `"utf-8"` | Text encoding for encode; used for decode output |

Decode automatically adds missing padding and falls back to `latin-1` if UTF-8 decoding fails.

**Risk:** low

**Examples:**
```json
{"operation": "encode", "data": "Hello, World!"}
{"operation": "decode", "data": "SGVsbG8sIFdvcmxkIQ==", "variant": "standard"}
```

---

### json_schema_validator

Validate a JSON value against a JSON Schema (Draft 7). Uses the `jsonschema` library when available; falls back to a basic type check.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `data` | `str` | required | JSON string to validate |
| `json_schema` | `dict` | required | JSON Schema object |
| `stop_on_first_error` | `bool` | `false` | Stop after first validation error |

Returns: `valid`, `error_count`, `errors` list (each with `path`, `message`, `schema_path`).

**Risk:** low

**Examples:**
```json
{
  "data": "{\"name\": \"Alice\", \"age\": 30}",
  "json_schema": {"type": "object", "required": ["name", "age"], "properties": {"name": {"type": "string"}, "age": {"type": "integer"}}}
}
```

> **Note:** the field is named `json_schema` (not `schema`) to avoid shadowing Pydantic's `BaseModel.schema()` method.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `path` | `str` | required | File path (relative to workspace root) |
| `content` | `str` | `""` | UTF-8 text content |
| `overwrite` | `bool` | `true` | Allow overwriting existing file |

**Risk:** medium · **Destructive:** yes

**Examples:**
```json
{"path": "answer.md", "content": "# Report\n\nDone."}
{"path": "output/data.csv", "content": "a,b,c\n1,2,3", "overwrite": true}
```

---

### calculator

Safely evaluate arithmetic and mathematical expressions using a sandboxed AST evaluator. No `eval()`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `expression` | `str` | required | Expression, e.g. `"sqrt(16) * pi"`, `"2 ** 10"` |
| `precision` | `int` | `6` | Decimal places (0–15) |
| `scientific_notation` | `bool` | `false` | Format result as scientific notation |

**Supported:** `+`, `-`, `*`, `/`, `**`, `%`, `//`, `sqrt`, `sin`, `cos`, `tan`, `log`, `log2`, `log10`, `exp`, `ceil`, `floor`, `abs`, `round`, `factorial`, `gcd`, `pi`, `e`, `tau`

**Risk:** low

**Examples:**
```json
{"expression": "2 + 2"}
{"expression": "sqrt(144) * pi", "precision": 4}
{"expression": "2 ** 32", "scientific_notation": true}
```

---

### json_transform

Parse, query, and transform JSON data. Input can be a JSON string or a URL.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `data` | `str` | required | JSON string or `http(s)://` URL |
| `query` | `str \| None` | `null` | Dot-notation path, e.g. `"items.0.title"` |
| `transform` | `Literal` | `"pretty"` | `pretty` · `minify` · `flatten` · `keys` · `values` · `summary` |
| `max_depth` | `int` | `10` | Max nesting depth for `flatten` (1–50) |

**Risk:** low

**Examples:**
```json
{"data": "{\"name\":\"Alice\",\"age\":30}", "transform": "pretty"}
{"data": "{\"a\":{\"b\":{\"c\":1}}}", "transform": "flatten"}
{"data": "https://api.github.com/repos/python/cpython", "query": "stargazers_count"}
```

---

### image_scraper

Scrape images from a web page with rich metadata via HEAD requests. More thorough than `web_extract_images`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str` | required | Web page URL |
| `limit` | `int` | `20` | Max images (1–200) |
| `download` | `bool` | `false` | Download files to workspace |
| `output_directory` | `str \| None` | `null` | Workspace-relative output path |
| `min_size_kb` | `int \| None` | `null` | Filter by minimum file size |
| `require_https` | `bool` | `false` | Skip non-HTTPS image URLs |
| `timeout_seconds` | `float` | `10.0` | Per-request timeout (1–60) |

**Risk:** low · **Destructive:** no (unless `download=true`)

**Examples:**
```json
{"url": "https://example.com", "limit": 20}
{"url": "https://example.com", "download": true, "output_directory": "artifacts/images", "min_size_kb": 5}
```

---

### html_report_generator

Generate a self-contained, styled HTML report from Markdown content. Uses the project UI/UX design system (`agents/skills/uiux/`).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | `str` | required | Report title |
| `content` | `str` | `""` | Markdown body content |
| `output_path` | `str \| None` | `null` | Output path (default: `artifacts/report.html`) |
| `theme` | `Literal` | `"dark"` | `dark` · `light` · `auto` |
| `palette_id` | `str \| None` | `null` | Palette ID from `palettes.json` |
| `style_id` | `str \| None` | `null` | Style ID from `styles.json` |
| `include_toc` | `bool` | `true` | Generate table of contents |
| `sections` | `list \| None` | `null` | Additional named sections `[{name, content}]` |

**Risk:** low

**Examples:**
```json
{"title": "Weekly Research Summary", "content": "## Overview\nThis week...", "theme": "dark"}
{"title": "Report", "content": "...", "output_path": "artifacts/report.html", "include_toc": false}
```

---

### web_search

Search the web via DuckDuckGo (DDGS). Returns normalized, deduplicated, ranked results.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | `str \| None` | `null` | Search query (max 500 chars) |
| `max_results` | `int` | `10` | Result count (1–50) |
| `region` | `str` | `"us-en"` | Region code |
| `safe_search` | `Literal` | `"moderate"` | `off` · `moderate` · `strict` |
| `time_range` | `Literal` | `"any"` | `any` · `day` · `week` · `month` · `year` |
| `result_type` | `Literal` | `"auto"` | `auto` · `text` · `news` · `images` |
| `include_snippets` | `bool` | `true` | Include body snippets |
| `include_metadata` | `bool` | `true` | Include title, date, rank |
| `domain_allowlist` | `list[str]` | `[]` | Only include these domains |
| `domain_blocklist` | `list[str]` | `[]` | Exclude these domains |

**Risk:** low

**Examples:**
```json
{"query": "latest python release notes", "max_results": 5}
{"query": "agentic workflows", "result_type": "news", "time_range": "week"}
```

---

### web_fetch

Fetch a webpage's raw HTML with redirect and timeout handling.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str` | required | Target URL |
| `timeout_seconds` | `int` | `20` | Request timeout (1–120) |
| `follow_redirects` | `bool` | `true` | Follow HTTP redirects |
| `headers` | `dict[str, str]` | `{}` | Additional request headers |
| `user_agent` | `str \| None` | `null` | Override user agent string |

**Risk:** low

**Examples:**
```json
{"url": "https://example.com"}
{"url": "https://docs.python.org/3/", "timeout_seconds": 15}
```

---

### web_extract_text

Extract readable text from a URL, raw HTML, or raw text string.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str \| None` | `null` | Fetch and extract from URL |
| `html` | `str \| None` | `null` | Extract from HTML string |
| `raw_text` | `str \| None` | `null` | Pass-through text normalization |
| `extraction_mode` | `Literal` | `"auto"` | `auto` · `article` · `documentation` · `blog` |
| `include_links` | `bool` | `false` | Include extracted hyperlinks |
| `include_metadata` | `bool` | `true` | Include title, description, og tags |

*Requires at least one of `url`, `html`, or `raw_text`.*

**Risk:** low

**Examples:**
```json
{"url": "https://example.com"}
{"html": "<html><body><article>Hello</article></body></html>", "include_links": true}
```

---

### web_extract_images

Extract image metadata from a webpage (faster than `image_scraper` — no HEAD requests).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str` | required | Web page URL |
| `limit` | `int` | `20` | Max images (1–200) |
| `include_alt_text` | `bool` | `true` | Include alt text |
| `min_width` | `int \| None` | `null` | Filter by minimum pixel width |
| `min_height` | `int \| None` | `null` | Filter by minimum pixel height |
| `image_type` | `Literal` | `"auto"` | `auto` · `hero` · `thumbnail` · `logo` · `icon` · `all` |

**Risk:** low

**Examples:**
```json
{"url": "https://example.com"}
{"url": "https://example.com", "image_type": "hero", "min_width": 200}
```

---

### web_image_grabber

Search for, extract, and download images into the workspace with deduplication and a JSON manifest.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `source_mode` | `Literal` | `"search_query"` | `search_query` · `page_urls` · `direct_urls` |
| `query` | `str \| None` | `null` | Search query (for `search_query` mode) |
| `urls` | `list[str]` | `[]` | Page or direct URLs |
| `output_directory` | `str \| None` | `null` | Workspace-relative output path |
| `max_images` | `int` | `10` | Max images to download (1–200) |
| `matching_mode` | `Literal` | `"visual_guess"` | `visual_guess` · `strict` |
| `allowed_extensions` | `list[str]` | `["jpg","jpeg","png","webp","gif"]` | Accepted extensions |
| `require_https` | `bool` | `true` | Skip non-HTTPS sources |
| `deduplicate` | `bool` | `true` | Skip URL duplicates |
| `overwrite_existing` | `bool` | `false` | Overwrite files |
| `create_manifest` | `bool` | `true` | Write `manifest.json` |
| `dry_run` | `bool` | `false` | Plan only, no downloads |

**Risk:** medium · **Destructive:** yes · **Dry run:** yes

**Examples:**
```json
{"query": "mountain landscape", "max_images": 5}
{"source_mode": "direct_urls", "urls": ["https://example.com/a.png"], "dry_run": true}
```

---

### rss_read

Read and normalize RSS/Atom feeds into structured item objects.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `feed_urls` | `list[str]` | required | RSS/Atom feed URLs (≥1) |
| `max_items` | `int` | `20` | Max items per feed (1–200) |
| `include_content` | `bool` | `false` | Include full item HTML content |
| `since_datetime` | `str \| None` | `null` | ISO 8601 cutoff (exclude older items) |

**Risk:** low

**Examples:**
```json
{"feed_urls": ["https://planetpython.org/rss20.xml"]}
{"feed_urls": ["https://example.com/feed.xml"], "max_items": 10, "include_content": true}
```

---

### dynamic_browser

Render JavaScript-heavy pages using Playwright. Falls back to `web_fetch` if Playwright is unavailable.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str` | required | Target URL |
| `timeout_seconds` | `int` | `30` | Timeout (1–120) |
| `wait_selector` | `str \| None` | `null` | CSS selector to wait for before capture |
| `viewport` | `dict[str,int] \| None` | `null` | Viewport `{width, height}` |
| `user_agent` | `str \| None` | `null` | Override user agent |
| `capture_screenshot` | `bool` | `false` | Reserved — not yet implemented |

**Risk:** medium

**Examples:**
```json
{"url": "https://example.com"}
{"url": "https://example.com", "wait_selector": "main", "timeout_seconds": 60}
```

---

### intelligent_theme_scraper

Extract design-system signals from webpage HTML/CSS: color palette, typography, spacing scale, animations, detected frameworks.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str` | required | Target URL |
| `analysis_depth` | `Literal` | `"balanced"` | `quick` · `balanced` · `deep` |
| `extract_css_variables` | `bool` | `true` | Extract CSS custom properties |
| `detect_frameworks` | `bool` | `true` | Detect CSS/JS frameworks |
| `include_component_summary` | `bool` | `true` | Count components and patterns |

**Risk:** low

**Examples:**
```json
{"url": "https://example.com"}
{"url": "https://example.com", "analysis_depth": "deep"}
```

---

### web_code_scraper

Analyze frontend source assets to extract implementation patterns: JS bundles, CSS assets, routes, API endpoints, framework signatures.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str` | required | Target URL |
| `include_js` | `bool` | `true` | Analyze JavaScript assets |
| `include_css` | `bool` | `true` | Analyze CSS assets |
| `include_network_analysis` | `bool` | `false` | Detect API endpoints and XHR patterns |

**Risk:** low

**Examples:**
```json
{"url": "https://example.com"}
{"url": "https://example.com", "include_network_analysis": true}
```

---

### semantic_content_extractor

Extract semantic structures from a page or text: emails, phone numbers, prices, FAQ blocks, contact cards, tables, JSON-LD schema, Open Graph metadata.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str \| None` | `null` | Fetch and extract from URL |
| `html` | `str \| None` | `null` | Extract from HTML string |
| `raw_text` | `str \| None` | `null` | Extract from plain text |
| `extraction_targets` | `list[str]` | `[]` | Limit extraction: `emails`, `phones`, `prices`, `faq`, `contacts`, `tables`, `json_ld`, `opengraph` (empty = all) |

*Requires at least one of `url`, `html`, or `raw_text`.*

**Risk:** low

**Examples:**
```json
{"url": "https://example.com"}
{"raw_text": "Contact us at support@example.com. Price: $29."}
{"url": "https://example.com", "extraction_targets": ["emails", "phones"]}
```

---

### search_and_extract_pipeline

Run a search → extract pipeline in one tool call. Chains `web_search` and `web_extract_text` with partial-success handling.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `topics` | `list[str]` | `[]` | Search topics to query |
| `seed_urls` | `list[str]` | `[]` | Skip search; extract from these URLs directly |
| `max_results` | `int` | `10` | Max search results (1–50) |
| `deduplicate` | `bool` | `true` | Deduplicate by URL |
| `freshness` | `Literal` | `"recent"` | `any` · `recent` · `day` · `week` · `month` · `year` |

*Requires either `topics` or `seed_urls`.*

**Risk:** low

**Examples:**
```json
{"topics": ["python packaging"], "max_results": 5}
{"seed_urls": ["https://docs.python.org/3/"], "deduplicate": true}
```

---

### run_command

Execute shell commands through a controlled, sandboxed interface. Dangerous patterns (e.g. `rm -rf`, `format`, `shutdown`) are blocked.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `command` | `str` | required | Shell command to run |
| `working_directory` | `str \| None` | `null` | Working directory (workspace-relative or absolute) |
| `timeout_seconds` | `int` | `30` | Execution timeout (1–300) |
| `shell` | `Literal` | `"auto"` | `auto` · `powershell` · `cmd` · `bash` · `sh` |
| `environment` | `dict[str,str]` | `{}` | Additional environment variables |
| `capture_output` | `bool` | `true` | Capture stdout/stderr |
| `dry_run` | `bool` | `false` | Preview command without executing |

**Risk:** high · **Destructive:** yes · **Dry run:** yes

**Blocked patterns:** `rm -rf`, `del /f /s`, `format c:`, `shutdown`, raw `/dev/sd` writes

**Examples:**
```json
{"command": "python --version"}
{"command": "npm test", "working_directory": ".", "dry_run": true}
{"command": "dir", "shell": "cmd", "timeout_seconds": 10}
```

---

## 7. Agent System

Agents are defined in `agents/*.md`. Each file is a system-prompt document loaded by the orchestrator bridge.

| Agent | File | Role |
|-------|------|------|
| Orchestrator | `orchestrator.md` | Coordinates the other agents; dispatches sub-tasks |
| Researcher | `researcher.md` | Web search, RSS, URL extraction |
| Coder | `coder.md` | Code generation, shell execution |
| Analyst | `analyst.md` | Data processing, JSON transformation |
| Writer | `writer.md` | Report drafting, HTML generation |
| Reviewer | `reviewer.md` | Quality checks, validation |
| Publisher | `publisher.md` | File writing, artifact packaging |
| Cleanup | `cleanup.md` | Temporary file removal, workspace tidy |

### Agent skills

Design-system knowledge for the Writer/Publisher agents:

```
agents/skills/uiux/
  palettes.json   # named color palettes
  styles.json     # typography + spacing presets
```

These are referenced by `html_report_generator` via `palette_id` and `style_id`.

---

## 8. Engine Internals

### EngineRunner (`engine/runner.py`)

The main orchestration loop. Per job:

1. Receives `user_input` + `session_id` / `job_id`
2. Sends prompt to LLM via `OrchestratorBridge`
3. Parses tool calls from the response
4. Dispatches tool calls via `ParallelToolExecutor` (up to 4 concurrent)
5. Injects tool results back into the conversation
6. Repeats until a completion condition is met (max `max_loops=30`)

**Completion guards** (`_is_effective_nontrivial_completion`):
- Blocks `direct_answer` if the LLM claims it wrote a file but `write_file` was not actually called
- `no_effect_fail` after `max_no_tool_retries` loops with no tool calls

**Rate limit handling:**
- On 429/rate-limit: `initial_wait=300s`, `max_wait=28800s` (8h), configurable backoff
- Actions: `pause` · `stop` · `try_different_model`

### SessionManager (`engine/session_manager.py`)

Manages the per-job workspace directory:
- `write_artifact(path, content)` — writes to `workspace/<job_id>/artifacts/`
- `log_product_output(text)` — writes LLM prose to `final_output.md` (or `final_response.md` if `final_output.md` already exists — preserving tool-written content)
- `log_tool_call(name, args, result)` — logs to `artifacts/logs/tools/`

### ParallelExecutor (`engine/parallel_executor.py`)

Runs multiple independent tool calls concurrently using a thread pool. Max parallelism defaults to 4 (configurable via `config.json`).

### SelfHealingEngine (`engine/self_healing.py`)

Monitors tool errors and retries transient failures. Logs recovery events to `logs/self_healing.jsonl`.

---

## 9. Backend API Reference

Base URL: `http://localhost:7900`

### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/auth/login` | No | Get session token (rate-limited: 5 failures/IP/15 min) |
| `POST` | `/api/auth/logout` | Yes | Revoke sessions |
| `GET` | `/api/auth/verify` | No | Check token |
| `GET` | `/api/auth/me` | Yes | Current user |

### Jobs

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/jobs` | Yes | List jobs (supports `?status=`, `?q=`, `?limit=`) |
| `POST` | `/api/jobs` | Yes | Create job |
| `GET` | `/api/jobs/{id}` | Yes | Get job status |
| `DELETE` | `/api/jobs/{id}` | Yes | Archive + delete |
| `POST` | `/api/jobs/{id}/start` | Yes | Start/resume |
| `POST` | `/api/jobs/{id}/stop` | Yes | Stop |
| `POST` | `/api/jobs/{id}/pause` | Yes | Pause |
| `POST` | `/api/jobs/{id}/resume` | Yes | Resume |
| `POST` | `/api/jobs/{id}/restart` | Yes | Re-queue |
| `GET` | `/api/jobs/{id}/output` | Yes | Download final output as plain text |
| `POST` | `/api/jobs/{id}/clone` | Yes | Clone job (copy prompt; optionally auto-start) |
| `POST` | `/api/jobs/{id}/retry` | Yes | Retry a failed/completed job with optional new prompt |

#### Job filtering (`GET /api/jobs`)

| Query param | Type | Description |
|-------------|------|-------------|
| `status` | `str` | Filter by status: `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, … |
| `q` | `str` | Case-insensitive substring match on title or prompt |
| `limit` | `int` | Max results (default 200) |

#### CloneJobRequest

```json
{"title": "Clone of my job", "prompt": "optional override", "auto_start": true}
```

#### RetryJobRequest

```json
{"prompt": "optional new prompt — falls back to original if omitted"}
```

### Tools

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/tools` | Yes | List all registered tools with schema |
| `GET` | `/api/tools/{name}` | Yes | Get a single tool schema by name |

`GET /api/tools` response:
```json
{"count": 23, "tools": [{"name": "web_search", "description": "...", "risk_level": "low", ...}]}
```

### Stats

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/stats` | Yes | System statistics snapshot |

`GET /api/stats` returns:
```json
{
  "server_started_at": "2026-05-21T10:00:00",
  "uptime_seconds": 3600,
  "jobs": {
    "total": 42,
    "by_status": {"COMPLETED": 38, "FAILED": 3, "RUNNING": 1},
    "success_rate": 0.926,
    "total_tool_calls": 317,
    "total_artifacts": 84
  },
  "tools": {"registered": 23},
  "queue": {"running": 1, "queued": 0}
}
```

### Artifacts

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/artifacts/{job_id}` | Yes | List job artifacts |
| `GET` | `/api/artifacts/{job_id}/{path}` | Yes | Download artifact file |

### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/health` | No | System health + provider API key status |

### Events (SSE)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/events/{job_id}` | Yes | Server-sent events stream for job |

---

## 10. Adding a New Tool

### 1. Create the tool file

```
tool_gateway/tools/my_tool.py
```

Minimum structure:

```python
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from .base import BaseTool
from .web_common import make_metadata  # if needed

class MyToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    param: str = Field(..., description="Required parameter")
    option: int = Field(10, ge=1, le=100, description="Optional with default")

class MyTool(BaseTool):
    name = "my_tool"
    description = "One-line description of what the tool does"
    risk_level = "low"          # "low" | "medium" | "high"
    destructive = False
    supports_dry_run = False
    input_model = MyToolArgs
    examples = [
        {"tool_name": "my_tool", "arguments": {"param": "hello"}},
    ]

    def execute(self, args: MyToolArgs) -> dict[str, Any]:
        # ... do work ...
        return {
            "result": "...",
            "_warnings": [],
            "_metadata": make_metadata(
                partial_success=False,
                fallbacks_used=[],
                inferred_values={},
            ),
        }
```

### 2. Export from `__init__.py`

```python
# tool_gateway/tools/__init__.py
from .my_tool import MyTool
```

### 3. Register in `registry.py`

```python
from .tools.my_tool import MyTool
registry.register_tool(MyTool())
```

### 4. Add to `validator.py`

```python
# In _ALLOWED_KEYS_BY_TOOL:
"my_tool": ["param", "option"],

# In _EXAMPLES_BY_TOOL:
"my_tool": {
    "tool_name": "my_tool",
    "arguments": {"param": "hello"},
},
```

### 5. Add to `normalizer.py`

Add any alias mappings (e.g. `"parameter"` → `"param"`) to the normalizer's alias table if needed.

### 6. Register in engine

```python
# engine/tool_executor.py — add to TOOL_CLASS_MAP:
"my_tool": MyTool,
```

### 7. Write tests

Add a test in `tests/` following the existing pattern, and add a direct smoke-test entry in `scripts/test_tools_direct.py`.

### 8. Verify

```bash
python -m pytest tests/ -q
python scripts/test_tools_direct.py
```

---

## 11. Testing

### Unit tests (pytest)

```bash
python -m pytest tests/ -q
# Expected: 67 passed (all new tools are covered by test_tool_theme_contract.py and test_validation.py)
```

Key test files:

| File | Coverage |
|------|----------|
| `test_registry.py` | Tool registration |
| `test_validation.py` | Argument validation edge cases |
| `test_tool_call_parsing.py` | LLM output parsing |
| `test_tool_executor_runtime_context.py` | Workspace path injection |
| `test_tool_theme_contract.py` | TOOL_THEME.md conformance for all 23 tools |
| `test_runner_completion_guards.py` | Completion mode logic |
| `test_shell_runner.py` | Shell tool safety + dry run |
| `test_write_file_tool.py` | File write + path validation |
| `test_web_search_tool.py` | Web search result normalization |
| `test_artifacts_primary_output.py` | Artifact file routing |
| `test_job_archive_sync.py` | Job archive behavior |
| `test_model_fallback_policy.py` | Multi-provider fallback |

### Direct tool smoke tests

Bypasses the full pipeline and calls each tool directly:

```bash
python scripts/test_tools_direct.py
# Expected: 38/38 pass (all 17 tools × ~2 cases each)
```

### End-to-end API tests

Submits real jobs to a running server and validates outputs:

```bash
# Server must be running first:
python scripts/run_webui.py

# In another terminal:
python scripts/test_api_e2e.py
# Expected: 11 passed, 0 failed / 11 total
```

Test groups:
1. **Utility Tools** — calculator + write_file, json_transform
2. **Basic Web Tools** — web_fetch + web_extract_text, web_search, rss_read
3. **Image Tools** — web_extract_images + image_scraper
4. **Extraction Tools** — semantic_content_extractor, intelligent_theme_scraper + web_code_scraper
5. **Report Generation** — html_report_generator, dynamic_browser + search_and_extract_pipeline
6. **System Tools** — run_command

---

## 12. Configuration

`config.json` at the workspace root. Key sections:

### Providers

```json
"providers": {
  "active": "gemini",
  "anthropic": {"model": "claude-opus-4-5", "api_key_env": "ANTHROPIC_API_KEY"},
  "gemini":    {"model": "gemini-2.5-flash", "api_key_env": "GOOGLE_GEMINI_API_KEY"},
  "openai":    {"model": "gpt-4o", "api_key_env": "OPENAI_API_KEY"}
}
```

`providers.active` controls which provider is used for new jobs.

### Orchestration

```json
"orchestration": {
  "max_loops": 30,
  "parallel": {"max_concurrent_jobs": 3, "max_concurrent_tools": 4},
  "model_fallback_policy": {"fallback_provider_order": ["anthropic", "gemini", "openai"]},
  "rate_limit": {
    "initial_wait_s": 300,
    "max_wait_s": 28800,
    "action": "pause"
  }
}
```

### Validating config.json

```bash
python scripts/validate_config.py
# Or check a different file:
python scripts/validate_config.py path/to/config.json
```

Exit codes: `0` = valid, `1` = errors found, `2` = file not found / JSON parse error.

---

## 13. Frontend UI Guide

The WebUI (`frontend/index.html`) uses a CRT-style terminal aesthetic: dark green monospace text, scanline overlay, blinking cursor.

### Tabs

| Tab | Description |
|-----|-------------|
| EXECUTION | Live streaming log of the current job's agent + tool activity |
| RESULT | Final job output — rendered from `final_output.md` or `final_response.md` |
| FILES | Workspace artifact browser for the selected job |
| TOOLS | Browsable catalog of all 23 registered tools with search and schema details |

### Sidebar

- **Job list** — click any job to select it and load its detail
- **Search bar** — type to filter the job list by title or status in real time
- **Job duration badge** — completed/failed jobs show elapsed time (e.g. `⏱ 12s`); running jobs show a live timer

### Job Controls

Control bar buttons appear for the selected job:

| Button | Action |
|--------|--------|
| ▶ START | Start / resume a queued job |
| ■ STOP | Stop a running job |
| ⏸ PAUSE | Pause a running job |
| ⏵ RESUME | Resume a paused job |
| ↺ RESTART | Re-queue a completed or failed job |
| ⧉ CLONE | Copy the job's prompt into a new job form (auto-fills title and prompt) |
| 🗑 DELETE | Archive and remove the job |

### TOOLS Tab

- Lists all 23 registered tools with name, description, risk level, and argument summary
- **Search box** filters tools by name or description as you type
- Tool cards are color-coded by risk: green (low), yellow (medium), red (high)
- Destructive tools have a red left border
- Count badge shows total registered tools

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `N` | Open the New Job modal (only when no text input is focused) |
| `Ctrl+Enter` | Submit the New Job form (when the form is open) |
| `Escape` | Close any open modal |

---

## 14. Scripts Reference

### `scripts/run_webui.py`

Main entry point for the WebUI server.

```bash
python scripts/run_webui.py
# Default port: 7900
# Override: PORT=8080 python scripts/run_webui.py
```

On startup:
1. Loads `.env` from the project root (if present) — sets environment variables without overwriting existing ones
2. Checks for at least one API key (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`) and prints a warning if none are found
3. Starts Uvicorn on `0.0.0.0:<port>`

### `scripts/validate_config.py`

Validate `config.json` against the expected schema.

```bash
python scripts/validate_config.py              # validates config.json in project root
python scripts/validate_config.py my.json     # validates a different file
```

Checks:
- `providers` is an object with `active` and at least the three known providers
- Each provider has `model`, `available_models`, `api_key_env`
- `providers.active` matches a known provider
- Active provider's `model` is listed in `available_models`
- API key environment variables are set (warning only)
- Orchestration numeric fields have correct types
- Unknown top-level keys (warning only)

Exit codes: `0` = valid (possibly with warnings), `1` = errors, `2` = file not found / JSON error.

### `scripts/test_tools_direct.py`

Direct smoke-test for all tools (bypasses the full pipeline).

```bash
python scripts/test_tools_direct.py
```

### `scripts/test_api_e2e.py`

End-to-end API tests. Requires a running server.

```bash
python scripts/run_webui.py &
python scripts/test_api_e2e.py
```

### Quality gates

```json
"quality": {
  "min_test_coverage": 80,
  "require_security_scan": true,
  "max_tool_response_time_seconds": 30
}
```

### Environment variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Gemini provider key |
| `ANTHROPIC_API_KEY` | Anthropic/Claude provider key |
| `OPENAI_API_KEY` | OpenAI provider key |
| `OVERLORD11_AUTH_DISABLED` | Set to `1` to bypass authentication (dev only) |
| `OVERLORD11_TASK_DIR` | Injected at runtime per-job — do not set manually |
