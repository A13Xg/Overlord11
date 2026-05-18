"""
Overlord11 Engine - Runner
============================
Core execution loop for the Overlord11 engine.
"""

import json
import os
import random
import re
import sys
import threading
import time
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    from .event_stream import EventStream, EventType
    from .delegation_guard import validate_retry_strategy
    from .loop_governor import LoopGovernor
    from .orchestrator_bridge import OrchestratorBridge
    from .parallel_executor import ParallelToolExecutor
    from .rate_limit import AllProvidersRateLimitedError
    from .self_healing import SelfHealingEngine
    from .session_manager import EngineSession
    from .tool_executor import ToolExecutor, extract_tool_calls
except ImportError:
    from event_stream import EventStream, EventType  # type: ignore[no-redef]
    from delegation_guard import validate_retry_strategy  # type: ignore[no-redef]
    from loop_governor import LoopGovernor  # type: ignore[no-redef]
    from orchestrator_bridge import OrchestratorBridge  # type: ignore[no-redef]
    from parallel_executor import ParallelToolExecutor  # type: ignore[no-redef]
    from rate_limit import AllProvidersRateLimitedError  # type: ignore[no-redef]
    from self_healing import SelfHealingEngine  # type: ignore[no-redef]
    from session_manager import EngineSession  # type: ignore[no-redef]
    from tool_executor import ToolExecutor, extract_tool_calls  # type: ignore[no-redef]

# Floor wait to avoid thundering-herd on rapid consecutive 429s.
_RATE_LIMIT_MIN_WAIT_S = 5.0

_BASE_DIR = Path(__file__).resolve().parent.parent
_TOOLS_DIR = _BASE_DIR / "tools" / "python"
_DELEGATION_TOOLS = {"delegate_task", "run_subagent"}


class EngineRunner:
    """Orchestrates the full agent execution loop."""

    def __init__(
        self,
        config_path: str = "config.json",
        verbose: bool = True,
        stop_event: Optional[threading.Event] = None,
        rate_limit_action: Optional[str] = None,
    ):
        config_file = Path(config_path)
        if not config_file.is_absolute():
            config_file = _BASE_DIR / config_path
        self._config = json.loads(config_file.read_text(encoding="utf-8"))
        self.verbose = verbose
        self.events = EventStream(verbose=verbose)
        self._tool_executor = ToolExecutor(tools_dir=_TOOLS_DIR, config=self._config)
        self._bridge = OrchestratorBridge(config=self._config)
        self._tool_executor.set_delegation_handler(self._delegation_handler)
        max_workers = (
            self._config.get("orchestration", {})
            .get("parallel", {})
            .get("max_concurrent_tools", 4)
        )
        self._parallel_executor = ParallelToolExecutor(
            tool_executor=self._tool_executor,
            max_workers=max_workers,
        )
        # Signalled externally (e.g. by the engine bridge on job cancel/shutdown)
        # to interrupt an in-progress rate-limit wait.
        self._stop_event: threading.Event = stop_event or threading.Event()
        self._healer = SelfHealingEngine()

        # Rate-limit behaviour when all providers return 429.
        # "pause"              — exponential backoff (5m, 10m, 20m … up to 8h), keeps retrying
        # "stop"               — fail the job immediately
        # "try_different_model"— wait only as long as the shortest provider Retry-After, then retry
        rl_cfg = self._config.get("orchestration", {}).get("rate_limit", {})
        self._rl_action: str = rate_limit_action or rl_cfg.get("action", "pause")
        self._rl_initial_wait_s: float = float(rl_cfg.get("initial_wait_s", 300))
        self._rl_max_wait_s: float = float(rl_cfg.get("max_wait_s", 28800))
        self._immutable_core_patterns: list[str] = (
            self._config.get("orchestration", {})
            .get("delegation", {})
            .get(
                "immutable_core_paths",
                [
                    "engine/",
                    "backend/core/",
                    "engine/runner.py",
                    "engine/tool_executor.py",
                    "engine/orchestrator_bridge.py",
                ],
            )
        )
        self._subagent_max_retries: int = int(
            self._config.get("orchestration", {})
            .get("delegation", {})
            .get("max_retries_per_step", 2)
        )
        self._loop_governor = LoopGovernor(
            self._config.get("orchestration", {}).get("loop_governor", {}),
            fallback_max_parent_loops=int(self._config.get("orchestration", {}).get("max_loops", 10)),
        )
        completion_cfg = self._config.get("orchestration", {}).get("completion", {})
        self._non_blocking_aux_tools: set[str] = {
            str(x).strip()
            for x in completion_cfg.get(
                "non_blocking_aux_tools",
                ["task_manager", "session_manager", "save_memory", "log_manager"],
            )
            if str(x).strip()
        }
        self._require_core_objective_before_aux_downgrade: bool = bool(
            completion_cfg.get("require_core_objective_before_aux_downgrade", True)
        )
        self._require_artifact_integrity_for_packaging: bool = bool(
            completion_cfg.get("require_artifact_integrity_for_packaging", True)
        )
        self._tool_failure_warning_threshold: int = int(
            completion_cfg.get("tool_failure_warning_threshold", 8)
        )
        self._repeat_param_failure_hard_stop: int = int(
            completion_cfg.get("repeat_param_failure_hard_stop", 6)
        )
        heal_cfg = self._config.get("orchestration", {}).get("self_healing", {})
        self._heal_repeat_suppress_after: int = max(1, int(heal_cfg.get("repeat_signature_suppress_after", 2)))
        self._heal_repeat_hard_stop_after: int = max(
            self._heal_repeat_suppress_after + 1,
            int(heal_cfg.get("repeat_signature_hard_stop_after", 4)),
        )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        job_id: Optional[str] = None,
        job_title: Optional[str] = None,
        agent_id: str = "OVR_DIR_01",
        streaming: bool = True,
        include_onboarding: bool = True,
        handoff_context: Optional[dict] = None,
    ) -> dict:
        """
        Run the agent loop and return a result dict.

        When streaming=True (default), each provider call streams tokens back
        through the EventStream as TOKEN events.  The frontend can subscribe to
        these events to render the LLM response in real time.  Falls back to
        non-streaming automatically if the provider does not support it.

        Args:
            user_input: The user's request or job prompt
            session_id: Optional existing session ID to restore (for resume)
            job_id: Optional job ID from the webui job system (used in workspace naming)
            agent_id: The agent to run (default: Orchestrator)
            streaming: Whether to stream tokens (default: True)
        """
        max_loops: int = self._loop_governor.max_parent_loops

        # Session setup
        session = EngineSession(
            session_id=session_id,
            job_id=job_id,
            description=user_input[:120],
            auto_update_consciousness_profile=bool(
                self._config.get("orchestration", {})
                .get("memory", {})
                .get("auto_update_consciousness_profile", False)
            ),
        )
        if not session_id:
            session.create()
        else:
            session.load()  # Restore _session_dir and existing logs for resume

        sid = session.session_id or "unknown"
        self._tool_executor.set_runtime_context(session_id=sid, task_dir=session.session_dir)
        # Reset events for this run but preserve registered callbacks
        existing_callbacks = list(self.events.callbacks)
        self.events = EventStream(verbose=self.verbose, callbacks=existing_callbacks)

        self.events.emit(EventType.SESSION_START, session_id=sid, agent_id=agent_id)
        gov_init = self._loop_governor.start(
            {
                "session_id": sid,
                "job_id": job_id,
                "agent_id": agent_id,
                "max_parent_loops": max_loops,
            }
        )
        self.events.emit(EventType.LOOP_GOVERNOR_INIT, session_id=sid, governor=gov_init)
        system_profile = session.record_system_profile(agent_id=agent_id)
        self.events.emit(
            EventType.SYSTEM_PROFILE,
            session_id=sid,
            system=system_profile.get("system"),
            release=system_profile.get("release"),
            shell=(system_profile.get("shell") or {}).get("env") or "auto",
        )

        # Build initial system prompt and message history
        system_prompt = self._bridge.build_system_prompt(agent_id, include_onboarding=include_onboarding)
        if not include_onboarding:
            system_prompt = (
                "Sub-agent execution mode:\n"
                "- Execute only the delegated task.\n"
                "- Use tool calls when needed; avoid narrative-only completion for non-trivial tasks.\n"
                "- Respect workspace/path/shell security policies.\n"
                "- Keep output concise and structured for the orchestrator.\n\n"
                + system_prompt
            )
        shell_type = str((system_profile.get("shell") or {}).get("type") or "auto").lower()
        shell_pref = "powershell" if shell_type in {"powershell", "cmd"} else shell_type
        if shell_pref not in {"powershell", "pwsh", "cmd", "bash", "sh", "zsh"}:
            shell_pref = "auto"
        syntax_hint = (
            "Use Windows shell syntax and commands."
            if shell_type in {"powershell", "cmd"}
            else "Use POSIX shell syntax and commands."
        )
        system_prompt = (
            system_prompt
            + "\n\n---\n\n"
            + "Execution environment profile:\n"
            + json.dumps(system_profile, indent=2, ensure_ascii=False)
            + "\n\nRuntime execution requirements:\n"
            + f"- Active shell family: {shell_type}\n"
            + f"- {syntax_hint}\n"
            + "- For run_shell_command, explicitly set parameters:\n"
            + f"  shell_preference=\"{shell_pref}\", reject_on_shell_mismatch=true, auto_switch_shell=true\n"
            + "- Any deliverable file intended for users should be written inside ./output and named answer.<ext> when possible (e.g., answer.md, answer.html, answer.png)."
        )
        tool_signature_cards = self._build_tool_signature_cards()
        if tool_signature_cards:
            system_prompt += (
                "\n\nTool signature quick reference (strict params; use exact names):\n"
                + tool_signature_cards
            )
        if handoff_context:
            system_prompt += (
                "\n\nSub-agent scoped handoff context (use only what is relevant):\n"
                + self._compact_json_snippet(handoff_context, max_chars=2400)
            )
        messages = [{"role": "user", "content": user_input}]

        final_output = ""
        status = "max_loops_reached"
        completion_mode = "no_effect_fail"
        failure_reason = ""
        total_tool_call_count = 0
        artifact_count = 0
        had_effectful_tool_success = False
        no_tool_retry_count = 0
        observed_dir_path: Optional[str] = None
        observed_dir_entries: set[str] = set()
        bookkeeping_warnings: list[dict[str, Any]] = []
        core_objective_met = False
        packaging_results: list[dict[str, Any]] = []
        tool_failure_signatures: Counter[str] = Counter()
        preflight_failure_count = 0
        repaired_preflight_count = 0
        last_non_aux_signature = ""
        non_aux_signature_streak = 0
        max_no_tool_retries = (
            self._config.get("orchestration", {})
            .get("no_tool_retries_for_nontrivial", 2)
        )
        loop = 0
        delegation_stats = {
            "subagent_total": 0,
            "subagent_success": 0,
            "subagent_fail": 0,
            "subagent_retries": 0,
            "subagent_parallel_batches": 0,
            "subagent_sequential_batches": 0,
            "subagent_duration_ms": 0.0,
        }

        while loop < max_loops:
            gate = self._loop_governor.before_parent_loop()
            if not gate.allow:
                status = "failed"
                completion_mode = "no_effect_fail"
                failure_reason = gate.reason or "max_parent_loops_exhausted"
                self.events.emit(
                    EventType.LOOP_BUDGET_DENY,
                    session_id=sid,
                    reason=failure_reason,
                    snapshot=self._loop_governor.snapshot(),
                )
                break
            loop += 1
            self.events.emit(EventType.AGENT_START, agent_id=agent_id, loop=loop)

            # Call provider — streaming when enabled, non-streaming as fallback.
            # TOKEN events are batched: we accumulate up to _TOKEN_BATCH_SIZE
            # characters before emitting to avoid flooding the SSE queue.
            _TOKEN_BATCH_SIZE = 6

            # Provider call with rate-limit auto-retry.
            # If all providers return 429, we pause in-place (emitting RATE_LIMITED),
            # wait out the cooldown, then retry the same loop turn — without losing
            # the conversation context accumulated so far.
            response = None
            _rl_retries = 0
            while True:
                try:
                    if streaming:
                        # Mutable container so the nested closure can modify it.
                        _buf: list[str] = []

                        def _token_cb(chunk: str) -> None:
                            _buf.append(chunk)
                            # Flush on newline or once the batch is large enough.
                            if "\n" in chunk or sum(len(c) for c in _buf) >= _TOKEN_BATCH_SIZE:
                                text = "".join(_buf)
                                _buf.clear()
                                self.events.emit(
                                    EventType.TOKEN,
                                    session_id=sid,
                                    agent_id=agent_id,
                                    loop=loop,
                                    text=text,
                                )

                        response = self._bridge.call_provider_streaming(
                            messages=messages,
                            system=system_prompt,
                            token_callback=_token_cb,
                            event_callback=lambda name, payload: self.events.emit(
                                EventType.PROVIDER_TRACE,
                                session_id=sid,
                                phase=name,
                                **payload,
                            ),
                        )
                        # Flush any remaining buffered tokens.
                        if _buf:
                            self.events.emit(
                                EventType.TOKEN,
                                session_id=sid,
                                agent_id=agent_id,
                                loop=loop,
                                text="".join(_buf),
                            )
                            _buf.clear()
                    else:
                        response = self._bridge.call_provider(
                            messages=messages,
                            system=system_prompt,
                            event_callback=lambda name, payload: self.events.emit(
                                EventType.PROVIDER_TRACE,
                                session_id=sid,
                                phase=name,
                                **payload,
                            ),
                        )
                    break  # success

                except AllProvidersRateLimitedError as exc:
                    _rl_retries += 1

                    # "stop" action — or stop_event already fired (user hit Stop/Pause)
                    if self._rl_action == "stop" or self._stop_event.is_set():
                        self.events.emit(EventType.ERROR, session_id=sid, message=str(exc), loop=loop)
                        session.log_event("error", {"message": str(exc), "loop": loop})
                        status = "rate_limited"
                        break

                    # Compute how long to wait based on the selected action.
                    if self._rl_action == "try_different_model":
                        # Respect the provider's actual Retry-After; try the model
                        # that becomes available soonest.
                        base_wait = max(exc.shortest_wait_s(), _RATE_LIMIT_MIN_WAIT_S)
                    else:
                        # "pause" — exponential backoff: initial × 2^(n-1), capped at max
                        base_wait = min(
                            self._rl_initial_wait_s * (2 ** (_rl_retries - 1)),
                            self._rl_max_wait_s,
                        )
                    # Add ±20% jitter so concurrent jobs don't all hammer the
                    # provider simultaneously when the cooldown expires.
                    wait_s = base_wait * (0.85 + random.random() * 0.30)

                    resume_at = datetime.fromtimestamp(
                        time.time() + wait_s, tz=timezone.utc
                    ).isoformat()
                    self.events.emit(
                        EventType.RATE_LIMITED,
                        session_id=sid,
                        loop=loop,
                        wait_s=round(wait_s, 1),
                        resume_at=resume_at,
                        retry_num=_rl_retries,
                        action=self._rl_action,
                        providers=list(exc.cooldowns.keys()),
                    )
                    session.log_event("rate_limited", {
                        "wait_s": wait_s,
                        "loop": loop,
                        "retry_num": _rl_retries,
                        "resume_at": resume_at,
                        "action": self._rl_action,
                    })
                    self._wait_interruptible(wait_s)
                    if self._stop_event.is_set():
                        status = "cancelled"
                        break

                except Exception as exc:
                    self.events.emit(EventType.ERROR, session_id=sid, message=str(exc), loop=loop)
                    session.log_event("error", {"message": str(exc), "loop": loop})
                    break

            if response is None:
                break

            if not response or not response.strip():
                failure_reason = "empty_model_response"
                completion_mode = "empty_response_fail"
                status = "failed"
                self.events.emit(
                    EventType.ERROR,
                    session_id=sid,
                    loop=loop,
                    message=failure_reason,
                )
                session.log_event("error", {"message": failure_reason, "loop": loop})
                break

            repeated_error_pattern = False

            agent_log = session.log_agent(agent_id, messages[-1].get("content", ""), response)
            self.events.emit(
                EventType.AGENT_COMPLETE,
                agent_id=agent_id,
                loop=loop,
                response_len=len(response),
                trace_path=agent_log.get("trace_path"),
            )

            tool_calls = extract_tool_calls(response)
            delegation_calls, tool_calls = self._partition_delegation_calls(tool_calls)
            total_tool_call_count += len(tool_calls) + len(delegation_calls)
            cycle = session.log_agent_cycle(
                agent_id=agent_id,
                loop=loop,
                system_prompt=system_prompt,
                messages=messages,
                response=response,
                tool_calls=[{"tool": tc.tool_name, "params": tc.params, "raw": tc.raw} for tc in tool_calls],
            )
            self.events.emit(
                EventType.AGENT_MESSAGE,
                session_id=sid,
                agent_id=agent_id,
                loop=loop,
                trace_path=cycle["trace_path"],
                request_preview=messages[-1].get("content", "")[:400],
                response_preview=response[:400],
            )

            # Append assistant message to context
            messages.append({"role": "assistant", "content": response})

            delegation_pairs: list[tuple[Any, dict]] = []
            if delegation_calls:
                self._active_delegation_context = {
                    "session_id": sid,
                    "parent_agent_id": agent_id,
                    "loop": loop,
                    "job_id": job_id,
                    "job_title": job_title,
                    "stats": delegation_stats,
                    "session": session,
                }
                delegation_pairs = self._tool_executor.execute_delegation_graph(
                    delegation_calls,
                    loop=loop,
                    emit_event=lambda evt, **kw: self.events.emit(getattr(EventType, evt), session_id=sid, parent_agent_id=agent_id, **kw),
                )
                self._active_delegation_context = None
                delegation_results = [result for _tc, result in delegation_pairs]
                messages = self._bridge.build_context(messages, delegation_results)
                had_effectful_tool_success = had_effectful_tool_success or any(
                    self._is_effectful_tool_result(result) for result in delegation_results
                )

            # Check for tool calls
            if not tool_calls:
                if delegation_calls:
                    post = self._loop_governor.after_parent_loop(
                        {
                            "effectful_tool_success_count": 1 if had_effectful_tool_success else 0,
                            "artifact_created_count": 0,
                            "delegation_completed_count": len([r for _tc, r in delegation_pairs if r.get("status") == "success"]),
                            "new_state_transition_count": 1,
                            "error_reduction_count": 0,
                            "repeated_tool_pattern": False,
                            "repeated_error_pattern": False,
                            "prose_only_non_trivial": False,
                            "empty_or_invalid_response": False,
                        }
                    )
                    snap = self._loop_governor.snapshot()
                    self.events.emit(EventType.LOOP_GOVERNOR_TICK, session_id=sid, loop=loop, snapshot=snap)
                    if snap.get("history"):
                        h = snap["history"][-1]
                        self.events.emit(EventType.LOOP_PROGRESS_SCORE, session_id=sid, loop=loop, progress_score=h.get("progress_score"), stall_score=h.get("stall_score"))
                        if int(h.get("credit_applied", 0)) > 0:
                            self.events.emit(EventType.LOOP_CREDIT_APPLIED, session_id=sid, loop=loop, credit=h.get("credit_applied"))
                    if post.warn:
                        self.events.emit(EventType.LOOP_STALL_WARNING, session_id=sid, loop=loop, warning=post.warn, stall_streak=snap.get("stall_streak"))
                    if not post.allow:
                        status = "failed"
                        completion_mode = "no_effect_fail"
                        failure_reason = post.reason or "stall_detected_no_progress"
                        break
                    continue
                format_issue = self._detect_tool_format_issue(response)
                if self._is_non_trivial_prompt(user_input):
                    if (
                        had_effectful_tool_success
                        and not format_issue
                        and self._is_effective_nontrivial_completion(
                            response,
                            observed_dir_path=observed_dir_path,
                            observed_entries=observed_dir_entries,
                        )
                    ):
                        final_output = response
                        status = "complete"
                        completion_mode = "tool_driven"
                        core_objective_met = True
                        break
                    if no_tool_retry_count < max_no_tool_retries:
                        no_tool_retry_count += 1
                        guidance = (
                            "SYSTEM REQUIREMENT: For non-trivial execution tasks you must emit at least one "
                            "parseable tool call in supported format. Prose-only planning is not completion. "
                            "Use one of: ```json {\"tool\":\"name\",\"params\":{...}}```, "
                            "<tool_call>{\"tool\":\"name\",\"params\":{...}}</tool_call>, "
                            "TOOL_CALL: name(param=\"value\"), or TOOL_CODE: name(param=\"value\")."
                        )
                        if format_issue:
                            guidance += (
                                f" Detected invalid tool-call format ({format_issue}). "
                                "Do not use pseudo tags like <tool_code> or <execute_bash>."
                            )
                        messages.append({
                            "role": "user",
                            "content": guidance,
                        })
                        continue

                    failure_reason = "invalid_tool_call_format" if format_issue else "no_effect_completion"
                    completion_mode = "no_effect_fail"
                    status = "failed"
                    self.events.emit(
                        EventType.ERROR,
                        session_id=sid,
                        loop=loop,
                        message=failure_reason,
                    )
                    session.log_event("error", {"message": failure_reason, "loop": loop})
                    break

                # Trivial/direct-answer path
                if self.detect_completion(response) or self._is_trivial_direct_answer(user_input, response):
                    final_output = response
                    status = "complete"
                    completion_mode = "direct_answer"
                    break
                failure_reason = "no_effect_completion"
                completion_mode = "no_effect_fail"
                status = "failed"
                break

            # Execute tool calls with dependency-aware parallelism.
            # Independent calls run concurrently; conflicting calls are
            # serialized into sequential waves by DependencyAnalyzer.
            ordered_pairs = self._parallel_executor.execute_all(
                tool_calls,
                on_call=lambda **kw: self.events.emit(EventType.TOOL_CALL, **kw),
                on_result=lambda **kw: self.events.emit(EventType.TOOL_RESULT, **kw),
                on_error=lambda **kw: self.events.emit(EventType.TOOL_ERROR, **kw),
                on_cache_hit=lambda **kw: self.events.emit(EventType.TOOL_CACHE_HIT, **kw),
                on_notification=lambda **kw: self.events.emit(
                    EventType.NOTIFICATION,
                    session_id=kw.pop("session_id", sid),
                    **kw,
                ),
                loop=loop,
                session_log_fn=session.log_tool_call,
            )
            if delegation_pairs:
                ordered_pairs = delegation_pairs + ordered_pairs
            tool_results = [result for _tc, result in ordered_pairs]
            effectful_success_count = len(
                [
                    result
                    for tc, result in ordered_pairs
                    if self._is_effectful_tool_result(result, tc.tool_name)
                ]
            )
            had_effectful_tool_success = had_effectful_tool_success or effectful_success_count > 0
            observed_dir_path, observed_dir_entries = self._update_observed_directory_snapshot(
                ordered_pairs=ordered_pairs,
                prior_path=observed_dir_path,
                prior_entries=observed_dir_entries,
            )
            for _tc, _result in ordered_pairs:
                if not isinstance(_result, dict) or _result.get("status") != "success":
                    continue
                payload = _result.get("result")
                if isinstance(_result.get("corrections"), list) and _result.get("corrections"):
                    repaired_preflight_count += 1
                if isinstance(payload, dict) and isinstance(payload.get("policy_diagnostics"), dict):
                    self.events.emit(
                        EventType.SHELL_POLICY_DIAGNOSTIC,
                        session_id=sid,
                        loop=loop,
                        tool=_tc.tool_name,
                        diagnostic=payload.get("policy_diagnostics"),
                    )
                if _tc.tool_name == "zip_tool":
                    packaging_results.append(
                        {
                            "loop": loop,
                            "tool": _tc.tool_name,
                            "status": _result.get("status"),
                            "payload": _result.get("result"),
                            "params": getattr(_tc, "params", {}),
                        }
                    )

            # Inject tool results into context
            messages = self._bridge.build_context(messages, tool_results)

            # ── Self-Healing Type B: inject structured recovery hints for tool errors ──
            _heal_hints = []
            current_non_aux_signature = ""
            for _tc, _result in ordered_pairs:
                if isinstance(_result, dict) and _result.get("status") == "error":
                    _err = _result.get("error") or _result.get("result") or str(_result)
                    signature = str(_result.get("failure_signature") or self._normalize_error_signature(_tc.tool_name, _err))
                    tool_failure_signatures[signature] += 1
                    parsed = _err if isinstance(_err, dict) else self._try_parse_json(str(_err))
                    if isinstance(parsed, dict) and parsed.get("error") == "param_preflight_failed":
                        preflight_failure_count += 1
                    if _tc.tool_name == "run_shell_command":
                        err_payload = _result.get("result")
                        if isinstance(err_payload, dict):
                            write_policy = err_payload.get("write_policy")
                            if isinstance(write_policy, dict) and isinstance(write_policy.get("diagnostics"), dict):
                                self.events.emit(
                                    EventType.SHELL_POLICY_DIAGNOSTIC,
                                    session_id=sid,
                                    loop=loop,
                                    tool=_tc.tool_name,
                                    diagnostic=write_policy.get("diagnostics"),
                                )
                    if self._is_auxiliary_tool(_tc.tool_name):
                        bookkeeping_warnings.append(
                            {
                                "tool": _tc.tool_name,
                                "error": str(_err),
                                "loop": loop,
                            }
                        )
                        self.events.emit(
                            EventType.BOOKKEEPING_WARNING,
                            session_id=sid,
                            loop=loop,
                            tool=_tc.tool_name,
                            error=str(_err),
                        )
                        continue
                    if not current_non_aux_signature:
                        current_non_aux_signature = signature
                    should_suppress = (
                        signature == last_non_aux_signature
                        and non_aux_signature_streak >= self._heal_repeat_suppress_after
                    )
                    if not should_suppress:
                        if isinstance(parsed, dict) and parsed.get("error") == "param_preflight_failed":
                            _hint = self._build_preflight_repair_hint(_tc.tool_name, parsed)
                        else:
                            _hint = (
                                f"⚠ TOOL ERROR — {_tc.tool_name}\n"
                                f"Error    : {_err}\n"
                                f"Recovery : Check tools/defs/{_tc.tool_name}.json for exact parameter names and types.\n"
                                f"Common causes: wrong parameter name (e.g. --add_task not --add-task), "
                                f"missing required parameter, incorrect value type.\n"
                                f"Action   : Retry this tool call with corrected parameters."
                            )
                        _heal_hints.append(_hint)
                    try:
                        self._healer.log_failure(
                            self._healer.classify_error(RuntimeError(_err), tool_name=_tc.tool_name),
                            session_id=sid,
                        )
                    except Exception:
                        pass
            if current_non_aux_signature and effectful_success_count == 0:
                if current_non_aux_signature == last_non_aux_signature:
                    non_aux_signature_streak += 1
                else:
                    last_non_aux_signature = current_non_aux_signature
                    non_aux_signature_streak = 1
            else:
                last_non_aux_signature = ""
                non_aux_signature_streak = 0

            if (
                current_non_aux_signature
                and non_aux_signature_streak >= self._heal_repeat_hard_stop_after
                and effectful_success_count == 0
            ):
                status = "failed"
                completion_mode = "no_effect_fail"
                failure_reason = "repeated_nonconvergent_tool_failure"
                self.events.emit(
                    EventType.ERROR,
                    session_id=sid,
                    loop=loop,
                    message=failure_reason,
                    signature=current_non_aux_signature,
                    streak=non_aux_signature_streak,
                    threshold=self._heal_repeat_hard_stop_after,
                )
                break
            if preflight_failure_count >= self._repeat_param_failure_hard_stop and effectful_success_count == 0:
                status = "failed"
                completion_mode = "no_effect_fail"
                failure_reason = "repeated_param_preflight_failure"
                self.events.emit(
                    EventType.ERROR,
                    session_id=sid,
                    loop=loop,
                    message=failure_reason,
                    preflight_failure_count=preflight_failure_count,
                    threshold=self._repeat_param_failure_hard_stop,
                )
                break
            if _heal_hints:
                messages.append({
                    "role": "user",
                    "content": "SYSTEM — RECOVERY GUIDANCE:\n\n" + "\n\n".join(_heal_hints),
                })
                repeated_error_pattern = True

            post = self._loop_governor.after_parent_loop(
                {
                    "effectful_tool_success_count": effectful_success_count,
                    "artifact_created_count": 0,
                    "delegation_completed_count": len([r for _tc, r in delegation_pairs if r.get("status") == "success"]),
                    "new_state_transition_count": 1 if tool_results else 0,
                    "error_reduction_count": 0,
                    "repeated_tool_pattern": False,
                    "repeated_error_pattern": repeated_error_pattern,
                    "prose_only_non_trivial": False,
                    "empty_or_invalid_response": False,
                }
            )
            snap = self._loop_governor.snapshot()
            self.events.emit(EventType.LOOP_GOVERNOR_TICK, session_id=sid, loop=loop, snapshot=snap)
            if snap.get("history"):
                h = snap["history"][-1]
                self.events.emit(EventType.LOOP_PROGRESS_SCORE, session_id=sid, loop=loop, progress_score=h.get("progress_score"), stall_score=h.get("stall_score"))
                if int(h.get("credit_applied", 0)) > 0:
                    self.events.emit(EventType.LOOP_CREDIT_APPLIED, session_id=sid, loop=loop, credit=h.get("credit_applied"))
            if post.warn:
                self.events.emit(EventType.LOOP_STALL_WARNING, session_id=sid, loop=loop, warning=post.warn, stall_streak=snap.get("stall_streak"))
            if not post.allow:
                status = "failed"
                completion_mode = "no_effect_fail"
                failure_reason = post.reason or "stall_detected_no_progress"
                break

        if status == "max_loops_reached":
            status = "failed"
            completion_mode = "no_effect_fail"
            failure_reason = failure_reason or "max_parent_loops_exhausted"
        if status != "complete" and not failure_reason:
            failure_reason = "execution_failed"
        output_text = final_output or (messages[-1].get("content", "") if messages else "")
        completion_checks, failed_checks, source_tool_ids = self._evaluate_completion_checks(
            output_text=output_text,
            packaging_results=packaging_results,
            task_root=session.session_dir,
        )
        if failed_checks:
            status = "failed"
            completion_mode = "no_effect_fail"
            failure_reason = "completion_contract_violation"
            self.events.emit(
                EventType.STATUS,
                session_id=sid,
                loop=loop,
                completion_checks=completion_checks,
                failed_checks=failed_checks,
                source_tool_ids=source_tool_ids,
            )
        if self._should_downgrade_auxiliary_failures(
            status=status,
            failure_reason=failure_reason,
            had_effectful_tool_success=had_effectful_tool_success,
            output_text=output_text,
            observed_dir_path=observed_dir_path,
            observed_dir_entries=observed_dir_entries,
            bookkeeping_warnings=bookkeeping_warnings,
            core_objective_met=core_objective_met,
            failed_completion_checks=bool(failed_checks),
        ):
            status = "complete"
            completion_mode = "tool_driven"
            failure_reason = ""
        self.events.emit(EventType.SESSION_END, session_id=sid, status=status, loops=loop)
        output_path = session.log_product_output(final_output or (messages[-1].get("content", "") if messages else ""))
        if output_path:
            artifact_count += 1
            self.events.emit(EventType.ARTIFACT_CREATED, session_id=sid, category="output", path=output_path)
        if status == "complete" and completion_mode != "direct_answer":
            completion_mode = "tool_driven"
        total_tool_failures = sum(tool_failure_signatures.values())
        correction_success_rate = (
            round(repaired_preflight_count / preflight_failure_count, 3)
            if preflight_failure_count > 0
            else 1.0
        )
        top_failure_signatures = [
            {"signature": sig, "count": count}
            for sig, count in tool_failure_signatures.most_common(8)
        ]
        if total_tool_failures >= self._tool_failure_warning_threshold:
            self.events.emit(
                EventType.STATUS,
                session_id=sid,
                loop=loop,
                warning="tool_failure_budget_warning",
                total_tool_failures=total_tool_failures,
                threshold=self._tool_failure_warning_threshold,
                top_failure_signatures=top_failure_signatures,
            )
        summary = {
            "job_id": job_id,
            "job_title": job_title or user_input[:120],
            "session_id": sid,
            "status": status,
            "completion_mode": completion_mode,
            "tool_call_count": total_tool_call_count,
            "artifact_count": artifact_count,
            "error": failure_reason or None,
            "output_preview": output_text[:300],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "subagents": delegation_stats,
            "loop_governor": self._loop_governor.snapshot(),
            "bookkeeping_warnings": bookkeeping_warnings,
            "completion_checks": completion_checks,
            "failed_checks": failed_checks,
            "source_tool_ids": source_tool_ids,
            "tool_failure_diagnostics": {
                "total_tool_failures": total_tool_failures,
                "preflight_failure_count": preflight_failure_count,
                "repaired_preflight_count": repaired_preflight_count,
                "correction_success_rate": correction_success_rate,
                "top_failure_signatures": top_failure_signatures,
                "warning_threshold": self._tool_failure_warning_threshold,
            },
        }
        session.write_job_summary(summary)
        session.close(status=status)

        return {
            "session_id": sid,
            "output": output_text,
            "events": self.events.get_events(),
            "status": status,
            "error": failure_reason or None,
            "completion_mode": completion_mode,
            "tool_call_count": total_tool_call_count,
            "artifact_count": artifact_count,
            "subagents": delegation_stats,
            "loop_governor": self._loop_governor.snapshot(),
            "bookkeeping_warnings": bookkeeping_warnings,
            "completion_checks": completion_checks,
            "failed_checks": failed_checks,
            "source_tool_ids": source_tool_ids,
            "tool_failure_diagnostics": {
                "total_tool_failures": total_tool_failures,
                "preflight_failure_count": preflight_failure_count,
                "repaired_preflight_count": repaired_preflight_count,
                "correction_success_rate": correction_success_rate,
                "top_failure_signatures": top_failure_signatures,
                "warning_threshold": self._tool_failure_warning_threshold,
            },
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _wait_interruptible(self, seconds: float) -> bool:
        """
        Sleep for up to `seconds`, waking every 5 s to check for stop_event.

        Returns True if the full wait completed, False if stop_event fired.
        """
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            remaining = end - time.monotonic()
            if self._stop_event.wait(timeout=min(5.0, max(0.01, remaining))):
                return False  # stop requested
        return True

    def detect_completion(self, response: str) -> bool:
        """Return True if the response looks like a final answer (no pending tool calls)."""
        tool_calls = extract_tool_calls(response)
        if tool_calls:
            return False
        if self._is_intermediate_or_handoff_response(response):
            return False
        # Heuristic: if response ends with typical closing phrases it's done
        lowered = response.lower().strip()
        completion_signals = [
            "task complete",
            "i have completed",
            "here is the result",
            "here are the results",
            "i'm done",
            "i am done",
            "the task is done",
        ]
        return any(sig in lowered for sig in completion_signals)

    def _is_non_trivial_prompt(self, prompt: str) -> bool:
        """
        Heuristic for tasks that should not complete with prose-only output.
        """
        lowered = (prompt or "").lower()
        if len(lowered.strip()) > 160:
            return True
        keywords = (
            "create", "build", "implement", "generate", "write code", "refactor",
            "run tests", "analyze", "research", "report", "html", "artifact",
            "security review", "scan", "fix",
        )
        return any(k in lowered for k in keywords)

    def _is_trivial_direct_answer(self, prompt: str, response: str) -> bool:
        """
        Permit concise answers for simple prompts without requiring verbose
        completion phrases.
        """
        if self._is_non_trivial_prompt(prompt):
            return False
        text = (response or "").strip()
        if not text:
            return False
        lowered = text.lower()
        disallowed_prefixes = (
            "i will",
            "i'll",
            "let me",
            "next,",
            "plan:",
            "step 1",
            "todo",
        )
        if any(lowered.startswith(prefix) for prefix in disallowed_prefixes):
            return False
        # Simple direct responses are often short and factual.
        return len(text) <= 120

    def _is_effectful_tool_result(self, result: dict, tool_name: Optional[str] = None) -> bool:
        """
        True when a tool call appears to have produced usable output.
        """
        if not isinstance(result, dict):
            return False
        if tool_name and self._is_auxiliary_tool(tool_name):
            return False
        if result.get("status") != "success":
            return False
        payload = result.get("result")
        if payload is None:
            return False
        if isinstance(payload, dict) and str(payload.get("status", "")).lower() == "error":
            return False
        if isinstance(payload, str):
            parsed = self._try_parse_json(payload)
            if isinstance(parsed, dict) and str(parsed.get("status", "")).lower() == "error":
                return False
            return bool(payload.strip())
        if isinstance(payload, (list, tuple, set, dict)):
            return len(payload) > 0
        return True

    def _contains_unexecuted_tool_intent(self, text: str) -> bool:
        lowered = (text or "").lower()
        if "```json" in lowered and "\"tool\"" in lowered and "\"params\"" in lowered:
            return True
        if "tool_call:" in lowered or "tool_code:" in lowered:
            return True
        if re.search(r"[\"']tool[\"']\s*:\s*[\"'][a-z0-9_\\-]+[\"']", text or "", re.IGNORECASE):
            if re.search(r"[\"']params[\"']\s*:", text or "", re.IGNORECASE):
                return True
        return False

    def _try_parse_json(self, text: str) -> Optional[dict]:
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
        return None

    def _normalize_error_signature(self, tool_name: str, error_value: Any) -> str:
        raw = str(error_value or "").lower()
        raw = re.sub(r"[a-z]:\\\\[^\\s\"']+", "<path>", raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        if len(raw) > 240:
            raw = raw[:240]
        return f"{tool_name}:{raw}"

    def _build_preflight_repair_hint(self, tool_name: str, preflight: dict) -> str:
        unknown = preflight.get("unknown_parameters") or []
        missing = preflight.get("missing_required") or []
        invalid_type = preflight.get("invalid_type") or []
        invalid_value = preflight.get("invalid_value") or []
        reason = preflight.get("reason", "param_preflight_failed")
        hint = preflight.get("hint", "")
        suggested_payload = preflight.get("suggested_payload")
        recipe = (
            f"REPAIR RECIPE — {tool_name}\n"
            f"Reason   : {reason}\n"
            f"Action   : Emit exactly one corrected tool call. No extra keys.\n"
        )
        if unknown:
            recipe += f"Remove   : {', '.join([str(x) for x in unknown])}\n"
        if missing:
            recipe += f"Add      : {', '.join([str(x) for x in missing])}\n"
        if invalid_type:
            recipe += "TypeFix  : " + ", ".join([str(x.get("field", "")) for x in invalid_type if isinstance(x, dict)]) + "\n"
        if invalid_value:
            recipe += "ValueFix : " + ", ".join([str(x.get("field", "")) for x in invalid_value if isinstance(x, dict)]) + "\n"
        if hint:
            recipe += f"Hint     : {hint}\n"
        if isinstance(suggested_payload, dict):
            recipe += "Payload  : " + json.dumps({"tool": tool_name, "params": suggested_payload}, ensure_ascii=False) + "\n"
        return recipe

    def _build_tool_signature_cards(self) -> str:
        focus_tools = ["task_manager", "zip_tool", "publisher_tool", "session_manager", "save_memory", "run_shell_command"]
        cards: list[str] = []
        tools_cfg = self._config.get("tools", {}) or {}
        for tool in focus_tools:
            info = tools_cfg.get(tool) or {}
            def_rel = info.get("def")
            if not def_rel:
                continue
            def_path = Path(def_rel)
            if not def_path.is_absolute():
                def_path = (_BASE_DIR / def_path).resolve()
            if not def_path.exists():
                continue
            try:
                schema = json.loads(def_path.read_text(encoding="utf-8"))
                params = (schema.get("parameters") or {})
                props = (params.get("properties") or {})
                required = params.get("required") or []
                enums = []
                for k, v in props.items():
                    if isinstance(v, dict) and isinstance(v.get("enum"), list):
                        enums.append(f"{k}={v.get('enum')}")
                cards.append(
                    f"- {tool}: required={required}; enums={'; '.join(enums[:2]) or 'none'}; "
                    f"example1={{\"tool\":\"{tool}\",\"params\":{self._signature_example(tool, 1)}}}; "
                    f"example2={{\"tool\":\"{tool}\",\"params\":{self._signature_example(tool, 2)}}}"
                )
            except Exception:
                continue
        return "\n".join(cards)

    def _signature_example(self, tool_name: str, variant: int) -> str:
        examples = {
            "task_manager": [
                {"action": "add_task", "title": "Create release kit", "project_dir": "workspace/<session>"},
                {"action": "update_status", "task_id": "T-001", "status": "in_progress", "project_dir": "workspace/<session>"},
            ],
            "zip_tool": [
                {"action": "create", "output": "output/release-kit.zip", "paths": ["output/artifacts"], "overwrite": True},
                {"action": "list", "file": "output/release-kit.zip"},
            ],
            "publisher_tool": [
                {"title": "Release Report", "content": "output/release.md", "theme": "tactical", "output_path": "output/release.html"},
                {"title": "Summary", "content": "# Heading", "output_path": "output/summary.html"},
            ],
            "session_manager": [
                {"action": "status", "session_id": "<session_id>"},
                {"action": "close", "session_id": "<session_id>", "description": "completed"},
            ],
            "save_memory": [
                {"key": "release_status", "value": "completed", "category": "decision"},
                {"key": "risk_note", "value": "manual rollback tested", "category": "context"},
            ],
            "run_shell_command": [
                {"command": "python -m unittest -q", "working_dir": ".", "shell_preference": "powershell", "reject_on_shell_mismatch": True, "auto_switch_shell": True},
                {"command": "dir output", "working_dir": ".", "shell_preference": "powershell", "reject_on_shell_mismatch": True, "auto_switch_shell": True},
            ],
        }
        vals = examples.get(tool_name, [{"sample": True}])
        idx = 0 if variant == 1 else min(1, len(vals) - 1)
        return json.dumps(vals[idx], ensure_ascii=False)

    def _evaluate_completion_checks(
        self,
        *,
        output_text: str,
        packaging_results: list[dict[str, Any]],
        task_root: Optional[Path],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        checks: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        sources: list[str] = []
        if not self._require_artifact_integrity_for_packaging:
            return checks, failed, sources

        lowered = (output_text or "").lower()
        claims_packaging = bool(
            re.search(r"\b(zip|archive|packag(?:e|ed|ing))\b", lowered)
            and re.search(r"\b(created|generated|built|completed|success)\b", lowered)
        )
        if not claims_packaging:
            return checks, failed, sources

        sources.append("zip_tool")
        if not packaging_results:
            item = {"id": "packaging_claim_requires_zip_evidence", "ok": False, "message": "Response claims package success but no zip_tool result was observed."}
            checks.append(item)
            failed.append(item)
            return checks, failed, sources

        # Canonicalize payload envelopes and prefer latest successful list/create pair.
        normalized: list[dict[str, Any]] = []
        for entry in packaging_results:
            payload = self._unwrap_tool_payload(entry.get("payload"))
            if not isinstance(payload, dict):
                continue
            status_ok = (
                str(entry.get("status", "")).lower() == "success"
                and str(payload.get("status", "success")).lower() != "error"
            )
            params = entry.get("params") if isinstance(entry.get("params"), dict) else {}
            action = str(payload.get("action") or params.get("action") or "").lower()
            archive_path = str(payload.get("file") or params.get("file") or params.get("output") or "").strip()
            normalized.append(
                {
                    "status_ok": status_ok,
                    "action": action,
                    "archive_path": archive_path,
                    "payload": payload,
                    "entry": entry,
                }
            )

        relevant = [n for n in normalized if n["status_ok"] and n["action"] in {"create", "list"}]
        latest = relevant[-1] if relevant else None
        if latest is None:
            item = {"id": "zip_tool_status_success", "ok": False, "message": "No successful zip create/list result was observed."}
            checks.append(item)
            failed.append(item)
            return checks, failed, sources
        checks.append({"id": "zip_tool_status_success", "ok": True})

        parsed = latest["payload"]
        file_path = str(latest.get("archive_path") or parsed.get("file") or "").strip()
        if not file_path:
            item = {"id": "zip_output_path_present", "ok": False, "message": "zip_tool result does not include output file path."}
            checks.append(item)
            failed.append(item)
            return checks, failed, sources
        p = Path(file_path)
        if not p.is_absolute() and task_root is not None:
            p = (task_root / "output" / p).resolve()
        exists_ok = p.exists()
        checks.append({"id": "zip_exists", "ok": exists_ok, "path": str(p)})
        if not exists_ok:
            failed.append({"id": "zip_exists", "ok": False, "path": str(p), "message": "Claimed archive does not exist."})
            return checks, failed, sources

        is_zip_ok = zipfile.is_zipfile(str(p))
        checks.append({"id": "zip_is_valid", "ok": is_zip_ok, "path": str(p)})
        if not is_zip_ok:
            failed.append({"id": "zip_is_valid", "ok": False, "path": str(p), "message": "Archive is not a valid ZIP file."})
            return checks, failed, sources

        file_count = parsed.get("file_count")
        if not isinstance(file_count, int):
            try:
                with zipfile.ZipFile(str(p), "r") as zf:
                    file_count = len([i for i in zf.infolist() if not i.is_dir()])
            except Exception:
                file_count = 0
        non_empty_ok = int(file_count or 0) > 0
        checks.append({"id": "zip_non_empty", "ok": non_empty_ok, "file_count": int(file_count or 0)})
        if not non_empty_ok:
            failed.append({"id": "zip_non_empty", "ok": False, "file_count": int(file_count or 0), "message": "Archive has zero files but response claimed successful package creation."})

        return checks, failed, sources

    def _unwrap_tool_payload(self, payload: Any) -> Any:
        parsed = payload if isinstance(payload, dict) else self._try_parse_json(str(payload))
        if not isinstance(parsed, dict):
            return parsed
        current = parsed
        for _ in range(4):
            inner = current.get("result")
            if not isinstance(inner, dict):
                break
            # Envelope-like structure; unwrap one level.
            has_envelope_markers = (
                "tool" in current
                or "duration_ms" in current
                or "invocation_mode" in current
                or "serialization_mode" in current
                or "validation_stage" in current
                or "cached" in current
            )
            if has_envelope_markers:
                current = inner
                continue
            break
        return current

    def _detect_tool_format_issue(self, response: str) -> Optional[str]:
        lowered = (response or "").lower()
        if "<tool_code>" in lowered or "</tool_code>" in lowered:
            return "pseudo_tool_code_tag"
        if "<execute_bash>" in lowered or "</execute_bash>" in lowered:
            return "pseudo_execute_bash_tag"
        return None

    def _is_auxiliary_tool(self, tool_name: str) -> bool:
        return str(tool_name or "").strip() in self._non_blocking_aux_tools

    def _is_intermediate_or_handoff_response(self, response: str) -> bool:
        lowered = (response or "").lower()
        markers = (
            "<execute_task",
            "i am delegating",
            "delegating the",
            "delegation plan",
            "your task is to",
            "ovr_cod_",
            "ovr_res_",
            "ovr_rev_",
            "simulate the handoff",
            "as there is no new task provided",
        )
        return any(marker in lowered for marker in markers)

    def _is_effective_nontrivial_completion(
        self,
        response: str,
        *,
        observed_dir_path: Optional[str],
        observed_entries: set[str],
    ) -> bool:
        text = (response or "").strip()
        if not text:
            return False
        if self._is_intermediate_or_handoff_response(text):
            return False
        if self._detect_tool_format_issue(text):
            return False
        if self._contains_unexecuted_tool_intent(text):
            return False
        # Prevent claiming repository-root verification when only scripts/ was observed.
        lowered = text.lower()
        claimed_dirs = self._extract_claimed_directories(lowered)
        if claimed_dirs and observed_entries:
            observed = {e.lower() for e in observed_entries}
            if not claimed_dirs.issubset(observed):
                return False
        if observed_dir_path and observed_dir_path.lower().endswith("\\scripts"):
            if "project root" in lowered and "scripts" not in lowered:
                return False
        # Must include either completion language or meaningful artifact/result details.
        completion_signals = (
            "completed",
            "task complete",
            "successfully",
            "created",
            "updated",
            "written",
            "report",
            "result",
        )
        return any(sig in lowered for sig in completion_signals)

    def _extract_claimed_directories(self, lowered_text: str) -> set[str]:
        claimed: set[str] = set()
        claim_contexts = re.findall(
            r"(?:confirms?|confirmed|contains?|includes?|present|found|has)\s+([^\n\.]+)",
            lowered_text,
        )
        for chunk in claim_contexts:
            for dir_name in re.findall(r"\b([a-z0-9_-]{2,})/(?=[\s,;\.\)\]]|$)", chunk):
                claimed.add(dir_name.lower())
        return claimed

    def _should_downgrade_auxiliary_failures(
        self,
        *,
        status: str,
        failure_reason: str,
        had_effectful_tool_success: bool,
        output_text: str,
        observed_dir_path: Optional[str],
        observed_dir_entries: set[str],
        bookkeeping_warnings: list[dict[str, Any]],
        core_objective_met: bool,
        failed_completion_checks: bool,
    ) -> bool:
        if status == "complete":
            return False
        if failed_completion_checks:
            return False
        if not bookkeeping_warnings:
            return False
        if self._require_core_objective_before_aux_downgrade and not core_objective_met:
            if not (
                had_effectful_tool_success
                and self._is_effective_nontrivial_completion(
                    output_text,
                    observed_dir_path=observed_dir_path,
                    observed_entries=observed_dir_entries,
                )
            ):
                return False
        return failure_reason in {
            "no_effect_completion",
            "execution_failed",
            "stall_detected_no_progress",
            "max_parent_loops_exhausted",
        }

    def _update_observed_directory_snapshot(
        self,
        *,
        ordered_pairs: list[tuple],
        prior_path: Optional[str],
        prior_entries: set[str],
    ) -> tuple[Optional[str], set[str]]:
        latest_path = prior_path
        latest_entries = set(prior_entries)
        for tc, result in ordered_pairs:
            if getattr(tc, "tool_name", "") != "list_directory":
                continue
            if not isinstance(result, dict):
                continue
            if result.get("status") != "success":
                continue
            payload = result.get("result")
            parsed = payload if isinstance(payload, dict) else self._try_parse_json(str(payload))
            if not isinstance(parsed, dict):
                continue
            p = parsed.get("path")
            entries = parsed.get("entries", [])
            if isinstance(p, str):
                latest_path = p
            if isinstance(entries, list):
                new_entries: set[str] = set()
                for item in entries:
                    if isinstance(item, dict) and isinstance(item.get("name"), str):
                        new_entries.add(item["name"])
                if new_entries:
                    latest_entries = new_entries
        return latest_path, latest_entries

    def _partition_delegation_calls(self, tool_calls: list) -> tuple[list, list]:
        delegation: list = []
        normal: list = []
        for tc in tool_calls:
            if getattr(tc, "tool_name", "") in _DELEGATION_TOOLS:
                delegation.append(tc)
            else:
                normal.append(tc)
        return delegation, normal

    def _delegation_handler(self, *, tool_name: str, params: dict) -> dict:
        ctx = getattr(self, "_active_delegation_context", None) or {}
        session_id = ctx.get("session_id", "unknown")
        parent_agent_id = ctx.get("parent_agent_id", "unknown")
        loop = int(ctx.get("loop", 0))
        job_id = ctx.get("job_id")
        job_title = ctx.get("job_title")
        stats = ctx.get("stats", {})
        ok, err = self._validate_delegation_call(params)
        if not ok:
            self.events.emit(EventType.SUBAGENT_FAIL, session_id=session_id, loop=loop, parent_agent_id=parent_agent_id, error=err)
            return {"status": "error", "errors": err, "subagent_agent_id": params.get("agent_id"), "subagent_session_id": session_id}
        wrapped = type("DelegationCall", (), {"tool_name": tool_name})()
        result = self._execute_subagent_call(
            tc=wrapped,
            params=params,
            session_id=session_id,
            parent_agent_id=parent_agent_id,
            loop=loop,
            job_id=job_id,
            job_title=job_title,
            stats=stats,
        )
        payload = result.get("result", {}) if isinstance(result, dict) else {}
        if not isinstance(payload, dict):
            payload = {"status": "error", "errors": "invalid_delegation_payload"}
        return payload

    def _execute_subagent_call(
        self,
        *,
        tc: Any,
        params: dict,
        session_id: str,
        parent_agent_id: str,
        loop: int,
        job_id: Optional[str],
        job_title: Optional[str],
        stats: dict,
    ) -> dict:
        agent_id = str(params.get("agent_id") or "").strip()
        task = str(params.get("task") or "").strip()
        timeout_s = int(params.get("timeout_s") or 300)
        inputs = params.get("inputs")
        expected = params.get("expected_outputs")
        task_payload = task
        uiux = self._build_uiux_context_for_subagent(agent_id=agent_id, task=task)
        if uiux:
            task_payload = f"{task_payload}\n\nUI/UX context:\n{uiux}"
        if inputs:
            task_payload += f"\n\nInputs:\n{json.dumps(inputs, ensure_ascii=False)}"
        if expected:
            task_payload += f"\n\nExpected outputs:\n{json.dumps(expected, ensure_ascii=False)}"

        stats["subagent_total"] += 1
        allowed = self._loop_governor.before_subagent(agent_id, {"timeout_s": timeout_s})
        if not allowed.allow:
            return {
                "status": "error",
                "tool": tc.tool_name,
                "duration_ms": 0.0,
                "error": allowed.reason or "max_subagent_loops_exhausted",
                "result": {
                    "status": "error",
                    "errors": allowed.reason or "max_subagent_loops_exhausted",
                    "agent_id": agent_id,
                    "subagent_session_id": session_id,
                    "subagent_agent_id": agent_id,
                },
            }
        self.events.emit(
            EventType.SUBAGENT_START,
            session_id=session_id,
            loop=loop,
            parent_agent_id=parent_agent_id,
            subagent_id=agent_id,
            timeout_s=timeout_s,
        )

        started = time.monotonic()
        attempts = 0
        max_attempts = max(1, self._subagent_max_retries + 1)
        final_result: dict = {}
        prev_attempt_plan: Optional[dict] = None
        while attempts < max_attempts:
            attempts += 1
            attempt_plan = {
                "agent_id": agent_id,
                "task": task_payload,
                "inputs": params.get("inputs"),
                "expected_outputs": params.get("expected_outputs"),
                "allow_parallel": bool(params.get("allow_parallel", False)),
                "timeout_s": timeout_s,
                "depends_on": params.get("depends_on", []),
                "step_id": params.get("step_id"),
                "retry_policy": params.get("retry_policy"),
            }
            retry_diag = {"retry_block_reason": None, "strategy_diff": {}}
            if attempts > 1 and prev_attempt_plan is not None:
                known_ids = {
                    str(cfg.get("id", "")).strip()
                    for cfg in (self._config.get("agents", {}) or {}).values()
                    if str(cfg.get("id", "")).strip()
                }
                valid_retry, retry_diag = validate_retry_strategy(
                    previous_attempt=prev_attempt_plan,
                    next_attempt=attempt_plan,
                    immutable_rules=self._immutable_core_patterns,
                    known_agent_ids=known_ids,
                )
                if not valid_retry:
                    retry_decision = self._loop_governor.increment_retry(1)
                    stats["subagent_retries"] += 1
                    self.events.emit(
                        EventType.SUBAGENT_RETRY,
                        session_id=session_id,
                        loop=loop,
                        parent_agent_id=parent_agent_id,
                        subagent_id=agent_id,
                        attempt=attempts,
                        max_attempts=max_attempts,
                        error=retry_diag.get("retry_block_reason"),
                        strategy_diff=retry_diag.get("strategy_diff"),
                    )
                    final_result = {
                        "status": "error",
                        "error": retry_diag.get("retry_block_reason"),
                        "result": {"status": "error"},
                        "tool": tc.tool_name,
                        "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    }
                    prev_attempt_plan = attempt_plan
                    if not retry_decision.allow:
                        final_result["error"] = retry_decision.reason or "retry_budget_exhausted"
                        break
                    continue
            run_prompt = task_payload if attempts == 1 else (
                "SYSTEM SELF-HEAL RETRY:\n"
                "Retry using different tool arguments or command strategy only. "
                "Do not modify immutable core files. "
                f"Immutable paths: {', '.join(self._immutable_core_patterns)}.\n\n"
                f"Previous failure: {final_result.get('error', 'unknown')}\n\n"
                f"{task_payload}"
            )
            child = EngineRunner(
                config_path=str((_BASE_DIR / "config.json")),
                verbose=False,
                stop_event=self._stop_event,
                rate_limit_action=self._rl_action,
            )
            prior_immutable = os.environ.get("OVERLORD11_IMMUTABLE_CORE_PATHS")
            try:
                if attempts > 1:
                    os.environ["OVERLORD11_IMMUTABLE_CORE_PATHS"] = json.dumps(self._immutable_core_patterns, ensure_ascii=False)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(
                        child.run,
                        run_prompt,
                        session_id,
                        job_id,
                        job_title,
                        agent_id,
                        False,
                        False,
                        {
                            "task": task,
                            "inputs": params.get("inputs"),
                            "expected_outputs": params.get("expected_outputs"),
                            "retry_attempt": attempts,
                            "parent_agent_id": parent_agent_id,
                            "immutable_rules": self._immutable_core_patterns,
                        },
                    )
                    try:
                        result = fut.result(timeout=timeout_s)
                    except FutureTimeoutError:
                        child._stop_event.set()
                        elapsed_s = round(time.monotonic() - started, 2)
                        self.events.emit(
                            EventType.SUBAGENT_TIMEOUT,
                            session_id=session_id,
                            loop=loop,
                            parent_agent_id=parent_agent_id,
                            subagent_id=agent_id,
                            timed_out=True,
                            timeout_s=timeout_s,
                            elapsed_s=elapsed_s,
                            attempt_count=attempts,
                        )
                        final_result = {
                            "status": "error",
                            "error": "subagent_timeout",
                            "result": {"status": "error", "timed_out": True, "timeout_s": timeout_s, "elapsed_s": elapsed_s},
                            "tool": tc.tool_name,
                            "duration_ms": round((time.monotonic() - started) * 1000, 2),
                        }
                        prev_attempt_plan = attempt_plan
                        if attempts < max_attempts:
                            retry_decision = self._loop_governor.increment_retry(1)
                            stats["subagent_retries"] += 1
                            self.events.emit(
                                EventType.SUBAGENT_RETRY,
                                session_id=session_id,
                                loop=loop,
                                parent_agent_id=parent_agent_id,
                                subagent_id=agent_id,
                                attempt=attempts,
                                max_attempts=max_attempts,
                                error="subagent_timeout",
                                strategy_diff=retry_diag.get("strategy_diff"),
                            )
                            if not retry_decision.allow:
                                final_result["error"] = retry_decision.reason or "retry_budget_exhausted"
                                break
                            continue
                        break
            finally:
                if prior_immutable is None:
                    os.environ.pop("OVERLORD11_IMMUTABLE_CORE_PATHS", None)
                else:
                    os.environ["OVERLORD11_IMMUTABLE_CORE_PATHS"] = prior_immutable
            is_ok = str(result.get("status", "")).lower() == "complete"
            duration_ms = round((time.monotonic() - started) * 1000, 2)
            if is_ok:
                stats["subagent_success"] += 1
                stats["subagent_duration_ms"] += duration_ms
                self.events.emit(
                    EventType.SUBAGENT_COMPLETE,
                    session_id=session_id,
                    loop=loop,
                    parent_agent_id=parent_agent_id,
                    subagent_id=agent_id,
                    duration_ms=duration_ms,
                    attempt_count=attempts,
                    usage={"tool_call_count": result.get("tool_call_count", 0), "artifact_count": result.get("artifact_count", 0)},
                    strategy_diff=retry_diag.get("strategy_diff"),
                )
                self._loop_governor.after_subagent(
                    agent_id,
                    {
                        "child_loops_used": attempts,
                        "status": "success",
                    },
                )
                return {
                    "status": "success",
                    "tool": tc.tool_name,
                    "duration_ms": duration_ms,
                    "result": {
                        "status": "success",
                        "agent_id": agent_id,
                        "outputs": result.get("output", ""),
                        "events": result.get("events", []),
                        "errors": None,
                        "attempt_count": attempts,
                        "timing": {"duration_ms": duration_ms},
                        "usage": {
                            "tool_call_count": result.get("tool_call_count", 0),
                            "artifact_count": result.get("artifact_count", 0),
                        },
                        "subagent_session_id": result.get("session_id"),
                        "subagent_agent_id": agent_id,
                        "timed_out": False,
                        "retry_block_reason": retry_diag.get("retry_block_reason"),
                        "strategy_diff": retry_diag.get("strategy_diff"),
                    },
                }
            final_result = {
                "status": "error",
                "error": result.get("error") or "subagent_failed",
                "result": result,
                "tool": tc.tool_name,
                "duration_ms": duration_ms,
            }
            if attempts < max_attempts:
                retry_decision = self._loop_governor.increment_retry(1)
                stats["subagent_retries"] += 1
                self.events.emit(
                    EventType.SUBAGENT_RETRY,
                    session_id=session_id,
                    loop=loop,
                    parent_agent_id=parent_agent_id,
                    subagent_id=agent_id,
                    attempt=attempts,
                    max_attempts=max_attempts,
                    error=final_result.get("error"),
                    strategy_diff=retry_diag.get("strategy_diff"),
                )
                if not retry_decision.allow:
                    final_result["error"] = retry_decision.reason or "retry_budget_exhausted"
                    break
            prev_attempt_plan = attempt_plan
        self._loop_governor.after_subagent(
            agent_id,
            {
                "child_loops_used": attempts,
                "status": final_result.get("status", "error"),
            },
        )
        stats["subagent_fail"] += 1
        self.events.emit(
            EventType.SUBAGENT_FAIL,
            session_id=session_id,
            loop=loop,
            parent_agent_id=parent_agent_id,
            subagent_id=agent_id,
            error=final_result.get("error", "subagent_failed"),
            attempt_count=attempts,
        )
        return {
            "status": "error",
            "tool": tc.tool_name,
            "duration_ms": final_result.get("duration_ms", 0.0),
            "error": final_result.get("error", "subagent_failed"),
            "result": {
                "status": "error",
                "agent_id": agent_id,
                "outputs": "",
                "events": final_result.get("result", {}).get("events", []),
                "errors": final_result.get("error", "subagent_failed"),
                "attempt_count": attempts,
                "timing": {"duration_ms": final_result.get("duration_ms", 0.0)},
                "usage": {
                    "tool_call_count": final_result.get("result", {}).get("tool_call_count", 0),
                    "artifact_count": final_result.get("result", {}).get("artifact_count", 0),
                },
                "subagent_session_id": final_result.get("result", {}).get("session_id") if isinstance(final_result.get("result"), dict) else None,
                "subagent_agent_id": agent_id,
                "timed_out": final_result.get("error") == "subagent_timeout",
                "retry_block_reason": final_result.get("error") if str(final_result.get("error", "")).startswith("agent_id_") else None,
                "strategy_diff": {},
            },
        }

    def _validate_delegation_call(self, params: dict) -> tuple[bool, str]:
        required = ("agent_id", "task", "inputs", "expected_outputs")
        missing = [k for k in required if k not in params]
        if missing:
            return False, f"delegation_missing_required_fields: {', '.join(missing)}"
        agent_id = str(params.get("agent_id") or "").strip()
        if not agent_id:
            return False, "delegation_invalid_agent_id"
        if not self._find_agent_name(agent_id):
            return False, f"delegation_unknown_agent: {agent_id}"
        if not str(params.get("task") or "").strip():
            return False, "delegation_empty_task"
        timeout_s = int(params.get("timeout_s") or 300)
        if timeout_s <= 0 or timeout_s > 7200:
            return False, "delegation_invalid_timeout_s"
        depends_on = params.get("depends_on", [])
        if depends_on is not None and not isinstance(depends_on, list):
            return False, "delegation_depends_on_must_be_list"
        return True, ""

    def _find_agent_name(self, agent_id: str) -> Optional[str]:
        for name, cfg in (self._config.get("agents", {}) or {}).items():
            if str((cfg or {}).get("id", "")).strip() == agent_id:
                return name
        return None

    def _delegations_are_independent(self, entries: list[dict]) -> bool:
        seen_outputs: set[str] = set()
        for item in entries:
            outputs = item.get("expected_outputs")
            if isinstance(outputs, str):
                output_keys = [outputs]
            elif isinstance(outputs, list):
                output_keys = [str(o) for o in outputs]
            elif isinstance(outputs, dict):
                output_keys = [str(k) for k in outputs.keys()]
            else:
                output_keys = []
            for key in output_keys:
                lk = key.strip().lower()
                if not lk:
                    continue
                if lk in seen_outputs:
                    return False
                seen_outputs.add(lk)
        return True

    def _build_uiux_context_for_subagent(self, *, agent_id: str, task: str) -> str:
        task_l = (task or "").lower()
        if agent_id not in {"OVR_PUB_07", "OVR_COD_03"} and not any(k in task_l for k in ("html", "report", "ui", "ux")):
            return ""
        skills_dir = _BASE_DIR / "skills" / "uiux"
        styles_file = skills_dir / "styles.json"
        palettes_file = skills_dir / "palettes.json"
        try:
            styles = json.loads(styles_file.read_text(encoding="utf-8")) if styles_file.exists() else {}
            palettes = json.loads(palettes_file.read_text(encoding="utf-8")) if palettes_file.exists() else {}
        except Exception:
            return ""
        style_keys = list(styles.keys())[:6] if isinstance(styles, dict) else []
        palette_keys = list(palettes.keys())[:6] if isinstance(palettes, dict) else []
        payload = {
            "summary": "Use intentional typography/color/motion and avoid default bland layouts.",
            "style_keys": style_keys,
            "palette_keys": palette_keys,
        }
        return json.dumps(payload, ensure_ascii=False)

    def _compact_json_snippet(self, payload: dict, *, max_chars: int = 2400) -> str:
        text = json.dumps(payload, ensure_ascii=False)
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1] + "…"
