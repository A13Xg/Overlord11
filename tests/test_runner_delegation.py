import unittest

from engine.runner import EngineRunner
from engine.tool_executor import ToolCall


class RunnerDelegationTests(unittest.TestCase):
    def setUp(self):
        self.runner = EngineRunner(verbose=False)

    def test_partition_delegation_calls(self):
        calls = [
            ToolCall(tool_name="read_file", params={"path": "a.txt"}),
            ToolCall(tool_name="delegate_task", params={"agent_id": "OVR_PUB_07", "task": "t", "inputs": {}, "expected_outputs": {}}),
            ToolCall(tool_name="run_subagent", params={"agent_id": "OVR_COD_03", "task": "x", "inputs": {}, "expected_outputs": {}}),
        ]
        delegation, normal = self.runner._partition_delegation_calls(calls)
        self.assertEqual(len(delegation), 2)
        self.assertEqual(len(normal), 1)
        self.assertEqual(normal[0].tool_name, "read_file")

    def test_validate_delegation_call_rejects_unknown_agent(self):
        ok, err = self.runner._validate_delegation_call(
            {
                "agent_id": "OVR_FAKE_99",
                "task": "Do work",
                "inputs": {},
                "expected_outputs": {},
                "timeout_s": 10,
            }
        )
        self.assertFalse(ok)
        self.assertIn("delegation_unknown_agent", err)

    def test_validate_delegation_call_accepts_known_agent(self):
        ok, err = self.runner._validate_delegation_call(
            {
                "agent_id": "OVR_PUB_07",
                "task": "Create report",
                "inputs": {"x": 1},
                "expected_outputs": {"file": "answer.html"},
                "allow_parallel": True,
                "timeout_s": 120,
            }
        )
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_delegation_independence_detects_overlap(self):
        self.assertFalse(
            self.runner._delegations_are_independent(
                [
                    {"expected_outputs": {"answer": "a.html"}},
                    {"expected_outputs": {"answer": "b.html"}},
                ]
            )
        )

    def test_uiux_context_is_added_for_publisher_html(self):
        payload = self.runner._build_uiux_context_for_subagent(
            agent_id="OVR_PUB_07",
            task="Generate stylized HTML report",
        )
        self.assertTrue(payload)


if __name__ == "__main__":
    unittest.main()
