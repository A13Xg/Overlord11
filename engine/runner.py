"""
Overlord11 Engine - Runner
============================
Core execution loop for the Overlord11 engine.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from .event_stream import EventStream, EventType
    from .orchestrator_bridge import OrchestratorBridge
    from .session_manager import EngineSession
    from .tool_executor import ToolExecutor, extract_tool_calls
except ImportError:
    from event_stream import EventStream, EventType  # type: ignore[no-redef]
    from orchestrator_bridge import OrchestratorBridge  # type: ignore[no-redef]
    from session_manager import EngineSession  # type: ignore[no-redef]
    from tool_executor import ToolExecutor, extract_tool_calls  # type: ignore[no-redef]

_BASE_DIR = Path(__file__).resolve().parent.parent
_TOOLS_DIR = _BASE_DIR / "tools" / "python"


class EngineRunner:
    """Orchestrates the full agent execution loop."""

    def __init__(self, config_path: str = "config.json", verbose: bool = True):
        config_file = Path(config_path)
        if not config_file.is_absolute():
            config_file = _BASE_DIR / config_path
        self._config = json.loads(config_file.read_text(encoding="utf-8"))
        self.verbose = verbose
        self.events = EventStream(verbose=verbose)
        self._tool_executor = ToolExecutor(tools_dir=_TOOLS_DIR, config=self._config)
        self._bridge = OrchestratorBridge(config=self._config)

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
            except Exception as exc:
                self.events.emit(EventType.ERROR, message=str(exc), loop=loop)
                session.log_event("error", {"message": str(exc), "loop": loop})
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

            # Execute each tool call
            tool_results = []
            for index, tc in enumerate(tool_calls, start=1):
                self.events.emit(EventType.TOOL_CALL, tool=tc.tool_name, params=tc.params, loop=loop, call_index=index)
                result = self._tool_executor.execute(tc)
                tool_log = session.log_tool_call(tc.tool_name, tc.params, result)

                if result["status"] == "success":
                    if result.get("cached"):
                        # Served from cache — emit a distinct event so the
                        # frontend can display a cache-hit indicator.
                        self.events.emit(
                            EventType.TOOL_CACHE_HIT,
                            tool=tc.tool_name,
                            cache_age_s=result.get("cache_age_s"),
                            loop=loop,
                            call_index=index,
                        )

                    # notification_tool signals the engine to broadcast a
                    # NOTIFICATION event directly over the SSE pipe so the
                    # frontend can show a browser toast immediately.
                    inner = result.get("result", {})
                    if isinstance(inner, dict) and inner.get("_notification"):
                        self.events.emit(
                            EventType.NOTIFICATION,
                            title=inner.get("title", ""),
                            message=inner.get("message", ""),
                            severity=inner.get("severity", "info"),
                            session_id=inner.get("session_id") or sid,
                        )

                    self.events.emit(
                        EventType.TOOL_RESULT,
                        tool=tc.tool_name,
                        duration_ms=result["duration_ms"],
                        result=result.get("result"),
                        loop=loop,
                        call_index=index,
                        cached=result.get("cached", False),
                        trace_path=tool_log.get("trace_path"),
                    )
                else:
                    self.events.emit(
                        EventType.TOOL_ERROR,
                        tool=tc.tool_name,
                        error=result["result"],
                        result=result.get("result"),
                        loop=loop,
                        call_index=index,
                        trace_path=tool_log.get("trace_path"),
                    )
                tool_results.append(result)

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
