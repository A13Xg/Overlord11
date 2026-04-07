"""
Overlord11 Engine — Parallel Tool Executor
===========================================
Executes a batch of tool calls with dependency-aware parallelism.

Flow:
  1. DependencyAnalyzer.partition() splits the batch into ordered waves.
  2. Single-call waves bypass thread overhead and run directly.
  3. Multi-call waves execute in a bounded ThreadPoolExecutor.
  4. Results are collected and returned in the original LLM-generation order,
     regardless of which threads finished first.

Thread safety:
  - EventStream.emit() is protected by an internal threading.Lock (added in
    this release) — safe to call from multiple threads simultaneously.
  - ToolExecutor.execute() is reentrant: each invocation uses only its own
    local variables after the sys.path lock is released.
  - The _sys_path_lock on ToolExecutor serializes the brief window where
    sys.path is mutated and a module is imported; the module object is then
    fully owned by the calling thread.
  - session_log_fn (session.log_tool_call) writes to per-session files with
    its own internal lock — safe from multiple threads.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Tuple

try:
    from .dependency_analyzer import DependencyAnalyzer
    from .tool_executor import ToolCall, ToolExecutor
except ImportError:
    from dependency_analyzer import DependencyAnalyzer  # type: ignore[no-redef]
    from tool_executor import ToolCall, ToolExecutor  # type: ignore[no-redef]

log = logging.getLogger("overlord11.parallel_executor")

# Type alias for the event-emit callbacks forwarded from runner.py
_EmitFn = Callable[..., None]


class ParallelToolExecutor:
    """
    Wraps ToolExecutor and executes tool call batches with dependency-aware
    parallelism.

    Args:
        tool_executor:  The underlying ToolExecutor that actually runs tools.
        max_workers:    Upper bound on simultaneous threads per wave.
                        Set via config orchestration.parallel.max_concurrent_tools.
    """

    def __init__(self, tool_executor: ToolExecutor, max_workers: int = 4) -> None:
        self._executor = tool_executor
        self._analyzer = DependencyAnalyzer()
        self._max_workers = max(1, max_workers)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute_all(
        self,
        tool_calls: List[ToolCall],
        *,
        on_call: _EmitFn,
        on_result: _EmitFn,
        on_error: _EmitFn,
        on_cache_hit: _EmitFn,
        on_notification: _EmitFn,
        loop: int,
        session_log_fn: Callable,
    ) -> List[Tuple[ToolCall, dict]]:
        """
        Execute all tool calls in dependency order.

        Each call fires the appropriate event callbacks (on_call, on_result,
        on_error, on_cache_hit, on_notification).  All callbacks are
        thread-safe because EventStream.emit() is mutex-guarded.

        Args:
            tool_calls:      Ordered list of tool calls from the LLM response.
            on_call:         Emits TOOL_CALL event.
            on_result:       Emits TOOL_RESULT event.
            on_error:        Emits TOOL_ERROR event.
            on_cache_hit:    Emits TOOL_CACHE_HIT event.
            on_notification: Emits NOTIFICATION event.
            loop:            Current agent loop number (for event context).
            session_log_fn:  session.log_tool_call(name, params, result) → dict.

        Returns:
            List of (ToolCall, result_dict) in original LLM generation order.
        """
        if not tool_calls:
            return []

        waves = self._analyzer.partition(tool_calls)

        if len(waves) < len(tool_calls):
            parallelized = sum(len(w) for w in waves if len(w) > 1)
            log.info(
                "Loop %d: %d tool call(s) → %d wave(s) | %d will run in parallel",
                loop, len(tool_calls), len(waves), parallelized,
            )
        else:
            log.debug(
                "Loop %d: %d tool call(s) all serialized (no parallelism opportunity)",
                loop, len(tool_calls),
            )

        # Map object id → original 1-based call index (preserves LLM order)
        original_index: dict[int, int] = {
            id(tc): i + 1 for i, tc in enumerate(tool_calls)
        }

        # Collect results keyed by original index for ordered reassembly
        results: dict[int, Tuple[ToolCall, dict]] = {}

        for wave_num, wave in enumerate(waves):
            if len(wave) == 1:
                # Single call — skip thread overhead
                tc = wave[0]
                call_index = original_index[id(tc)]
                result = self._execute_one(
                    tc, call_index,
                    on_call, on_result, on_error,
                    on_cache_hit, on_notification,
                    loop, session_log_fn,
                )
                results[call_index] = (tc, result)

            else:
                log.info(
                    "Loop %d, wave %d/%d: running [%s] in parallel",
                    loop, wave_num + 1, len(waves),
                    ", ".join(tc.tool_name for tc in wave),
                )
                n_threads = min(len(wave), self._max_workers)
                with ThreadPoolExecutor(max_workers=n_threads) as pool:
                    future_to_tc = {
                        pool.submit(
                            self._execute_one,
                            tc,
                            original_index[id(tc)],
                            on_call, on_result, on_error,
                            on_cache_hit, on_notification,
                            loop, session_log_fn,
                        ): tc
                        for tc in wave
                    }
                    for future in as_completed(future_to_tc):
                        tc = future_to_tc[future]
                        call_index = original_index[id(tc)]
                        try:
                            result = future.result()
                        except Exception as exc:
                            log.error(
                                "Unhandled exception in parallel tool %s: %s",
                                tc.tool_name, exc,
                            )
                            result = {
                                "status": "error",
                                "result": f"Parallel execution error: {exc}",
                                "tool": tc.tool_name,
                                "duration_ms": 0.0,
                            }
                        results[call_index] = (tc, result)

        # Return in original LLM generation order
        return [results[i] for i in sorted(results)]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _execute_one(
        self,
        tc: ToolCall,
        call_index: int,
        on_call: _EmitFn,
        on_result: _EmitFn,
        on_error: _EmitFn,
        on_cache_hit: _EmitFn,
        on_notification: _EmitFn,
        loop: int,
        session_log_fn: Callable,
    ) -> dict:
        """
        Execute a single tool call and fire all relevant event callbacks.

        This method is designed to be safe when called from multiple threads:
          - All emit callbacks are thread-safe (EventStream lock).
          - ToolExecutor.execute() is reentrant.
          - session_log_fn writes to isolated per-session files.
        """
        on_call(tool=tc.tool_name, params=tc.params, loop=loop, call_index=call_index)

        result = self._executor.execute(tc)
        tool_log = session_log_fn(tc.tool_name, tc.params, result)

        if result["status"] == "success":
            if result.get("cached"):
                on_cache_hit(
                    tool=tc.tool_name,
                    cache_age_s=result.get("cache_age_s"),
                    loop=loop,
                    call_index=call_index,
                )

            # notification_tool sets _notification=True in the inner result
            # dict to signal the engine to push a browser toast.
            inner = result.get("result", {})
            if isinstance(inner, dict) and inner.get("_notification"):
                on_notification(
                    title=inner.get("title", ""),
                    message=inner.get("message", ""),
                    severity=inner.get("severity", "info"),
                )

            on_result(
                tool=tc.tool_name,
                duration_ms=result["duration_ms"],
                result=result.get("result"),
                loop=loop,
                call_index=call_index,
                cached=result.get("cached", False),
                trace_path=tool_log.get("trace_path"),
            )
        else:
            on_error(
                tool=tc.tool_name,
                error=result["result"],
                result=result.get("result"),
                loop=loop,
                call_index=call_index,
                trace_path=tool_log.get("trace_path"),
            )

        return result
