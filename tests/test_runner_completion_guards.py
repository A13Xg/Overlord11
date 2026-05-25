import unittest
import shutil
from pathlib import Path

from engine.runner import EngineRunner
from engine.tool_executor import ToolCall


class RunnerCompletionGuardTests(unittest.TestCase):
    def setUp(self):
        self._workspace_root = Path(__file__).resolve().parent.parent / "workspace"
        self._before = {p.name for p in self._workspace_root.iterdir() if p.is_dir()} if self._workspace_root.exists() else set()

    def tearDown(self):
        if not self._workspace_root.exists():
            return
        protected = {"archive", "users"}
        after = {p.name for p in self._workspace_root.iterdir() if p.is_dir()}
        created = [name for name in (after - self._before) if name not in protected]
        for name in created:
            target = self._workspace_root / name
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)

    def _runner(self):
        runner = EngineRunner(verbose=False)
        runner._config.setdefault("orchestration", {})
        runner._config["orchestration"]["max_loops"] = 3
        runner._config["orchestration"]["no_tool_retries_for_nontrivial"] = 1
        return runner

    def test_empty_response_fails(self):
        runner = self._runner()
        runner._bridge.call_provider_streaming = lambda **kwargs: ""  # type: ignore[method-assign]
        result = runner.run("Create a Python package with tests.")
        self.assertEqual(result.get("status"), "failed")
        self.assertEqual(result.get("completion_mode"), "empty_response_fail")
        self.assertEqual(result.get("error"), "empty_model_response")

    def test_non_trivial_prose_only_fails_after_retry(self):
        runner = self._runner()
        responses = [
            "I will now plan the implementation in prose only.",
            "Still prose-only plan, no tool calls.",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "No tools here either."

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        result = runner.run("Build and test a new module with README and CLI.")
        self.assertEqual(result.get("status"), "failed")
        self.assertEqual(result.get("completion_mode"), "no_effect_fail")
        self.assertEqual(result.get("error"), "no_effect_completion")

    def test_trivial_direct_answer_can_complete_without_tools(self):
        runner = self._runner()
        runner._bridge.call_provider_streaming = lambda **kwargs: "2 + 2 equals 4."  # type: ignore[method-assign]
        result = runner.run("What is 2+2?")
        self.assertEqual(result.get("status"), "complete")
        self.assertEqual(result.get("completion_mode"), "direct_answer")
        self.assertEqual(int(result.get("tool_call_count", -1)), 0)

    def test_non_trivial_can_complete_after_effectful_tool_work(self):
        runner = self._runner()
        responses = [
            "```json\n{\"tool_name\":\"dummy_tool\",\"arguments\":{\"x\":1}}\n```",
            "Completed. Implemented the module and tests successfully.",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "Completed."

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        runner._parallel_executor.execute_all = lambda *args, **kwargs: [  # type: ignore[method-assign]
            (
                ToolCall(tool_name="dummy_tool", params={"x": 1}, raw=""),
                {"status": "success", "result": {"changed_files": ["a.py"]}, "tool": "dummy_tool", "duration_ms": 1.0},
            )
        ]
        result = runner.run("Build a module and add tests.")
        self.assertEqual(result.get("status"), "complete")
        self.assertEqual(result.get("completion_mode"), "tool_driven")
        self.assertGreaterEqual(int(result.get("tool_call_count", 0)), 1)

    def test_invalid_pseudo_tool_format_fails_with_specific_reason(self):
        runner = self._runner()
        responses = [
            "<tool_call>{\"tool\":\"dummy_tool\",\"params\":{\"x\":1}}</tool_call>",
            "<tool_call>{\"tool\":\"dummy_tool\",\"params\":{\"x\":1}}</tool_call>",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "still invalid"

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        result = runner.run("Scan and generate report with tool calls.")
        self.assertEqual(result.get("status"), "failed")
        self.assertEqual(result.get("error"), "invalid_tool_call_format")

    def test_non_trivial_delegation_only_message_does_not_complete(self):
        runner = self._runner()
        responses = [
            "```json\n{\"tool_name\":\"dummy_tool\",\"arguments\":{\"x\":1}}\n```",
            "Now, I am delegating the initial code inspection to OVR_COD_03.\n<execute_task agent=\"OVR_COD_03\">read_file(path=\"engine/runner.py\")</execute_task>",
            "I am delegating the rest of this task to OVR_COD_03.",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "delegating"

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        runner._parallel_executor.execute_all = lambda *args, **kwargs: [  # type: ignore[method-assign]
            (
                ToolCall(tool_name="dummy_tool", params={"x": 1}, raw=""),
                {"status": "success", "result": {"changed_files": ["a.py"]}, "tool": "dummy_tool", "duration_ms": 1.0},
            )
        ]
        result = runner.run("Inspect code and implement a minimal fix.")
        self.assertEqual(result.get("status"), "failed")
        self.assertEqual(result.get("completion_mode"), "no_effect_fail")

    def test_scope_mismatch_claim_after_list_directory_does_not_complete(self):
        runner = self._runner()
        responses = [
            "```json\n{\"tool_name\":\"list_directory\",\"arguments\":{\"path\":\".\"}}\n```",
            "The directory listing confirms agents/, tools/, docs/, and config.json are present.",
            "Same confirmation as above.",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "same claim"

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        runner._parallel_executor.execute_all = lambda *args, **kwargs: [  # type: ignore[method-assign]
            (
                ToolCall(tool_name="list_directory", params={"path": "."}, raw=""),
                {
                    "status": "success",
                    "result": {
                        "status": "success",
                        "path": r"C:\\repo\\scripts",
                        "entries": [{"name": "run_webui.py"}, {"name": "scratch"}],
                    },
                    "tool": "list_directory",
                    "duration_ms": 1.0,
                },
            )
        ]
        result = runner.run("Analyze repository structure and generate a verification report with metadata.")
        self.assertEqual(result.get("status"), "failed")

    def test_replay_payload_with_shell_auto_succeeds_first_try(self):
        runner = self._runner()
        responses = [
            "```json\n{\"tool_name\":\"run_command\",\"arguments\":{\"command\":\"python --version\",\"timeout_seconds\":30,\"shell\":\"auto\"}}\n```",
            "Completed. shell_used: powershell, exit_code: 0",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "Completed."

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        result = runner.run("Run python version and report shell and exit code.")
        self.assertEqual(result.get("status"), "complete")
        self.assertEqual(result.get("completion_mode"), "tool_driven")

    def test_duplicate_shell_alias_calls_are_deduped(self):
        runner = self._runner()
        responses = [
            "```json\n[\n"
            "{\"tool_name\":\"run_command\",\"arguments\":{\"command\":\"python --version\",\"timeout_seconds\":30,\"shell\":\"auto\"}},\n"
            "{\"tool_name\":\"run_command\",\"arguments\":{\"command\":\"python --version\",\"timeout_seconds\":30,\"shell\":\"auto\"}}\n"
            "]\n```",
            "Completed.",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "Completed."

        seen_counts = {"calls": 0}

        def fake_execute_all(tool_calls, **kwargs):
            seen_counts["calls"] = len(tool_calls)
            return [
                (
                    ToolCall(tool_name="run_command", params={"command": "python --version"}, raw=""),
                    {"status": "success", "result": {"exit_code": 0}, "tool": "run_command", "duration_ms": 1.0},
                )
            ]

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        runner._parallel_executor.execute_all = fake_execute_all  # type: ignore[method-assign]
        result = runner.run("Run python version and report.")
        self.assertEqual(result.get("status"), "complete")
        self.assertEqual(seen_counts["calls"], 1)

    def test_failed_write_file_then_claim_saved_does_not_complete(self):
        runner = self._runner()
        responses = [
            "```json\n{\"tool_name\":\"run_command\",\"arguments\":{\"command\":\"python --version\",\"timeout_seconds\":30}}\n```",
            "```json\n{\"tool_name\":\"write_file\",\"arguments\":{\"path\":\"answer.md\",\"content\":\"report\"}}\n```",
            "The diagnostics report was saved to answer.md.",
            "Still saved to answer.md.",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "saved"

        call_idx = {"i": 0}

        def fake_execute_all(tool_calls, **kwargs):
            call_idx["i"] += 1
            if call_idx["i"] == 1:
                return [
                    (
                        ToolCall(tool_name="run_command", params={"command": "python --version"}, raw=""),
                        {"status": "success", "result": {"exit_code": 0}, "tool": "run_command", "duration_ms": 1.0},
                    )
                ]
            return [
                (
                    ToolCall(tool_name="write_file", params={"path": "answer.md"}, raw=""),
                    {
                        "status": "error",
                        "result": {
                            "ok": False,
                            "errors": [{"code": "UNKNOWN_TOOL", "message": "Unknown tool: write_file", "details": {}}],
                        },
                        "tool": "write_file",
                        "duration_ms": 1.0,
                    },
                )
            ]

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        runner._parallel_executor.execute_all = fake_execute_all  # type: ignore[method-assign]
        result = runner.run("Run diagnostics and save answer.md.")
        self.assertEqual(result.get("status"), "failed")

    def test_command_derived_claim_without_run_command_does_not_complete(self):
        runner = self._runner()
        responses = [
            "```json\n{\"tool_name\":\"write_file\",\"arguments\":{\"path\":\"answer.md\",\"content\":\"report\"}}\n```",
            "Diagnostics report complete. Shell used: powershell. Exit code: 0. OS release: 11. Python version: 3.14.4.",
            "Diagnostics report complete. Shell used: powershell. Exit code: 0. OS release: 11. Python version: 3.14.4.",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "same claim"

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        runner._parallel_executor.execute_all = lambda *args, **kwargs: [  # type: ignore[method-assign]
            (
                ToolCall(tool_name="write_file", params={"path": "answer.md", "content": "report"}, raw=""),
                {"status": "success", "result": {"path": "answer.md"}, "tool": "write_file", "duration_ms": 1.0},
            )
        ]
        result = runner.run("Create diagnostics report from command output and save it.")
        self.assertEqual(result.get("status"), "failed")

    def test_self_healing_disabled_fails_fast_on_tool_error(self):
        runner = self._runner()
        runner._config.setdefault("orchestration", {})
        runner._config["orchestration"]["self_healing"] = {
            "enabled": False,
            "fail_fast_on_tool_error_when_disabled": True,
            "fail_fast_on_any_error_when_disabled": True,
        }
        # Keep runtime flags in sync for this test instance.
        runner._self_healing_enabled = False
        runner._fail_fast_tool_error_when_disabled = True
        runner._fail_fast_any_error_when_disabled = True

        responses = [
            "```json\n{\"tool_name\":\"write_file\",\"arguments\":{\"path\":\"answer.md\",\"content\":\"x\"}}\n```",
            "I should never be reached because fail-fast is enabled.",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "unexpected"

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        runner._parallel_executor.execute_all = lambda *args, **kwargs: [  # type: ignore[method-assign]
            (
                ToolCall(tool_name="write_file", params={"path": "answer.md", "content": "x"}, raw=""),
                {
                    "status": "error",
                    "result": {
                        "ok": False,
                        "errors": [{"code": "VALIDATION_ERROR", "message": "path invalid", "details": {}}],
                    },
                    "tool": "write_file",
                    "duration_ms": 1.0,
                },
            )
        ]

        result = runner.run("Write answer.md with content")
        self.assertEqual(result.get("status"), "failed")
        self.assertEqual(result.get("completion_mode"), "no_effect_fail")
        self.assertIn("tool_failure_fail_fast", result.get("error") or "")

    def test_command_derived_claim_with_run_command_can_complete(self):
        runner = self._runner()
        responses = [
            "```json\n{\"tool_name\":\"run_command\",\"arguments\":{\"command\":\"python --version\",\"timeout_seconds\":30}}\n```",
            "```json\n{\"tool_name\":\"write_file\",\"arguments\":{\"path\":\"answer.md\",\"content\":\"report\"}}\n```",
            "Diagnostics report complete. Shell used: powershell. Exit code: 0. OS release: 11. Python version: 3.14.4.",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "complete"

        call_idx = {"i": 0}

        def fake_execute_all(tool_calls, **kwargs):
            call_idx["i"] += 1
            if call_idx["i"] == 1:
                return [
                    (
                        ToolCall(tool_name="run_command", params={"command": "python --version"}, raw=""),
                        {"status": "success", "result": {"exit_code": 0}, "tool": "run_command", "duration_ms": 1.0},
                    )
                ]
            return [
                (
                    ToolCall(tool_name="write_file", params={"path": "answer.md", "content": "report"}, raw=""),
                    {"status": "success", "result": {"path": "answer.md"}, "tool": "write_file", "duration_ms": 1.0},
                )
            ]

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        runner._parallel_executor.execute_all = fake_execute_all  # type: ignore[method-assign]
        result = runner.run("Create diagnostics report from command output and save it.")
        self.assertEqual(result.get("status"), "complete")

    def test_required_output_ext_prompts_until_file_exists(self):
        runner = self._runner()
        responses = [
            "```json\n{\"tool_name\":\"dummy_tool\",\"arguments\":{\"x\":1}}\n```",
            "Completed without writing the HTML.",
            "```json\n{\"tool_name\":\"dummy_tool\",\"arguments\":{\"write_html\":true}}\n```",
            "Completed with the HTML file saved.",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "Completed."

        call_idx = {"i": 0}

        def fake_execute_all(tool_calls, **kwargs):
            call_idx["i"] += 1
            if call_idx["i"] == 2:
                task_dir = Path(runner._tool_executor._runtime_context["OVERLORD11_TASK_DIR"])
                out = task_dir / "output" / "report.html"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text("<html><body>done</body></html>", encoding="utf-8")
            return [
                (
                    ToolCall(tool_name="dummy_tool", params={}, raw=""),
                    {"status": "success", "result": {"changed_files": ["output/report.html"]}, "tool": "dummy_tool", "duration_ms": 1.0},
                )
            ]

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        runner._parallel_executor.execute_all = fake_execute_all  # type: ignore[method-assign]
        result = runner.run("Create an HTML report.", required_output_ext=".html")
        self.assertEqual(result.get("status"), "complete")
        self.assertGreaterEqual(call_idx["i"], 2)


if __name__ == "__main__":
    unittest.main()
