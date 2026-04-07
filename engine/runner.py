"""
Overlord11 Engine - Runner
============================
Core execution loop for the Overlord11 engine.
"""

import json
import random
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
    from .session_manager import EngineSession
    from .tool_executor import ToolExecutor, extract_tool_calls
except ImportError:
    from event_stream import EventStream, EventType  # type: ignore[no-redef]
    from orchestrator_bridge import OrchestratorBridge  # type: ignore[no-redef]
    from parallel_executor import ParallelToolExecutor  # type: ignore[no-redef]
    from rate_limit import AllProvidersRateLimitedError  # type: ignore[no-redef]
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
        agent_id: str = "OVR_DIR_01",
        streaming: bool = True,
    ) -> dict:
        """
        Run the agent loop and return a result dict.

        When streaming=True (default), each provider call streams tokens back
        through the EventStream as TOKEN events.  The frontend can subscribe to
        these events to render the LLM response in real time.  Falls back to
        non-streaming automatically if the provider does not support it.
        """
        max_loops: int = self._config.get("orchestration", {}).get("max_loops", 10)

        # Session setup
        session = EngineSession(
            session_id=session_id,
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
        system_prompt = (
            system_prompt
            + "\n\n---\n\n"
            + "Execution environment profile:\n"
            + json.dumps(system_profile, indent=2, ensure_ascii=False)
        )
        messages = [{"role": "user", "content": user_input}]

        final_output = ""
        status = "max_loops_reached"
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

            agent_log = session.log_agent(agent_id, messages[-1].get("content", ""), response)
            self.events.emit(
                EventType.AGENT_COMPLETE,
                agent_id=agent_id,
                loop=loop,
                response_len=len(response),
                trace_path=agent_log.get("trace_path"),
            )

            tool_calls = extract_tool_calls(response)
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
                # No tools → done
                final_output = response
                status = "complete"
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

            # Inject tool results into context
            messages = self._bridge.build_context(messages, tool_results)

        self.events.emit(EventType.SESSION_END, session_id=sid, status=status, loops=loop)
        output_path = session.log_product_output(final_output or (messages[-1].get("content", "") if messages else ""))
        if output_path:
            self.events.emit(EventType.ARTIFACT_CREATED, session_id=sid, category="output", path=output_path)
        session.close(status=status)

        return {
            "session_id": sid,
            "output": final_output or (messages[-1].get("content", "") if messages else ""),
            "events": self.events.get_events(),
            "status": status,
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
        return any(sig in lowered for sig in completion_signals) or len(lowered) > 50
