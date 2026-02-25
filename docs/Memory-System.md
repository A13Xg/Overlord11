# Memory System

The `Consciousness.md` file is the shared memory layer for all Overlord11 agents. It enables cross-session continuity, cross-agent communication, and work deduplication.

---

## Overview

`Consciousness.md` lives in the project root and is:

- **Read** by every agent at the start of each session
- **Written** by any agent when it produces a reusable finding or wants to signal another agent
- **Gitignored** in production deployments (it is a runtime artifact)
- **Plaintext Markdown** so it is human-readable at any time

---

## File Structure

```
Consciousness.md
├── Active Memory
│   ├── Cross-Agent Signals     ← one agent notifying others
│   ├── Shared Context          ← always-relevant configuration
│   ├── Work In Progress        ← prevent duplicate work
│   ├── Pending Handoffs        ← one agent's output ready for another
│   └── Error States            ← blocking errors visible to all
├── Agent Registry              ← static list of available agents
├── Communication Protocols     ← how to add/resolve/read entries
└── Archive                     ← resolved entries (purged monthly)
```

---

## Entry Format

Every memory entry follows this format:

```markdown
### [PRIORITY] Title
- **Source**: OVR_XXX_00
- **Created**: YYYY-MM-DD HH:MM
- **TTL**: 7d
- **Status**: ACTIVE
- **Context**: Brief description (max 100 words)
- **Action**: What other agents should do
```

### Priority Levels

| Priority | Use Case | Default TTL |
|----------|----------|-------------|
| `[CRITICAL]` | Blocking errors, API failures, security issues | 24 hours |
| `[HIGH]` | Important context for current work | 7 days |
| `[NORMAL]` | General information sharing | 14 days |
| `[LOW]` | Nice-to-know, background info | 30 days |
| `[PERSISTENT]` | Always-relevant configuration, never expires | No expiry |

### Status Values

| Status | Meaning |
|--------|---------|
| `ACTIVE` | Entry is current and agents should act on it |
| `PENDING` | A handoff waiting for another agent to pick up |
| `RESOLVED` | Work completed; entry will be archived |

---

## Reading Entries

At the start of every session, agents should:

1. **Check Error States** — are there any `[CRITICAL]` blockers?
2. **Check Work In Progress** — is someone already doing this task?
3. **Check Pending Handoffs** — is there output waiting for you?
4. **Check Cross-Agent Signals** — any relevant context?
5. **Check Shared Context** — current provider, workspace conventions

### Rule: Respect `[CRITICAL]` Entries

If an Error States entry is marked `[CRITICAL]` and `ACTIVE`, do not proceed with tasks that use the affected resource (e.g., an API, a file, a service). Instead, read the entry's **Action** field and follow it.

---

## Writing Entries

### Using the `save_memory` Tool

```bash
python tools/python/save_memory_tool.py \
  --key "API Rate Limit" \
  --value "Anthropic rate limited until 14:00. Switch to Gemini." \
  --priority CRITICAL \
  --ttl 2h
```

### Writing Directly

Add your entry to the appropriate section:

```markdown
### [HIGH] Research Data Available: Python Testing Frameworks
- **Source**: OVR_RES_02
- **Created**: 2026-02-25 12:30
- **TTL**: 7d
- **Status**: ACTIVE
- **Context**: Completed research on 5 Python testing frameworks. Findings in workspace/20260225_123000/output/research.json. Includes popularity data, feature matrix, and 3 source citations.
- **Action**: OVR_ANL_04 can ingest this for comparative analysis. OVR_WRT_05 can use for report.
```

---

## Resolving Entries

When you complete the work described in an entry:

1. Change `**Status**: ACTIVE` to `**Status**: RESOLVED`
2. Add a resolution note:
   ```
   - **Resolution**: Comparative analysis completed. Report at workspace/20260225_140000/output/report.md
   ```
3. After 24 hours, move to the Archive section

---

## Section Guide

### Cross-Agent Signals

Use for: notifications that any agent might need to act on.

```markdown
### [NORMAL] New Config Available
- **Source**: OVR_DIR_01
- **Created**: 2026-02-25 10:00
- **TTL**: 7d
- **Status**: ACTIVE
- **Context**: config.json updated to add Gemini 2.5 Flash Lite model. All agents should use this for cost-sensitive tasks.
- **Action**: Update any cached model selection logic.
```

### Shared Context

Use for: persistent configuration and conventions that all agents need.

```markdown
### [PERSISTENT] Active Model Configuration
- **Source**: SYSTEM
- **Created**: 2026-01-12
- **TTL**: persistent
- **Status**: ACTIVE
- **Context**: Active provider is set in config.json. Supports anthropic (claude-opus-4-5), gemini (gemini-2.5-pro), openai (gpt-4o).
- **Action**: Use config.json for all provider/model selection.
```

### Work In Progress

Use for: preventing duplicate work across agents or sessions.

```markdown
### [NORMAL] Code Generation: REST API Project
- **Source**: OVR_COD_03
- **Created**: 2026-02-25 11:00
- **TTL**: 24h
- **Status**: ACTIVE
- **Context**: Generating Python FastAPI project in workspace/20260225_110000. Includes user auth and database integration.
- **Action**: Do not duplicate this work. Results will be signaled when complete.
```

### Pending Handoffs

Use for: one agent's output that is ready for another agent to consume.

```markdown
### [HIGH] Analysis Complete: Q1 Revenue Data
- **Source**: OVR_ANL_04
- **Created**: 2026-02-25 13:00
- **TTL**: 48h
- **Status**: PENDING
- **Context**: Statistical analysis complete. Output at workspace/20260225_130000/output/analysis.json. Includes trend data, anomalies, and executive summary bullets.
- **Action**: OVR_WRT_05: transform into executive report (Tier 1). OVR_PUB_07: transform into HTML dashboard (Tier 2) if requested.
```

### Error States

Use for: blocking errors that all agents must know about.

```markdown
### [CRITICAL] Anthropic API Rate Limited
- **Source**: OVR_RES_02
- **Created**: 2026-02-25 09:00
- **TTL**: 1h
- **Status**: ACTIVE
- **Context**: Anthropic API returning 429 errors. Cooldown period active until ~10:00.
- **Action**: All agents: switch to Gemini provider temporarily. Update config.json providers.active = "gemini".
```

---

## Anti-Bloat Rules

To prevent the memory file from growing unmanageably:

1. **Hard limit**: Max 20 active entries per section
2. **TTL enforcement**: Entries expire and must be renewed to stay active
3. **Word limit**: Context field max 100 words
4. **Mandatory cleanup**: Agents must resolve their own entries
5. **Archive rotation**: Monthly purge of resolved entries
6. **Priority decay**: Entries not acted on should be reviewed and possibly demoted

---

## Programmatic Access

The `save_memory` tool appends structured entries to `Consciousness.md`. The tool:

1. Reads the current file
2. Appends the new entry to the appropriate section
3. Validates the entry format
4. Writes the updated file atomically

For manual edits, always use the format above to ensure all agents can parse the entry correctly.
