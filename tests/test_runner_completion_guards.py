import unittest
import zipfile
from pathlib import Path

from engine.runner import EngineRunner
from engine.tool_executor import ToolCall


class RunnerCompletionGuardTests(unittest.TestCase):
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
            "```json\n{\"tool\":\"dummy_tool\",\"params\":{\"x\":1}}\n```",
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
            "<tool_code>\nprint(search_file_content(path='.', pattern='TODO'))\n</tool_code>",
            "<tool_code>\nprint(search_file_content(path='.', pattern='TODO'))\n</tool_code>",
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
            "```json\n{\"tool\":\"dummy_tool\",\"params\":{\"x\":1}}\n```",
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
            "```json\n{\"tool\":\"list_directory\",\"params\":{\"path\":\".\"}}\n```",
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

    def test_max_loops_exhaustion_sets_explicit_error_reason(self):
        runner = self._runner()
        runner._config["orchestration"]["max_loops"] = 1
        runner._loop_governor.max_parent_loops = 1
        runner._bridge.call_provider_streaming = lambda **kwargs: "I will keep planning without tool calls."  # type: ignore[method-assign]
        result = runner.run("Build a complex module with tests and docs.")
        self.assertEqual(result.get("status"), "failed")
        self.assertTrue(result.get("error"))

    def test_non_trivial_completion_allows_incidental_tools_path_mentions(self):
        runner = self._runner()
        responses = [
            "```json\n{\"tool\":\"dummy_tool\",\"params\":{\"x\":1}}\n```",
            "Completed successfully. Updated references in tools/python/publisher_tool.py and produced the final report.",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "Completed successfully."

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        runner._parallel_executor.execute_all = lambda *args, **kwargs: [  # type: ignore[method-assign]
            (
                ToolCall(tool_name="dummy_tool", params={"x": 1}, raw=""),
                {"status": "success", "result": {"changed_files": ["a.py"]}, "tool": "dummy_tool", "duration_ms": 1.0},
            )
        ]
        result = runner.run("Run checks and produce a final report.")
        self.assertEqual(result.get("status"), "complete")
        self.assertEqual(result.get("completion_mode"), "tool_driven")

    def test_non_trivial_aux_only_progress_does_not_complete(self):
        runner = self._runner()
        responses = [
            "```json\n{\"tool\":\"task_manager\",\"params\":{\"action\":\"add_task\",\"title\":\"Track only\"}}\n```",
            "Completed. Here is a long narrative summary that still has no real artifact work.",
            "Completed. Still no real artifact work was performed.",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "No additional actions."

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        runner._parallel_executor.execute_all = lambda *args, **kwargs: [  # type: ignore[method-assign]
            (
                ToolCall(tool_name="task_manager", params={"action": "add_task"}, raw=""),
                {"status": "success", "result": {"status": "added", "task_id": "T-001"}, "tool": "task_manager", "duration_ms": 1.0},
            )
        ]
        result = runner.run("Create multiple artifacts and package them.")
        self.assertEqual(result.get("status"), "failed")
        self.assertEqual(result.get("completion_mode"), "no_effect_fail")

    def test_non_trivial_unexecuted_tool_intent_does_not_complete(self):
        runner = self._runner()
        responses = [
            "```json\n{\"tool\":\"dummy_tool\",\"params\":{\"x\":1}}\n```",
            "```json\n{\"tool\":\"execute_python\",\"params\":{\"code\":\"print('next step')\"}}\n```",
            "```json\n{\"tool\":\"execute_python\",\"params\":{\"code\":\"print('still next step')\"}}\n```",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "```json\n{\"tool\":\"execute_python\",\"params\":{\"code\":\"print('loop')\"}}\n```"

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        runner._parallel_executor.execute_all = lambda *args, **kwargs: [  # type: ignore[method-assign]
            (
                ToolCall(tool_name="dummy_tool", params={"x": 1}, raw=""),
                {"status": "success", "result": {"changed_files": ["a.py"]}, "tool": "dummy_tool", "duration_ms": 1.0},
            )
        ]
        result = runner.run("Build artifacts and package output.")
        self.assertEqual(result.get("status"), "failed")
        self.assertEqual(result.get("completion_mode"), "no_effect_fail")

    def test_auxiliary_tool_failures_become_warnings_after_core_progress(self):
        runner = self._runner()
        responses = [
            (
                "```json\n{\"tool\":\"dummy_tool\",\"params\":{\"x\":1}}\n```\n"
                "```json\n{\"tool\":\"session_manager\",\"params\":{\"action\":\"close\",\"summary\":\"done\"}}\n```"
            ),
            "Completed successfully. Final output has been produced.",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "Completed successfully."

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        runner._parallel_executor.execute_all = lambda *args, **kwargs: [  # type: ignore[method-assign]
            (
                ToolCall(tool_name="dummy_tool", params={"x": 1}, raw=""),
                {"status": "success", "result": {"changed_files": ["a.py"]}, "tool": "dummy_tool", "duration_ms": 1.0},
            ),
            (
                ToolCall(tool_name="session_manager", params={"action": "close"}, raw=""),
                {"status": "error", "result": "simulated close failure", "tool": "session_manager", "duration_ms": 1.0, "error": "simulated close failure"},
            ),
        ]
        result = runner.run("Perform non-trivial work and provide final output.")
        self.assertEqual(result.get("status"), "complete")
        warnings = result.get("bookkeeping_warnings") or []
        self.assertGreaterEqual(len(warnings), 1)

    def test_packaging_claim_with_empty_zip_fails_completion_contract(self):
        runner = self._runner()
        empty_zip = Path(__file__).resolve().parent / "_empty_test_bundle.zip"
        if empty_zip.exists():
            empty_zip.unlink()
        with zipfile.ZipFile(empty_zip, "w"):
            pass
        responses = [
            "```json\n{\"tool\":\"zip_tool\",\"params\":{\"action\":\"create\",\"output\":\"output/bundle.zip\",\"paths\":[\"output/artifacts\"]}}\n```",
            "Completed successfully. I created the final zip archive package for delivery.",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "Completed successfully."

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        runner._parallel_executor.execute_all = lambda *args, **kwargs: [  # type: ignore[method-assign]
            (
                ToolCall(tool_name="zip_tool", params={"action": "create"}, raw=""),
                {
                    "status": "success",
                    "result": {"status": "success", "file": str(empty_zip), "file_count": 0},
                    "tool": "zip_tool",
                    "duration_ms": 1.0,
                },
            ),
        ]
        result = runner.run("Create a zip package and confirm it is ready.")
        self.assertEqual(result.get("status"), "failed")
        self.assertEqual(result.get("error"), "completion_contract_violation")
        failed = result.get("failed_checks") or []
        self.assertTrue(any(item.get("id") == "zip_non_empty" for item in failed))
        if empty_zip.exists():
            empty_zip.unlink()

    def test_repeated_nonconvergent_tool_failure_stops_early(self):
        runner = self._runner()
        runner._heal_repeat_suppress_after = 1
        runner._heal_repeat_hard_stop_after = 2
        responses = [
            "```json\n{\"tool\":\"dummy_tool\",\"params\":{\"x\":1}}\n```",
            "```json\n{\"tool\":\"dummy_tool\",\"params\":{\"x\":1}}\n```",
            "```json\n{\"tool\":\"dummy_tool\",\"params\":{\"x\":1}}\n```",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "```json\n{\"tool\":\"dummy_tool\",\"params\":{\"x\":1}}\n```"

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        runner._parallel_executor.execute_all = lambda *args, **kwargs: [  # type: ignore[method-assign]
            (
                ToolCall(tool_name="dummy_tool", params={"x": 1}, raw=""),
                {"status": "error", "result": "simulated deterministic failure", "tool": "dummy_tool", "duration_ms": 1.0, "error": "simulated deterministic failure"},
            ),
        ]
        result = runner.run("Run a non-trivial tool flow.")
        self.assertEqual(result.get("status"), "failed")
        self.assertEqual(result.get("error"), "repeated_nonconvergent_tool_failure")

    def test_packaging_check_unwraps_nested_cached_zip_payload(self):
        runner = self._runner()
        zip_path = Path(__file__).resolve().parent / "_nested_zip_bundle.zip"
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("a.txt", "ok")
        responses = [
            "```json\n{\"tool\":\"zip_tool\",\"params\":{\"action\":\"list\",\"file\":\"output/release-kit.zip\"}}\n```",
            "Completed successfully. I created the final zip archive package for delivery.",
        ]

        def fake_call(**kwargs):
            return responses.pop(0) if responses else "Completed successfully."

        runner._bridge.call_provider_streaming = fake_call  # type: ignore[method-assign]
        runner._parallel_executor.execute_all = lambda *args, **kwargs: [  # type: ignore[method-assign]
            (
                ToolCall(tool_name="zip_tool", params={"action": "list"}, raw=""),
                {
                    "status": "success",
                    "result": {
                        "status": "success",
                        "result": {
                            "status": "success",
                            "action": "list",
                            "file": str(zip_path),
                            "file_count": 1,
                        },
                        "tool": "zip_tool",
                        "duration_ms": 1.0,
                        "cached": True,
                    },
                    "tool": "zip_tool",
                    "duration_ms": 0.0,
                    "cached": True,
                },
            ),
        ]
        result = runner.run("Create a zip package and confirm it is ready.")
        self.assertEqual(result.get("status"), "complete")
        if zip_path.exists():
            zip_path.unlink()


if __name__ == "__main__":
    unittest.main()
