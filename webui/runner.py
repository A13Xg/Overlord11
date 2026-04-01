"""
webui/runner.py — Autonomous runner loop for Overlord11 Tactical WebUI.

Implements:
  - Milestone A: iteration loop, budgets, verify gate, pause/stop/resume
  - Milestone B: DIRECTIVES_APPLIED, ARTIFACT_WRITTEN events
  - Milestone C: self-healing venv repair (ModuleNotFoundError detection)
  - Milestone D: provider interface, StepPlan, safe patch apply

Runner lifecycle:
  JOB_STARTING → (iterations) → COMPLETE | FAILED | STOPPED
                              | TIME_BUDGET_EXCEEDED
                              | ITERATION_BUDGET_EXCEEDED
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
import time
import venv as _venv_mod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .events import EventLevel, EventType, emit_event, make_event
from .llm_interface import LLMCallError, LLMConfigError, llm_call
from .models import JobState, JobStatus
from .providers.router import get_provider_config
from .reviewer import run_review
from . import state_store

# ---------------------------------------------------------------------------
# Control flags and SSE queues
# ---------------------------------------------------------------------------

_control_flags: dict[str, str | None] = {}
_sse_queues: dict[str, list[asyncio.Queue]] = {}
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Regex to detect missing module errors in verify output
_MISSING_MODULE_RE = re.compile(
    r"ModuleNotFoundError: No module named '([^']+)'", re.IGNORECASE
)

# Max packages that can be auto-installed per job
_MAX_AUTO_PACKAGES = 20

# ---------------------------------------------------------------------------
# Public control API
# ---------------------------------------------------------------------------

def set_control(job_id: str, flag: str) -> None:
    """Set a control flag for a running job (pause/resume/stop)."""
    _control_flags[job_id] = flag


def subscribe_sse(job_id: str) -> asyncio.Queue:
    """Register a new SSE subscriber and return its queue."""
    q: asyncio.Queue = asyncio.Queue()
    _sse_queues.setdefault(job_id, []).append(q)
    return q


def unsubscribe_sse(job_id: str, q: asyncio.Queue) -> None:
    """Remove an SSE subscriber queue."""
    queues = _sse_queues.get(job_id, [])
    if q in queues:
        queues.remove(q)


# ---------------------------------------------------------------------------
# Internal emit helper
# ---------------------------------------------------------------------------

def _emit(event: dict[str, Any]) -> None:
    """Persist event to disk and push to all live SSE queues."""
    state_store.append_event(event)
    job_id = event.get("job_id", "")
    for q in list(_sse_queues.get(job_id, [])):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


def _emit_ev(job_id: str, ev_type: EventType, level=EventLevel.INFO, **payload) -> dict:
    """Convenience wrapper: build + emit + return event."""
    ev = make_event(ev_type, job_id, payload=payload or None, level=level)
    _emit(ev)
    return ev


# ---------------------------------------------------------------------------
# Main runner entry point
# ---------------------------------------------------------------------------

async def run_job(job_id: str) -> None:
    """Async task that executes the full autonomous runner loop for *job_id*."""
    state = state_store.load_state(job_id)
    if state is None:
        return

    _control_flags[job_id] = None
    start_wall = time.monotonic()

    # Transition → RUNNING
    state.status = JobStatus.RUNNING
    state.started_at = datetime.now(timezone.utc).isoformat()
    state_store.save_state(state)
    _emit_ev(job_id, EventType.STATUS, status="RUNNING")
    _emit_ev(job_id, EventType.JOB_STARTING, goal=state.goal)

    # Resolve provider config (log assumption if missing key)
    try:
        pcfg = get_provider_config(state.provider, state.model)
        state.provider = pcfg["provider"]
        state.model = pcfg["model"]
        if not pcfg["api_key"]:
            _emit_assumption(
                job_id,
                f"No API key for provider '{state.provider}' "
                f"(env: {pcfg['api_key_env']}). Running in dry-run mode.",
            )
    except Exception as exc:
        state.provider = state.provider or "anthropic"
        _emit_assumption(job_id, f"Provider config error: {exc}. Defaulting to dry-run mode.")

    state_store.save_state(state)

    try:
        for iteration in range(1, state.max_iterations + 1):
            # ----------------------------------------------------------------
            # Budget: time
            # ----------------------------------------------------------------
            elapsed = time.monotonic() - start_wall
            if elapsed >= state.max_time_seconds:
                await _finish(
                    state,
                    JobStatus.FAILED,
                    f"Time budget exceeded ({elapsed:.0f}s ≥ {state.max_time_seconds}s)",
                    ev_type=EventType.TIME_BUDGET_EXCEEDED,
                )
                return

            # ----------------------------------------------------------------
            # Cooperative pause / stop check
            # ----------------------------------------------------------------
            flag = _control_flags.get(job_id)
            if flag == "stop":
                await _finish(state, JobStatus.STOPPED, "Stopped by user", ev_type=EventType.STOPPED)
                return
            if flag == "pause":
                state.status = JobStatus.PAUSED
                state_store.save_state(state)
                _emit_ev(job_id, EventType.PAUSED, iteration=iteration)
                while _control_flags.get(job_id) == "pause":
                    await asyncio.sleep(0.5)
                if _control_flags.get(job_id) == "stop":
                    await _finish(state, JobStatus.STOPPED, "Stopped while paused", ev_type=EventType.STOPPED)
                    return
                state.status = JobStatus.RUNNING
                state_store.save_state(state)
                _emit_ev(job_id, EventType.RESUMED, iteration=iteration)

            # ----------------------------------------------------------------
            # Apply pending directives
            # ----------------------------------------------------------------
            if state.pending_directives:
                applied = state.pending_directives[:]
                state.applied_directives.extend(applied)
                state.pending_directives = []
                state_store.save_state(state)
                _emit_ev(
                    job_id,
                    EventType.DIRECTIVES_APPLIED,
                    count=len(applied),
                    directives=[d.get("text", "") for d in applied],
                )

            # ----------------------------------------------------------------
            # ITERATION event
            # ----------------------------------------------------------------
            state.iteration = iteration
            _emit_ev(
                job_id,
                EventType.ITERATION,
                iteration=iteration,
                max_iterations=state.max_iterations,
                elapsed_s=round(elapsed, 1),
            )

            # ----------------------------------------------------------------
            # Step planning (LLM)
            # ----------------------------------------------------------------
            action = await _plan_step(state, iteration)

            if action.get("action") == "complete":
                summary = action.get("summary", "Goal achieved.")
                # Still run verify before accepting COMPLETE
                passed, output = await _run_verify(state)
                state.last_verify_passed = passed
                state.last_verify_output = output[-2000:]
                state_store.save_state(state)
                if passed:
                    review_passed = await _run_review_gate(state)
                    if review_passed:
                        await _finish(state, JobStatus.COMPLETE, summary, ev_type=EventType.COMPLETE)
                        return
                    # Reviewer failed — continue iterating
                else:
                    repaired = await _repair_loop(state, output)
                    if repaired:
                        review_passed = await _run_review_gate(state)
                        if review_passed:
                            await _finish(state, JobStatus.COMPLETE, f"Repaired and verified on iteration {iteration}", ev_type=EventType.COMPLETE)
                            return
                continue

            elif action.get("action") in ("patch", "repair"):
                await _apply_patch(state, action, iteration)

            elif action.get("action") == "tool_call":
                await _execute_tool(state, action)

            # ----------------------------------------------------------------
            # Verify gate
            # ----------------------------------------------------------------
            passed, output = await _run_verify(state)
            state.last_verify_passed = passed
            state.last_verify_output = output[-2000:]
            state_store.save_state(state)

            if passed:
                review_passed = await _run_review_gate(state)
                if review_passed:
                    await _finish(state, JobStatus.COMPLETE, f"Verify gate passed on iteration {iteration}", ev_type=EventType.COMPLETE)
                    return
            else:
                repaired = await _repair_loop(state, output)
                if repaired:
                    review_passed = await _run_review_gate(state)
                    if review_passed:
                        await _finish(state, JobStatus.COMPLETE, f"Repaired and verified on iteration {iteration}", ev_type=EventType.COMPLETE)
                        return

        # Max iterations reached
        await _finish(
            state,
            JobStatus.FAILED,
            f"Iteration budget exhausted ({state.max_iterations} iterations)",
            ev_type=EventType.ITERATION_BUDGET_EXCEEDED,
        )

    except asyncio.CancelledError:
        await _finish(state, JobStatus.FAILED, "Runner task cancelled")
        raise
    except Exception as exc:
        await _finish(state, JobStatus.FAILED, f"Unhandled runner error: {exc}")


# ---------------------------------------------------------------------------
# Step planning
# ---------------------------------------------------------------------------

async def _plan_step(state: JobState, iteration: int) -> dict[str, Any]:
    """Ask the LLM what to do next. Returns an action dict."""
    system = _build_system_prompt()
    history = _build_history(state, iteration)

    try:
        raw = await asyncio.to_thread(
            llm_call,
            history,
            job_id=state.job_id,
            system=system,
            provider=state.provider,
            model=state.model,
            emit=_emit,
        )
        action = _parse_action(raw, state.job_id)
    except (LLMConfigError, LLMCallError) as exc:
        _emit_assumption(state.job_id, f"LLM call failed ({exc}); defaulting to complete action")
        action = {"action": "complete", "summary": f"LLM unavailable: {exc}"}

    # Persist StepPlan if it's a structured action
    if action.get("action") in ("tool_call", "patch", "repair"):
        plan_artifact = f"plans/step_{iteration:03d}.json"
        state_store.write_artifact(state.job_id, plan_artifact, json.dumps(action, ensure_ascii=False, indent=2))
        _emit_ev(
            state.job_id,
            EventType.PLAN_CREATED,
            iteration=iteration,
            artifact_ref=plan_artifact,
        )
        _emit_artifact_written(state.job_id, plan_artifact)

    return action


def _build_system_prompt() -> str:
    return (
        "You are Overlord11, an autonomous coding assistant. "
        "Respond ONLY with a JSON object (no markdown fences) with one of:\n"
        '  {"action":"tool_call","tool":"<name>","args":{...}}\n'
        '  {"action":"patch","diff":"<unified diff>","rationale":"<why>"}\n'
        '  {"action":"repair","diff":"<unified diff>","rationale":"<why>"}\n'
        '  {"action":"complete","summary":"<what was achieved>"}\n'
        "Be concise. Prefer minimal diffs. Never hardcode API keys or model names."
    )


def _build_history(state: JobState, iteration: int) -> list[dict[str, str]]:
    if state.last_verify_passed is True:
        verify_line = "PASS"
    elif state.last_verify_passed is False:
        verify_line = "FAIL: " + (state.last_verify_output or "n/a")
    else:
        verify_line = "n/a"

    directives_text = ""
    if state.applied_directives:
        directives_text = "\n".join(
            d.get("text", "") for d in state.applied_directives[-3:]
        )
    elif state.pending_directives:
        directives_text = "\n".join(
            d.get("text", "") for d in state.pending_directives[-3:]
        )

    return [
        {
            "role": "user",
            "content": (
                f"GOAL: {state.goal}\n\n"
                f"ITERATION: {iteration}/{state.max_iterations}\n"
                f"LAST VERIFY: {verify_line}\n"
                f"DIRECTIVES: {directives_text or 'none'}\n\n"
                "What is the next action?"
            ),
        }
    ]


def _parse_action(raw: str, job_id: str) -> dict[str, Any]:
    """Parse LLM response into an action dict.

    Emits ASSUMPTION_LOG if the response cannot be parsed as structured JSON
    so operators have visibility into LLM output quality.
    """
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "action" in data:
            return data
    except json.JSONDecodeError:
        pass
    # Malformed JSON — log and default to complete action
    _emit_assumption(
        job_id,
        f"LLM returned unparseable JSON; defaulting to 'complete' action. "
        f"Raw (first 200 chars): {raw[:200]!r}",
    )
    return {"action": "complete", "summary": raw[:500]}


# ---------------------------------------------------------------------------
# Action executors
# ---------------------------------------------------------------------------

async def _apply_patch(state: JobState, action: dict[str, Any], iteration: int) -> None:
    """Apply a unified diff patch to the repo."""
    diff = action.get("diff", "")
    rationale = action.get("rationale", "")

    _emit_ev(state.job_id, EventType.PATCH_APPLY_START, iteration=iteration, rationale=rationale[:200])

    if diff:
        artifact_path = f"diffs/iter_{iteration:03d}.patch"
        state_store.write_artifact(state.job_id, artifact_path, diff)
        _emit_artifact_written(state.job_id, artifact_path)

        # Reject patches that target paths outside the repo root
        if _patch_escapes_root(diff):
            _emit_ev(
                state.job_id,
                EventType.PATCH_APPLY_RESULT,
                iteration=iteration,
                success=False,
                reason="Patch rejected: targets path outside repo root",
                level=EventLevel.ERROR,
            )
            return

        result = await asyncio.to_thread(
            _run_shell,
            ["patch", "-p1", "--forward", "--batch"],
            input_text=diff,
            cwd=str(_PROJECT_ROOT),
        )
        success = result["returncode"] == 0
        _emit_ev(
            state.job_id,
            EventType.PATCH_APPLY_RESULT,
            iteration=iteration,
            success=success,
            output=result["stdout"][-500:],
            artifact_ref=artifact_path,
        )
    else:
        _emit_ev(state.job_id, EventType.PATCH_APPLY_RESULT, iteration=iteration, success=False, reason="empty diff")


def _patch_escapes_root(diff: str) -> bool:
    """Return True if the patch tries to write outside the project root.

    Catches:
    - Path traversal via ``..`` segments
    - Absolute Unix paths (starting with ``/``)
    - Absolute Windows paths (e.g. ``C:\\`` or ``\\\\server``)
    - Paths that resolve outside _PROJECT_ROOT after normalization
    """
    for line in diff.splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            path_part = line[4:].split("\t")[0].strip()
            # Skip /dev/null (used for new files in git diffs)
            if path_part == "/dev/null":
                continue
            # Normalize: strip a/ or b/ prefix added by git
            path_part = re.sub(r'^[ab]/', '', path_part)
            # Reject absolute paths (Unix or Windows)
            if path_part.startswith("/") or re.match(r'^[A-Za-z]:[/\\]', path_part) or path_part.startswith("\\\\"):
                return True
            # Reject traversal via .. (use pathlib.Path.parts for cross-platform handling)
            from pathlib import PurePosixPath, PureWindowsPath
            try:
                parts = PurePosixPath(path_part).parts
                if ".." in parts:
                    return True
                # Also check Windows-style separators in case of mixed paths
                if "\\" in path_part:
                    win_parts = PureWindowsPath(path_part).parts
                    if ".." in win_parts:
                        return True
            except Exception:
                return True  # reject unparseable paths
            # Resolve against project root and verify containment
            try:
                resolved = (_PROJECT_ROOT / path_part).resolve()
                if not str(resolved).startswith(str(_PROJECT_ROOT.resolve())):
                    return True
            except Exception:
                return True  # reject on any resolution error
    return False


async def _execute_tool(state: JobState, action: dict[str, Any]) -> None:
    """
    Execute a named tool_call action.

    Supported built-in tools (safe, sandboxed):
      - ``shell``        Run a shell command (cwd=project root, timeout=60s)
      - ``read_file``    Read a text file relative to project root
      - ``write_file``   Write/overwrite a text file relative to project root
      - ``list_dir``     List directory contents relative to project root

    Unknown tools emit STEP_END with success=False and a descriptive error.
    """
    tool_name = action.get("tool", "unknown")
    args = action.get("args", {})
    _emit_ev(state.job_id, EventType.STEP_START, tool=tool_name, args=args)

    try:
        output, success = await _dispatch_tool(state, tool_name, args)
    except Exception as exc:
        output = f"Tool execution error: {exc}"
        success = False

    _emit_ev(
        state.job_id,
        EventType.STEP_END,
        tool=tool_name,
        success=success,
        output=str(output)[:500],
        level=EventLevel.INFO if success else EventLevel.WARN,
    )


async def _dispatch_tool(
    state: JobState,
    tool_name: str,
    args: dict[str, Any],
) -> tuple[str, bool]:
    """Route a tool_call to the appropriate implementation.

    Returns (output_text, success).
    """
    root = _PROJECT_ROOT

    if tool_name == "shell":
        cmd_str = args.get("command", "")
        if not cmd_str:
            return "Missing 'command' arg", False
        # Clamp timeout to a safe range (1-300 seconds)
        try:
            timeout = max(1, min(300, int(args.get("timeout", 60))))
        except (TypeError, ValueError):
            timeout = 60
        result = await asyncio.to_thread(
            _run_shell,
            ["bash", "-c", cmd_str],
            cwd=str(root),
            timeout=timeout,
        )
        output = (result["stdout"] + result["stderr"])[-2000:]
        return output, result["returncode"] == 0

    elif tool_name == "read_file":
        rel_path = args.get("path", "")
        if not rel_path:
            return "Missing 'path' arg", False
        # Safety: resolve and confirm within project root
        target = (root / rel_path).resolve()
        if not str(target).startswith(str(root.resolve())):
            return f"Path outside project root rejected: {rel_path!r}", False
        if not target.exists():
            return f"File not found: {rel_path!r}", False
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            return content[:8000], True
        except OSError as exc:
            return str(exc), False

    elif tool_name == "write_file":
        rel_path = args.get("path", "")
        content = args.get("content", "")
        if not rel_path:
            return "Missing 'path' arg", False
        target = (root / rel_path).resolve()
        if not str(target).startswith(str(root.resolve())):
            return f"Path outside project root rejected: {rel_path!r}", False
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            # Persist as artifact
            # Use sanitized relative path to avoid basename collisions
            safe_rel = rel_path.replace("/", "_").replace("\\", "_").lstrip("_")
            artifact_path = f"diffs/write_{safe_rel}"
            state_store.write_artifact(state.job_id, artifact_path, content[:8000])
            _emit_artifact_written(state.job_id, artifact_path)
            return f"Wrote {len(content)} bytes to {rel_path}", True
        except OSError as exc:
            return str(exc), False

    elif tool_name == "list_dir":
        rel_path = args.get("path", ".")
        target = (root / rel_path).resolve()
        if not str(target).startswith(str(root.resolve())):
            return f"Path outside project root rejected: {rel_path!r}", False
        if not target.is_dir():
            return f"Not a directory: {rel_path!r}", False
        try:
            entries = sorted(
                (("d" if e.is_dir() else "f"), e.name)
                for e in target.iterdir()
            )
            lines = [f"{'[dir]' if t=='d' else '     '} {n}" for t, n in entries]
            return "\n".join(lines[:200]), True
        except OSError as exc:
            return str(exc), False

    else:
        return f"Unknown tool: {tool_name!r}. Supported: shell, read_file, write_file, list_dir", False


# ---------------------------------------------------------------------------
# Verify gate
# ---------------------------------------------------------------------------

async def _run_verify(state: JobState) -> tuple[bool, str]:
    """
    Run the verify gate command.

    Uses ``state.verify_command`` if set, otherwise falls back to the default
    ``python tests/test.py --skip-web --quiet``.  If the default test script
    does not exist the verify gate is skipped and a warning is emitted so the
    runner does not stall on a misconfigured project.

    Uses venv python if one exists for this job.
    """
    _emit_ev(state.job_id, EventType.VERIFY_START, iteration=state.iteration)

    python_cmd = _get_python_cmd(state)

    if state.verify_command:
        cmd = list(state.verify_command)
    else:
        default_script = _PROJECT_ROOT / "tests" / "test.py"
        if not default_script.exists():
            warning = (
                f"Default verify script not found: {default_script}. "
                "Skipping verify gate — job will not be marked COMPLETE without passing verify."
            )
            _emit_assumption(state.job_id, warning)
            artifact_path = f"verify/iter_{state.iteration:03d}.log"
            state_store.write_artifact(state.job_id, artifact_path, warning)
            _emit_artifact_written(state.job_id, artifact_path)
            _emit_ev(
                state.job_id,
                EventType.VERIFY_RESULT,
                iteration=state.iteration,
                passed=False,
                returncode=-1,
                output_tail=warning,
                artifact_ref=artifact_path,
                level=EventLevel.WARN,
            )
            return False, warning
        cmd = [python_cmd, str(default_script), "--skip-web", "--quiet"]

    result = await asyncio.to_thread(
        _run_shell,
        cmd,
        cwd=str(_PROJECT_ROOT),
    )
    passed = result["returncode"] == 0
    output = (result["stdout"] + result["stderr"])[-3000:]

    artifact_path = f"verify/iter_{state.iteration:03d}.log"
    state_store.write_artifact(state.job_id, artifact_path, output)
    _emit_artifact_written(state.job_id, artifact_path)

    _emit_ev(
        state.job_id,
        EventType.VERIFY_RESULT,
        iteration=state.iteration,
        passed=passed,
        returncode=result["returncode"],
        output_tail=output[-500:],
        artifact_ref=artifact_path,
        level=EventLevel.INFO if passed else EventLevel.WARN,
    )
    return passed, output


def _get_python_cmd(state: JobState) -> str:
    """Return the python executable to use: venv python if available, else sys.executable."""
    if state.venv_path:
        venv = Path(state.venv_path)
        candidates = [venv / "bin" / "python", venv / "Scripts" / "python.exe"]
        for c in candidates:
            if c.exists():
                return str(c)
    return sys.executable


# ---------------------------------------------------------------------------
# Self-healing venv repair loop (Milestone C)
# ---------------------------------------------------------------------------

async def _repair_loop(state: JobState, verify_output: str) -> bool:
    """
    Attempt repair after a verify failure.

    1. Look for ModuleNotFoundError → install into job-scoped venv.
    2. Re-run verify with venv python.
    3. If still failing, try LLM-driven patch repair (up to 3 attempts).

    Returns True if verify eventually passes.
    """
    _emit_ev(
        state.job_id,
        EventType.REPAIR_START,
        iteration=state.iteration,
        verify_output_tail=verify_output[-500:],
    )
    state.last_repair = f"Repair started at iteration {state.iteration}"
    state_store.save_state(state)

    # ----------------------------------------------------------------
    # Phase 1: deterministic venv install
    # ----------------------------------------------------------------
    missing = _MISSING_MODULE_RE.findall(verify_output)
    if missing:
        for pkg in missing:
            # Use the top-level package name as the pip install target.
            # Note: import names don't always match PyPI names (e.g. 'PIL' → 'pillow',
            # 'cv2' → 'opencv-python').  For common mismatches, the pip install may still
            # succeed if the package registers the import name as a provided extra.
            # A known-mappings dict can be added here if specific cases are needed.
            pkg = pkg.split(".")[0]  # e.g. 'foo.bar' → 'foo'
            if len(state.installed_packages) >= _MAX_AUTO_PACKAGES:
                _emit_assumption(
                    state.job_id,
                    f"Max auto-install limit ({_MAX_AUTO_PACKAGES}) reached. Skipping '{pkg}'.",
                )
                break
            if pkg in state.installed_packages:
                _emit_assumption(
                    state.job_id,
                    f"Package '{pkg}' was already installed but still missing — skipping re-install.",
                )
                break

            installed = await _venv_install(state, pkg)
            if installed:
                # Re-run verify with venv python (VERIFY_RETRY)
                _emit_ev(state.job_id, EventType.VERIFY_RETRY, iteration=state.iteration, reason=f"Installed {pkg}")
                passed, output = await _run_verify(state)
                state.last_verify_passed = passed
                state.last_verify_output = output[-2000:]
                state_store.save_state(state)
                if passed:
                    _emit_ev(state.job_id, EventType.REPAIR_RESULT, iteration=state.iteration, success=True, method="venv_install", package=pkg)
                    return True
                verify_output = output  # use fresh output for next phase

    # ----------------------------------------------------------------
    # Phase 2: LLM-driven patch repair (up to 3 attempts)
    # ----------------------------------------------------------------
    for attempt in range(1, 4):
        repair_system = (
            "You are a repair agent. Analyze the verify failure and propose a MINIMAL "
            "unified diff to fix it. Respond ONLY with: "
            '{"action":"repair","diff":"<unified diff>","rationale":"<explanation>"}'
        )
        repair_messages = [
            {
                "role": "user",
                "content": (
                    f"VERIFY FAILURE:\n{verify_output[-1500:]}\n\n"
                    f"GOAL: {state.goal}\n\nPropose a minimal repair diff."
                ),
            }
        ]

        try:
            raw = await asyncio.to_thread(
                llm_call,
                repair_messages,
                job_id=state.job_id,
                system=repair_system,
                provider=state.provider,
                model=state.model,
                emit=_emit,
            )
            action = _parse_action(raw, state.job_id)
        except Exception as exc:
            _emit_ev(
                state.job_id, EventType.REPAIR_RESULT,
                iteration=state.iteration,
                attempt=attempt, success=False, reason=f"LLM error: {exc}",
                level=EventLevel.WARN,
            )
            break

        if action.get("action") in ("repair", "patch") and action.get("diff"):
            await _apply_patch(state, action, state.iteration)
            passed, output = await _run_verify(state)
            state.last_verify_passed = passed
            state.last_verify_output = output[-2000:]
            state.last_repair = f"LLM repair attempt {attempt} at iteration {state.iteration}"
            state_store.save_state(state)
            _emit_ev(
                state.job_id, EventType.REPAIR_RESULT,
                iteration=state.iteration,
                attempt=attempt, success=passed,
            )
            if passed:
                return True
            verify_output = output
        else:
            _emit_ev(
                state.job_id, EventType.REPAIR_RESULT,
                iteration=state.iteration,
                attempt=attempt, success=False, reason="No diff in LLM response",
                level=EventLevel.WARN,
            )
            break

    return False


async def _venv_install(state: JobState, pkg: str) -> bool:
    """
    Create a job-scoped venv (if it doesn't exist) and pip-install *pkg*.
    Updates state.venv_path and state.installed_packages.
    Returns True on success.
    """
    job_dir = Path(state_store._job_dir(state.job_id))
    venv_path = job_dir / ".venv"

    _emit_ev(
        state.job_id,
        EventType.DEP_INSTALL_START,
        iteration=state.iteration,
        package=pkg,
        venv_path=str(venv_path),
    )

    # Create venv if missing
    if not venv_path.exists():
        try:
            await asyncio.to_thread(_create_venv, str(venv_path))
        except Exception as exc:
            _emit_ev(
                state.job_id, EventType.DEP_INSTALL_RESULT,
                iteration=state.iteration,
                package=pkg, success=False,
                reason=f"venv creation failed: {exc}",
                level=EventLevel.ERROR,
            )
            return False

    # Find pip inside the venv
    venv = Path(venv_path)
    pip_candidates = [
        venv / "bin" / "pip",
        venv / "Scripts" / "pip.exe",
        venv / "bin" / "pip3",
    ]
    pip_cmd: list[str] | None = None
    for c in pip_candidates:
        if c.exists():
            pip_cmd = [str(c)]
            break
    if not pip_cmd:
        # Fallback: use python -m pip as a list of args
        python_candidates = [venv / "bin" / "python", venv / "Scripts" / "python.exe"]
        for c in python_candidates:
            if c.exists():
                pip_cmd = [str(c), "-m", "pip"]
                break

    if not pip_cmd:
        _emit_ev(
            state.job_id, EventType.DEP_INSTALL_RESULT,
            iteration=state.iteration,
            package=pkg, success=False,
            reason="pip not found in venv",
            level=EventLevel.ERROR,
        )
        return False

    # Run pip install (pip_cmd is always a list now)
    cmd_parts = pip_cmd + ["install", pkg]

    result = await asyncio.to_thread(
        _run_shell, cmd_parts, cwd=str(_PROJECT_ROOT), timeout=120
    )
    success = result["returncode"] == 0
    output = (result["stdout"] + result["stderr"])[-2000:]

    artifact_path = f"install/iter_{state.iteration:03d}_{pkg}.log"
    state_store.write_artifact(state.job_id, artifact_path, output)
    _emit_artifact_written(state.job_id, artifact_path)

    if success:
        state.venv_path = str(venv_path)
        state.installed_packages.append(pkg)
        state_store.save_state(state)

    _emit_ev(
        state.job_id,
        EventType.DEP_INSTALL_RESULT,
        iteration=state.iteration,
        package=pkg,
        success=success,
        output_tail=output[-300:],
        artifact_ref=artifact_path,
        level=EventLevel.INFO if success else EventLevel.ERROR,
    )
    return success


def _create_venv(path: str) -> None:
    """Create a Python virtual environment at *path* (blocking)."""
    _venv_mod.create(path, with_pip=True, clear=False)


# ---------------------------------------------------------------------------
# Reviewer gate
# ---------------------------------------------------------------------------

async def _run_review_gate(state: JobState) -> bool:
    """Run the reviewer gate over job artifacts."""
    _emit_ev(state.job_id, EventType.REVIEW_START, iteration=state.iteration)

    artifacts: dict[str, str] = {}
    for meta in state_store.list_artifacts(state.job_id):
        content = state_store.read_artifact(state.job_id, meta.path)
        if content:
            artifacts[meta.path] = content

    review = await asyncio.to_thread(run_review, state.job_id, state.goal, artifacts)

    artifact_path = f"reports/review_iter_{state.iteration:03d}.json"
    report = {
        "passed": review.passed,
        "summary": review.summary(),
        "findings": [
            {"severity": f.severity, "rule": f.rule, "detail": f.detail, "file": f.file}
            for f in review.findings
        ],
    }
    state_store.write_artifact(state.job_id, artifact_path, json.dumps(report, ensure_ascii=False, indent=2))
    _emit_artifact_written(state.job_id, artifact_path)

    _emit_ev(
        state.job_id,
        EventType.REVIEW_RESULT,
        iteration=state.iteration,
        passed=review.passed,
        summary=review.summary(),
        findings=report["findings"],
        artifact_ref=artifact_path,
        level=EventLevel.INFO if review.passed else EventLevel.WARN,
    )
    return review.passed


# ---------------------------------------------------------------------------
# Terminal state helpers
# ---------------------------------------------------------------------------

async def _finish(
    state: JobState,
    status: JobStatus,
    reason: str,
    ev_type: EventType = EventType.FAILED,
) -> None:
    state.status = status
    state.finished_at = datetime.now(timezone.utc).isoformat()
    state.stop_reason = reason
    state_store.save_state(state)
    level = EventLevel.INFO if status == JobStatus.COMPLETE else EventLevel.ERROR
    _emit_ev(state.job_id, ev_type, reason=reason, level=level)
    _emit_ev(state.job_id, EventType.STATUS, status=str(status), reason=reason)
    # Cleanup: remove control flags so finished jobs don't leak memory
    _control_flags.pop(state.job_id, None)


def _emit_assumption(job_id: str, message: str) -> None:
    _emit_ev(job_id, EventType.ASSUMPTION_LOG, message=message, level=EventLevel.WARN)


def _emit_artifact_written(job_id: str, artifact_ref: str) -> None:
    _emit_ev(job_id, EventType.ARTIFACT_WRITTEN, artifact_ref=artifact_ref)


# ---------------------------------------------------------------------------
# Shell helper (blocking — run via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _run_shell(
    cmd: list[str],
    cwd: str | None = None,
    input_text: str | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            timeout=timeout,
            input=input_text,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "Command timed out"}
    except FileNotFoundError as exc:
        return {"returncode": -1, "stdout": "", "stderr": str(exc)}
