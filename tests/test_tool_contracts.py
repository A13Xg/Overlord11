import ast
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path


class ToolContractTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self.config = json.loads((self.root / "config.json").read_text(encoding="utf-8"))
        self.tools = self.config.get("tools", {})

    def _help_flags(self, impl_path: Path) -> set[str]:
        proc = subprocess.run(
            [sys.executable, str(impl_path), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        text = (proc.stdout or "") + (proc.stderr or "")
        flags = set()
        for m in re.finditer(r"--([a-zA-Z0-9_-]+)", text):
            flags.add(m.group(1).replace("-", "_"))
        return flags

    def test_tool_definitions_match_implementations(self):
        findings: list[str] = []

        for tool_name, info in sorted(self.tools.items()):
            def_path = self.root / info["def"]
            impl_path = self.root / info["impl"]

            if not def_path.exists():
                findings.append(f"{tool_name}: missing def file {def_path}")
                continue
            if not impl_path.exists():
                findings.append(f"{tool_name}: missing impl file {impl_path}")
                continue

            schema = json.loads(def_path.read_text(encoding="utf-8"))
            schema_name = schema.get("name")
            if schema_name != tool_name:
                findings.append(f"{tool_name}: schema name mismatch ({schema_name})")

            params = (schema.get("parameters") or {})
            props = params.get("properties") or {}
            required = params.get("required") or []

            for req in required:
                if req not in props:
                    findings.append(f"{tool_name}: required key '{req}' missing from properties")

            tree = ast.parse(impl_path.read_text(encoding="utf-8"))
            mains = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"]
            if not mains:
                findings.append(f"{tool_name}: main() missing in implementation")
                continue

            main_fn = mains[0]
            has_kwargs = main_fn.args.kwarg is not None
            main_args = {a.arg for a in main_fn.args.args}
            flags = self._help_flags(impl_path)
            supported = set(main_args) | flags
            if has_kwargs:
                # kwargs path can accept any schema key; this still validates CLI shape
                supported |= set(props.keys())

            missing = sorted(k for k in props.keys() if k not in supported)
            if missing:
                findings.append(f"{tool_name}: unsupported schema params {missing}")

        self.assertEqual(findings, [], "\n" + "\n".join(findings))


if __name__ == "__main__":
    unittest.main()

