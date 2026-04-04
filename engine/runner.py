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
    ) -> dict:
        """Run the agent loop and return a result dict."""
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

        # Build initial system prompt and message history
        system_prompt = self._bridge.build_system_prompt(agent_id)
        messages = [{"role": "user", "content": user_input}]

        final_output = ""
        status = "max_loops_reached"
        loop = 0

        while loop < max_loops:
            loop += 1
            self.events.emit(EventType.AGENT_START, agent_id=agent_id, loop=loop)

            # Call provider
            try:
                response = self._bridge.call_provider(messages=messages, system=system_prompt)
            except Exception as exc:
                self.events.emit(EventType.ERROR, message=str(exc), loop=loop)
                session.log_event("error", {"message": str(exc), "loop": loop})
                break

            self.events.emit(EventType.AGENT_COMPLETE, agent_id=agent_id, loop=loop, response_len=len(response))
            session.log_agent(agent_id, messages[-1].get("content", ""), response)

            # Append assistant message to context
            messages.append({"role": "assistant", "content": response})

            # Check for tool calls
            tool_calls = extract_tool_calls(response)
            if not tool_calls:
                # No tools → done
                final_output = response
                status = "complete"
                break

            # Execute each tool call
            tool_results = []
            for tc in tool_calls:
                self.events.emit(EventType.TOOL_CALL, tool=tc.tool_name, params=tc.params)
                result = self._tool_executor.execute(tc)
                session.log_tool_call(tc.tool_name, tc.params, result)

                if result["status"] == "success":
                    self.events.emit(
                        EventType.TOOL_RESULT,
                        tool=tc.tool_name,
                        duration_ms=result["duration_ms"],
                    )
                else:
                    self.events.emit(
                        EventType.TOOL_ERROR,
                        tool=tc.tool_name,
                        error=result["result"],
                    )
                tool_results.append(result)

            # Inject tool results into context
            messages = self._bridge.build_context(messages, tool_results)

        self.events.emit(EventType.SESSION_END, session_id=sid, status=status, loops=loop)
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
