#!/usr/bin/env bash
set -euo pipefail

DEFAULT_PORT=4310
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

kill_port() {
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
}

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

APP_CMD="python3 app.py --port {port}"
APP_CMD="${APP_CMD//\{port\}/$PORT}"

echo "[launcher] Starting app on port $PORT"
eval "$APP_CMD"
