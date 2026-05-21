import tempfile
import unittest
from pathlib import Path

from engine.tool_executor import ToolCall, ToolExecutor


class ToolExecutorRuntimeContextTests(unittest.TestCase):
    def test_write_file_uses_task_workspace_root_by_default(self):
        ex = ToolExecutor()
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp).resolve()
            ex.set_runtime_context(session_id="sess-1", task_dir=task_dir)
            result = ex.execute(
                ToolCall(
                    tool_name="write_file",
                    params={"path": "answer.md", "content": "hello workspace"},
                )
            )
            self.assertEqual(result.get("status"), "success")
            expected = task_dir / "answer.md"
            self.assertTrue(expected.exists(), f"Expected file at {expected}")
            self.assertEqual(expected.read_text(encoding="utf-8"), "hello workspace")


if __name__ == "__main__":
    unittest.main()

