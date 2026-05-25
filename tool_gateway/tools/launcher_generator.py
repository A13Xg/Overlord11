from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseTool


class LauncherGeneratorArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    project_dir: str = Field(min_length=1)
    app_command: str = Field(min_length=1)
    port: int = Field(default=3000, ge=1, le=65535)
    overwrite: bool = True


class LauncherGeneratorTool(BaseTool):
    name = "launcher_generator"
    description = "Generate cross-platform launchers with dependency install and -kill support"
    risk_level = "medium"
    destructive = True
    supports_dry_run = False
    timeout_behavior = "not_applicable"
    examples = [
        {
            "project_dir": "output/app",
            "app_command": "python3 app.py --port {port}",
            "port": 3000,
        }
    ]
    input_model = LauncherGeneratorArgs

    def execute(self, args: LauncherGeneratorArgs) -> dict[str, Any]:
        workspace_root = Path(self._resolve_workspace_root()).resolve()
        project_dir = self._resolve_target_path(args.project_dir, workspace_root)
        launcher_dir = project_dir / "launcher"
        launcher_dir.mkdir(parents=True, exist_ok=True)

        launch_sh = launcher_dir / "launch.sh"
        launch_ps1 = launcher_dir / "launch.ps1"

        if (launch_sh.exists() or launch_ps1.exists()) and not args.overwrite:
            raise ValueError("Launcher files already exist and overwrite=false")

        app_cmd_escaped = args.app_command.replace('"', '\\"')

        sh_content = self._build_sh(app_cmd_escaped, args.port)
        ps1_content = self._build_ps1(args.app_command, args.port)

        launch_sh.write_text(sh_content, encoding="utf-8")
        launch_ps1.write_text(ps1_content, encoding="utf-8")

        try:
            launch_sh.chmod(0o755)
        except OSError:
            pass

        return {
            "project_dir": str(project_dir),
            "launcher_dir": str(launcher_dir),
            "files": [str(launch_sh), str(launch_ps1)],
            "port": args.port,
            "app_command": args.app_command,
        }

    def _build_sh(self, app_command: str, port: int) -> str:
        return f"""#!/usr/bin/env bash
set -euo pipefail

DEFAULT_PORT={port}
PORT="$DEFAULT_PORT"
KILL_MODE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -kill|--kill)
      KILL_MODE=1
      shift
      ;;
    -port|--port)
      PORT="$2"
      shift 2
      ;;
    *)
      echo "Unknown arg: $1"
      exit 1
      ;;
  esac
done

kill_port() {{
  local pids
  pids=$(lsof -ti tcp:"$PORT" || true)
  if [[ -n "$pids" ]]; then
    echo "[launcher] Stopping port $PORT: $pids"
    kill -TERM $pids || true
    sleep 1
    pids=$(lsof -ti tcp:"$PORT" || true)
    if [[ -n "$pids" ]]; then
      kill -KILL $pids || true
    fi
  else
    echo "[launcher] No process on port $PORT"
  fi
}}

if [[ "$KILL_MODE" == "1" ]]; then
  kill_port
  exit 0
fi

if [[ -f "requirements.txt" ]]; then
  echo "[launcher] Installing Python dependencies"
  python3 -m pip install -r requirements.txt
fi

if [[ -f "package.json" ]]; then
  echo "[launcher] Installing Node dependencies"
  if [[ -f "package-lock.json" ]]; then
    npm ci
  else
    npm install
  fi
fi

APP_CMD=\"{app_command}\"
APP_CMD=\"${{APP_CMD//\{{port\}}/$PORT}}\"

echo "[launcher] Starting app on port $PORT"
eval "$APP_CMD"
"""

    def _build_ps1(self, app_command: str, port: int) -> str:
        return f"""param(
  [switch]$Kill,
  [int]$Port = {port}
)

$ErrorActionPreference = "Stop"

function Stop-PortProcess {{
  param([int]$TargetPort)

  $pids = @()
  try {{
    $pids = (Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess | Sort-Object -Unique)
  }} catch {{
    $pids = @()
  }}

  if (-not $pids -or $pids.Count -eq 0) {{
    Write-Host "[launcher] No process on port $TargetPort"
    return
  }}

  Write-Host "[launcher] Stopping port $TargetPort: $($pids -join ', ')"
  foreach ($pid in $pids) {{
    try {{ Stop-Process -Id $pid -ErrorAction SilentlyContinue }} catch {{ }}
  }}
  Start-Sleep -Seconds 1
  foreach ($pid in $pids) {{
    try {{ Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue }} catch {{ }}
  }}
}}

if ($Kill) {{
  Stop-PortProcess -TargetPort $Port
  exit 0
}}

if (Test-Path "requirements.txt") {{
  Write-Host "[launcher] Installing Python dependencies"
  python -m pip install -r requirements.txt
}}

if (Test-Path "package.json") {{
  Write-Host "[launcher] Installing Node dependencies"
  if (Test-Path "package-lock.json") {{ npm ci }} else {{ npm install }}
}}

$appCmd = "{app_command}".Replace("{{port}}", "$Port")
Write-Host "[launcher] Starting app on port $Port"
Invoke-Expression $appCmd
"""

    def _resolve_workspace_root(self) -> str:
        base = os.environ.get("OVERLORD11_TASK_DIR") or os.getcwd()
        return str(Path(base).resolve())

    def _resolve_target_path(self, raw_path: str, workspace_root: Path) -> Path:
        p = Path(raw_path)
        resolved = (workspace_root / p).resolve() if not p.is_absolute() else p.resolve()
        try:
            resolved.relative_to(workspace_root)
        except ValueError as exc:
            raise ValueError("project_dir must resolve within workspace root") from exc
        return resolved
