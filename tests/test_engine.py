"""
tests/test_engine.py
=====================
Unit tests for the Overlord11 internal execution engine.

Run: python tests/test_engine.py
"""

import asyncio
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.event_stream import EventStream, make_event
from engine.session_manager import Session, SessionManager, SessionState
from engine.tool_executor import ToolExecutor
from engine.self_healing import (
    SelfHealingSystem,
    classify_error,
    ErrorClass,
    build_healing_message,
)
from tools.python.execute_python import execute_python


# ──────────────────────────────────────────────────────────────────────────────
# EventStream tests
# ──────────────────────────────────────────────────────────────────────────────

class TestEventStream(unittest.TestCase):

    def setUp(self):
        self.stream = EventStream(session_id="test-001")

    def test_emit_stores_in_history(self):
        self.stream.emit("log", message="hello")
        self.assertEqual(len(self.stream), 1)
        self.assertEqual(self.stream._history[0]["type"], "log")
        self.assertEqual(self.stream._history[0]["message"], "hello")

    def test_emit_agent_start(self):
        self.stream.emit_agent_start(agent="orchestrator", task="test task")
        evt = self.stream._history[-1]
        self.assertEqual(evt["type"], "agent_start")
        self.assertEqual(evt["agent"], "orchestrator")

    def test_emit_tool_call(self):
        self.stream.emit_tool_call(tool="read_file", args={"path": "foo.txt"})
        evt = self.stream._history[-1]
        self.assertEqual(evt["type"], "tool_call")
        self.assertEqual(evt["tool"], "read_file")

    def test_emit_complete_marks_closed(self):
        self.stream.emit_complete(result="done")
        self.assertTrue(self.stream._closed)

    def test_get_history_since(self):
        t0 = time.time() - 0.1
        self.stream.emit("log", message="a")
        self.stream.emit("log", message="b")
        history = self.stream.get_history(since=t0)
        self.assertEqual(len(history), 2)

    def test_make_event_shape(self):
        evt = make_event("log", "sid-1", message="test")
        self.assertIn("type", evt)
        self.assertIn("session_id", evt)
        self.assertIn("ts", evt)
        self.assertIn("message", evt)


# ──────────────────────────────────────────────────────────────────────────────
# SessionManager tests
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionManager(unittest.TestCase):

    def setUp(self):
        self.mgr = SessionManager(log_dir="/tmp/ovr11_test_sessions")

    def tearDown(self):
        import shutil
        shutil.rmtree("/tmp/ovr11_test_sessions", ignore_errors=True)

    def test_create_returns_session(self):
        s = self.mgr.create(task="test task")
        self.assertIsNotNone(s)
        self.assertEqual(s.task, "test task")
        self.assertEqual(s.state, SessionState.QUEUED)

    def test_get_by_id(self):
        s = self.mgr.create(task="hello")
        found = self.mgr.get(s.session_id)
        self.assertIs(found, s)

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.mgr.get("nonexistent"))

    def test_list_all(self):
        self.mgr.create(task="a")
        self.mgr.create(task="b")
        self.assertEqual(len(self.mgr.list_all()), 2)

    def test_next_queued_oldest_first(self):
        s1 = self.mgr.create(task="first")
        time.sleep(0.01)
        s2 = self.mgr.create(task="second")
        nxt = self.mgr.next_queued()
        self.assertEqual(nxt.session_id, s1.session_id)

    def test_has_running(self):
        s = self.mgr.create(task="task")
        self.assertFalse(self.mgr.has_running())
        s.start()
        self.assertTrue(self.mgr.has_running())

    def test_delete(self):
        s = self.mgr.create(task="to delete")
        self.mgr.delete(s.session_id)
        self.assertIsNone(self.mgr.get(s.session_id))

    def test_session_lifecycle(self):
        s = self.mgr.create(task="lifecycle")
        s.start()
        self.assertEqual(s.state, SessionState.RUNNING)
        s.complete("done")
        self.assertEqual(s.state, SessionState.COMPLETED)
        self.assertEqual(s.result, "done")

    def test_session_to_dict(self):
        s = self.mgr.create(task="dict test")
        d = s.to_dict()
        self.assertIn("session_id", d)
        self.assertIn("task", d)
        self.assertIn("state", d)


# ──────────────────────────────────────────────────────────────────────────────
# ToolExecutor tests
# ──────────────────────────────────────────────────────────────────────────────

class TestToolExecutor(unittest.TestCase):

    def setUp(self):
        self.executor = ToolExecutor()

    def test_parse_fenced_json(self):
        text = '```tool_call\n{"tool": "read_file", "args": {"path": "test.txt"}}\n```'
        calls = self.executor.parse(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["tool"], "read_file")
        self.assertEqual(calls[0]["args"]["path"], "test.txt")

    def test_parse_xml_tag(self):
        text = '<tool_call>{"tool": "write_file", "args": {"path": "out.txt", "content": "hi"}}</tool_call>'
        calls = self.executor.parse(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["tool"], "write_file")

    def test_parse_multiple_calls(self):
        text = (
            '```tool_call\n{"tool": "read_file", "args": {"path": "a.txt"}}\n```\n'
            '<tool_call>{"tool": "write_file", "args": {"path": "b.txt"}}</tool_call>'
        )
        calls = self.executor.parse(text)
        self.assertEqual(len(calls), 2)

    def test_has_tool_calls_true(self):
        text = '```tool_call\n{"tool": "read_file", "args": {}}\n```'
        self.assertTrue(self.executor.has_tool_calls(text))

    def test_has_tool_calls_false(self):
        text = "Just a normal response with no tool calls."
        self.assertFalse(self.executor.has_tool_calls(text))

    def test_execute_unknown_tool(self):
        result = self.executor.execute("totally_nonexistent_tool_xyz", {})
        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"].lower())

    def test_parse_empty_text(self):
        calls = self.executor.parse("")
        self.assertEqual(calls, [])


# ──────────────────────────────────────────────────────────────────────────────
# SelfHealingSystem tests
# ──────────────────────────────────────────────────────────────────────────────

class TestSelfHealingSystem(unittest.TestCase):

    def test_classify_api_error(self):
        self.assertEqual(classify_error("rate limit exceeded"), ErrorClass.API_ERROR)
        self.assertEqual(classify_error("API timeout"), ErrorClass.API_ERROR)

    def test_classify_parse_error(self):
        self.assertEqual(classify_error("JSON decode error"), ErrorClass.PARSE_ERROR)

    def test_classify_tool_error(self):
        self.assertEqual(classify_error("Tool not found"), ErrorClass.TOOL_ERROR)

    def test_classify_loop_limit(self):
        self.assertEqual(classify_error("max_loops exceeded"), ErrorClass.LOOP_LIMIT)

    def test_classify_runtime_error(self):
        self.assertEqual(classify_error("Something unexpected"), ErrorClass.RUNTIME_ERROR)

    def test_should_retry_within_limit(self):
        healer = SelfHealingSystem(max_retries=3, retry_delay=0)
        self.assertTrue(healer.should_retry("some error"))

    def test_should_retry_exceeds_limit(self):
        healer = SelfHealingSystem(max_retries=2, retry_delay=0)
        healer.heal("error 1")
        healer.heal("error 2")
        self.assertFalse(healer.should_retry("error 3"))

    def test_should_not_retry_loop_limit(self):
        healer = SelfHealingSystem(max_retries=3, retry_delay=0)
        self.assertFalse(healer.should_retry("max_loops exceeded"))

    def test_heal_returns_strategy_message(self):
        healer = SelfHealingSystem(max_retries=3, retry_delay=0)
        msg = healer.heal("Tool not found")
        self.assertIsInstance(msg, str)
        self.assertGreater(len(msg), 10)

    def test_heal_increments_retry_count(self):
        healer = SelfHealingSystem(max_retries=3, retry_delay=0)
        healer.heal("error 1")
        healer.heal("error 2")
        self.assertEqual(healer.retry_count, 2)

    def test_summary(self):
        healer = SelfHealingSystem(max_retries=3, retry_delay=0)
        healer.heal("test error")
        s = healer.summary()
        self.assertEqual(s["total_retries"], 1)
        self.assertEqual(len(s["attempts"]), 1)

    def test_build_healing_message_all_classes(self):
        for cls in [ErrorClass.TOOL_ERROR, ErrorClass.API_ERROR, ErrorClass.PARSE_ERROR,
                    ErrorClass.RUNTIME_ERROR, ErrorClass.LOOP_LIMIT]:
            msg = build_healing_message(cls, "test error")
            self.assertIsInstance(msg, str)
            self.assertGreater(len(msg), 5)


# ──────────────────────────────────────────────────────────────────────────────
# execute_python tool tests
# ──────────────────────────────────────────────────────────────────────────────

class TestExecutePython(unittest.TestCase):

    def test_simple_print(self):
        result = execute_python('print("hello overlord11")')
        self.assertTrue(result["success"])
        self.assertIn("hello overlord11", result["stdout"])
        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(result["timed_out"])

    def test_error_handling(self):
        result = execute_python("raise ValueError('test error')")
        self.assertFalse(result["success"])
        self.assertIn("ValueError", result["stderr"])
        self.assertNotEqual(result["exit_code"], 0)

    def test_math_computation(self):
        result = execute_python("print(sum(range(100)))")
        self.assertTrue(result["success"])
        self.assertIn("4950", result["stdout"])

    def test_empty_code(self):
        result = execute_python("")
        self.assertFalse(result["success"])
        self.assertIn("No code provided", result["stderr"])

    def test_timeout_cap(self):
        # timeout capped at 120 — just verify the function accepts large values
        result = execute_python('x = 1+1\nprint(x)', timeout=9999)
        self.assertTrue(result["success"])

    def test_invalid_working_dir(self):
        result = execute_python("print(1)", working_dir="/nonexistent/path/xyz")
        self.assertFalse(result["success"])
        self.assertIn("does not exist", result["stderr"])

    def test_stdout_stderr_separation(self):
        code = 'import sys\nprint("stdout")\nprint("stderr", file=sys.stderr)'
        result = execute_python(code)
        self.assertIn("stdout", result["stdout"])
        self.assertIn("stderr", result["stderr"])

    def test_temp_dir_cleaned_up(self):
        """Temp directories created internally must be removed after execution."""
        import glob as glob_mod
        before = set(glob_mod.glob("/tmp/ovr11_exec_*"))
        execute_python('print("temp dir test")')
        after = set(glob_mod.glob("/tmp/ovr11_exec_*"))
        leaked = after - before
        self.assertEqual(leaked, set(), f"Temp dirs were not cleaned up: {leaked}")

    def test_caller_working_dir_not_removed(self):
        """If the caller supplies working_dir, it must NOT be deleted."""
        import tempfile
        tmpdir = tempfile.mkdtemp(prefix="ovr11_caller_")
        try:
            execute_python('print("keep caller dir")', working_dir=tmpdir)
            self.assertTrue(os.path.isdir(tmpdir), "Caller-supplied working_dir was deleted")
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ──────────────────────────────────────────────────────────────────────────────
# Session pause / resume / stop tests
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionPauseResumeStop(unittest.TestCase):
    """Verify that Session state transitions are correctly propagated."""

    def setUp(self):
        self.mgr = SessionManager(log_dir="/tmp/ovr11_test_prs")

    def tearDown(self):
        import shutil
        shutil.rmtree("/tmp/ovr11_test_prs", ignore_errors=True)

    def test_pause_changes_state(self):
        s = self.mgr.create(task="pause test")
        s.start()
        self.assertEqual(s.state, SessionState.RUNNING)
        s.pause()
        self.assertEqual(s.state, SessionState.PAUSED)

    def test_resume_changes_state(self):
        s = self.mgr.create(task="resume test")
        s.start()
        s.pause()
        self.assertEqual(s.state, SessionState.PAUSED)
        s.resume()
        self.assertEqual(s.state, SessionState.RUNNING)

    def test_fail_stops_session(self):
        s = self.mgr.create(task="stop test")
        s.start()
        s.fail("Stopped by user")
        self.assertEqual(s.state, SessionState.FAILED)
        self.assertEqual(s.error, "Stopped by user")

    def test_runner_exits_on_external_stop(self):
        """
        If session.fail() is called externally mid-run (simulating a stop
        action from the API), the runner must detect FAILED on the next loop
        tick and exit without calling the provider again.
        """
        from unittest.mock import MagicMock
        from engine.runner import EngineRunner

        mgr = SessionManager(log_dir="/tmp/ovr11_test_runner_stop")
        try:
            runner = EngineRunner(session_manager=mgr, max_loops=10)
            session = mgr.create(task="external stop test")

            bridge_call_count = [0]

            def mock_call(*args, **kwargs):
                bridge_call_count[0] += 1
                if bridge_call_count[0] == 1:
                    # First call: return a tool-call response so the loop
                    # continues, and externally stop the session.
                    session.fail("Stopped by user")
                    # Return a fenced tool call — but since state is FAILED
                    # the loop will break at the top of the next iteration.
                    return ('```tool_call\n{"tool": "nonexistent", "args": {}}\n```', "mock")
                # Should never reach a second call
                raise AssertionError("Bridge called more than once after external stop")

            runner._bridge = MagicMock()
            runner._bridge.call.side_effect = mock_call

            result = runner.run_session(session)

            # The runner must stop; result state is FAILED because session.fail()
            # was called externally and the runner respects it.
            self.assertEqual(result["state"], SessionState.FAILED)
            # Bridge must have been called exactly once
            self.assertEqual(bridge_call_count[0], 1)
        finally:
            import shutil
            shutil.rmtree("/tmp/ovr11_test_runner_stop", ignore_errors=True)



if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
