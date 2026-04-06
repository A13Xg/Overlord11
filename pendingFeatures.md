# Pending Features — Overlord11

> Last updated: 2026-04-06
> Status key: ✅ Done | 🔄 In Progress | ⬜ Pending | ⭐ Priority

---

## Current Sprint — v2.4.0

| Feature | Priority | Status | Notes |
|---------|----------|--------|-------|
| Complete Test Suite | High | ⬜ | Cover all 41+ tools; test launcher w/ pass-fail report |
| Auth Login Page | High | ⬜ | AES256 hash table, multi-user, admin/admin default, tactical theme |
| TTL Enforcement (consciousness_tool) | High | ⬜ | Auto-expire entries past their TTL |
| Parallel Job Execution | High | ⬜ | Worker pool + dependency detection to prevent concurrent tool conflicts |
| WebUI File Browser + HTML Preview | High | ⬜ | Workspace tree, inline preview (md/html/json/py), fitting extras |
| Job Templates | Medium | ⬜ | Variety of pre-built templates; no redundant/similar ones |
| Provider Health Display | High | ⬜ | All models queried; smart fallback; session memory for failures; Gemma models |
| Setup Wizard | Medium | ⬜ | Master console (server/system) + per-user (auto-start, fallback, alerts) |

---

## Priority Backlog — ⭐ Starred

| Feature | Why Starred |
|---------|-------------|
| ~~⭐ LLM Streaming~~ | ✅ Done — streaming SSE for Anthropic/OpenAI/Gemini, TOKEN events, live output panel in WebUI |
| ⭐ NotificationTool | Desktop/browser push notifications for job complete, errors, handoffs |
| ~~⭐ DataVisualizer~~ | ✅ Done — self-contained HTML charts (bar/line/pie/scatter/heatmap/timeline/dashboard), no external deps |
| ⭐ Tool Result Caching | Hash(tool + params) → cached result; skip redundant tool calls within and across sessions |

---

## Extended Backlog

| Feature | Category | Notes |
|---------|----------|-------|
| Agent-to-Agent Direct Messaging | Architecture | Named queues; skip Orchestrator for peer-to-peer handoffs |
| Workflow Builder | WebUI | Drag-drop visual pipeline builder for agent chains |
| Plugin/Extension System | Architecture | Drop a `.py` into `plugins/` and it auto-registers as a tool |
| Vector Memory Store | Memory | Embeddings for semantic search in Consciousness.md / Memory.md |
| Scheduled Jobs | Engine | Cron-style recurring tasks; stored in `.webui_schedules.json` |
| Multi-workspace Comparison View | WebUI | Side-by-side diff of two workspace runs |
| Agent Performance Metrics | WebUI | Token counts, latency, tool call frequency per agent |
| Export/Import Agent Configs | WebUI | Download/upload `.json` bundles of agent+tool configs |
| Rate Limiting & Budget Tracker | Engine | Per-provider spend tracking; hard stop at configurable budget |
| WebSocket Upgrade | Backend | Replace SSE with bidirectional WS for richer event handling |
| Theme Toggle | WebUI | Dark/light/custom theme switcher |
| Consciousness TTL Dashboard | WebUI | Visual expiry timeline for Consciousness.md entries |

---

## Implementation Notes

- All new tools follow the pattern: `tools/defs/<name>.json` + `tools/python/<name>.py`
- All new tools must be registered in `config.json` and documented in `docs/Tools-Reference.md`
- All new backend routes go in `backend/api/` as their own module
- Auth is session-cookie based (FastAPI `SessionMiddleware`); hash storage in `backend/auth/users.json`
- Parallel job execution: `max_concurrent_jobs` configurable in `config.json` under `orchestration`
- Provider health: session-level failed-model set; time-based decay (retry after 5 min) for persistent failures
