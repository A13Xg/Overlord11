# Overlord11

Overlord11 is a FastAPI-based WebUI for running goal-driven jobs with LLM orchestration, tool execution, and per-job workspace artifacts.

## What It Does

- Runs jobs from a browser UI.
- Supports orchestrated tool use via MCP (`mcp_orchestrated` mode).
- Streams live job events/tokens during execution.
- Stores all job outputs under `workspace/<session_id>/`.
- Exposes artifact APIs and in-UI file browsing (including `output`, `artifacts`, and other created files).

## Quick Start

1. Create and activate a Python environment (Python 3.11+ recommended).
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure API keys:

```bash
cp .env.example .env
```

4. Edit `.env` and set at least the key for your active provider in `config.json`.
5. Start the WebUI:

```bash
python scripts/run_webui.py
```

6. Open `http://localhost:7900`.

## Configuration

- Main config: `config.json`
- Runtime mode: `runtime.mode`
  - `mcp_orchestrated` uses MCP tool planning/calling.
- MCP enablement: `mcp.enabled`
- MCP server list: `mcp.servers`
- Workspace root: `workspace.root`

## Testing

Run all tests:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Notes:
- Some bash-specific shell executor tests are skipped on Windows by design.

## MCP Notes

- MCP server implementation lives in `tools/mcp/`.
- In hardened MCP mode, dangerous generic tools can be blocked by policy (`run_command`, `execute_python`).
- File-path arguments are sandboxed to the active job workspace to prevent writes outside allowed roots.

## Artifacts and Outputs

Each job writes under `workspace/<session_id>/`.

Common folders:
- `output/` or `outputs/`
- `artifacts/`
- `logs/`
- `tools/`
- `agent/`

The UI also shows an **Other Created Files** section for files created in other workspace locations.

## Utility Scripts

- `scripts/run_webui.py` - start backend server.
- `scripts/cleanup_workspace.py` - remove stale workspace/session artifacts.
- `scripts/kill_port.py --port 7900` - stop process bound to a port.
- `scripts/kill_port_7900.ps1` - Windows helper for port 7900.

## Security and Safety Defaults

- Session/workspace confinement for tool side effects.
- Path traversal protection for artifact/file APIs.
- Configurable loop guards and self-heal limits for orchestration loops.

