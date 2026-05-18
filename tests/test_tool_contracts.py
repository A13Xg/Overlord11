import json
import unittest
from pathlib import Path

from pydantic import BaseModel

from engine.tool_executor import ToolExecutor


class ToolContractTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self.config = json.loads((self.root / "config.json").read_text(encoding="utf-8"))

    def test_tool_contracts_exist_for_all_configured_tools(self):
        ex = ToolExecutor(tools_dir=(self.root / "tools" / "python"), config=self.config)
        configured = set((self.config.get("tools") or {}).keys())
        resolved = set(ex._tool_contracts.keys())  # noqa: SLF001
        self.assertEqual(configured, resolved)

    def test_tool_contracts_use_pydantic_models_and_python_only_mode(self):
        ex = ToolExecutor(tools_dir=(self.root / "tools" / "python"), config=self.config)
        self.assertEqual(ex._execution_mode, "python_only")  # noqa: SLF001
        self.assertFalse(hasattr(ex, "_call_subprocess"))
        for tool_name, contract in ex._tool_contracts.items():  # noqa: SLF001
            self.assertTrue(issubclass(contract.params_model, BaseModel), msg=tool_name)
            self.assertTrue(callable(contract.invoke), msg=tool_name)


if __name__ == "__main__":
    unittest.main()
