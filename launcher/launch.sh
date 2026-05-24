#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

DEFAULT_PORT="${OVERLORD_PORT:-${PORT:-7900}}"
PORT="${DEFAULT_PORT}"
ACTION="run"
ACTION_SET="false"

usage() {
  cat <<'EOF'
Overlord11 Bash Launcher

Usage:
  ./launcher/launch.sh [options]

Options:
  -p, --port <port>   Port to run/stop (default: OVERLORD_PORT, PORT, or 7900)
  -stop               Stop process listening on the selected port (SIGTERM)
  -kill               Force kill process on the selected port (SIGKILL)
  -h, --help          Show help

Examples:
  ./launcher/launch.sh
  ./launcher/launch.sh --port 8000
  ./launcher/launch.sh -stop --port 7900
  ./launcher/launch.sh -kill -p 7900
EOF
}

log() {
  echo "[launcher] $*"
}

err() {
  echo "[launcher] ERROR: $*" >&2
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

require_port_number() {
  if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [[ "$PORT" -lt 1 ]] || [[ "$PORT" -gt 65535 ]]; then
    err "Invalid port: $PORT"
    exit 1
  fi
}

run_install_cmd() {
  local cmd="$1"
  if command_exists sudo; then
    eval "sudo ${cmd}"
  else
    eval "${cmd}"
  fi
}

install_python() {
  log "Python 3 not found. Attempting install..."

  if command_exists brew; then
    brew install python
    return
  fi

  if command_exists apt-get; then
    run_install_cmd "apt-get update"
    run_install_cmd "apt-get install -y python3 python3-pip"
    return
  fi

  if command_exists dnf; then
    run_install_cmd "dnf install -y python3 python3-pip"
    return
  fi

  if command_exists yum; then
    run_install_cmd "yum install -y python3 python3-pip"
    return
  fi

  if command_exists pacman; then
    run_install_cmd "pacman -Sy --noconfirm python python-pip"
    return
  fi

  if command_exists zypper; then
    run_install_cmd "zypper --non-interactive install python3 python3-pip"
    return
  fi

  err "Could not auto-install Python 3 on this system. Install Python 3 manually and re-run."
  exit 1
}

install_node() {
  log "Node.js/npm not found. Attempting install..."

  if command_exists brew; then
    brew install node
    return
  fi

  if command_exists apt-get; then
    run_install_cmd "apt-get update"
    run_install_cmd "apt-get install -y nodejs npm"
    return
  fi

  if command_exists dnf; then
    run_install_cmd "dnf install -y nodejs npm"
    return
  fi

  if command_exists yum; then
    run_install_cmd "yum install -y nodejs npm"
    return
  fi

  if command_exists pacman; then
    run_install_cmd "pacman -Sy --noconfirm nodejs npm"
    return
  fi

  if command_exists zypper; then
    run_install_cmd "zypper --non-interactive install nodejs npm"
    return
  fi

  err "Could not auto-install Node.js/npm on this system. Install Node.js manually and re-run."
  exit 1
}

resolve_python() {
  if command_exists python3; then
    echo "python3"
    return
  fi

  if command_exists python; then
    if python - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info.major == 3 else 1)
PY
    then
      echo "python"
      return
    fi
  fi

  install_python

  if command_exists python3; then
    echo "python3"
    return
  fi

  if command_exists python; then
    echo "python"
    return
  fi

  err "Python install completed but python executable is still unavailable."
  exit 1
}

ensure_pip() {
  local py_cmd="$1"
  if ! "$py_cmd" -m pip --version >/dev/null 2>&1; then
    log "pip missing. Attempting bootstrap via ensurepip..."
    "$py_cmd" -m ensurepip --upgrade >/dev/null 2>&1 || true
  fi

  if ! "$py_cmd" -m pip --version >/dev/null 2>&1; then
    err "pip is unavailable for $py_cmd. Install pip and re-run."
    exit 1
  fi
}

ensure_node_npm() {
  if ! command_exists node || ! command_exists npm; then
    install_node
  fi

  if ! command_exists node || ! command_exists npm; then
    err "Node.js/npm install completed but executables are still unavailable."
    exit 1
  fi
}

install_python_deps() {
  local py_cmd="$1"
  local req_file="${PROJECT_ROOT}/requirements.txt"

  if [[ -f "$req_file" ]]; then
    log "Installing Python dependencies from requirements.txt"
    "$py_cmd" -m pip install --upgrade pip
    "$py_cmd" -m pip install -r "$req_file"
  else
    log "No requirements.txt found. Skipping Python dependency install."
  fi
}

install_npm_deps() {
  local package_json="${PROJECT_ROOT}/package.json"
  if [[ -f "$package_json" ]]; then
    local lock_file="${PROJECT_ROOT}/package-lock.json"
    if [[ -f "$lock_file" ]]; then
      log "Installing npm dependencies with package-lock.json (npm ci)"
      (cd "$PROJECT_ROOT" && npm ci)
    else
      log "Installing npm dependencies (npm install)"
      (cd "$PROJECT_ROOT" && npm install)
    fi
  else
    log "No package.json found. Skipping npm dependency install."
  fi
}

pids_on_port() {
  local pids=""

  if command_exists lsof; then
    pids="$(lsof -ti tcp:"$PORT" -sTCP:LISTEN || true)"
  elif command_exists ss; then
    pids="$(ss -ltnp 2>/dev/null | awk -v p=":$PORT" '$4 ~ p {print $NF}' | sed -E 's/.*pid=([0-9]+).*/\1/' | grep -E '^[0-9]+$' || true)"
  elif command_exists netstat; then
    pids="$(netstat -ltnp 2>/dev/null | awk -v p=":$PORT" '$4 ~ p {print $7}' | cut -d/ -f1 | grep -E '^[0-9]+$' || true)"
  fi

  echo "$pids" | tr ' ' '\n' | grep -E '^[0-9]+$' | sort -u || true
}

stop_or_kill_port() {
  local signal="TERM"
  if [[ "$ACTION" == "kill" ]]; then
    signal="KILL"
  fi

  local pids
  pids="$(pids_on_port)"

  if [[ -z "$pids" ]]; then
    log "No listening process found on port $PORT"
    return
  fi

  log "Sending SIG${signal} to process(es) on port $PORT: $(echo "$pids" | paste -sd ',' -)"
  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    kill "-${signal}" "$pid" 2>/dev/null || true
  done <<< "$pids"

  log "Port action completed for $PORT"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--port)
      if [[ $# -lt 2 ]]; then
        err "Missing value after $1"
        usage
        exit 1
      fi
      PORT="$2"
      shift 2
      ;;
    -stop)
      if [[ "$ACTION_SET" == "true" && "$ACTION" != "stop" ]]; then
        err "Use either -stop or -kill, not both."
        exit 1
      fi
      ACTION="stop"
      ACTION_SET="true"
      shift
      ;;
    -kill)
      if [[ "$ACTION_SET" == "true" && "$ACTION" != "kill" ]]; then
        err "Use either -stop or -kill, not both."
        exit 1
      fi
      ACTION="kill"
      ACTION_SET="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      err "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

require_port_number

if [[ "$ACTION" == "stop" || "$ACTION" == "kill" ]]; then
  stop_or_kill_port
  exit 0
fi

PY_CMD="$(resolve_python)"
ensure_pip "$PY_CMD"
ensure_node_npm
install_python_deps "$PY_CMD"
install_npm_deps

log "Starting Overlord11 on port $PORT"
cd "$PROJECT_ROOT"
PORT="$PORT" "$PY_CMD" scripts/run_webui.py
