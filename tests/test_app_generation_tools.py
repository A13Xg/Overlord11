import tempfile
import unittest
from pathlib import Path

from tool_gateway.executor import ToolGateway
from tool_gateway.registry import ToolRegistry
from tool_gateway.tools import HtmlReportGeneratorTool, LauncherGeneratorTool, ScaffoldGeneratorTool


class AppGenerationToolsTests(unittest.TestCase):
    def setUp(self):
        reg = ToolRegistry()
        reg.register_tool(ScaffoldGeneratorTool())
        reg.register_tool(LauncherGeneratorTool())
        reg.register_tool(HtmlReportGeneratorTool())
        self.gw = ToolGateway(reg)

    def test_scaffold_generator_creates_output_app_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            import os

            old_task = os.environ.get("OVERLORD11_TASK_DIR")
            os.environ["OVERLORD11_TASK_DIR"] = tmp
            try:
                res = self.gw.execute_tool_call({
                    "tool_name": "scaffold_generator",
                    "arguments": {
                        "output_dir": "output/app",
                        "app_name": "crypto-dashboard",
                        "app_type": "webapp",
                        "language": "python",
                    },
                })
                self.assertTrue(res["ok"])
                app_dir = Path(tmp) / "output" / "app"
                self.assertTrue((app_dir / "README.md").exists())
                self.assertTrue((app_dir / "launcher").exists())
                self.assertTrue((app_dir / "app.py").exists())
            finally:
                if old_task is None:
                    os.environ.pop("OVERLORD11_TASK_DIR", None)
                else:
                    os.environ["OVERLORD11_TASK_DIR"] = old_task

    def test_html_report_generator_defaults_to_output_report_inside_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            import os

            old_task = os.environ.get("OVERLORD11_TASK_DIR")
            os.environ["OVERLORD11_TASK_DIR"] = tmp
            try:
                res = self.gw.execute_tool_call({
                    "tool_name": "html_report_generator",
                    "arguments": {
                        "title": "Diagnostics",
                        "content": "## Summary\nAll systems nominal.",
                        "theme": "dark",
                    },
                })
                self.assertTrue(res["ok"])
                report = Path(tmp) / "output" / "report.html"
                self.assertTrue(report.exists())
                self.assertEqual(res["data"]["output_path"], "output/report.html")
            finally:
                if old_task is None:
                    os.environ.pop("OVERLORD11_TASK_DIR", None)
                else:
                    os.environ["OVERLORD11_TASK_DIR"] = old_task

    def test_launcher_generator_creates_launchers_with_kill_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            import os

            old_task = os.environ.get("OVERLORD11_TASK_DIR")
            os.environ["OVERLORD11_TASK_DIR"] = tmp
            try:
                project_dir = Path(tmp) / "output" / "app"
                project_dir.mkdir(parents=True, exist_ok=True)

                res = self.gw.execute_tool_call({
                    "tool_name": "launcher_generator",
                    "arguments": {
                        "project_dir": "output/app",
                        "app_command": "python3 app.py --port {port}",
                        "port": 3210,
                    },
                })
                self.assertTrue(res["ok"])

                sh = project_dir / "launcher" / "launch.sh"
                ps1 = project_dir / "launcher" / "launch.ps1"
                self.assertTrue(sh.exists())
                self.assertTrue(ps1.exists())

                sh_text = sh.read_text(encoding="utf-8")
                ps_text = ps1.read_text(encoding="utf-8")
                self.assertIn("-kill", sh_text)
                self.assertIn("--kill", sh_text)
                self.assertIn("Stop-PortProcess", ps_text)
                self.assertIn("requirements.txt", sh_text)
                self.assertIn("package.json", sh_text)
            finally:
                if old_task is None:
                    os.environ.pop("OVERLORD11_TASK_DIR", None)
                else:
                    os.environ["OVERLORD11_TASK_DIR"] = old_task


if __name__ == "__main__":
    unittest.main()
