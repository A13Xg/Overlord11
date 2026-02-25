# Troubleshooting

Answers to common questions and fixes for frequent errors.

---

## Setup Issues

### `ModuleNotFoundError: No module named 'requests'`

**Cause:** Required dependencies not installed.

**Fix:**
```bash
pip install requests beautifulsoup4
```

---

### `ModuleNotFoundError: No module named 'bs4'`

**Cause:** BeautifulSoup not installed.

**Fix:**
```bash
pip install beautifulsoup4
```

---

### `Error: File not found at .env`

**Cause:** `.env` file not created.

**Fix:**
```bash
cp .env.example .env
# Then edit .env and add your API key(s)
```

---

### API key not found / `AuthenticationError`

**Cause:** The environment variable for your active provider is not set.

**Fix:**
1. Check which provider is active: `cat config.json | grep '"active"'`
2. Open `.env` and verify the correct key is set:
   - Anthropic: `ANTHROPIC_API_KEY=sk-ant-...`
   - Gemini: `GOOGLE_GEMINI_API_KEY=AIza...`
   - OpenAI: `OPENAI_API_KEY=sk-...`
3. Ensure `.env` is being loaded by your runtime

---

## Provider & API Issues

### `RateLimitError` / `429 Too Many Requests`

**Cause:** You have exceeded the API rate limit for your provider.

**Fix:**
1. Wait for the cooldown period (usually a few minutes)
2. Switch to a different provider temporarily:
   ```json
   { "providers": { "active": "gemini" } }
   ```
3. Consider upgrading your API tier for higher rate limits
4. Record the error in `Consciousness.md` so all agents know to avoid the affected provider

---

### `TimeoutError` when fetching pages

**Cause:** The target URL is slow or unreachable.

**Fix:**
```bash
# Increase timeout
python tools/python/web_fetch.py --url https://example.com --timeout 60

# For web_scraper
python tools/python/web_scraper.py --action extract_article --url https://example.com --wait_timeout 30
```

---

### Gemini returns garbled or truncated output

**Cause:** `max_tokens` too low for the requested content.

**Fix:** Increase `max_tokens` in `config.json`:
```json
"gemini": {
  "max_tokens": 16384
}
```

---

## Tool Issues

### `web_scraper` returns empty content

**Cause:** The page requires JavaScript rendering and Selenium is not installed.

**Fix:**
```bash
pip install selenium
# Also install a Chrome/Chromium browser and ChromeDriver
```

Or use `wait_for_js: false` to skip JS rendering:
```bash
python tools/python/web_scraper.py --action extract_article --url https://example.com --wait_for_js false
```

---

### `code_analyzer` reports no issues on a clearly broken file

**Cause:** `code_analyzer` uses pattern-based analysis; it is not a full linter. It may miss some issues.

**Fix:** Supplement with the `run_shell_command` tool to run actual linters:
```bash
python tools/python/run_shell_command.py --command "python -m py_compile my_file.py"
python tools/python/run_shell_command.py --command "python -m flake8 my_file.py"
```

---

### `publisher_tool` output has no styling

**Cause:** The content file is empty or the path is wrong.

**Fix:**
```bash
# Verify the content file exists and has content
cat report.md

# Then run publisher_tool
python tools/python/publisher_tool.py --title "Test" --content report.md --theme modern
```

---

### `save_memory` adds duplicate entries to `Consciousness.md`

**Cause:** The same key is used multiple times without resolving the previous entry.

**Fix:** Before calling `save_memory`, search for an existing entry:
```bash
python tools/python/search_file_content.py --pattern "your_key_here" --path Consciousness.md
```

Then either resolve the existing entry first, or update it with `replace`.

---

### `replace` tool fails with "old_str not found"

**Cause:** The `old_str` does not exactly match the file content (whitespace, newlines, encoding differences).

**Fix:**
```bash
# Read the exact current content first
python tools/python/read_file.py --path my_file.py --start_line 10 --end_line 15

# Then use the exact string as old_str
```

---

## Memory System Issues

### `Consciousness.md` is bloated / too large

**Cause:** Entries have accumulated without cleanup.

**Fix:**
1. Mark resolved entries as `**Status**: RESOLVED`
2. Move entries older than their TTL to the Archive section
3. Purge the Archive (it is safe to delete old resolved entries)
4. Check that all agents are following the anti-bloat rules (max 20 active entries per section)

---

### Agent is repeating work already done

**Cause:** The agent did not read `Consciousness.md` before starting, or there is no WIP entry for the in-progress work.

**Fix:**
1. Ensure agents always read `Consciousness.md` at session start
2. When starting long-running work, add a WIP entry immediately:
   ```markdown
   ### [NORMAL] WIP: Analysis of Dataset X
   - **Source**: OVR_ANL_04
   - **Status**: ACTIVE
   - **Context**: Running analysis on dataset X. Do not duplicate.
   - **Action**: Wait for RESOLVED status before starting related work.
   ```

---

## Test Failures

### Tests fail with `FileNotFoundError` on `test_workspace`

**Cause:** The test workspace directory was manually deleted.

**Fix:** The test suite recreates the workspace automatically. Just run:
```bash
python tests/test.py
```

---

### Web tests fail with `ConnectionError`

**Cause:** No internet access, or the test URL is unavailable.

**Fix:** Skip web tests:
```bash
python tests/test.py --skip-web
```

---

### `run_shell_command` tests fail on Windows

**Cause:** The test uses Unix shell commands.

**Fix:** The test suite handles platform differences for most commands. If a specific test fails, check that the command works natively in your environment:
```bash
python tools/python/run_shell_command.py --command "echo hello"
```

---

## Configuration Issues

### Changes to `config.json` have no effect

**Cause:** Your runner is caching the config at startup.

**Fix:** Restart the runner / LLM session. The config is read at runtime, not cached across restarts in the framework itself.

---

### `scaffold_generator` fails with "Template not found"

**Cause:** Invalid template name.

**Fix:** List available templates:
```bash
python tools/python/scaffold_generator.py --list-templates
```

---

## Getting More Help

If your issue is not covered here:

1. **Check the relevant Wiki page** for the component you are working with
2. **Run the tests** to verify the tool works in isolation: `python tests/test.py --tool <tool_name>`
3. **Enable verbose logging** by setting `"level": "debug"` in `config.json` under `logging`
4. **Read the logs** in `logs/` — all tool calls and errors are logged in JSONL format:
   ```bash
   tail -f logs/master.jsonl | python -m json.tool
   ```
5. **Open an issue** on the repository with the tool name, input, expected output, and actual output
