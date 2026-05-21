import tempfile
import unittest
from pathlib import Path

from tool_gateway.executor import ToolGateway
from tool_gateway.registry import ToolRegistry
from tool_gateway.tools import WriteFileTool


class WriteFileToolTests(unittest.TestCase):
    def setUp(self):
        reg = ToolRegistry()
        reg.register_tool(WriteFileTool())
        self.gw = ToolGateway(reg)

    def test_write_file_success_in_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            import os

            old = os.environ.get("OVERLORD11_TASK_DIR")
            os.environ["OVERLORD11_TASK_DIR"] = tmp
            try:
                res = self.gw.execute_tool_call(
                    {"tool_name": "write_file", "arguments": {"path": "answer.md", "content": "hello"}}
                )
                self.assertTrue(res["ok"])
                p = Path(tmp) / "answer.md"
                self.assertTrue(p.exists())
                self.assertEqual(p.read_text(encoding="utf-8"), "hello")
            finally:
                if old is None:
                    os.environ.pop("OVERLORD11_TASK_DIR", None)
                else:
                    os.environ["OVERLORD11_TASK_DIR"] = old

    def test_write_file_outside_workspace_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            import os

            old = os.environ.get("OVERLORD11_TASK_DIR")
            os.environ["OVERLORD11_TASK_DIR"] = tmp
            try:
                outside = str((Path(tmp).parent / "outside.md").resolve())
                res = self.gw.execute_tool_call(
                    {"tool_name": "write_file", "arguments": {"path": outside, "content": "hello"}}
                )
                self.assertFalse(res["ok"])
                self.assertEqual(res["errors"][0]["code"], "EXECUTION_ERROR")
            finally:
                if old is None:
                    os.environ.pop("OVERLORD11_TASK_DIR", None)
                else:
                    os.environ["OVERLORD11_TASK_DIR"] = old


if __name__ == "__main__":
    unittest.main()

