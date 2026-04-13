# Agents Reference

Complete reference for all eight Overlord11 agents.

---

## OVR_DIR_01 — Orchestrator

**File:** `agents/orchestrator.md`  
**Role:** Master coordinator — the entry point for every request.

### Responsibilities

1. Parse and classify incoming requests
2. Determine output tier (0, 1, or 2) before any delegation
3. Decompose complex tasks into ordered subtasks with clear handoff contracts
4. Delegate each subtask to the appropriate specialist agent
5. Track work-in-progress and dependencies across agents
6. Synthesize partial outputs into a unified final deliverable
7. Handle escalations, retries, and fallback strategies on agent errors
8. Maintain session state in `Consciousness.md`

### Output Tier Decision

| Tier | Trigger Keywords / Conditions | Output |
|------|-------------------------------|--------|
| **0** | Simple Q&A, yes/no, one-liner, quick fact | Inline text — no agent invocation |
| **1** | Docs, how-tos, comparisons, summaries, guides | Writer → `.md` |
| **2** | "detailed", "full", "breakdown", "visualize", "infographic", "comprehensive", dashboards | Publisher → `.html` |

### Delegation Patterns

**Feature Request:**
```
Orchestrator → Researcher → Coder → Reviewer → Writer [Tier 1]
```

**Bug Fix:**
```
Orchestrator → Analyst → Coder → Reviewer
```

**Research Report (simple):**
```
Orchestrator → Researcher → Analyst → Writer [Tier 1] → Reviewer
```

**Detailed Research Report / Infographic:**
```
Orchestrator → Researcher → Analyst → Reviewer → Publisher [Tier 2]
```

**Data Analysis (simple):**
```
Orchestrator → Researcher → Analyst → Writer [Tier 1] → Reviewer
```

**Data Dashboard / Comprehensive Analysis:**
```
Orchestrator → Researcher → Analyst → Reviewer → Publisher [Tier 2]
```

**Documentation Update:**
```
Orchestrator → Analyst → Writer [Tier 1] → Reviewer
```

### Quality Checklist

- [ ] `Memory.md` read at session start — permanent rules applied
- [ ] `Consciousness.md` checked for active signals and pending handoffs
- [ ] Request fully understood before delegation begins
- [ ] Output tier assessed and documented in the plan
- [ ] All required agents identified and invoked
- [ ] Agent outputs verified against subtask contracts
- [ ] Reviewer agent always invoked before final delivery
- [ ] Publisher invoked when Tier 2 output is needed
- [ ] `Consciousness.md` updated with session state
- [ ] Final output addresses the original request completely
- [ ] No specialist work performed by Orchestrator directly

---

## OVR_RES_02 — Researcher

**File:** `agents/researcher.md`  
**Tools:** `web_fetch`, `web_scraper`, `read_file`, `list_directory`, `glob`, `search_file_content`, `save_memory`, `project_scanner`, `consciousness_tool`, `error_handler`

### Responsibilities

1. Perform targeted web searches and retrieve page content
2. Read and extract relevant content from local files and project documentation
3. Collect multiple sources on a topic and cross-reference for accuracy
4. Structure raw findings into clean, cited summaries
5. Identify knowledge gaps and flag ambiguous or conflicting information
6. Scan project structures to understand existing codebases
7. Persist key findings to memory for cross-session continuity

### Workflow

1. **Scope** — clarify exactly what information is needed
2. **Source Plan** — list target sources before fetching
3. **Fetch** — use `web_fetch` for single pages, `web_scraper` for multi-page extraction
4. **Local Scan** — use file tools for local data
5. **Cross-Reference** — validate findings against at least 2 independent sources
6. **Extract** — pull only relevant information; discard noise
7. **Structure** — organize findings with headings, citations, and confidence levels
8. **Gaps** — explicitly list what was not found
9. **Persist** — save key facts to `Consciousness.md`
10. **Handoff** — return structured findings to Orchestrator

### Output Format

```markdown
## Research Findings: [Topic]

### Summary
[2-3 sentence overview]

### Key Facts
- Fact 1 [Source: URL or file]

### Detailed Findings
[Organized sections with citations]

### Gaps & Uncertainties
- [What was not found]

### Sources
1. [URL] — [description]
```

### Quality Checklist

- [ ] Minimum 2 independent sources for factual claims
- [ ] All sources cited with URLs or file paths
- [ ] Conflicting information explicitly flagged
- [ ] Only relevant information included
- [ ] Confidence level indicated for major findings
- [ ] Knowledge gaps documented

---

## OVR_COD_03 — Coder

**File:** `agents/coder.md`  
**Tools:** `read_file`, `write_file`, `replace`, `run_shell_command`, `code_analyzer`, `project_scanner`, `scaffold_generator`, `git_tool`, `search_file_content`, `glob`, `task_manager`, `error_logger`, `project_docs_init`, `launcher_generator`, `ui_design_system`, `execute_python`

### Responsibilities

1. Implement features, functions, classes, and modules from specifications
2. Debug existing code by analyzing errors and runtime behavior
3. Write unit tests, integration tests, and test fixtures
4. Refactor code for clarity, performance, and maintainability
5. Generate project scaffolding with `scaffold_generator`
6. Run static analysis with `code_analyzer` before handoff
7. Execute code via `run_shell_command` to verify correctness
8. Manage version control with `git_tool`

### Workflow

1. **Understand** — read spec fully; note ambiguities
2. **Explore** — use `read_file`, `search_file_content`, `glob`, `project_scanner`
3. **Analyze** — run `code_analyzer` on relevant existing files
4. **Plan** — write implementation plan before writing any code
5. **Implement** — write incrementally; `write_file` for new, `replace` for edits
6. **Test** — write tests; run with `run_shell_command`
7. **Verify** — re-run `code_analyzer` to confirm no new issues
8. **Document** — add docstrings; update changelogs
9. **Commit** — stage and commit with `git_tool`
10. **Handoff** — return file paths, test results, and summary

### Quality Checklist

- [ ] All acceptance criteria addressed
- [ ] No syntax errors
- [ ] Tests written and passing
- [ ] `code_analyzer` run; issues resolved
- [ ] No hardcoded secrets or environment-specific paths
- [ ] Docstrings added for public functions
- [ ] Git commit made with descriptive message
- [ ] Handoff summary includes all changed files and test results

#### Encoding Safety (required for every file written)

- [ ] All `open()` calls include `encoding="utf-8"` (and `errors="replace"` for reads)
- [ ] All `json.dumps()` calls include `ensure_ascii=False`
- [ ] All `subprocess` output decoded with `.decode("utf-8", errors="replace")`
- [ ] `safe_str()` helper present in every module that prints, logs, or returns text
- [ ] `io.TextIOWrapper` guard added for `sys.stdout`/`sys.stderr` on `win32` entry points
- [ ] No bare `print(user_data)` or `print(file_content)` — always routed through `safe_str()`

> The full encoding safety patterns with copy-paste code are in `agents/coder.md` under **Encoding Safety (Mandatory)** and in `docs/Development.md` under **Encoding Safety**.

---

## OVR_ANL_04 — Analyst

**File:** `agents/analyst.md`  
**Tools:** `read_file`, `calculator`, `code_analyzer`, `project_scanner`, `search_file_content`, `glob`, `save_memory`, `consciousness_tool`, `response_formatter`, `file_converter`

### Responsibilities

1. Analyze structured and unstructured data for patterns and insights
2. Compute metrics, statistics, and comparisons with `calculator`
3. Summarize findings into actionable recommendations
4. Identify root causes from logs, code, and diagnostic data
5. Produce structured analysis output (tables, ranked lists, metric bars)
6. Save synthesized insights to `Consciousness.md` for downstream agents

### Quality Checklist

- [ ] Analysis grounded in actual data (not assumptions)
- [ ] All metrics computed with `calculator`, not estimated
- [ ] Findings organized by priority or impact
- [ ] Root causes distinguished from symptoms
- [ ] Recommendations are actionable and specific
- [ ] Uncertainty levels stated for ambiguous findings

---

## OVR_WRT_05 — Writer

**File:** `agents/writer.md`
**Tools:** `read_file`, `write_file`, `replace`, `list_directory`, `glob`, `task_manager`, `consciousness_tool`, `response_formatter`, `file_converter`

### Responsibilities

1. Write and update technical documentation (READMEs, API docs, guides)
2. Produce reports, summaries, and narrative write-ups from structured data
3. Draft release notes, changelogs, and announcements
4. Translate technical findings into audience-appropriate language
5. Apply consistent tone, structure, and style
6. Rewrite existing content for clarity, conciseness, and correctness

### Tone Guidelines

| Content Type | Voice | Style |
|--------------|-------|-------|
| Technical docs | Precise, imperative | Assume competent reader |
| Reports | Objective, evidence-first | Tables and bullet points |
| READMEs | Welcoming, clear | Answer "what, why, how" |
| Changelogs | Factual, impact-focused | Keep a Changelog format |

### Quality Checklist

- [ ] Audience and purpose defined before writing
- [ ] Outline created before drafting
- [ ] All factual claims verified against source material
- [ ] Active voice used throughout
- [ ] No redundant sentences or filler phrases
- [ ] Code examples are accurate
- [ ] Consistent heading hierarchy
- [ ] Reviewer agent invoked for final pass

---

## OVR_REV_06 — Reviewer

**File:** `agents/reviewer.md`  
**Tools:** `read_file`, `code_analyzer`, `run_shell_command`, `search_file_content`, `glob`, `cleanup_tool`, `ui_design_system`, `consciousness_tool`, `error_handler`

### Responsibilities

1. Review all final outputs (code and documents) before delivery
2. Check code for bugs, security issues, style violations, and test coverage
3. Check documents for factual accuracy, completeness, and style consistency
4. Block outputs that contain hardcoded secrets or credentials
5. Return specific, actionable change requests when output is insufficient
6. Approve output that meets all quality standards

### Review Checklist — Code

- [ ] No syntax errors; code runs without crashing
- [ ] No hardcoded secrets, API keys, or passwords
- [ ] All acceptance criteria met
- [ ] Tests present and passing
- [ ] Static analysis (`code_analyzer`) shows no critical issues
- [ ] Error handling present for expected failure modes
- [ ] Documentation updated

#### Encoding Safety (CRITICAL — flag any violation as MAJOR)

- [ ] Every `open()` call specifies `encoding="utf-8"` — bare `open(path)` is a defect
- [ ] Every `json.dumps()` call includes `ensure_ascii=False`
- [ ] All `subprocess` stdout/stderr decoded with `.decode("utf-8", errors="replace")`
- [ ] Any module that prints or logs has a `safe_str()` helper guarding output
- [ ] Entry-point scripts on Windows wrap `sys.stdout`/`sys.stderr` with `io.TextIOWrapper(encoding="utf-8")`
- [ ] No raw `print(content)` where content may contain non-ASCII

### Review Checklist — Documents

- [ ] All factual claims verified or sourced
- [ ] No contradictions with other documented facts
- [ ] Correct grammar, spelling, and punctuation
- [ ] Consistent heading hierarchy and formatting
- [ ] Code examples tested and accurate
- [ ] Audience-appropriate language used

---

## OVR_PUB_07 — Publisher

**File:** `agents/publisher.md`  
**Tools:** `read_file`, `write_file`, `replace`, `publisher_tool`, `response_formatter`

### Responsibilities

1. Receive finalized content from Writer or Analyst
2. Select the appropriate visual theme based on content type
3. Generate a fully self-contained HTML report using `publisher_tool`
4. Ensure the output requires no external dependencies (all CSS inline)
5. Verify the HTML file is valid and renders correctly

### Theme Selection Guide

| Theme | Content Type |
|-------|-------------|
| `techno` | Code, engineering, APIs, DevOps |
| `classic` | Business, finance, executive reports |
| `informative` | Research, academia, data science |
| `contemporary` | Health, science, environment |
| `abstract` | Arts, creative, culture |
| `modern` | Startups, product, marketing |
| `colorful` | Education, children's content |
| `tactical` | Security, defense, risk |
| `editorial` | Journalism, history, narrative |
| `auto` | Let `publisher_tool` choose based on title/content |

### Quality Checklist

- [ ] Theme appropriate for content type
- [ ] HTML is fully self-contained (no external CSS/JS links)
- [ ] All sections from source content present in output
- [ ] No raw Markdown syntax visible in rendered output
- [ ] File size reasonable (< 5 MB for typical reports)
- [ ] Output file saved to correct path

---

## OVR_CLN_08 — Cleanup

**File:** `agents/cleanup.md`
**Tools:** `cleanup_tool`, `session_clean`, `read_file`, `glob`, `search_file_content`, `run_shell_command`

### Responsibilities

1. Scan project for hardcoded secrets, API keys, and credentials
2. Remove temporary files (`.tmp`, `__pycache__`, `tmpclaude-*`, etc.)
3. Validate project structure against expected layout
4. Check for orphaned files (unreferenced assets, dead code)
5. Report findings with severity levels

### When to Invoke

- Before any delivery to the user (pre-deployment sanity check)
- Before committing to version control
- When the Orchestrator adds a cleanup phase to the delegation plan
- On explicit user request ("clean up", "check for secrets", "validate structure")

### Workflow

1. **Scan** — Run `cleanup_tool` with `full_scan` action on project root
2. **Classify** — Group findings by severity (CRITICAL / WARNING / INFO)
3. **Remediate** — Auto-fix safe issues (temp file deletion); flag unsafe issues for human review
4. **Report** — Return structured findings with file paths, line numbers, and recommendations

### Quality Checklist

- [ ] No hardcoded secrets remain in any tracked file
- [ ] All temporary files removed
- [ ] Project structure matches expected layout from `config.json`
- [ ] No orphaned tool definitions (JSON without Python impl or vice versa)
- [ ] Findings report is clear, actionable, and severity-sorted
