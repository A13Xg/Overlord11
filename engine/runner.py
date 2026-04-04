"""
engine/runner.py
=================
Main execution loop for the Overlord11 internal engine.

Execution flow
--------------
1. Accept a task string + optional config overrides
2. Create a Session via SessionManager
3. Build initial context (system is embedded in OrchestratorBridge)
4. Loop:
     a. Call provider via OrchestratorBridge
     b. Detect tool calls in response
     c. Execute tools via ToolExecutor
     d. Append results to context
     e. If no tool calls → task complete
     f. On error → SelfHealingSystem attempts recovery
5. Return final result

Pause / Resume / Stop
---------------------
  The session state is checked at the top of every loop iteration:
    PAUSED   → busy-wait (0.5 s sleep) until resumed or failed/stopped
    FAILED   → the session was externally stopped; exit immediately
  Callers can pause/resume/stop by mutating session.state directly.

This does NOT modify any agent .md definitions or CLI workflow.
"""

import json
import time
from typing import Any, Dict, List, Optional

from engine.event_stream import EventStream
from engine.orchestrator_bridge import OrchestratorBridge
from engine.self_healing import SelfHealingSystem
from engine.session_manager import Session, SessionManager, SessionState
from engine.tool_executor import ToolExecutor


class EngineRunner:
    """
    Drives the agent execution loop for a single session.

    Designed to run either synchronously (blocking) or to be awaited
    inside an async context via asyncio.to_thread().
    """

    def __init__(
        self,
        session_manager: Optional[SessionManager] = None,
        max_loops: int = 10,
        max_retries: int = 3,
        provider_override: Optional[str] = None,
    ):
        self._session_mgr = session_manager or SessionManager()
        self._max_loops = max_loops
        self._max_retries = max_retries
        self._provider_override = provider_override
        self._bridge = OrchestratorBridge(provider_override=provider_override)
        self._executor = ToolExecutor()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        task: str,
        agent: str = "orchestrator",
        provider: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a task synchronously.

        Returns a result dict:
        {
            "session_id": str,
            "state":      str,   # "completed" | "failed"
            "result":     str | None,
            "error":      str | None,
            "loop_count": int,
            "healing":    dict,
        }
        """
        session = self._session_mgr.create(
            task=task,
            provider=provider or self._provider_override or "anthropic",
            agent=agent,
            metadata=metadata,
        )
        return self._execute(session, provider=provider)

    def run_session(self, session: Session, provider: Optional[str] = None) -> Dict[str, Any]:
        """Execute a pre-created session (used by backend job runner)."""
        return self._execute(session, provider=provider)

    # ------------------------------------------------------------------
    # Internal execution loop
    # ------------------------------------------------------------------

    def _execute(self, session: Session, provider: Optional[str] = None) -> Dict[str, Any]:
        stream = session.stream
        healer = SelfHealingSystem(max_retries=self._max_retries)

        session.start()
        stream.emit_agent_start(agent=session.agent, task=session.task)

        # Seed context with the user task
        session.add_context("user", session.task)

        loop_count = 0
        done = False

        while not done and loop_count < self._max_loops:
            # --- External state checks (pause / stop) ---
            if session.state == SessionState.FAILED:
                # Session was externally stopped via stop_job_session()
                break
            if session.state == SessionState.PAUSED:
                # Busy-wait while paused (short sleep to avoid spinning)
                time.sleep(0.5)
                continue

            loop_count += 1
            session.loop_count = loop_count
            stream.emit_log(f"Loop {loop_count}/{self._max_loops}", level="debug")

            # --- Agent call ---
            messages = self._build_messages(session)
            try:
                response_text, prov_used = self._bridge.call(
                    agent_name=session.agent,
                    messages=messages,
                    provider=provider,
                )
                stream.emit_log(f"Provider response received ({prov_used})", level="debug")
            except RuntimeError as exc:
                error_str = str(exc)
                stream.emit_error(error=error_str)
                if healer.should_retry(error_str):
                    healing_msg = healer.heal(error_str)
                    stream.emit_healing(
                        attempt=healer.retry_count,
                        strategy="api_retry",
                        original_error=error_str,
                    )
                    session.add_context("user", healing_msg)
                    continue
                else:
                    session.fail(error_str)
                    return self._build_result(session, healer)

            # Append assistant response to context
            session.add_context("assistant", response_text)

            # --- Tool detection ---
            tool_calls = self._executor.parse(response_text)

            if not tool_calls:
                # No tool calls → task considered complete
                done = True
                session.complete(response_text)
                stream.emit_log("Task complete — no further tool calls detected")
                break

            # --- Execute tools ---
            for call in tool_calls:
                tool_name = call.get("tool", "")
                args = call.get("args", {})

                stream.emit_tool_call(tool=tool_name, args=args)

                exec_result = self._executor.execute(tool_name, args)

                stream.emit_tool_result(tool=tool_name, result=exec_result)

                if exec_result["success"]:
                    result_text = json.dumps(exec_result["result"], default=str)
                    session.add_context(
                        "user",
                        f"Tool '{tool_name}' result:\n{result_text}",
                    )
                else:
                    error_str = exec_result["error"] or "Unknown tool error"
                    stream.emit_error(error=error_str)

                    if healer.should_retry(error_str):
                        healing_msg = healer.heal(error_str)
                        stream.emit_healing(
                            attempt=healer.retry_count,
                            strategy="tool_retry",
                            original_error=error_str,
                        )
                        session.add_context("user", healing_msg)
                    else:
                        # Max retries exceeded — fail the session
                        session.fail(f"Tool '{tool_name}' failed after max retries: {error_str}")
                        return self._build_result(session, healer)

        if not done and session.state not in (SessionState.FAILED, SessionState.COMPLETED):
            # Exceeded max loops (session was not externally stopped)
            loop_error = f"Exceeded max_loops ({self._max_loops}) without completing"
            if healer.should_retry(loop_error):
                # Ask for a final summary
                healing_msg = healer.heal(loop_error)
                session.add_context("user", healing_msg)
                try:
                    response_text, _ = self._bridge.call(
                        agent_name=session.agent,
                        messages=self._build_messages(session),
                        provider=provider,
                    )
                    session.complete(response_text)
                except Exception as exc:
                    session.fail(str(exc))
            else:
                session.fail(loop_error)

        return self._build_result(session, healer)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_messages(self, session: Session) -> List[Dict[str, str]]:
        """Convert session context to provider message format."""
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in session.context
        ]

    def _build_result(self, session: Session, healer: SelfHealingSystem) -> Dict[str, Any]:
        return {
            "session_id": session.session_id,
            "state": session.state,
            "result": session.result,
            "error": session.error,
            "loop_count": session.loop_count,
            "healing": healer.summary(),
        }
