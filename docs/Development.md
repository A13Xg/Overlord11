# Development

Guide for contributors: setting up a dev environment, running tests, linting, and making changes.

---

## Dev Environment Setup

### Prerequisites

- Python 3.8 or higher
- Git

### Setup

```bash
git clone https://github.com/A13Xg/Overlord11.git
cd Overlord11

# Install required dependencies
pip install requests beautifulsoup4 ddgs

# Install optional dependencies (for full test coverage)
pip install pillow selenium

# Copy and configure environment
cp .env.example .env
# Edit .env and add at least one API key
```

---

## Running Tests

The test suite is in `tests/test.py`. It exercises all 28 core tool modules with real-world scenarios and produces verbose expected-vs-actual output. A separate WebUI suite (`tests/test_webui.py`) covers 31 endpoint tests for the Tactical WebUI.

```bash
# Run all tests (includes live web calls)
python tests/test.py

# Skip internet-dependent tests (fast, ~1-5s)
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

# Typical CI invocation
python tests/test.py --skip-web --quiet --no-color --output ci_results.json
```

### All Flags

| Flag | Description |
|------|-------------|
| `--skip-web` | Skip internet-dependent tests |
| `--tool NAME` | Run one tool's tests (e.g. `--tool calculator`) |
| `--tool A,B,C` | Run multiple tools (comma-separated) |
| `--quiet` / `-q` | Summary + failures only — LLM/CI friendly |
| `--no-color` | Disable ANSI colour codes (also: `NO_COLOR=1` env var) |
| `--output PATH` | Write JSON results to PATH instead of `tests/test_results.json` |
| `--list` | Print available tool names and exit |
| `--fail-fast` | Abort on the first test failure |

### Test Matrix

| Mode | Tests | Coverage |
|------|-------|----------|
| `--skip-web` | **72** | All local tools, encoding, file I/O, git, shell, analysis |
| Full (web) | **81** | All of the above + web fetch, DuckDuckGo search, scraper |

### Test Output Format

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

  ══════════════════════════════════════════════════════════════════════════════
    OVERLORD11 TOOL TEST SUITE — RESULTS
    Session: 20260224_213345_test
  ══════════════════════════════════════════════════════════════════════════════

    [read_file]             7/7 passed
    [write_file]            6/6 passed
    [list_directory]        3/3 passed
    ...

    SUMMARY:  81/81 tests passed  |  16 tools tested  |  Total time: 4823ms
  ══════════════════════════════════════════════════════════════════════════════
```

### JSON Results (`tests/test_results.json`)

Every run writes a machine-readable JSON file with a full `environment` block so an LLM reading the output can reason about why a test passed or failed:

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

The `environment` block captures:
- Python version and platform
- Whether `rg` (ripgrep) is available on PATH — this affects `search_file_content` behavior
- Whether optional packages are installed — this affects `web_scraper` capabilities

### Test Workspace

Tests create temporary files in `tests/test_workspace/`. This directory is gitignored. It is automatically created and deleted between test runs.

---

## Pre-Commit Checks

Before pushing, run the test suite and use the Cleanup agent (OVR_CLN_08) or `cleanup_tool` to scan for secrets, remove temp files, and validate project structure:

```bash
# Run tests
python tests/test.py --skip-web --quiet

# Run cleanup tool
python tools/python/cleanup_tool.py --path . --action full_scan
```

---

## Code Style

The project follows these conventions:

### Python

- **Docstrings**: All public functions require docstrings (enforced by `quality.require_docstrings` in `config.json`)
- **Typing**: Use type hints for function signatures
- **Error handling**: Catch specific exceptions; return error dicts rather than raising in tool functions
- **Logging**: Use `log_manager.log_tool_invocation()` in every tool's CLI `main()` function

#### Encoding Safety (required, not optional)

Encoding bugs are invisible until a user hits a non-ASCII character. Follow these rules in every file:

| Rule | Correct | Wrong |
|------|---------|-------|
| File reads | `open(p, encoding="utf-8", errors="replace")` | `open(p)` |
| File writes | `open(p, "w", encoding="utf-8")` | `open(p, "w")` |
| JSON output | `json.dumps(obj, ensure_ascii=False)` | `json.dumps(obj)` |
| subprocess output | `.decode("utf-8", errors="replace")` | `.decode()` |
| Terminal output | route through `safe_str()` | `print(raw_content)` |

Every module that prints or logs must include a `safe_str()` helper:

```python
def safe_str(val, max_len: int = 200) -> str:
    """Encoding-safe string conversion. Prevents UnicodeEncodeError on cp1252/cp437 terminals."""
    if val is None:
        return "(none)"
    s = str(val)
    if len(s) > max_len:
        s = s[:max_len] + "..."
    try:
        s.encode(sys.stdout.encoding or "utf-8")
        return s
    except (UnicodeEncodeError, LookupError):
        return s.encode("ascii", errors="backslashreplace").decode("ascii")
```

Entry-point scripts must guard stdout/stderr on Windows:

```python
import io, sys
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
```

See [Agents Reference](Agents-Reference.md) — the Coder agent's **Encoding Safety** section for full patterns and rules.

### Markdown

- H1 for document title (one per file)
- H2 for major sections
- H3 for subsections
- Code blocks with language identifiers (` ```python `, ` ```bash `, etc.)
- Tables for structured comparisons
- Relative links between docs files

### JSON (Tool Schemas)

- Always include a `description` field for every parameter
- List all required parameters in the `required` array
- Provide `default` values for optional parameters
- Use `enum` for parameters with fixed valid values

---

## Making Changes to Agents

Agent files (`agents/*.md`) are system prompts loaded directly by the LLM. When editing them:

1. **Test your changes** with the target provider before committing — agent behavior can change subtly with prompt wording
2. **Preserve the checklist format** — all agents have a Quality Checklist; keep it
3. **Keep IDs stable** — changing an agent's `id` in the file invalidates any `Consciousness.md` entries referencing the old ID
4. **Update ONBOARDING.md** if you change agent roles significantly — it is the universal onboarding document

---

## Making Changes to Tools

When modifying a tool:

1. **Update both the schema and the implementation** — keep `tools/defs/my_tool.json` and `tools/python/my_tool.py` in sync
2. **Run the tool test** before committing: `python tests/test.py --tool my_tool`
3. **Update the docs**: `docs/Tools-Reference.md`
4. **Backward compatibility**: don't remove required parameters from a schema without updating all agents that use the tool

---

## Making Changes to `config.json`

`config.json` is the single source of truth. Be careful:

- **Agent tool lists**: agents will only use tools listed in their `tools` array
- **Fallback provider order**: this determines failover behavior in production
- **Quality thresholds**: lowering `min_test_coverage` weakens the safety net
- **`max_loops` and `max_retries_per_agent`**: increasing these can cause runaway agent loops

---

## Commit Message Convention

Use conventional commits format:

```
feat: add web_scraper smart image scoring
fix: handle missing Consciousness.md gracefully
docs: update Tools Reference for web_scraper
chore: bump version to 2.1.0
refactor: consolidate provider config loading
test: add publisher_tool theme coverage tests
```

---

## Repository Layout Quick Reference

```
Overlord11/
├── agents/          # 8 agent system prompts — edit carefully
├── tools/
│   ├── defs/        # 30 JSON Schema tool definitions
│   └── python/      # Tool Python implementations
├── directives/      # Behavioral instruction files for AI sessions
├── docs/            # Wiki documentation
├── skills/          # UI/UX design system datasets
├── tests/
│   ├── test.py              # 81-test suite
│   └── test_results.json    # Machine-readable results (auto-generated)
├── config.json      # Unified configuration
├── Consciousness.md # Shared agent memory (runtime artifact)
├── ONBOARDING.md    # Universal LLM onboarding guide
├── CHANGELOG.md     # Release history
├── .env.example     # API key template
├── .env             # Your API keys (gitignored)
└── .gitignore
```

---

## Reporting Issues

When reporting a bug or requesting a feature:

1. **Bug report**: include the tool name, input parameters, expected output, and actual output
2. **Feature request**: describe the use case (what task it enables) and proposed implementation approach
3. **Agent behavior issue**: include the provider, model, system prompt (agent file name), and the problematic request/response pair
