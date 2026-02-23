# AgenticToolset - Test Execution Guide

> **Purpose**: This file is a system prompt for an LLM to run the full integration test suite for the AgenticToolset. Follow the instructions below exactly.

---

## Overview

The AgenticToolset contains **8 tools** and **9 agents**. The test suite validates that every tool runs correctly and every agent definition file is well-formed.

### What Gets Tested

**Tools (8):**

| Tool | Test Actions |
|------|-------------|
| `session_manager` | create, status, log_change, log_agent, log_tool, add_note, close, list, active |
| `project_scanner` | full scan, compact mode, depth-limited scan, project_name validation |
| `dependency_analyzer` | full analysis, security-only check |
| `code_analyzer` | single file analysis, project-wide python analysis, complexity check |
| `metrics_collector` | LOC metrics, file metrics, function metrics |
| `scaffold_generator` | list templates (verify >= 4), generate python_cli scaffold |
| `log_manager` | log_decision, log_agent_switch, log_error, log_event, query, summary, list_sessions |
| `web_researcher` | search (DuckDuckGo), fetch, extract, find_feeds, parse_feed |

**Agents (9):**

| Agent ID | File | Checks |
|----------|------|--------|
| AGNT_DIR_01 | orchestrator.md | ID present, all required sections, no stale refs |
| AGNT_ARC_02 | architect.md | ID present, all required sections, no stale refs |
| AGNT_COD_03 | implementer.md | ID present, all required sections, no stale refs |
| AGNT_REV_04 | reviewer.md | ID present, all required sections, no stale refs |
| AGNT_DBG_05 | debugger.md | ID present, all required sections, no stale refs |
| AGNT_RES_06 | researcher.md | ID present, all required sections, no stale refs |
| AGNT_TST_07 | tester.md | ID present, all required sections, no stale refs |
| AGNT_DOC_08 | doc_writer.md | ID present, all required sections, no stale refs |
| AGNT_WEB_09 | web_researcher.md | ID present, all required sections, no stale refs |

**Config Validation:**
- `config.json` is valid JSON
- `project_name` is "AgenticToolset"
- All 9 agents registered in `agent_registry`
- All 8 tools registered in `tool_registry`
- No stale "ClaudeToolset" or "CT_" references

---

## Step 1: Run the Automated Test Suite

Execute the test script from the project root:

```bash
python AgenticToolset/test_suite.py
```

For verbose output:

```bash
python AgenticToolset/test_suite.py --verbose
```

To run only tool tests or only agent tests:

```bash
python AgenticToolset/test_suite.py --tools
python AgenticToolset/test_suite.py --agents
```

### Expected Output

The test suite should print a line for each test case with `PASS` or `FAIL`, followed by a summary:

```
============================================================
TEST RESULTS
============================================================
  Total:   ~75+
  Passed:  ~75+
  Failed:  0
  Skipped: 0
  Duration: <60s

ALL TESTS PASSED
```

The exit code is `0` if all tests pass, `1` if any fail.

---

## Step 2: Interpret Results

### All Tests Pass
If all tests pass, the toolset is fully functional. No further action needed.

### Failures
If any tests fail, check:

1. **Tool failures**: Run the failing tool manually with `--help` to verify it loads. Common causes:
   - Python version < 3.11
   - Missing `logs/` or `workspace/` directories (should auto-create)
   - File permission issues

2. **Agent validation failures**: Read the agent file and check for:
   - Missing sections (Identity, Responsibilities, Workflow, Output Format, Quality Checklist)
   - Stale `CT_` prefixes that should be `AGNT_`
   - Stale `ClaudeToolset` references that should be `AgenticToolset`

3. **Web researcher failures**: These require internet access. If running offline:
   - The `search`, `fetch`, `extract`, `find_feeds`, and `parse_feed` tests will fail
   - This is expected behavior in an offline environment
   - All other tests should still pass

4. **Config validation failures**: Read `config.json` and verify:
   - Valid JSON syntax
   - All agents listed in `agent_registry`
   - All tools listed in `tool_registry`

---

## Step 3: Manual Verification (Optional)

After the automated tests pass, perform these manual checks:

### 3a. Verify No Stale References Across All Files

```bash
grep -ri "ClaudeToolset" AgenticToolset/
grep -ri "CT_DIR\|CT_ARC\|CT_COD\|CT_REV\|CT_DBG\|CT_RES\|CT_TST\|CT_DOC" AgenticToolset/
```

Both commands should return **zero results**.

### 3b. Verify Tool Help Output

Each tool should print usage information when run with `--help`:

```bash
python AgenticToolset/tools/python/session_manager.py --help
python AgenticToolset/tools/python/project_scanner.py --help
python AgenticToolset/tools/python/dependency_analyzer.py --help
python AgenticToolset/tools/python/code_analyzer.py --help
python AgenticToolset/tools/python/metrics_collector.py --help
python AgenticToolset/tools/python/scaffold_generator.py --help
python AgenticToolset/tools/python/log_manager.py --help
python AgenticToolset/tools/python/web_researcher.py --help
```

### 3c. Verify Agent File Structure

Read each agent file in `AgenticToolset/agents/` and confirm:
- The `# ROLE:` header includes the correct agent name and ID
- The `## Identity` section lists the correct `Agent ID` value
- All cross-references to other agents use `AGNT_` prefix
- The `## Tools Available` section lists relevant tools

### 3d. End-to-End Workflow Test

Run a minimal end-to-end workflow:

```bash
# 1. Create session
python AgenticToolset/tools/python/session_manager.py --action create --description "E2E test"

# 2. Scan the project (use the session_id from step 1)
python AgenticToolset/tools/python/project_scanner.py --path . --session_id SESSION_ID

# 3. Analyze code
python AgenticToolset/tools/python/code_analyzer.py --path AgenticToolset/tools/python/ --session_id SESSION_ID

# 4. Web search
python AgenticToolset/tools/python/web_researcher.py --action search --query "test query" --session_id SESSION_ID

# 5. Close session
python AgenticToolset/tools/python/session_manager.py --action close --session_id SESSION_ID --description "E2E complete"

# 6. Verify session summary
python AgenticToolset/tools/python/log_manager.py --action summary --session_id SESSION_ID
```

---

## Step 4: Report Findings

After running all tests, produce a structured report:

```markdown
## Test Report

### Automated Suite
- **Result**: PASS / FAIL
- **Total**: X tests
- **Passed**: X
- **Failed**: X
- **Duration**: Xs

### Failures (if any)
| Test | Error |
|------|-------|
| [test name] | [error message] |

### Manual Verification
- Stale reference check: PASS / FAIL
- Tool --help check: PASS / FAIL
- Agent structure check: PASS / FAIL
- E2E workflow: PASS / FAIL

### Notes
- [Any observations or recommendations]
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: log_manager` | Running from wrong directory | Run from `AgenticToolset/` or use full paths |
| `FileNotFoundError` on logs/ | First run, dirs not created | Tools auto-create dirs; run any tool once |
| Web researcher tests all fail | No internet access | Expected offline; skip these tests |
| `JSONDecodeError` on config.json | Malformed JSON | Validate with `python -m json.tool AgenticToolset/config.json` |
| SSL errors on web tests | Outdated certificates | Update system certificates or Python |
| Scaffold test fails | Temp directory permissions | Check `TEMP` / `TMP` environment variables |
