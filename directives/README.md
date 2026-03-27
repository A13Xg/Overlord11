# Directives

Behavioral instruction files that modify how an AI operates during a session. These are designed to be manually loaded into any LLM — copy the relevant file(s) into the system prompt or paste them at session start.

## How They Layer

```
┌─────────────────────────────────────────────────┐
│  Task-Specific Directive (highest priority)      │
│  CodingBehavior / WritingBehavior / General      │
├─────────────────────────────────────────────────┤
│  OutputFormat — presentation & structure rules    │
├─────────────────────────────────────────────────┤
│  CustomBehavior — decision-making, autonomy,     │
│  error handling, transparency mode               │
├─────────────────────────────────────────────────┤
│  Personality — tone & voice (always active)      │
│  + optional Personality Type override            │
└─────────────────────────────────────────────────┘
```

Higher layers override lower layers where they conflict. `Personality` is never fully overridden — it governs voice across all tasks.

## Files

### Core (load these for every session)

| File | What It Controls |
|------|-----------------|
| `Personality.md` | Tone, voice, conversational dynamics, response length, forbidden phrases |
| `CustomBehavior.md` | Decision-making, autonomy boundaries, error handling, context management, transparency mode, contradiction resolution, proactive communication |
| `OutputFormat.md` | Markdown structure, verbosity (med-low), 5-section standard response format, code block rules |

### Task-Specific (load the one that matches the current task)

| File | When to Load |
|------|-------------|
| `CodingBehavior.md` | Writing, modifying, debugging, or testing code. Includes: operating mode (CheckMode/GoMode), `.ai/` context directory, task planning, implementation cycle, independent testing, git practices, handoff protocol |
| `WritingBehavior.md` | Documentation, reports, technical writing, content creation. Includes: audience/purpose framing, document templates, revision cycle handling |
| `GeneralBehavior.md` | Research, Q&A, analysis, troubleshooting, planning. Includes: multi-part request handling, when to push back |

### Personality Types (optional — copy one into the session)

Defined inside `Personality.md`. Only use one per session.

| Type | One-Line Summary |
|------|-----------------|
| **ChildFriendly** | Simple words, short blocks, emoji, warm and encouraging |
| **Assistant** | Asks subject + 1-3 knowledge scale, calibrates all responses to that level |
| **Cautious** | Clarifying questions before acting, confidence % on every response |
| **Quick** | Fastest path to working — scripts over systems, skip tests/docs/packaging |
| **Mentor** | Teaches as it works — explains the why behind every significant decision |

## Quick Start

**Minimal setup** (general use):
1. Load `Personality.md` + `CustomBehavior.md` + `OutputFormat.md`

**Coding session**:
1. Load the three core files + `CodingBehavior.md`
2. Optionally paste a Personality Type

**Writing session**:
1. Load the three core files + `WritingBehavior.md`

**Mix and match**:
- Core files are always loaded
- Only one task-specific file at a time (or layer them for hybrid tasks — e.g., research phase uses `GeneralBehavior`, then writing phase uses `WritingBehavior`)
- Only one Personality Type at a time
