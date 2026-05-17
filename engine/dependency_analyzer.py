"""
Overlord11 Engine — Tool Call Dependency Analyzer
==================================================
Partitions a batch of tool calls from a single LLM response into ordered
"execution waves".  Tool calls within the same wave are independent and can
run concurrently.  Waves must execute in strict order — the output of wave N
is fully available before wave N+1 begins.

Conflict rules (evaluated in priority order):
  1. Serial tools  — tools with side-effects that mutate shared state must
                     always run alone, never merged into a shared wave.
  2. Same tool     — two calls to the same tool share Python module state
                     (importlib cache, class-level mutables); conservative
                     serialization prevents subtle data races.
  3. Shared path   — two calls whose parameters reference the same filesystem
                     path (read or write) may interfere; serialized.

If no conflict exists between two calls they may be placed in the same wave
and executed by a thread pool.

Design notes:
  - Pure static analysis — no I/O, no imports of tool modules.
  - O(n²) conflict detection is fine: LLMs rarely emit more than ~10 tool
    calls per response.
  - Greedy wave assignment preserves LLM generation order within each wave,
    which makes event logs easier to read.
"""

from __future__ import annotations

import re
from typing import List, Set

try:
    from .tool_executor import ToolCall
except ImportError:
    from tool_executor import ToolCall  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Serial (never-parallel) tools
# ---------------------------------------------------------------------------

# Any tool that writes files, mutates the shell environment, or produces
# side-effects that later calls depend on must be serialized.
SERIAL_TOOLS: frozenset[str] = frozenset({
    "write_file",
    "replace",
    "run_shell_command",
    "git_tool",
    "database_tool",
    "computer_control",
    "session_clean",
    "cleanup_tool",
    "launcher_generator",
    "scaffold_generator",
    "project_docs_init",
    "execute_python",
})


# ---------------------------------------------------------------------------
# Path extraction helpers
# ---------------------------------------------------------------------------

# Parameter names whose values are almost always filesystem paths.
_PATH_PARAM_KEYS: frozenset[str] = frozenset({
    "path", "file_path", "output_path", "source", "destination",
    "target", "src", "dst", "dir", "directory", "filename",
    "workspace_path", "project_path", "filepath", "input_path",
    "data_file",
})

# Heuristic: string value looks like an absolute or relative path.
_PATH_VALUE_RE = re.compile(
    r"(?:[a-zA-Z]:[/\\]|^/[a-zA-Z]|^\./|^\.\./|^[a-zA-Z][\w\-]*/)",
    re.MULTILINE,
)


def _extract_paths(params: dict) -> Set[str]:
    """
    Extract normalised filesystem paths from a tool's parameter dict.

    Normalisation: backslash → forward-slash, lowercase, stripped.
    Only string values are examined.
    """
    paths: Set[str] = set()
    for key, val in params.items():
        if not isinstance(val, str):
            continue
        if key.lower() in _PATH_PARAM_KEYS or _PATH_VALUE_RE.search(val):
            paths.add(val.replace("\\", "/").lower().strip())
    return paths


# ---------------------------------------------------------------------------
# Conflict predicate
# ---------------------------------------------------------------------------

def _conflicts(a: ToolCall, b: ToolCall) -> bool:
    """
    Return True if tool calls *a* and *b* must not run concurrently.

    Evaluated in priority order so that the cheapest check (serial tool
    membership) happens before the more expensive path extraction.
    """
    # Rule 1: either call is a serial tool → must serialize
    if a.tool_name in SERIAL_TOOLS or b.tool_name in SERIAL_TOOLS:
        return True

    # Rule 2: same tool name → conservative serialization
    if a.tool_name == b.tool_name:
        return True

    # Rule 3: overlapping filesystem paths
    paths_a = _extract_paths(a.params)
    paths_b = _extract_paths(b.params)
    if paths_a and paths_b and (paths_a & paths_b):
        return True

    return False


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

class DependencyAnalyzer:
    """
    Partition a list of ToolCall objects into sequential execution waves.

    Usage::

        analyzer = DependencyAnalyzer()
        waves = analyzer.partition(tool_calls)
        for wave in waves:
            run_in_parallel(wave)   # safe — calls within a wave don't conflict
    """

    def partition(self, tool_calls: List[ToolCall]) -> List[List[ToolCall]]:
        """
        Partition *tool_calls* into the minimum number of ordered waves
        such that all calls within a wave are pairwise non-conflicting.

        Returns:
            Ordered list of waves.  Each wave is a list of ToolCall objects
            that can be executed concurrently.  An empty input returns [].
            A single call returns [[call]].
        """
        if not tool_calls:
            return []
        if len(tool_calls) == 1:
            return [list(tool_calls)]

        n = len(tool_calls)

        # Build symmetric conflict adjacency (index-based for O(1) lookup)
        conflict_sets: List[Set[int]] = [set() for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                if _conflicts(tool_calls[i], tool_calls[j]):
                    conflict_sets[i].add(j)
                    conflict_sets[j].add(i)

        # Greedy wave assignment: place each call into the earliest wave
        # where it does not conflict with any call already in that wave.
        # This preserves LLM generation order within each wave.
        wave_members: List[List[int]] = []  # wave_members[w] = [call indices]

        for i in range(n):
            placed = False
            for members in wave_members:
                if not any(j in conflict_sets[i] for j in members):
                    members.append(i)
                    placed = True
                    break
            if not placed:
                wave_members.append([i])

        return [[tool_calls[idx] for idx in members] for members in wave_members]

    def explain(self, tool_calls: List[ToolCall]) -> dict:
        """
        Return a human-readable breakdown of the wave partition for debugging
        and logging.  Not called during normal execution.

        Returns::

            {
                "waves": [["tool_a", "tool_b"], ["tool_c"]],
                "conflicts": [{"a": "tool_a", "b": "tool_c", "reason": "serial_tool"}],
                "parallelizable": 2,
                "serialized": 1,
            }
        """
        waves = self.partition(tool_calls)
        n = len(tool_calls)
        conflicts = []
        for i in range(n):
            for j in range(i + 1, n):
                a, b = tool_calls[i], tool_calls[j]
                if _conflicts(a, b):
                    reason = "serial_tool"
                    if a.tool_name not in SERIAL_TOOLS and b.tool_name not in SERIAL_TOOLS:
                        reason = "same_tool" if a.tool_name == b.tool_name else "shared_path"
                    conflicts.append({"a": a.tool_name, "b": b.tool_name, "reason": reason})

        parallelizable = sum(len(w) for w in waves if len(w) > 1)
        return {
            "waves": [[tc.tool_name for tc in w] for w in waves],
            "conflicts": conflicts,
            "parallelizable": parallelizable,
            "serialized": n - parallelizable,
        }
