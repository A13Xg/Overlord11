import json
import unittest
from pathlib import Path

from engine.tool_executor import ToolCall, ToolExecutor


class ToolExecutorDelegationGraphTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parent.parent
        cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
        self.ex = ToolExecutor(tools_dir=(root / "tools" / "python"), config=cfg)

    def test_graph_respects_dependencies(self):
        order = []

        def handler(*, tool_name, params):
            order.append(str(params.get("step_id")))
            return {"status": "success", "outputs": params.get("step_id")}

        self.ex.set_delegation_handler(handler)
        calls = [
            ToolCall("delegate_task", {"agent_id": "OVR_COD_03", "task": "A", "inputs": {}, "expected_outputs": {}, "step_id": "a"}),
            ToolCall("delegate_task", {"agent_id": "OVR_COD_03", "task": "B", "inputs": {}, "expected_outputs": {}, "step_id": "b", "depends_on": ["a"]}),
        ]
        results = self.ex.execute_delegation_graph(calls, loop=1)
        self.assertEqual([r[0].params.get("step_id") for r in results], ["a", "b"])
        self.assertEqual(order, ["a", "b"])

    def test_graph_reports_unknown_dependency(self):
        self.ex.set_delegation_handler(lambda **_: {"status": "success"})
        calls = [
            ToolCall("delegate_task", {"agent_id": "OVR_COD_03", "task": "A", "inputs": {}, "expected_outputs": {}, "step_id": "a", "depends_on": ["missing"]}),
        ]
        results = self.ex.execute_delegation_graph(calls, loop=1)
        self.assertEqual(results[0][1].get("status"), "error")


if __name__ == "__main__":
    unittest.main()
