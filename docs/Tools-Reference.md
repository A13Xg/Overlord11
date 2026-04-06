# Tools Reference

Complete reference for all Overlord11 tools — parameters, return values, and CLI examples.

---

## File System Tools

### `read_file`

**Schema:** `tools/defs/read_file.json`  
**Implementation:** `tools/python/read_file.py`

Read the full contents of a file. Supports optional line-range pagination for large files.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | ✓ | Absolute or relative path to the file |
| `encoding` | string | | File encoding (default: `utf-8`) |
| `start_line` | integer | | 1-based line number to start reading from |
| `end_line` | integer | | 1-based line number to stop reading at (inclusive) |

**Returns:** File content as a string, or an error message.

```bash
python tools/python/read_file.py --path config.json
python tools/python/read_file.py --path README.md --start_line 1 --end_line 30
```

---

### `write_file`

**Schema:** `tools/defs/write_file.json`  
**Implementation:** `tools/python/write_file.py`

Write content to a file. Creates parent directories automatically.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | ✓ | Path to write to |
| `content` | string | ✓ | Content to write |
| `mode` | string | | `overwrite` (default) or `append` |
| `encoding` | string | | File encoding (default: `utf-8`) |

```bash
python tools/python/write_file.py --path output/report.md --content "# Report" --mode overwrite
```

---

### `list_directory`

**Schema:** `tools/defs/list_directory.json`  
**Implementation:** `tools/python/list_directory.py`

List directory contents with metadata (size, type, modification time).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | ✓ | Directory path to list |
| `recursive` | boolean | | Include subdirectories (default: `false`) |
| `include_hidden` | boolean | | Include hidden files (default: `false`) |

```bash
python tools/python/list_directory.py --path tools/python/
```

---

### `glob`

**Schema:** `tools/defs/glob_tool.json`  
**Implementation:** `tools/python/glob_tool.py`

Find files matching a glob pattern.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pattern` | string | ✓ | Glob pattern (e.g., `**/*.py`, `src/**/*.ts`) |
| `base_path` | string | | Root directory for the search (default: current dir) |

```bash
python tools/python/glob_tool.py --pattern "**/*.py" --base_path tools/
python tools/python/glob_tool.py --pattern "agents/*.md"
```

---

### `search_file_content`

**Schema:** `tools/defs/search_file_content.json`  
**Implementation:** `tools/python/search_file_content.py`

Ripgrep-powered regex search across files.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pattern` | string | ✓ | Regex or literal search pattern |
| `path` | string | | Root path to search in (default: current dir) |
| `file_pattern` | string | | Glob filter for file names (e.g., `*.py`) |
| `case_sensitive` | boolean | | Default: `false` |
| `max_results` | integer | | Maximum matches to return |
| `context_lines` | integer | | Lines of context around each match |

```bash
python tools/python/search_file_content.py --pattern "def main" --path tools/python/
python tools/python/search_file_content.py --pattern "TODO" --path . --file_pattern "*.py"
```

---

### `replace`

**Schema:** `tools/defs/replace.json`  
**Implementation:** `tools/python/replace.py`

Precise find-and-replace within a file.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | ✓ | File to modify |
| `old_str` | string | ✓ | Exact string to find (must be unique in the file) |
| `new_str` | string | ✓ | Replacement string |

---

## Execution Tools

### `run_shell_command`

**Schema:** `tools/defs/run_shell_command.json`  
**Implementation:** `tools/python/run_shell_command.py`

Execute shell commands with timeout and output capture.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `command` | string | ✓ | Shell command to execute |
| `cwd` | string | | Working directory (default: project root) |
| `timeout` | integer | | Timeout in seconds (default: 60) |
| `env` | object | | Additional environment variables |

```bash
python tools/python/run_shell_command.py --command "python --version"
python tools/python/run_shell_command.py --command "pip install requests" --timeout 120
```

---

### `git_tool`

**Schema:** `tools/defs/git_tool.json`  
**Implementation:** `tools/python/git_tool.py`

Git operations: status, diff, commit, push, and branch management.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | ✓ | `status`, `diff`, `add`, `commit`, `push`, `log`, `branch`, `checkout` |
| `path` | string | | Repository path (default: current dir) |
| `message` | string | | Commit message (for `commit` action) |
| `files` | array | | Files to add (for `add` action) |
| `branch` | string | | Branch name (for `branch`/`checkout`) |

```bash
python tools/python/git_tool.py --action status
python tools/python/git_tool.py --action commit --message "Add feature X"
python tools/python/git_tool.py --action log --path .
```

---

### `calculator`

**Schema:** `tools/defs/calculator.json`  
**Implementation:** `tools/python/calculator.py`

Evaluate math expressions, perform statistics, and convert units.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `expression` | string | ✓ | Math expression or statistical function call |

**Supported operations:**
- Arithmetic: `2 + 3 * 4`, `sqrt(144)`, `log(100, 10)`
- Statistics: `mean([1,2,3,4,5])`, `stdev([10,20,30])`
- Unit conversion: handled via expressions

```bash
python tools/python/calculator.py --expression "sqrt(144)"
python tools/python/calculator.py --expression "mean([10, 20, 30, 40])"
```

---

### `scaffold_generator`

**Implementation:** `tools/python/scaffold_generator.py`

Generate project scaffolding from templates.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `--template` | string | ✓ | Template name: `python_cli`, `python_api`, `node_api` |
| `--name` | string | ✓ | Project name |
| `--output` | string | ✓ | Output directory |

```bash
python tools/python/scaffold_generator.py --template python_cli --name my_tool --output ./new_project
python tools/python/scaffold_generator.py --list-templates
```

---

## Web Tools

### `web_fetch`

**Schema:** `tools/defs/web_fetch.json`  
**Implementation:** `tools/python/web_fetch.py`

HTTP GET with automatic HTML-to-Markdown conversion.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | ✓ | URL to fetch |
| `output_format` | string | | `markdown` (default), `text`, `json`, `raw_html` |
| `timeout` | integer | | Request timeout in seconds (default: 30) |
| `follow_redirects` | boolean | | Follow HTTP redirects (default: `true`) |

```bash
python tools/python/web_fetch.py --url https://docs.python.org/3/
python tools/python/web_fetch.py --url https://api.example.com/data --output_format json
```

---

### `web_scraper`

**Schema:** `tools/defs/web_scraper.json`  
**Implementation:** `tools/python/web_scraper.py`

Advanced web scraper with intelligent content detection, cascading fetch pipeline, and smart image scoring.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | ✓ | See actions table below |
| `url` | string | | Target URL |
| `analysis_goal` | string | | Goal description for `analyze_content` |
| `extract_mode` | string | | `auto`, `full`, `article`, `images_only`, `structured`, `raw` |
| `smart_images` | boolean | | Enable image relevance scoring (default: `false`) |
| `min_image_score` | number | | Minimum relevance score 0.0–1.0 (default: `0.4`) |
| `max_images` | integer | | Max images to process (default: 20) |
| `query` | string | | Search query (for `search` action) |
| `max_results` | integer | | Max search results (default: 10) |
| `wait_for_js` | boolean | | Use Selenium for JS rendering (default: `true`) |
| `wait_timeout` | integer | | Page load timeout in seconds (default: 15) |

**Actions:**

| Action | Description |
|--------|-------------|
| `analyze_content` | **Recommended.** Returns structured package: summary, full text, images, tables, and a ready-to-use `llm_prompt` field |
| `detect_type` | Classify the page type (article, docs, product, etc.) |
| `scrape_full` | Full page extraction with chosen `extract_mode` |
| `extract_article` | Extract article body, title, author, and publication date |
| `extract_text` | Plain text extraction only |
| `download_images` | Download images, optionally with smart relevance scoring |
| `analyze_structure` | Return page structure (headings, links, tables) |
| `summarize` | Return a brief page summary |
| `validate_url` | Check if the URL is accessible |
| `search` | Perform a web search |
| `find_feeds` | Discover RSS/Atom feeds on a page |
| `parse_feed` | Parse an RSS/Atom feed |

```bash
python tools/python/web_scraper.py --action analyze_content --url "https://example.com" --analysis_goal "Extract key findings"
python tools/python/web_scraper.py --action download_images --url "https://example.com" --smart_images true --min_image_score 0.5
python tools/python/web_scraper.py --action search --query "Python testing frameworks" --max_results 10
```

---

## Analysis & Memory Tools

### `code_analyzer`

**Schema:** `tools/defs/code_analyzer.json`  
**Implementation:** `tools/python/code_analyzer.py`

Static analysis for bugs, security issues, complexity, and style.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | ✓ | File or directory to analyze |
| `checks` | array | | Checks to run: `bugs`, `security`, `complexity`, `style`, `all` (default) |
| `max_complexity` | integer | | Complexity threshold (default: 10) |

```bash
python tools/python/code_analyzer.py --path tools/python/
python tools/python/code_analyzer.py --path tools/python/web_scraper.py --checks security
```

---

### `project_scanner`

**Schema:** `tools/defs/project_scanner.json`  
**Implementation:** `tools/python/project_scanner.py`

Codebase structure analysis, language detection, and entry point discovery.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | ✓ | Project root to scan |
| `depth` | integer | | Max directory depth (default: 4) |
| `include_stats` | boolean | | Include line count statistics (default: `true`) |

```bash
python tools/python/project_scanner.py --path .
python tools/python/project_scanner.py --path . --depth 2
```

---

### `save_memory`

**Schema:** `tools/defs/save_memory.json`  
**Implementation:** `tools/python/save_memory.py`

Persist facts to `Consciousness.md` for cross-session continuity.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `key` | string | ✓ | Memory entry identifier |
| `value` | string | ✓ | Content to persist |
| `priority` | string | | `CRITICAL`, `HIGH`, `NORMAL` (default), `PERSISTENT` |
| `ttl` | string | | Time-to-live (e.g., `7d`, `24h`, `persistent`) |

```bash
python tools/python/save_memory.py --key "project_goal" --value "Build provider-agnostic toolset"
python tools/python/save_memory.py --key "api_limit" --value "Rate limited until 14:00" --priority CRITICAL --ttl 2h
```

---

### `publisher_tool`

**Schema:** `tools/defs/publisher_tool.json`  
**Implementation:** `tools/python/publisher_tool.py`

Generate themed, fully self-contained HTML reports from Markdown or plain text content.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `--title` | string | ✓ | Report title |
| `--content` | string | ✓ | Input file path (Markdown or plain text) |
| `--theme` | string | | Visual theme (default: `auto`) — see [Output Tiers](Output-Tiers.md) |
| `--output` | string | | Output file path (default: auto-generated in `workspace/`) |

```bash
python tools/python/publisher_tool.py --title "Q1 Analysis" --content report.md --theme modern
python tools/python/publisher_tool.py --title "Security Audit" --content audit.txt --theme tactical --output reports/audit.html
python tools/python/publisher_tool.py --title "Auto Theme Test" --content data.md
```

---

## Session & Log Tools

### `session_manager`

**Implementation:** `tools/python/session_manager.py`

Manage work sessions with unique IDs and track agent activity.

| Action | Description |
|--------|-------------|
| `create` | Create a new session |
| `status` | Get session details |
| `log_change` | Log a file change within a session |
| `log_agent` | Record agent usage |
| `log_tool` | Record tool usage |
| `add_note` | Add a free-text note |
| `close` | Close a session with a summary |
| `list` | List all sessions |
| `active` | Get the current active session |

```bash
python tools/python/session_manager.py --action create --description "Implement user auth"
python tools/python/session_manager.py --action list
python tools/python/session_manager.py --action close --session_id 20260215_120000
```

---

### `log_manager`

**Implementation:** `tools/python/log_manager.py`

Central logging system for tool invocations and agent decisions (JSONL format).

```bash
python tools/python/log_manager.py --action summary --session_id 20260215_120000
python tools/python/log_manager.py --action query --session_id 20260215_120000
```

---

## Design System Tools

### `ui_design_system`

**Schema:** `tools/defs/ui_design_system.json`
**Implementation:** `tools/python/ui_design_system.py`

Generate a complete UI/UX design system specification. 10 styles × 10 palettes = 100 combinations.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `style_id` | string | | Style identifier (e.g., `brutalist`, `glassmorphism`) |
| `palette_id` | string | | Palette identifier (e.g., `midnight-ink`, `neon-city`) |
| `stack` | string | | Tech stack: `html-tailwind`, `html-css`, `react`, `nextjs`, `vue`, `svelte` |
| `page` | string | | Page name for per-page overrides |
| `project_name` | string | | Used for deterministic default selection |
| `output_format` | string | | `md` (default) or `json` |
| `persist` | boolean | | Write `design-system/MASTER.md` to disk (default: `false`) |

```bash
python tools/python/ui_design_system.py --style_id brutalist --palette_id neon-city --stack react --persist true
python tools/python/ui_design_system.py --project_name "MyApp"
```

---

## Project Management Tools

### `task_manager`

**Schema:** `tools/defs/task_manager.json`
**Implementation:** `tools/python/task_manager.py`

Manage tasks in `TaskingLog.md` with T-NNN IDs, checkboxes, and subtasks.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | ✓ | `create`, `update`, `list`, `complete`, `delete` |
| `task_id` | string | | Task ID (e.g., `T-001`) — required for update/complete/delete |
| `title` | string | | Task title — required for create |
| `status` | string | | Status update: `todo`, `in_progress`, `done`, `blocked` |
| `session_id` | string | | Session ID for logging |

```bash
python tools/python/task_manager.py --action create --title "Implement auth" --session_id 20260315_120000
python tools/python/task_manager.py --action update --task_id T-001 --status in_progress
python tools/python/task_manager.py --action list
```

---

### `error_logger`

**Schema:** `tools/defs/error_logger.json`
**Implementation:** `tools/python/error_logger.py`

Log errors to `ErrorLog.md` with severity, attempts, and resolution tracking.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | ✓ | `log`, `resolve`, `list` |
| `error` | string | | Error description — required for log |
| `severity` | string | | `low`, `medium`, `high`, `critical` (default: `medium`) |
| `resolution` | string | | Resolution description — required for resolve |
| `session_id` | string | | Session ID for logging |

```bash
python tools/python/error_logger.py --action log --error "API timeout on fetch" --severity high
python tools/python/error_logger.py --action resolve --error "API timeout" --resolution "Added retry logic"
```

---

### `project_docs_init`

**Schema:** `tools/defs/project_docs_init.json`
**Implementation:** `tools/python/project_docs_init.py`

Initialize the 5 standardized project files in a sandboxed project directory.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | ✓ | Project root to initialize |
| `project_name` | string | | Project name (auto-detected from directory if omitted) |
| `session_id` | string | | Session ID for logging |

Creates: `ProjectOverview.md`, `Settings.md`, `TaskingLog.md`, `AInotes.md`, `ErrorLog.md`

```bash
python tools/python/project_docs_init.py --path ./my_project --project_name "My Project"
```

---

### `cleanup_tool`

**Schema:** `tools/defs/cleanup_tool.json`
**Implementation:** `tools/python/cleanup_tool.py`

Pre-deployment scan: detect hardcoded secrets, remove temp files, validate project structure.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | ✓ | Project root to scan |
| `action` | string | | `full_scan`, `secrets_only`, `temp_only`, `structure_only` (default: `full_scan`) |
| `fix` | boolean | | Auto-fix safe issues like temp file removal (default: `false`) |
| `session_id` | string | | Session ID for logging |

```bash
python tools/python/cleanup_tool.py --path . --action full_scan
python tools/python/cleanup_tool.py --path . --action secrets_only
python tools/python/cleanup_tool.py --path . --action temp_only --fix true
```

---

### `launcher_generator`

**Schema:** `tools/defs/launcher_generator.json`
**Implementation:** `tools/python/launcher_generator.py`

Generate `run.py` (ASCII title, color menu, concurrent mode) + `run.bat` + `run.command` for Python projects.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | ✓ | Project root to generate launchers in |
| `project_name` | string | ✓ | Project name (used in ASCII title) |
| `modes` | array | | List of run modes for the menu (default: auto-detect) |
| `session_id` | string | | Session ID for logging |

```bash
python tools/python/launcher_generator.py --path ./my_project --project_name "My App"
```

---

## Error Handling & Recovery Tools

### `error_handler`

**Schema:** `tools/defs/error_handler.json`
**Implementation:** `tools/python/error_handler.py`

Catch, classify, and recover from tool execution errors with retry logic.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `error` | string | ✓ | Error message or traceback |
| `tool_name` | string | | Tool that produced the error |
| `context` | string | | Additional context about what was being attempted |
| `session_id` | string | | Session ID for logging |

```bash
python tools/python/error_handler.py --error "FileNotFoundError: config.json" --tool_name read_file
```

---

### `consciousness_tool`

**Schema:** `tools/defs/consciousness_tool.json`
**Implementation:** `tools/python/consciousness_tool.py`

Read, query, and manage entries in `Consciousness.md` programmatically.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | ✓ | `read`, `query`, `add`, `resolve`, `list_active` |
| `section` | string | | Target section (e.g., `signals`, `wip`, `handoffs`, `errors`) |
| `query` | string | | Search term for query action |
| `entry` | string | | Entry content for add action |
| `session_id` | string | | Session ID for logging |

```bash
python tools/python/consciousness_tool.py --action list_active
python tools/python/consciousness_tool.py --action query --query "rate limit"
```

---

### `response_formatter`

**Schema:** `tools/defs/response_formatter.json`
**Implementation:** `tools/python/response_formatter.py`

Format agent responses into structured output (sections, tables, summaries).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `content` | string | ✓ | Raw content to format |
| `format` | string | | Output format: `sections`, `table`, `summary`, `bullet` (default: `sections`) |
| `session_id` | string | | Session ID for logging |

```bash
python tools/python/response_formatter.py --content "Raw analysis output..." --format summary
```

---

### `file_converter`

**Schema:** `tools/defs/file_converter.json`
**Implementation:** `tools/python/file_converter.py`

Convert files between formats (JSON, CSV, YAML, Markdown).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `input_path` | string | ✓ | Input file path |
| `output_format` | string | ✓ | Target format: `json`, `csv`, `yaml`, `md` |
| `output_path` | string | | Output file path (auto-generated if omitted) |
| `session_id` | string | | Session ID for logging |

```bash
python tools/python/file_converter.py --input_path data.json --output_format csv
python tools/python/file_converter.py --input_path report.csv --output_format md --output_path report.md
```

---

## Automation & Vision Tools

### `computer_control`

**Schema:** `tools/defs/computer_control.json`
**Implementation:** `tools/python/computer_control.py`

Desktop automation: mouse control, keyboard input, window management, screenshots.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | ✓ | `click`, `type`, `screenshot`, `move`, `scroll`, `key_press`, `window_list` |
| `x` | integer | | X coordinate (for click/move) |
| `y` | integer | | Y coordinate (for click/move) |
| `text` | string | | Text to type (for type action) |
| `key` | string | | Key to press (for key_press action) |
| `session_id` | string | | Session ID for logging |

```bash
python tools/python/computer_control.py --action screenshot
python tools/python/computer_control.py --action window_list
```

---

### `vision_tool`

**Schema:** `tools/defs/vision_tool.json`
**Implementation:** `tools/python/vision_tool.py`

Image analysis: OCR, object detection, screenshot interpretation.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `image_path` | string | ✓ | Path to the image file |
| `action` | string | | `analyze`, `ocr`, `describe` (default: `analyze`) |
| `session_id` | string | | Session ID for logging |

```bash
python tools/python/vision_tool.py --image_path screenshot.png --action ocr
python tools/python/vision_tool.py --image_path ui_mockup.png --action describe
```

---

## Code Execution Tools

### `execute_python`

**Schema:** `tools/defs/execute_python.json`
**Implementation:** `tools/python/execute_python.py`

Execute arbitrary Python code in a sandboxed environment with timeout enforcement and output capture. Uses AST-based static analysis to block dangerous operations (`os`, `sys`, `subprocess`, file I/O, etc.) before any code runs. Output is captured from stdout/stderr.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `code` | string | ✓ | Python source code to execute |
| `timeout` | integer | | Maximum execution time in seconds (default: `30`) |
| `allow_network` | boolean | | If `true`, network modules (urllib, requests) are permitted (default: `false`) |

**Returns:**

```json
{
  "status": "success",
  "stdout": "4\n",
  "stderr": "",
  "returncode": 0,
  "duration_ms": 12.5
}
```

**Available in sandbox:** `math`, `json`, `re`, `datetime`, `collections`, `itertools`, `functools`, `string`, and all safe built-ins (`abs`, `len`, `range`, `print`, etc.).

**Blocked in sandbox:** `os`, `sys`, `subprocess`, `importlib`, `shutil`, `socket`, `threading`, `multiprocessing`, `open`, `exec`, `eval`, `__import__`, and all network modules when `allow_network=false`.

```bash
python tools/python/execute_python.py --code "print(2 ** 10)"
python tools/python/execute_python.py --code "import math; print(math.factorial(10))" --timeout 5
```

---

## Utility Tools

### `datetime_tool`

**Schema:** `tools/defs/datetime_tool.json`  
**Implementation:** `tools/python/datetime_tool.py`

Parse, format, calculate, and convert dates and times. Pure stdlib — zero external dependencies.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | ✓ | `now`, `parse`, `format`, `add`, `subtract`, `diff`, `convert`, `timestamp`, `validate` |
| `input` | string | | Date/time string to operate on (ISO 8601, `MM/DD/YYYY`, natural formats) |
| `start` | string | | Start datetime for `diff` action |
| `end` | string | | End datetime for `diff` action |
| `output_format` | string | | strftime format string for `format` action |
| `days` | number | | Days to add/subtract |
| `hours` | number | | Hours to add/subtract |
| `minutes` | number | | Minutes to add/subtract |
| `seconds` | number | | Seconds to add/subtract |
| `weeks` | number | | Weeks to add/subtract |
| `timezone_name` | string | | Target timezone for `convert` (`UTC`, `UTC+5`, `America/New_York`) |
| `unix_timestamp` | number | | Unix epoch for `timestamp` action |

```bash
python tools/python/datetime_tool.py --action now
python tools/python/datetime_tool.py --action diff --start "2026-01-01" --end "2026-04-06"
python tools/python/datetime_tool.py --action add --input "2026-04-06" --days 30
```

---

### `http_request`

**Schema:** `tools/defs/http_request.json`  
**Implementation:** `tools/python/http_request.py`

Full-featured HTTP client for non-GET methods, authenticated requests, and structured request bodies. Use `web_fetch` for simple GET requests; use this for POST/PUT/PATCH/DELETE, auth tokens, or custom headers.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `method` | string | ✓ | `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS` |
| `url` | string | ✓ | Full URL including protocol |
| `headers` | object | | Custom HTTP headers |
| `params` | object | | URL query parameters |
| `json_body` | any | | Request body (auto-sets `Content-Type: application/json`) |
| `form_data` | object | | Form-encoded body |
| `body` | string | | Raw string body |
| `timeout_seconds` | integer | | Timeout in seconds (default: 30) |
| `follow_redirects` | boolean | | Follow redirects (default: `true`) |
| `auth_bearer` | string | | Bearer token for Authorization header |
| `auth_basic` | string | | Basic auth credentials as `username:password` |
| `return_format` | string | | `auto` (default), `json`, `text` |

```bash
python tools/python/http_request.py --method POST --url https://api.example.com/items --json_body '{"name":"test"}'
python tools/python/http_request.py --method GET --url https://api.example.com/data --auth_bearer mytoken123
```

---

### `json_tool`

**Schema:** `tools/defs/json_tool.json`  
**Implementation:** `tools/python/json_tool.py`

Parse, validate, query, transform, and format JSON data. Supports dot-notation path queries, deep merge, structural diff, and in-place set/delete.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | ✓ | `parse`, `validate`, `query`, `format`, `merge`, `diff`, `keys`, `set`, `delete` |
| `input` | string | | JSON string to operate on |
| `input_b` | string | | Second JSON string for `merge`/`diff` |
| `path` | string | | Dot-notation path (e.g., `users.0.name`) |
| `value` | string | | JSON-encoded value to set |
| `indent` | integer | | Indentation for `format` (default: 2; 0 = minified) |
| `recursive` | boolean | | Include nested keys for `keys` action (default: `true`) |
| `file` | string | | Path to JSON file (alternative to `input`) |
| `file_b` | string | | Path to second JSON file for `merge`/`diff` |

```bash
python tools/python/json_tool.py --action query --file config.json --path "providers.active"
python tools/python/json_tool.py --action format --input '{"a":1,"b":2}' --indent 4
python tools/python/json_tool.py --action diff --file config.json --file_b config.backup.json
```

---

### `hash_tool`

**Schema:** `tools/defs/hash_tool.json`  
**Implementation:** `tools/python/hash_tool.py`

Compute and verify cryptographic hashes for strings and files. Supports MD5, SHA-1, SHA-256, SHA-512, and SHA3-256.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | ✓ | `hash_string`, `hash_file`, `verify_file`, `compare` |
| `input` | string | | String to hash |
| `input_b` | string | | Second string for `compare` |
| `file` | string | | File to hash |
| `file_b` | string | | Second file for `compare` |
| `algorithm` | string | | `md5`, `sha1`, `sha256` (default), `sha512`, `sha3_256` |
| `expected` | string | | Expected hex hash for `verify_file` |
| `encoding` | string | | String encoding (default: `utf-8`) |

```bash
python tools/python/hash_tool.py --action hash_file --file config.json
python tools/python/hash_tool.py --action verify_file --file release.zip --expected abc123...
python tools/python/hash_tool.py --action compare --file_a v1.py --file_b v2.py
```

---

### `zip_tool`

**Schema:** `tools/defs/zip_tool.json`  
**Implementation:** `tools/python/zip_tool.py`

Create, extract, inspect, and modify ZIP archives.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | ✓ | `create`, `extract`, `list`, `add`, `remove`, `info` |
| `file` | string | | Path to ZIP archive |
| `output` | string | | Output archive path for `create` |
| `output_dir` | string | | Directory to extract into |
| `paths` | array | | Files/dirs to include (`create`/`add`) or filenames to delete (`remove`) |
| `compression` | string | | `deflate` (default), `store`, `bzip2`, `lzma` |
| `overwrite` | boolean | | Overwrite existing archive (default: `false`) |
| `password` | string | | Password for encrypted archives (extraction only) |

```bash
python tools/python/zip_tool.py --action create --output dist/project.zip --paths '["src/", "README.md"]'
python tools/python/zip_tool.py --action extract --file dist/project.zip --output_dir ./extracted
python tools/python/zip_tool.py --action list --file dist/project.zip
```

---

### `regex_tool`

**Schema:** `tools/defs/regex_tool.json`  
**Implementation:** `tools/python/regex_tool.py`

Test, extract, replace, and analyze regular expressions with structured output including capture groups and character spans.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | ✓ | `test`, `match`, `findall`, `extract`, `replace`, `split`, `validate` |
| `pattern` | string | ✓ | Python regex pattern |
| `input` | string | | String to operate on |
| `replacement` | string | | Replacement string for `replace` (supports `\1`, `\g<name>`) |
| `flags` | array | | `IGNORECASE`, `MULTILINE`, `DOTALL`, `VERBOSE`, `ASCII` |
| `max_matches` | integer | | Max matches to return (default: 100) |

```bash
python tools/python/regex_tool.py --action findall --pattern "\d+" --input "I have 3 cats and 12 dogs"
python tools/python/regex_tool.py --action replace --pattern "foo" --input "foo bar foo" --replacement "baz"
python tools/python/regex_tool.py --action validate --pattern "(?P<year>\d{4})-(?P<month>\d{2})"
```

---

### `env_tool`

**Schema:** `tools/defs/env_tool.json`  
**Implementation:** `tools/python/env_tool.py`

Read, write, validate, and manage `.env` files. Safely handles comments, quoted values, and multiline strings.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | ✓ | `read`, `write`, `delete`, `validate`, `get`, `list` |
| `file` | string | | Path to `.env` file (default: `.env`) |
| `key` | string | | Variable name for `get`/`write`/`delete` |
| `value` | string | | Value to set (`write`) |
| `pairs` | object | | Dict of key→value for bulk write |
| `required` | array | | Required variable names for `validate` |
| `allow_empty` | boolean | | Treat empty values as present for `validate` (default: `false`) |
| `create` | boolean | | Create file if missing (`write`, default: `true`) |

```bash
python tools/python/env_tool.py --action read --file .env
python tools/python/env_tool.py --action validate --required '["ANTHROPIC_API_KEY","GOOGLE_GEMINI_API_KEY"]'
python tools/python/env_tool.py --action write --key DB_HOST --value localhost
```

---

### `diff_tool`

**Schema:** `tools/defs/diff_tool.json`  
**Implementation:** `tools/python/diff_tool.py`

Compare two strings or files and produce unified diffs or structured side-by-side comparisons.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | ✓ | `diff_strings`, `diff_files`, `patch_apply` |
| `a` | string | | First string to compare or source text to patch |
| `b` | string | | Second string to compare or unified diff patch |
| `file_a` | string | | Path to first file |
| `file_b` | string | | Path to second file |
| `context` | integer | | Unchanged lines around each change (default: 3) |
| `output_format` | string | | `unified` (default) or `side_by_side` |
| `encoding` | string | | File encoding (default: `utf-8`) |

```bash
python tools/python/diff_tool.py --action diff_files --file_a original.py --file_b modified.py
python tools/python/diff_tool.py --action diff_strings --a "hello world" --b "hello Python"
```

---

### `database_tool`

**Schema:** `tools/defs/database_tool.json`  
**Implementation:** `tools/python/database_tool.py`

SQLite-backed persistent structured storage. Create tables, insert/query/update/delete rows, and inspect schemas — all using a local SQLite file that persists between sessions.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | ✓ | `create_table`, `insert`, `select`, `update`, `delete`, `execute`, `schema`, `drop_table`, `count` |
| `db` | string | | Path to SQLite file (default: `data.db`) |
| `table` | string | | Table name |
| `columns` | string | | Column definitions for `create_table` (e.g., `id INTEGER PRIMARY KEY, name TEXT`) |
| `row` | object | | Single row dict for `insert` |
| `rows` | array | | List of row dicts for bulk `insert` |
| `where` | string | | SQL WHERE clause (without `WHERE` keyword) |
| `set_values` | object | | Column→value dict for `update` |
| `order_by` | string | | ORDER BY clause for `select` |
| `limit` | integer | | Max rows for `select` |
| `sql` | string | | Raw SQL for `execute` |
| `params` | array | | Positional params for parameterized `execute` |
| `if_not_exists` | boolean | | Use `IF NOT EXISTS` on `create_table` (default: `true`) |

```bash
python tools/python/database_tool.py --action create_table --db sessions.db --table tasks --columns "id INTEGER PRIMARY KEY, title TEXT, status TEXT"
python tools/python/database_tool.py --action insert --db sessions.db --table tasks --row '{"title":"Fix bug","status":"todo"}'
python tools/python/database_tool.py --action select --db sessions.db --table tasks --where "status = 'todo'"
```

---

### `session_manager`

**Schema:** `tools/defs/session_manager.json`  
**Implementation:** `tools/python/session_manager.py`

Manage work sessions with unique IDs and track agent activity, file changes, and notes across the lifecycle of a task.

| Action | Description |
|--------|-------------|
| `create` | Create a new session |
| `status` | Get session details and summary |
| `log_change` | Log a file change within a session |
| `log_agent` | Record agent invocation |
| `log_tool` | Record tool invocation |
| `add_note` | Add a free-text note |
| `close` | Close a session with a summary |
| `list` | List all sessions |
| `active` | Get the current active session |

```bash
python tools/python/session_manager.py --action create --description "Implement user auth"
python tools/python/session_manager.py --action list
python tools/python/session_manager.py --action close --session_id 20260215_120000
```

---

### `log_manager`

**Schema:** `tools/defs/log_manager.json`  
**Implementation:** `tools/python/log_manager.py`

Central logging infrastructure. Writes structured JSONL entries to `logs/master.jsonl` and supports querying, summarizing, and rotating logs. All tool invocations and agent decisions should flow through `log_manager`.

| Action | Description |
|--------|-------------|
| `write` | Append a log entry |
| `query` | Filter entries by session, agent, or tool |
| `summary` | Aggregate stats for a session |
| `rotate` | Archive old log files |
| `tail` | Return the last N entries |

```bash
python tools/python/log_manager.py --action summary --session_id 20260215_120000
python tools/python/log_manager.py --action query --session_id 20260215_120000 --tool read_file
python tools/python/log_manager.py --action tail --n 20
```

---

## Session Management Tools

### `session_clean`

**Schema:** `tools/defs/session_clean.json`  
**Implementation:** `tools/python/session_clean.py`

Reset Overlord11 between tasks. Purges all workspace session folders and clears active entries from `Consciousness.md`, while **preserving** `Memory.md` (permanent preferences and rules) and the `logs/` directory (audit trail).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | ✓ | `clean` (full reset), `purge_workspace`, `reset_consciousness`, `status` |
| `archive` | boolean | | Move sessions to `workspace/archive/` instead of deleting (default: `false`) |
| `older_than_days` | integer | | Only purge sessions older than N days (default: 0 = all) |
| `dry_run` | boolean | | Report what would be cleaned without making changes (default: `false`) |
| `session_id` | string | | Session ID for logging this cleanup |

**What is preserved:** `Memory.md`, `logs/`, `Consciousness.md` Shared Context and Agent Registry sections.

**What is purged:** `workspace/SESSION_ID/` folders, `Consciousness.md` active entries (Cross-Agent Signals, Work In Progress, Pending Handoffs, Error States).

```bash
python tools/python/session_clean.py --action status
python tools/python/session_clean.py --action clean --dry_run true
python tools/python/session_clean.py --action clean --archive true
python tools/python/session_clean.py --action purge_workspace --older_than_days 7
```
