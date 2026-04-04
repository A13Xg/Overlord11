"""
Overlord11 Engine - CLI Entry Point
======================================
Interactive terminal interface for the Overlord11 engine.
"""

import json
import os
import sys
from pathlib import Path

# Ensure engine package is importable
_BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE_DIR))

from engine import EngineRunner, EventStream, EventType  # noqa: E402

# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_DIM = "\033[2m"


def _c(text: str, colour: str) -> str:
    return f"{colour}{text}{_RESET}"


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

def _get_config() -> dict:
    cfg_path = _BASE_DIR / "config.json"
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def _print_banner() -> None:
    version = _get_config().get("version", "?")
    banner = rf"""
{_BOLD}{_CYAN}
  ___  _   _ ___ ___ _    ___  ___  ___  _ _
 / _ \| | | | __| _ \ |  / _ \| _ \|   \/ |/|
| (_) | |_| | _||   / |_| (_) |   /| |) |  /|
 \___/ \___/|___|_|_\____\___/|_|_\|___/|_| |
                    ENGINE  v{version}
{_RESET}"""
    print(banner)


# ---------------------------------------------------------------------------
# Session listing helper
# ---------------------------------------------------------------------------

def _list_sessions() -> list:
    workspace = _BASE_DIR / "workspace"
    index_file = workspace / "session_index.json"
    if not index_file.exists():
        return []
    try:
        data = json.loads(index_file.read_text(encoding="utf-8"))
        sessions = data.get("sessions", {})
        return sorted(
            [{"id": sid, **info} for sid, info in sessions.items()],
            key=lambda x: x.get("created_at", ""),
            reverse=True,
        )[:10]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Event callback for live display
# ---------------------------------------------------------------------------

def _make_event_callback(verbose: bool):
    def _on_event(event: dict):
        etype = event.get("type", "")
        if etype == EventType.AGENT_START:
            print(_c(f"  ▶ Agent {event.get('agent_id')} — loop {event.get('loop')}", _CYAN))
        elif etype == EventType.AGENT_COMPLETE:
            print(_c(f"  ✔ Agent complete (loop {event.get('loop')}, {event.get('response_len', 0)} chars)", _GREEN))
        elif etype == EventType.TOOL_CALL:
            print(_c(f"  ⚙ Tool call: {event.get('tool')}", _YELLOW))
        elif etype == EventType.TOOL_RESULT:
            print(_c(f"  ✔ Tool result: {event.get('tool')} ({event.get('duration_ms', 0):.0f}ms)", _GREEN))
        elif etype == EventType.TOOL_ERROR:
            print(_c(f"  ✘ Tool error: {event.get('tool')} — {event.get('error', '')[:80]}", _RED))
        elif etype == EventType.SESSION_START:
            print(_c(f"  Session started: {event.get('session_id')}", _DIM))
        elif etype == EventType.SESSION_END:
            print(_c(f"  Session ended: {event.get('status')}", _DIM))
        elif etype == EventType.ERROR:
            print(_c(f"  ✘ Error: {event.get('message', '')[:120]}", _RED))
    return _on_event


# ---------------------------------------------------------------------------
# Provider / model selection helpers
# ---------------------------------------------------------------------------

def _save_config(cfg: dict) -> None:
    cfg_path = _BASE_DIR / "config.json"
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _menu_select_provider(cfg: dict) -> None:
    providers = [p for p in cfg.get("providers", {}) if p != "active"]
    current = cfg["providers"].get("active", "?")
    print(f"\nCurrent provider: {_c(current, _CYAN)}")
    for i, p in enumerate(providers, 1):
        marker = " ◀" if p == current else ""
        print(f"  {i}. {p}{marker}")
    choice = input("Select provider number (or Enter to cancel): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(providers):
        new_provider = providers[int(choice) - 1]
        cfg["providers"]["active"] = new_provider
        _save_config(cfg)
        print(_c(f"Provider switched to: {new_provider}", _GREEN))


def _menu_select_model(cfg: dict) -> None:
    active = cfg["providers"].get("active", "anthropic")
    provider_cfg = cfg["providers"].get(active, {})
    current_model = provider_cfg.get("model", "?")
    models = list(provider_cfg.get("available_models", {}).keys())
    print(f"\nProvider: {_c(active, _CYAN)}  Current model: {_c(current_model, _GREEN)}")
    for i, m in enumerate(models, 1):
        desc = provider_cfg["available_models"].get(m, "")
        marker = " ◀" if m == current_model else ""
        print(f"  {i}. {m}{marker}  {_c(desc, _DIM)}")
    choice = input("Select model number (or Enter to cancel): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(models):
        new_model = models[int(choice) - 1]
        cfg["providers"][active]["model"] = new_model
        _save_config(cfg)
        print(_c(f"Model switched to: {new_model}", _GREEN))


# ---------------------------------------------------------------------------
# Run session helper
# ---------------------------------------------------------------------------

def _run_session(session_id=None) -> None:
    user_input = input(_c("\nEnter your request: ", _BOLD)).strip()
    if not user_input:
        print(_c("No input provided.", _YELLOW))
        return

    cfg = _get_config()
    runner = EngineRunner(verbose=False)
    runner.events.callbacks.append(_make_event_callback(verbose=True))

    print(_c("\nRunning engine...\n", _CYAN))
    try:
        result = runner.run(user_input=user_input, session_id=session_id)
    except Exception as exc:
        print(_c(f"\n✘ Engine error: {exc}", _RED))
        return

    print("\n" + _c("─" * 60, _DIM))
    print(_c("OUTPUT:", _BOLD))
    print(result.get("output", "(no output)"))
    print(_c("─" * 60, _DIM))
    status = result.get("status", "?")
    colour = _GREEN if status == "complete" else _YELLOW
    print(_c(f"Status: {status}  │  Session: {result.get('session_id')}", colour))


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def main() -> None:
    _print_banner()

    while True:
        cfg = _get_config()
        active_provider = cfg["providers"].get("active", "?")
        active_model = cfg["providers"].get(active_provider, {}).get("model", "?")
        print(f"\n{_c('MENU', _BOLD)}  (provider: {_c(active_provider, _CYAN)}  model: {_c(active_model, _GREEN)})")
        print("  1. Start new session")
        print("  2. Resume existing session")
        print("  3. Select provider")
        print("  4. Select model")
        print("  5. Exit")
        choice = input(_c("\nChoice: ", _BOLD)).strip()

        if choice == "1":
            _run_session()

        elif choice == "2":
            sessions = _list_sessions()
            if not sessions:
                print(_c("No sessions found.", _YELLOW))
                continue
            print("\nRecent sessions:")
            for i, s in enumerate(sessions, 1):
                print(f"  {i}. [{s.get('id')}]  {s.get('description', '')[:60]}  ({s.get('status', '?')})")
            idx = input("Select session number (or Enter to cancel): ").strip()
            if idx.isdigit() and 1 <= int(idx) <= len(sessions):
                sid = sessions[int(idx) - 1]["id"]
                _run_session(session_id=sid)

        elif choice == "3":
            _menu_select_provider(cfg)

        elif choice == "4":
            _menu_select_model(cfg)

        elif choice in ("5", "q", "exit", "quit"):
            print(_c("Goodbye.", _GREEN))
            break
        else:
            print(_c("Invalid choice.", _RED))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(_c("\n\nInterrupted. Goodbye.", _YELLOW))
        sys.exit(0)
