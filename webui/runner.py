"""
webui/runner.py — Autonomous runner loop for Overlord11 Tactical WebUI.

Each job runs in its own asyncio task.  The runner:

  1. Emits JOB_STARTING and sets status → RUNNING.
  2. Runs up to max_iterations, checking wall-clock budget each loop.
  3. Each iteration:
       a. Calls the LLM (orchestrator-driven step planning).
       b. Executes the action returned (tool_call | patch | complete).
       c. Runs the verify gate: `python tests/test.py --skip-web --quiet`.
       d. On verify failure: triggers repair loop (up to 3 attempts).
       e. On verify pass or after repair: runs reviewer gate.
       f. On reviewer pass: marks COMPLETE.
  4. If budgets exceeded without COMPLETE: marks FAILED with reason.

Pause/resume/stop are cooperative: the runner checks `_control_flags[job_id]`
at the top of each iteration.

All significant events are emitted via `_emit(event)` which:
  - appends to events.jsonl (via state_store.append_event)
  - broadcasts to all SSE subscribers via the job's asyncio.Queue
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .events import EventLevel, EventType, make_event
from .llm_interface import LLMCallError, LLMConfigError, get_provider_config, llm_call
from .models import JobState, JobStatus
from .reviewer import run_review
from . import state_store

# ---------------------------------------------------------------------------
# Control flags: "pause" | "resume" | "stop" | None
# ---------------------------------------------------------------------------

_control_flags: dict[str, str | None] = {}

# SSE broadcast queues: job_id → list of asyncio.Queue
_sse_queues: dict[str, list[asyncio.Queue]] = {}

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Public control API (called by HTTP endpoints)
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
            pass  # drop if consumer is too slow


# ---------------------------------------------------------------------------
# Main runner entry point
# ---------------------------------------------------------------------------

async def run_job(job_id: str) -> None:
    """
    Async task that executes the full autonomous runner loop for *job_id*.
    Must be launched via asyncio.create_task(run_job(job_id)).
    """
    state = state_store.load_state(job_id)
    if state is None:
        return

    _control_flags[job_id] = None
    start_wall = time.monotonic()

    # -----------------------------------------------------------------------
    # Transition → RUNNING
    # -----------------------------------------------------------------------
    state.status = JobStatus.RUNNING
    state.started_at = datetime.now(timezone.utc).isoformat()
    state_store.save_state(state)
    _emit(make_event(EventType.JOB_STARTING, job_id, {"goal": state.goal}))

    # Resolve provider config (log assumption if using default)
    try:
        pcfg = get_provider_config(state.provider, state.model)
        state.provider = pcfg["provider"]
        state.model = pcfg["model"]
        if not pcfg["api_key"]:
            _emit_assumption(
                job_id,
                f"No API key found for provider '{state.provider}' "
                f"(env: {pcfg['api_key_env']}). Running in stub mode.",
            )
    except (LLMConfigError, Exception) as exc:
        state.provider = state.provider or "anthropic"
        _emit_assumption(job_id, f"Provider config error: {exc}. Defaulting to stub mode.")

    state_store.save_state(state)

    # -----------------------------------------------------------------------
    # Main iteration loop
    # -----------------------------------------------------------------------
    try:
        for iteration in range(1, state.max_iterations + 1):
            # Budget: time
            elapsed = time.monotonic() - start_wall
            if elapsed >= state.max_time_seconds:
                await _fail(
                    state,
                    f"Time budget exceeded ({elapsed:.0f}s ≥ {state.max_time_seconds}s)",
                )
                return

            # Cooperative pause/stop check
            flag = _control_flags.get(job_id)
            if flag == "stop":
                await _fail(state, "Stopped by user request")
                return
            if flag == "pause":
                state.status = JobStatus.PAUSED
                state_store.save_state(state)
                _emit(make_event(EventType.PAUSED, job_id, {"iteration": iteration}))
                while _control_flags.get(job_id) == "pause":
                    await asyncio.sleep(0.5)
                if _control_flags.get(job_id) == "stop":
                    await _fail(state, "Stopped while paused")
                    return
                state.status = JobStatus.RUNNING
                state_store.save_state(state)
                _emit(make_event(EventType.RESUMED, job_id, {"iteration": iteration}))

            # ----------------------------------------------------------------
            # Emit ITERATION event
            # ----------------------------------------------------------------
            state.iteration = iteration
            _emit(
                make_event(
                    EventType.ITERATION,
                    job_id,
                    {
                        "iteration": iteration,
                        "max_iterations": state.max_iterations,
                        "elapsed_s": round(elapsed, 1),
                    },
                )
            )

            # ----------------------------------------------------------------
            # Step planning: call LLM to decide what to do next
            # ----------------------------------------------------------------
            action = await _plan_step(state, iteration)

            # ----------------------------------------------------------------
            # Execute action
            # ----------------------------------------------------------------
            if action.get("action") == "complete":
                summary = action.get("summary", "Goal achieved.")
                await _complete(state, summary)
                return

            elif action.get("action") == "patch":
                await _apply_patch(state, action)

            elif action.get("action") == "tool_call":
                await _execute_tool(state, action)

            elif action.get("action") == "repair":
                await _apply_patch(state, action)

            # ----------------------------------------------------------------
            # Verify gate
            # ----------------------------------------------------------------
            passed, output = await _run_verify(state)
            state.last_verify_passed = passed
            state.last_verify_output = output[-2000:] if output else ""
            state_store.save_state(state)

            if passed:
                # Run reviewer gate
                review_passed = await _run_review_gate(state)
                if review_passed:
                    await _complete(state, f"Verify gate passed on iteration {iteration}")
                    return
                # else reviewer found errors — continue iterating

            else:
                # Repair loop
                repaired = await _repair_loop(state, output)
                if repaired:
                    review_passed = await _run_review_gate(state)
                    if review_passed:
                        await _complete(
                            state, f"Repaired and verified on iteration {iteration}"
                        )
                        return

        # Max iterations reached
        await _fail(
            state,
            f"Iteration budget exhausted ({state.max_iterations} iterations) without satisfying verify gate",
        )

    except asyncio.CancelledError:
        await _fail(state, "Runner task cancelled")
        raise
    except Exception as exc:
        await _fail(state, f"Unhandled runner error: {exc}")


# ---------------------------------------------------------------------------
# Step planning
# ---------------------------------------------------------------------------

async def _plan_step(state: JobState, iteration: int) -> dict[str, Any]:
    """
    Ask the LLM what to do next.  Returns an action dict.
    Falls back to {"action": "complete", "summary": "..."} on errors.
    """
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
        # Try to parse JSON action
        return _parse_action(raw, state.job_id)
    except (LLMConfigError, LLMCallError) as exc:
        _emit(
            make_event(
                EventType.ASSUMPTION_LOG,
                state.job_id,
                {"message": f"LLM call failed ({exc}); defaulting to complete action"},
                level=EventLevel.WARN,
            )
        )
        return {"action": "complete", "summary": f"LLM unavailable: {exc}"}


def _build_system_prompt() -> str:
    return (
        "You are Overlord11, an autonomous coding assistant. "
        "Your job is to complete the user's goal by proposing actions. "
        "Respond ONLY with a JSON object (no markdown fences) with one of these shapes:\n"
        '  {"action":"tool_call","tool":"<name>","args":{...}}\n'
        '  {"action":"patch","diff":"<unified diff>","rationale":"<why>"}\n'
        '  {"action":"repair","diff":"<unified diff>","rationale":"<why>"}\n'
        '  {"action":"complete","summary":"<what was achieved>"}\n'
        "Be concise, prefer minimal diffs, never hardcode API keys or model names."
    )


def _build_history(state: JobState, iteration: int) -> list[dict[str, str]]:
    if state.last_verify_passed is True:
        verify_line = "PASS"
    elif state.last_verify_passed is False:
        verify_line = "FAIL: " + (state.last_verify_output or "n/a")
    else:
        verify_line = "n/a"

    messages: list[dict[str, str]] = [
        {
            "role": "user",
            "content": (
                f"GOAL: {state.goal}\n\n"
                f"ITERATION: {iteration}/{state.max_iterations}\n"
                f"LAST VERIFY: {verify_line}\n"
                f"DIRECTIVES: {json.dumps(state.directives, ensure_ascii=False) if state.directives else 'none'}\n\n"
                "What is the next action?"
            ),
        }
    ]
    return messages


def _parse_action(raw: str, job_id: str) -> dict[str, Any]:
    """Parse LLM response into an action dict."""
    raw = raw.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "action" in data:
            return data
    except json.JSONDecodeError:
        pass
    # Fallback: treat as complete
    return {"action": "complete", "summary": raw[:500]}


# ---------------------------------------------------------------------------
# Action executors
# ---------------------------------------------------------------------------

async def _apply_patch(state: JobState, action: dict[str, Any]) -> None:
    """Apply a unified diff patch to the repo."""
    diff = action.get("diff", "")
    rationale = action.get("rationale", "")
    _emit(
        make_event(
            EventType.TOOL_START,
            state.job_id,
            {"tool": "apply_patch", "rationale": rationale[:200]},
        )
    )

    if diff:
        artifact_name = f"patch_iter{state.iteration:03d}.patch"
        state_store.write_artifact(state.job_id, artifact_name, diff)

        # Apply via `patch` command
        result = await asyncio.to_thread(
            _run_shell,
            ["patch", "-p1", "--forward", "--batch"],
            input_text=diff,
            cwd=str(_PROJECT_ROOT),
        )
        success = result["returncode"] == 0
        _emit(
            make_event(
                EventType.TOOL_END,
                state.job_id,
                {
                    "tool": "apply_patch",
                    "success": success,
                    "output": result["stdout"][-500:],
                    "artifact": artifact_name,
                },
            )
        )
    else:
        _emit(make_event(EventType.TOOL_END, state.job_id, {"tool": "apply_patch", "success": False, "output": "empty diff"}))


async def _execute_tool(state: JobState, action: dict[str, Any]) -> None:
    """Execute a named tool_call action (stub — logs the call)."""
    tool_name = action.get("tool", "unknown")
    args = action.get("args", {})
    _emit(make_event(EventType.TOOL_START, state.job_id, {"tool": tool_name, "args": args}))
    # Real tool dispatch would route to tools/python/<tool>.py here.
    # For Phase 1 this is a structured placeholder.
    _emit(
        make_event(
            EventType.TOOL_END,
            state.job_id,
            {"tool": tool_name, "success": True, "output": "[stub] tool dispatched"},
        )
    )


# ---------------------------------------------------------------------------
# Verify gate
# ---------------------------------------------------------------------------

async def _run_verify(state: JobState) -> tuple[bool, str]:
    """Run `python tests/test.py --skip-web --quiet` and return (passed, output)."""
    _emit(make_event(EventType.VERIFY_START, state.job_id, {}))

    result = await asyncio.to_thread(
        _run_shell,
        [sys.executable, "tests/test.py", "--skip-web", "--quiet"],
        cwd=str(_PROJECT_ROOT),
    )
    passed = result["returncode"] == 0
    output = (result["stdout"] + result["stderr"])[-3000:]

    # Save as artifact
    artifact_name = f"verify_iter{state.iteration:03d}.txt"
    state_store.write_artifact(state.job_id, artifact_name, output)

    _emit(
        make_event(
            EventType.VERIFY_RESULT,
            state.job_id,
            {
                "passed": passed,
                "returncode": result["returncode"],
                "output_tail": output[-500:],
                "artifact": artifact_name,
            },
            level=EventLevel.INFO if passed else EventLevel.WARN,
        )
    )
    return passed, output


# ---------------------------------------------------------------------------
# Repair loop
# ---------------------------------------------------------------------------

async def _repair_loop(state: JobState, verify_output: str) -> bool:
    """
    Attempt up to 3 repair iterations after a verify failure.

    Returns True if verify eventually passes.
    """
    _emit(
        make_event(
            EventType.REPAIR_START,
            state.job_id,
            {"verify_output_tail": verify_output[-500:]},
        )
    )

    for attempt in range(1, 4):
        repair_system = (
            "You are a repair agent. The verify gate failed. "
            "Analyze the failure output and propose a MINIMAL unified diff to fix it. "
            "Respond ONLY with: "
            '{"action":"repair","diff":"<unified diff>","rationale":"<explanation>"}'
        )
        repair_messages = [
            {
                "role": "user",
                "content": (
                    f"VERIFY FAILURE OUTPUT:\n{verify_output[-1500:]}\n\n"
                    f"GOAL: {state.goal}\n\n"
                    "Propose a minimal repair diff."
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
            _emit(
                make_event(
                    EventType.REPAIR_RESULT,
                    state.job_id,
                    {
                        "attempt": attempt,
                        "success": False,
                        "reason": f"LLM error: {exc}",
                    },
                    level=EventLevel.WARN,
                )
            )
            break

        if action.get("action") in ("repair", "patch") and action.get("diff"):
            await _apply_patch(state, action)
            passed, output = await _run_verify(state)
            state.last_verify_passed = passed
            state.last_verify_output = output[-2000:]
            state_store.save_state(state)
            _emit(
                make_event(
                    EventType.REPAIR_RESULT,
                    state.job_id,
                    {"attempt": attempt, "success": passed},
                )
            )
            if passed:
                return True
            verify_output = output
        else:
            # No diff — nothing to apply
            _emit(
                make_event(
                    EventType.REPAIR_RESULT,
                    state.job_id,
                    {"attempt": attempt, "success": False, "reason": "No diff in response"},
                    level=EventLevel.WARN,
                )
            )
            break

    return False


# ---------------------------------------------------------------------------
# Reviewer gate
# ---------------------------------------------------------------------------

async def _run_review_gate(state: JobState) -> bool:
    """Run the reviewer gate over job artifacts."""
    _emit(make_event(EventType.REVIEW_START, state.job_id, {}))

    # Load all text artifacts
    artifacts: dict[str, str] = {}
    for name in state_store.list_artifacts(state.job_id):
        content = state_store.read_artifact(state.job_id, name)
        if content:
            artifacts[name] = content

    review = await asyncio.to_thread(run_review, state.job_id, state.goal, artifacts)

    _emit(
        make_event(
            EventType.REVIEW_RESULT,
            state.job_id,
            {
                "passed": review.passed,
                "summary": review.summary(),
                "findings": [
                    {
                        "severity": f.severity,
                        "rule": f.rule,
                        "detail": f.detail,
                        "file": f.file,
                    }
                    for f in review.findings
                ],
            },
            level=EventLevel.INFO if review.passed else EventLevel.WARN,
        )
    )
    return review.passed


# ---------------------------------------------------------------------------
# Terminal state helpers
# ---------------------------------------------------------------------------

async def _complete(state: JobState, summary: str) -> None:
    state.status = JobStatus.COMPLETE
    state.finished_at = datetime.now(timezone.utc).isoformat()
    state.stop_reason = summary
    state_store.save_state(state)
    _emit(make_event(EventType.COMPLETE, state.job_id, {"summary": summary}))


async def _fail(state: JobState, reason: str) -> None:
    state.status = JobStatus.FAILED
    state.finished_at = datetime.now(timezone.utc).isoformat()
    state.stop_reason = reason
    state_store.save_state(state)
    _emit(
        make_event(
            EventType.FAILED,
            state.job_id,
            {"reason": reason},
            level=EventLevel.ERROR,
        )
    )


def _emit_assumption(job_id: str, message: str) -> None:
    _emit(make_event(EventType.ASSUMPTION_LOG, job_id, {"message": message}))


# ---------------------------------------------------------------------------
# Shell helper (blocking — run via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _run_shell(
    cmd: list[str],
    cwd: str | None = None,
    input_text: str | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    """
    Run a subprocess synchronously.  Returns dict with returncode, stdout, stderr.
    """
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
