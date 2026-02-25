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

**Schema:** `tools/defs/glob.json`  
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
**Implementation:** (inline in agents)

Precise find-and-replace within a file.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | ✓ | File to modify |
| `old_str` | string | ✓ | Exact string to find (must be unique in the file) |
| `new_str` | string | ✓ | Replacement string |

> **Note:** This tool is defined in `tools/defs/replace.json` but implemented inline by the LLM agent, not as a standalone Python script.

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
**Implementation:** `tools/python/calculator_tool.py`

Evaluate math expressions, perform statistics, and convert units.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `expression` | string | ✓ | Math expression or statistical function call |

**Supported operations:**
- Arithmetic: `2 + 3 * 4`, `sqrt(144)`, `log(100, 10)`
- Statistics: `mean([1,2,3,4,5])`, `stdev([10,20,30])`
- Unit conversion: handled via expressions

```bash
python tools/python/calculator_tool.py --expression "sqrt(144)"
python tools/python/calculator_tool.py --expression "mean([10, 20, 30, 40])"
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
**Implementation:** `tools/python/save_memory_tool.py`

Persist facts to `Consciousness.md` for cross-session continuity.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `key` | string | ✓ | Memory entry identifier |
| `value` | string | ✓ | Content to persist |
| `priority` | string | | `CRITICAL`, `HIGH`, `NORMAL` (default), `PERSISTENT` |
| `ttl` | string | | Time-to-live (e.g., `7d`, `24h`, `persistent`) |

```bash
python tools/python/save_memory_tool.py --key "project_goal" --value "Build provider-agnostic toolset"
python tools/python/save_memory_tool.py --key "api_limit" --value "Rate limited until 14:00" --priority CRITICAL --ttl 2h
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
