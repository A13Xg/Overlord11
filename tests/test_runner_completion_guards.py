import unittest

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


if __name__ == "__main__":
    unittest.main()
