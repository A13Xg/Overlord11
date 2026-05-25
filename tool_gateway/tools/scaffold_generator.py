from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseTool


class ScaffoldGeneratorArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    output_dir: str = Field(default="output/app", min_length=1)
    app_name: str = Field(default="generated-app", min_length=1)
    app_type: str = Field(default="webapp", min_length=1)
    language: str = Field(default="python", min_length=1)
    overwrite: bool = True


class ScaffoldGeneratorTool(BaseTool):
    name = "scaffold_generator"
    description = "Create a standalone app scaffold under output/app"
    risk_level = "medium"
    destructive = True
    supports_dry_run = False
    timeout_behavior = "not_applicable"
    examples = [
        {
            "output_dir": "output/app",
            "app_name": "crypto-dashboard",
            "app_type": "webapp",
            "language": "python",
        }
    ]
    input_model = ScaffoldGeneratorArgs

    def execute(self, args: ScaffoldGeneratorArgs) -> dict[str, Any]:
        workspace_root = Path(self._resolve_workspace_root()).resolve()
        output_dir = self._resolve_target_path(args.output_dir, workspace_root)

        if output_dir.exists() and not args.overwrite:
            raise ValueError("output_dir already exists and overwrite=false")

        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "launcher").mkdir(parents=True, exist_ok=True)
        (output_dir / "src").mkdir(parents=True, exist_ok=True)
        (output_dir / "tests").mkdir(parents=True, exist_ok=True)

        self._write_if_missing(
            output_dir / "README.md",
            f"# {args.app_name}\n\nType: {args.app_type}\nLanguage: {args.language}\n\n"
            "This directory is a standalone runnable app package.\n"
            "Use launcher/launch.sh or launcher/launch.ps1 to run it.\n",
            args.overwrite,
        )
        self._write_if_missing(
            output_dir / ".gitignore",
            "__pycache__/\n*.pyc\n.venv/\nnode_modules/\n",
            args.overwrite,
        )

        if args.language.lower() == "python":
            self._write_if_missing(output_dir / "requirements.txt", "", args.overwrite)
            self._write_if_missing(
                output_dir / "app.py",
                "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
                "import argparse\n\n"
                "class Handler(BaseHTTPRequestHandler):\n"
                "    def do_GET(self):\n"
                "        self.send_response(200)\n"
                "        self.send_header('Content-Type', 'text/html; charset=utf-8')\n"
                "        self.end_headers()\n"
                "        self.wfile.write(b'<html><body><h1>App scaffold is running</h1></body></html>')\n\n"
                "def main():\n"
                "    parser = argparse.ArgumentParser()\n"
                "    parser.add_argument('--port', type=int, default=3000)\n"
                "    args = parser.parse_args()\n"
                "    server = HTTPServer(('0.0.0.0', args.port), Handler)\n"
                "    print(f'Listening on http://0.0.0.0:{args.port}')\n"
                "    server.serve_forever()\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n",
                args.overwrite,
            )
        else:
            self._write_if_missing(
                output_dir / "package.json",
                '{\n'
                f'  "name": "{args.app_name}",\n'
                '  "version": "0.1.0",\n'
                '  "private": true,\n'
                '  "scripts": {\n'
                '    "start": "node src/index.js"\n'
                '  }\n'
                '}\n',
                args.overwrite,
            )
            self._write_if_missing(
                output_dir / "src" / "index.js",
                "const http = require('http');\n"
                "const port = process.env.PORT || 3000;\n"
                "http.createServer((req, res) => {\n"
                "  res.writeHead(200, {'Content-Type': 'text/html; charset=utf-8'});\n"
                "  res.end('<html><body><h1>App scaffold is running</h1></body></html>');\n"
                "}).listen(port, '0.0.0.0', () => console.log(`Listening on http://0.0.0.0:${port}`));\n",
                args.overwrite,
            )

        return {
            "output_dir": str(output_dir),
            "app_name": args.app_name,
            "app_type": args.app_type,
            "language": args.language,
            "created": [
                str(output_dir / "README.md"),
                str(output_dir / "launcher"),
                str(output_dir / "src"),
                str(output_dir / "tests"),
            ],
        }

    def _write_if_missing(self, path: Path, content: str, overwrite: bool) -> None:
        if path.exists() and not overwrite:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _resolve_workspace_root(self) -> str:
        base = os.environ.get("OVERLORD11_TASK_DIR") or os.getcwd()
        return str(Path(base).resolve())

    def _resolve_target_path(self, raw_path: str, workspace_root: Path) -> Path:
        p = Path(raw_path)
        resolved = (workspace_root / p).resolve() if not p.is_absolute() else p.resolve()
        try:
            resolved.relative_to(workspace_root)
        except ValueError as exc:
            raise ValueError("output_dir must resolve within workspace root") from exc
        return resolved
