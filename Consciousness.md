# Consciousness

> Shared Memory Space for Cross-Agent Communication

---

## Purpose

This document is the **ephemeral shared memory** for all Overlord11 agents. It enables real-time cross-agent communication: active signals, work-in-progress tracking, pending handoffs, and error broadcasting. Its active sections are cleared between tasks by `session_clean`.

For **permanent** preferences, rules, and standing decisions that survive session resets, see `Memory.md`.

Key properties:
- Cross-agent context sharing without direct coupling
- Persistent state within a session; ephemeral between sessions
- Coordinated multi-agent workflows
- Prevention of redundant work across agents

---

## Memory Management Rules

### Entry Lifecycle

1. **Creation**: Any agent may add entries with proper formatting
2. **Expiration**: Entries expire after their TTL (time-to-live) or when marked `[RESOLVED]`
3. **Cleanup**: Expired entries should be moved to Archive or deleted
4. **Limit**: Maximum 20 active entries per section to prevent context bloat

### Entry Format

```
### [PRIORITY] Title
- **Source**: Agent ID (e.g., OVR_DIR_01, OVR_ANL_04)
- **Created**: YYYY-MM-DD HH:MM
- **TTL**: Duration or "persistent"
- **Status**: ACTIVE | PENDING | RESOLVED
- **Context**: Brief description (max 100 words)
- **Action**: What other agents should do with this information
```

### Priority Levels

| Priority | Use Case | TTL Default |
|----------|----------|-------------|
| `[CRITICAL]` | Blocking issues, errors | 24 hours |
| `[HIGH]` | Important context for current work | 7 days |
| `[NORMAL]` | General information sharing | 14 days |
| `[LOW]` | Nice-to-know, background info | 30 days |
| `[PERSISTENT]` | Always-relevant configuration | No expiry |

---

## Active Memory

### Cross-Agent Signals

<!-- Agents add signals here when they need other agents to be aware of something -->

_No active signals._

<!-- Example:
### [HIGH] Research Data Available for Analysis
- **Source**: OVR_RES_02
- **Created**: 2026-01-12 18:00
- **TTL**: 7 days
- **Status**: ACTIVE
- **Context**: Completed research on "quantum computing 2025" with 12 sources. Data formatted as JSON in Research-InfoGather/output/session_xyz.json
- **Action**: AS system can ingest this for visualization; WL system can use for report writing
-->

---

### Shared Context

<!-- Persistent context that all agents should be aware of -->

### [PERSISTENT] Execution Environment Profile
- **Source**: SYSTEM
- **Created**: 2026-04-06
- **TTL**: persistent
- **Status**: ACTIVE
- **Context**: Runtime host is Windows 11 Pro. Preferred shell is bash (Git Bash / WSL). Python 3.x via PATH. The engine (`engine/runner.py`) detects and records the live system profile at session start — check the injected execution environment block in the system prompt for current values.
- **Action**: Default to Unix-style shell syntax in tool calls. When `run_shell_command` is used, emit Windows-compatible commands when the session's system profile confirms a Windows host.

### [PERSISTENT] Active Model Configuration
- **Source**: SYSTEM
- **Created**: 2026-01-12
- **TTL**: persistent
- **Status**: ACTIVE
- **Context**: Active provider is set in `config.json` under `providers.active`. Supports `anthropic` (claude-opus-4-5), `gemini` (gemini-2.5-pro), and `openai` (gpt-4o). Fallback order defined in `orchestration.fallback_provider_order`.
- **Action**: All agents should use the configured provider from `config.json`. Do not hardcode provider or model names.

### [PERSISTENT] Workspace Conventions
- **Source**: SYSTEM
- **Created**: 2026-01-12
- **TTL**: persistent
- **Status**: ACTIVE
- **Context**: Each system has isolated workspace. Cross-system file sharing via `/output/` directories. Session IDs format: `YYYYMMDD_HHMMSS`
- **Action**: Use session IDs for cross-referencing work between agents

---

### Work In Progress

<!-- Agents register active work here to prevent duplication -->

_No work in progress._

<!-- Example:
### [NORMAL] Code Generation: REST API Project
- **Source**: OVR_COD_03
- **Created**: 2026-01-12 19:30
- **TTL**: 24 hours
- **Status**: ACTIVE
- **Context**: Generating Python FastAPI project in workspace/session_20260112_193000. Includes user auth, database integration.
- **Action**: Other agents should not duplicate this work. Results will be signaled when complete.
-->

---

### Pending Handoffs

<!-- When one agent's output is ready for another agent -->

_No pending handoffs._

<!-- Example:
### [HIGH] Analysis Ready for Document Generation
- **Source**: OVR_ANL_04
- **Created**: 2026-01-12 20:00
- **TTL**: 48 hours
- **Status**: PENDING
- **Context**: Statistical analysis complete. Output at Analysis-Summarize/output/analysis_20260112.json. Includes charts data, summary stats, trend analysis.
- **Action**: WL system can transform into executive report. Recommended style: professional.
-->

---

### Error States

<!-- Critical errors that other agents should know about -->

_No active errors._

<!-- Example:
### [CRITICAL] API Rate Limit Reached
- **Source**: OVR_RES_02
- **Created**: 2026-01-12 21:00
- **TTL**: 1 hour
- **Status**: ACTIVE
- **Context**: Anthropic API rate limited. Requests failing with 429. Cooldown period active.
- **Action**: All agents should delay API calls or switch to Gemini provider temporarily.
-->

---

## Agent Registry

### Active Agents

| Agent ID | Agent | Role | Definition | Status |
|----------|-------|------|------------|--------|
| OVR_DIR_01 | Orchestrator | Master coordinator — delegates to all other agents | `agents/orchestrator.md` | Available |
| OVR_RES_02 | Researcher | Web research, information gathering, source verification | `agents/researcher.md` | Available |
| OVR_COD_03 | Coder | Code generation, debugging, testing, refactoring | `agents/coder.md` | Available |
| OVR_ANL_04 | Analyst | Data analysis, summarization, pattern recognition | `agents/analyst.md` | Available |
| OVR_WRT_05 | Writer | Documentation, reports, content creation | `agents/writer.md` | Available |
| OVR_REV_06 | Reviewer | QA, code review, proofreading, validation | `agents/reviewer.md` | Available |
| OVR_PUB_07 | Publisher | Styled self-contained HTML report generation (Tier 2) | `agents/publisher.md` | Available |
| OVR_CLN_08 | Cleanup | Pre-deployment sanity check — secrets scan, temp cleanup, structure validation | `agents/cleanup.md` | Available |

---

## Communication Protocols

### Adding an Entry

1. Choose appropriate section (Signals, Context, WIP, Handoffs, Errors)
2. Select priority level based on urgency
3. Fill all required fields in entry format
4. Keep context under 100 words
5. Specify clear action for consuming agents

### Resolving an Entry

1. Change status to `[RESOLVED]`
2. Add resolution note if helpful
3. Move to Archive section after 24 hours

### Reading Entries

1. Check relevant sections before starting work
2. Respect `[CRITICAL]` entries immediately
3. Act on `PENDING` handoffs if capable
4. Avoid duplicating `ACTIVE` work in progress

---

## Archive

<!-- Resolved entries moved here for reference, purge monthly -->

_Archive empty._

---

## Anti-Bloat Measures

To prevent context runaway:

1. **Hard limits**: Max 20 entries per section
2. **TTL enforcement**: Entries expire and must be renewed
3. **Word limits**: Context field max 100 words
4. **Mandatory cleanup**: Agents must resolve their own entries
5. **Archive rotation**: Monthly purge of resolved entries
6. **Priority decay**: Unactioned entries demote priority over time

---

## Quick Reference

### Add Signal
```markdown
### [PRIORITY] Brief Title
- **Source**: YOUR_AGENT_ID
- **Created**: YYYY-MM-DD HH:MM
- **TTL**: duration
- **Status**: ACTIVE
- **Context**: What happened (max 100 words)
- **Action**: What others should do
```

### Mark Resolved
```markdown
- **Status**: RESOLVED
- **Resolution**: Brief note on outcome
```

### Check Before Work
1. Read Error States (any blockers?)
2. Read Work In Progress (already being done?)
3. Read Pending Handoffs (can I help?)
4. Read Cross-Agent Signals (relevant context?)
