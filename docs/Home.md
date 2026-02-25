# Overlord11 Wiki — Home

> **Provider-agnostic multi-agent LLM toolset** · v2.1.0

Welcome to the Overlord11 documentation. This wiki covers everything you need to understand, configure, use, and extend the framework.

---

## What Is Overlord11?

Overlord11 is a structured multi-agent framework that coordinates **seven specialist AI agents** across any LLM provider — Anthropic Claude, Google Gemini, or OpenAI GPT. It provides:

- A **task routing layer** (the Orchestrator) that decomposes requests and delegates to the right specialists
- **Seven specialist agents**, each with a distinct role and quality checklist
- **Fifteen built-in tools** for file I/O, web research, code analysis, project scanning, and report generation
- A **shared memory system** (`Consciousness.md`) for cross-agent, cross-session context
- **Provider-agnostic design** — no provider-specific code in agent definitions or tool schemas
- **Three output tiers** — inline text, Markdown documents, or styled self-contained HTML reports
- **Encoding safety by default** — all agents enforce UTF-8 file I/O, `safe_str()` output guards, and Windows console protection
- **81-test suite** — covering all 16 modules with encoding, ripgrep/fallback, Unicode, and CI-friendly output modes

---

## Quick Navigation

| Document | What It Covers |
|----------|---------------|
| [Getting Started](Getting-Started.md) | Installation, setup, first run, and verification |
| [Architecture](Architecture.md) | System design, agent roles, data flow, and component interactions |
| [Agents Reference](Agents-Reference.md) | All 7 agents — identities, workflows, tools, and quality checklists |
| [Tools Reference](Tools-Reference.md) | All 15 tools — parameters, return values, and CLI examples |
| [Configuration Reference](Configuration-Reference.md) | Every field in `config.json` explained |
| [Providers](Providers.md) | LLM provider guide: models, costs, switching, and fallbacks |
| [Memory System](Memory-System.md) | `Consciousness.md` format, rules, priority levels, and best practices |
| [Output Tiers](Output-Tiers.md) | Tier 0/1/2 decision logic, Publisher themes, and examples |
| [Extension Guide](Extension-Guide.md) | How to add new agents, tools, and LLM providers |
| [Development](Development.md) | Contributing, testing, linting, and dev environment setup |
| [Troubleshooting](Troubleshooting.md) | FAQ, common errors, and debugging tips |

---

## Core Concepts

### The Seven Agents

| ID | Agent | One-Line Role |
|----|-------|---------------|
| OVR_DIR_01 | **Orchestrator** | Routes every request; delegates and synthesizes |
| OVR_RES_02 | **Researcher** | Fetches and structures information from web and files |
| OVR_COD_03 | **Coder** | Writes, debugs, tests, and refactors code |
| OVR_ANL_04 | **Analyst** | Analyzes data and produces structured insights |
| OVR_WRT_05 | **Writer** | Creates polished Markdown documents and reports |
| OVR_REV_06 | **Reviewer** | Quality gates all outputs before delivery |
| OVR_PUB_07 | **Publisher** | Produces styled self-contained HTML reports |

### The Three Output Tiers

| Tier | When | Format |
|------|------|--------|
| **0 — Direct** | Simple Q&A, one-liners | Inline text |
| **1 — Markdown** | Docs, guides, summaries | `.md` file via Writer |
| **2 — HTML Report** | Detailed reports, dashboards | Self-contained `.html` via Publisher |

### The Memory System

`Consciousness.md` is the single shared memory file. Every agent reads it at session start and writes findings at session end. It enables:
- **Cross-session continuity** — persisted facts survive between runs
- **Cross-agent handoffs** — structured pending handoff entries
- **Error broadcasting** — `[CRITICAL]` entries block all agents until resolved
- **Work deduplication** — `[WIP]` entries prevent duplicate work

---

## Repository Layout

```
Overlord11/
├── agents/          # Agent system prompts (.md files)
├── tools/
│   ├── defs/        # Tool JSON schemas (provider-agnostic)
│   └── python/      # Tool Python implementations
├── docs/            # This wiki
├── tests/
│   ├── test.py              # 81-test suite covering all 16 modules
│   └── test_results.json    # Machine-readable results (auto-generated)
├── config.json      # Unified configuration
├── Consciousness.md # Shared agent memory
├── ONBOARDING.md    # Universal LLM onboarding guide
├── CHANGELOG.md     # Release history
└── .env.example     # API key template
```

---

## Getting Help

- **New user?** Start with [Getting Started](Getting-Started.md)
- **Looking for a specific agent?** See [Agents Reference](Agents-Reference.md)
- **Need to use a tool from CLI?** See [Tools Reference](Tools-Reference.md)
- **Something broken?** Check [Troubleshooting](Troubleshooting.md)
- **Want to extend the framework?** See [Extension Guide](Extension-Guide.md)
