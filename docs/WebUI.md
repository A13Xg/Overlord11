# Tactical WebUI

The **Overlord11 Tactical WebUI** is a read-only browser-based interface for monitoring and inspecting Overlord11 agent jobs, artifacts, and finished products. It provides a dark "tactical" dashboard with live auto-refresh, a provider/model settings panel, and Markdown preview for deliverables.

---

## Quick Start

### 1. Install requirements

```bash
pip install -r requirements-webui.txt
```

### 2. Launch the server

```bash
python scripts/run_webui.py
```

Or directly with uvicorn:

```bash
uvicorn webui.app:app --host 127.0.0.1 --port 8844 --reload
```

### 3. Open the dashboard

Navigate to **http://127.0.0.1:8844** in your browser.

The interactive API docs are available at **http://127.0.0.1:8844/docs**.

---

## Browsing Jobs

Jobs are read from `workspace/jobs/` on the filesystem. Each subdirectory is treated as a job. The sidebar lists all jobs sorted by most-recently-updated, with colour-coded status indicators:

| Colour | Status |
|--------|--------|
| 🟠 Orange | Running |
| 🟢 Green | Completed |
| 🔴 Red | Failed |
| 🟡 Yellow | Pending |

Use the **filter buttons** (All / Running / Done / Failed) or the **search box** to narrow the list. The jobs list auto-refreshes every **5 seconds**. A running job's detail view refreshes every **3 seconds**.

---

## Job Detail Tabs

Click any job in the sidebar to open its detail view. Four tabs are available:

### Overview
Shows: Job ID, status, goal, provider, model, created/updated timestamps, and the verify summary (if present). A collapsible **State Snapshot** renders the raw `state.json` content as formatted JSON.

### Events
A reverse-chronological list of events from `events.jsonl`. Each event is colour-coded by type (info/warn/error/success) and shows the timestamp and message.

### Artifacts
A file tree of all files in the job directory (excluding `state.json` and `events.jsonl`). Click any row to **inline-preview** the file. Markdown files (`.md`) are rendered with Marked.js. A download button (↓) is available for each file. Finished products are marked with ⭐.

### ⭐ Finished Products
Filters to only show finished-product artifacts (files in `artifacts/deliverables/`, `artifacts/reports/`, or `artifacts/`). Markdown files are rendered inline automatically.

---

## Finished Products

A file is considered a **finished product** if its path (relative to the job directory) starts with any of:

- `artifacts/deliverables/`
- `artifacts/reports/`
- `artifacts/`

Or exactly matches:

- `artifacts/reports/debrief.md`
- `artifacts/final_report.md`
- `artifacts/output.md`

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check — returns `{"status":"ok"}` |
| `GET` | `/api/jobs` | List all jobs. Query: `?status=running\|completed\|failed\|pending`, `?q=search` |
| `GET` | `/api/jobs/{job_id}` | Full job detail (state, events, artifacts) |
| `GET` | `/api/jobs/{job_id}/artifacts` | List artifacts for a job |
| `GET` | `/api/jobs/{job_id}/artifacts/{path}` | Download/view a specific artifact |
| `GET` | `/api/config` | Current provider/model configuration (no API keys) |
| `GET` | `/docs` | Interactive OpenAPI docs (Swagger UI) |

All endpoints are **read-only** (GET/HEAD/OPTIONS only).

---

## Settings Panel

Click the **⚙ Settings** button in the top-right to open the settings overlay. It shows the currently active provider and model, populated from `config.json`. All available models and their descriptions are listed in the dropdown.

> **Note:** The Settings panel is view-only. To change the active provider or model, edit `config.json` directly.

---

## Troubleshooting

### Backend offline / "Cannot reach backend"
- Ensure the server is running: `python scripts/run_webui.py`
- Check the port is not in use: `lsof -i :8844`
- Verify you are browsing `http://127.0.0.1:8844` (not HTTPS)

### CORS errors in browser console
The WebUI serves both the API and the frontend from the same origin, so CORS should not be an issue for normal use. If you are running the frontend separately (e.g., on a different port during development), the backend has `allow_origins=["*"]` enabled.

### No jobs appear
- Ensure `workspace/jobs/` exists and contains subdirectories
- Each job directory should ideally have a `state.json` file with a `status` field
- Jobs without `state.json` will show as `pending` with the directory mtime as the timestamp

### Port already in use
Change the port in `scripts/run_webui.py` or pass `--port XXXX` directly to uvicorn.

### Markdown not rendering
Marked.js is loaded from the jsDelivr CDN. Ensure you have internet access, or host the script locally and update the `<script>` tag in `webui/static/index.html`.
