"""
Overlord11 Engine - Runner
============================
Core execution loop for the Overlord11 engine.
"""

import json
import random
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from .event_stream import EventStream, EventType
    from .orchestrator_bridge import OrchestratorBridge
    from .parallel_executor import ParallelToolExecutor
    from .rate_limit import AllProvidersRateLimitedError
    from .self_healing import SelfHealingEngine
    from .session_manager import EngineSession
    from .tool_executor import ToolExecutor, extract_tool_calls
except ImportError:
    from event_stream import EventStream, EventType  # type: ignore[no-redef]
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
        max_loops: int = self._config.get("orchestration", {}).get("max_loops", 10)

        # Session setup
        session = EngineSession(
            session_id=session_id,
            job_id=job_id,
            description=user_input[:120],
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
        system_profile = session.record_system_profile(agent_id=agent_id)
        self.events.emit(
            EventType.SYSTEM_PROFILE,
            session_id=sid,
            system=system_profile.get("system"),
            release=system_profile.get("release"),
            shell=(system_profile.get("shell") or {}).get("env") or "auto",
        )

        # Build initial system prompt and message history
        system_prompt = self._bridge.build_system_prompt(agent_id)
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
        max_no_tool_retries = (
            self._config.get("orchestration", {})
            .get("no_tool_retries_for_nontrivial", 2)
        )
        loop = 0

        while loop < max_loops:
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

            agent_log = session.log_agent(agent_id, messages[-1].get("content", ""), response)
            self.events.emit(
                EventType.AGENT_COMPLETE,
                agent_id=agent_id,
                loop=loop,
                response_len=len(response),
                trace_path=agent_log.get("trace_path"),
            )

            tool_calls = extract_tool_calls(response)
            total_tool_call_count += len(tool_calls)
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

            # Check for tool calls
            if not tool_calls:
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
            tool_results = [result for _tc, result in ordered_pairs]
            had_effectful_tool_success = had_effectful_tool_success or any(
                self._is_effectful_tool_result(result) for result in tool_results
            )
            observed_dir_path, observed_dir_entries = self._update_observed_directory_snapshot(
                ordered_pairs=ordered_pairs,
                prior_path=observed_dir_path,
                prior_entries=observed_dir_entries,
            )

            # Inject tool results into context
            messages = self._bridge.build_context(messages, tool_results)

            # ── Self-Healing Type B: inject structured recovery hints for tool errors ──
            _heal_hints = []
            for _tc, _result in ordered_pairs:
                if isinstance(_result, dict) and _result.get("status") == "error":
                    _err = _result.get("error") or _result.get("result") or str(_result)
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
            if _heal_hints:
                messages.append({
                    "role": "user",
                    "content": "SYSTEM — RECOVERY GUIDANCE:\n\n" + "\n\n".join(_heal_hints),
                })

        self.events.emit(EventType.SESSION_END, session_id=sid, status=status, loops=loop)
        output_path = session.log_product_output(final_output or (messages[-1].get("content", "") if messages else ""))
        if output_path:
            artifact_count += 1
            self.events.emit(EventType.ARTIFACT_CREATED, session_id=sid, category="output", path=output_path)
        if status == "complete" and completion_mode != "direct_answer":
            completion_mode = "tool_driven"
        output_text = final_output or (messages[-1].get("content", "") if messages else "")
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

    def _is_effectful_tool_result(self, result: dict) -> bool:
        """
        True when a tool call appears to have produced usable output.
        """
        if not isinstance(result, dict):
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

    def _try_parse_json(self, text: str) -> Optional[dict]:
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
        return None

    def _detect_tool_format_issue(self, response: str) -> Optional[str]:
        lowered = (response or "").lower()
        if "<tool_code>" in lowered or "</tool_code>" in lowered:
            return "pseudo_tool_code_tag"
        if "<execute_bash>" in lowered or "</execute_bash>" in lowered:
            return "pseudo_execute_bash_tag"
        return None

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
        # Prevent claiming repository-root verification when only scripts/ was observed.
        lowered = text.lower()
        claims_repo_structure = any(k in lowered for k in ("agents/", "tools/", "docs/"))
        if claims_repo_structure and observed_entries:
            required = {"agents", "tools", "docs"}
            if not required.issubset({e.lower() for e in observed_entries}):
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
        return any(sig in lowered for sig in completion_signals) or len(text) >= 80

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
