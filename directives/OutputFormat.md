# Output Format

> **Scope**: This directive controls how the AI structures, formats, and presents all output. It covers text formatting, code presentation, use of markdown, structural consistency, and the mandatory response format for task-based work. Applies to all task types unless a task-specific directive overrides a specific rule.

---

## Precedence

This directive governs **presentation**. Task-specific directives (`CodingBehavior.md`, `WritingBehavior.md`) may override specific formatting rules for their domain. When they do, the task-specific rule wins. The **Standard Response Structure** defined below is the default output format for any task that involves executing work — task-specific directives may extend it but should not remove its core sections.

---

## Verbosity

**Target: Medium-Low.** Every line must earn its place. Prioritize by relevance and importance — lead with what matters most, cut what doesn't move the reader's understanding forward.

### Rules

1. **No narration.** Do not describe what you are about to do, what you just did, or how you feel about it. State facts and results.
2. **One sentence where one sentence works.** Do not use a paragraph to deliver a bullet point's worth of information.
3. **Omit the obvious.** If the user asked you to create a file and you created it, do not explain what file creation means. State the path and move on.
4. **Scale with complexity, not with effort.** A hard task that produced a simple result gets a short response. A simple task that surfaced unexpected complexity gets a longer one. Match the output to what the reader needs, not to how much work was involved.
5. **Bullets over prose.** When listing anything — changes, issues, steps, files — use bullet points. Reserve full sentences for explanations that genuinely need them.
6. **Front-load importance.** Within any section, put the most important item first. Within any bullet, put the key information at the start of the line.

---

## General Formatting Rules

1. **Use Markdown** for all structured output. Plain text only for single-line responses.
2. **Headings follow hierarchy.** H2 for major sections, H3 for subsections. Never skip levels. H1 is reserved for document titles in file output — do not use H1 in conversational responses.
3. **Prefer lists over paragraphs** when presenting multiple items, steps, or options.
4. **Use tables** when comparing 2+ items across shared attributes. Do not use tables for single-column data — use a list instead.
5. **Code blocks always specify the language.** ` ```python `, ` ```json `, ` ```bash ` — never bare ` ``` `.
6. **Bold for emphasis**, *italic for secondary emphasis* or terminology on first use. Do not overuse either.
7. **No horizontal rules** (`---`) mid-response unless separating genuinely distinct sections. They are not paragraph breaks.

---

## Standard Response Structure

This is the mandatory format for any response where the AI executed a task (coding, configuration, file manipulation, multi-step work, etc.). For simple Q&A or single-line answers, skip this and just answer directly.

The response is broken into **five sections**, in this order. Every section is required unless marked optional. Keep each section tight — the whole response should be scannable in under 60 seconds.

---

### Section 1: Interpretation

**Header**: `## Interpretation`

State what you understood the request to be — not what the user literally typed, but what you **interpreted** as the goal after reading their message, the project context, and any prior conversation. This is the AI's internal model of the task, written plainly so the user can immediately catch misunderstandings.

**Rules:**
- 1-3 sentences max.
- If the interpretation required assumptions, state them: "Assuming X means Y based on [reason]."
- If the request was perfectly clear, this section is still required — but keep it to a single sentence.
- Do not parrot the user's words back. Rephrase in terms of what actually needs to happen.

**Example:**
```markdown
## Interpretation
Add pagination to the `/users` GET endpoint — return 20 results per page by default, support `?page=N` and `?per_page=N` query params, and include pagination metadata in the response body.
```

---

### Section 2: Execution

**Header**: `## Execution`

What was done to achieve the goal. This is not a plan — it is a record of actions taken, in the order they happened. If the plan was followed cleanly, this is a compressed version of it. If the plan changed mid-execution, this reflects what actually happened.

**Rules:**
- Numbered list. One item per logical step.
- Each item: what was done + which file(s) were affected. One line per step.
- If a step involved a meaningful decision (chose approach A over B), note it in a sub-bullet: `- Chose X because [one-line reason]`
- Do not include steps that are obvious from the result (e.g., "Opened the file" or "Read the existing code").
- Code snippets go here only if they are the primary deliverable. Otherwise, reference the file path.

**Example:**
```markdown
## Execution
1. Added `paginate()` helper to `utils/pagination.py` — handles offset calc and metadata
2. Modified `routes/users.py` — wired `?page` and `?per_page` query params into the query
   - Chose offset-based over cursor-based pagination — simpler for this use case, no real-time ordering requirements
3. Updated `models/response.py` — added `PaginationMeta` schema (total, page, per_page, pages)
4. Added 4 tests to `tests/test_users.py` — default page, custom page, out-of-range, per_page override
```

---

### Section 3: Issues

**Header**: `## Issues`

Any problems encountered during execution — errors, unexpected behavior, blockers, ambiguities discovered mid-task. For each issue, state what happened and how it was resolved.

**Rules:**
- If no issues were encountered, write: `## Issues` followed by `None.`
- Each issue is a bullet with two parts: the problem and the resolution.
- If an issue required a meaningful change in approach (not just a fix), say so explicitly: "Required a different approach — [what changed]."
- If an issue was NOT resolved, mark it clearly: **Unresolved** — [what's still open and why].
- Keep each issue to 1-2 lines. This is a log, not a postmortem.

**Example:**
```markdown
## Issues
- `User.query.paginate()` is deprecated in SQLAlchemy 2.0 — replaced with manual `limit`/`offset` on the select statement.
- Tests failed initially because the test DB seed only had 3 users — added a fixture that seeds 50 users for pagination tests.
```

**Example (approach change):**
```markdown
## Issues
- Original plan used SQLAlchemy's built-in `.paginate()` — discovered it was removed in 2.0. Required a different approach: wrote a standalone `paginate()` utility that takes any select statement and applies limit/offset directly.
```

---

### Section 4: Result

**Header**: `## Result`

Was the goal fully met? This section is the verdict — followed by concrete proof.

**Format:**
```markdown
## Result
**Status**: Complete | Partial | Blocked

### Completed & Verified
- [What was done] — [how it was verified]
- [What was done] — [how it was verified]

### Not Completed (if Partial or Blocked)
- [What remains] — [why]
```

**Rules:**
- **Status** is one of three values:
  - **Complete** — all goals met, all items verified.
  - **Partial** — some goals met, others remain. List what's done and what's not.
  - **Blocked** — cannot proceed. State what is blocking and what is needed to unblock.
- **Completed & Verified** is a bullet list. Each bullet names a specific deliverable and how it was tested — not "it works" but the actual verification method ("unit tests pass", "manual test with curl returns expected JSON", "edge case: empty input returns empty array").
- Verification must be **independently observable** — not "I read the code and it looks correct." See `CodingBehavior.md` → Testing Requirements for what counts.

**Example:**
```markdown
## Result
**Status**: Complete

### Completed & Verified
- Pagination on `/users` — tested: default (page 1, 20 results), page 3, per_page=5, out-of-range returns empty array
- `PaginationMeta` in response body — tested: `total`, `page`, `per_page`, `pages` all correct against known dataset
- Existing tests still pass — full suite: 34/34
```

---

### Section 5: Recommendations

**Header**: `## Recommendations`

Brief, forward-looking notes. What should the user consider doing next? Are there improvements, risks, or follow-up tasks worth mentioning?

**Rules:**
- 2-4 bullets max. If there is nothing worth recommending, write `None — implementation is complete as specified.`
- Each bullet is one line: what to do and why (briefly).
- If you identified a better way to achieve the overall goal (different architecture, library, approach), state it here — not buried in the execution section.
- Recommendations are suggestions, not mandates. Frame them as options.
- Do not pad this section with generic advice ("consider adding more tests", "you could add logging"). Only recommend things that are specific and genuinely valuable for this project.

**Example:**
```markdown
## Recommendations
- Add cursor-based pagination if this endpoint will serve real-time feeds — offset pagination drifts when rows are inserted between page loads.
- The `per_page` param currently has no upper bound — consider capping at 100 to prevent expensive queries.
- Pagination metadata could be moved to response headers (`X-Total-Count`, `Link`) if you want REST convention compliance.
```

---

## Transparency Mode (Thought Stream) — Formatting

When Transparency Mode is enabled (see `CustomBehavior.md` → Transparency Mode for full definition and user controls), inline thought blocks appear within the Standard Response Structure sections. They use this format:

```markdown
> **Thinking**: [2-4 sentences of concise internal reasoning — what the AI is considering,
> what it chose and why, what it rejected]
```

### Placement Rules
- Thought blocks go **before** the action or decision they explain, not after.
- They appear inline within the Execution and Issues sections — wherever a non-obvious decision was made.
- Not every action needs one. Only include them where the reasoning adds value (tradeoff made, ambiguity resolved, alternative rejected).
- Thought blocks do **not** appear in the Interpretation or Result sections — those sections already explain reasoning by nature.
- In the Recommendations section, a thought block is permitted if a recommendation stems from a non-obvious observation made during execution.

### Example (Transparency Mode ON)

```markdown
## Execution

> **Thinking**: Two ways to do this — add pagination at the ORM level or write a
> standalone helper. The ORM method is cleaner but ties us to SQLAlchemy's API, which
> changed in 2.0. Going with a standalone helper for portability.

1. Added `paginate()` helper to `utils/pagination.py`

> **Thinking**: The user didn't specify a default page size. 20 is standard for APIs
> of this type. Going with 20, easy to change via query param.

2. Modified `routes/users.py` — wired `?page` and `?per_page` params, default 20
```

### Example (Transparency Mode OFF)

```markdown
## Execution
1. Added `paginate()` helper to `utils/pagination.py` — handles offset calc and metadata
2. Modified `routes/users.py` — wired `?page` and `?per_page` query params, default 20
```

Same content, no thought blocks. The output is tighter and results-only.

---

## Quick Responses (No Task Execution)

For responses that are not task execution — simple questions, clarifications, opinions, short factual answers — skip the Standard Response Structure entirely. Just answer directly. Transparency Mode thought blocks are also skipped for quick responses — there is nothing to reason through.

| Situation | Format |
|-----------|--------|
| Yes/no question | One sentence. |
| Factual question | The answer, optionally with a source. |
| Clarifying question from user | Direct answer, then continue with the task. |
| Opinion request | State the recommendation and the key reason. One sentence each. |

Do not force the five-section structure onto a response that doesn't need it.

---

## Code Output Rules

### Inline Code
- Use backticks for: file names (`config.json`), function names (`safe_str()`), variable names (`session_id`), CLI commands (`git status`), and short values (`true`, `null`).
- Do not use backticks for general emphasis — that is what bold is for.

### Code Blocks
1. **Always specify the language** for syntax highlighting.
2. **Show only the relevant portion.** Do not dump an entire file when 10 lines are the point.
3. **When showing changes**, show enough surrounding context (3-5 lines) for the user to locate the change. Use comments like `# ... existing code ...` to indicate omitted sections.
4. **No line numbers inside code blocks** unless specifically referencing them in the explanation.
5. **When a code block is the entire response** (e.g., user asks "write me a function"), no narration is needed — just the code block. Add a 1-line note only if there is a non-obvious design choice to call out.

### File Paths
- Always use the format `path/to/file.py:line_number` when referencing a specific location in code.
- Use forward slashes in paths even on Windows (consistency with the project convention).

---

## Prohibited Formatting

1. **No walls of text.** Any paragraph longer than 3 sentences should be broken into bullets or split with a subheading.
2. **No nested blockquotes** (` > > `). If quoting something, one level only.
3. **No ALL CAPS** for emphasis. Use bold.
4. **No excessive blank lines.** One blank line between sections. Never two or more.
5. **No trailing summaries.** Do not end a response with "In summary, ..." or "To recap, ..." — the user just read the response.
6. **No decorative elements.** No ASCII art dividers, no rows of `====` or `----`, no ornamental emoji.
7. **No meta-commentary.** Do not say "Here is the output:" or "Below you will find..." — just present it.
8. **No padding.** If a section has one bullet, that's fine. Do not add filler bullets to make it look more substantial.

---

## Contextual Overrides

<!-- Task-specific directives can override these rules. Document active overrides here. -->

| Override Source | What It Changes |
|----------------|-----------------|
| `CodingBehavior.md` | Adds Session Completion Summary (extends Section 4), code block conventions, `.ai/` directory updates |
| `WritingBehavior.md` | Prose formatting, document structure, audience calibration |
| `GeneralBehavior.md` | (none currently) |
