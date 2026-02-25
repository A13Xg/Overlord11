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
pip install requests beautifulsoup4

# Install optional dependencies (for full test coverage)
pip install pillow selenium

# Copy and configure environment
cp .env.example .env
# Edit .env and add at least one API key
```

---

## Running Tests

The test suite is in `tests/test.py`. It exercises all 15 tools with real-world scenarios.

```bash
# Run all tests
python tests/test.py

# Run tests for a specific tool
python tests/test.py --tool read_file
python tests/test.py --tool publisher_tool

# Skip tests that require internet access
python tests/test.py --skip-web

# Run all tests, verbose output
python tests/test.py --verbose
```

### Test Output Format

```
Overlord11 Tool Test Suite
  Session: 20260225_001608_test
  Workspace: tests/test_workspace

  Running: read_file ... 7/7
  Running: write_file ... 6/6
  ...

  OVERLORD11 TOOL TEST SUITE — RESULTS
  ──────────────────────────────────────
  [read_file]       7/7 passed
  [write_file]      6/6 passed
  [list_directory]  3/3 passed
  ...
  Total: 72/75 passed
```

### Test Workspace

Tests create temporary files in `tests/test_workspace/`. This directory is gitignored. It is automatically created and cleaned up between test runs.

---

## Pre-Commit Hook

Run the pre-commit script before pushing:

```bash
python pre_commit_clean.py --verbose
```

This will:
1. Clean temporary files (`tmpclaude-*`, `*.tmp`, `__pycache__`, etc.)
2. Run Python syntax checks on all `.py` files
3. Run the full test suite
4. Report a summary of what was cleaned

### Dry Run

```bash
# See what would be cleaned without deleting anything
python pre_commit_clean.py --dry-run --verbose
```

### Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Show what would be deleted without deleting |
| `--verbose` / `-v` | Show detailed output |
| `--all` | Clean all temp files (not just tmpclaude) |
| `--clean-only` | Only run cleaning, skip tests |

---

## Code Style

The project follows these conventions:

### Python

- **Docstrings**: All public functions require docstrings (enforced by `quality.require_docstrings` in `config.json`)
- **Typing**: Use type hints for function signatures
- **Error handling**: Catch specific exceptions; return error dicts rather than raising in tool functions
- **Logging**: Use `log_manager.log_tool_invocation()` in every tool's CLI `main()` function
- **Encoding**: Always specify `encoding="utf-8"` for file I/O

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
├── agents/          # Agent system prompts — edit carefully
├── tools/
│   ├── defs/        # JSON Schema tool definitions
│   └── python/      # Python tool implementations
├── docs/            # Wiki documentation
├── tests/           # Test suite
│   ├── test.py      # Main test runner
│   └── test_workspace/  # Ephemeral test artifacts (gitignored)
├── config.json      # Unified configuration
├── Consciousness.md # Shared agent memory (runtime artifact)
├── ONBOARDING.md    # Universal LLM onboarding guide
├── .env.example     # API key template
├── .env             # Your API keys (gitignored)
├── .gitignore
└── pre_commit_clean.py  # Pre-commit cleanup + test runner
```

---

## Reporting Issues

When reporting a bug or requesting a feature:

1. **Bug report**: include the tool name, input parameters, expected output, and actual output
2. **Feature request**: describe the use case (what task it enables) and proposed implementation approach
3. **Agent behavior issue**: include the provider, model, system prompt (agent file name), and the problematic request/response pair
