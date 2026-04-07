"""
Overlord11 - Scaffold Generator
====================================
Generates project scaffolding from templates. Creates directory structures,
boilerplate files, configuration, and starter code for various project types.

Usage:
    python scaffold_generator.py --template python_cli --name my_tool --project_dir ./task/app
    python scaffold_generator.py --template python_api --name my_api --project_dir ./task/app
    python scaffold_generator.py --template node_api --name my_server --project_dir ./task/app
    python scaffold_generator.py --list-templates
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from log_manager import log_tool_invocation
from task_workspace import ensure_env_task_layout

# --- Template Definitions ---

TEMPLATES = {
    "python_cli": {
        "description": "Python CLI application with argparse, logging, and config",
        "language": "python",
        "structure": {
            "{name}/": {
                "__init__.py": '"""{{name}} - A command-line tool."""\n\n__version__ = "0.1.0"\n',
                "cli.py": '''"""Command-line interface for {{name}}."""

import argparse
import logging
import sys

from . import __version__


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="{{name}}",
        description="{{description}}",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    logger.info("Starting {{name}}")
    # TODO: Implement main logic
    return 0


if __name__ == "__main__":
    sys.exit(main())
''',
                "config.py": '''"""Configuration management for {{name}}."""

import json
from pathlib import Path

DEFAULT_CONFIG = {
    "debug": False,
    "log_level": "INFO",
}


def load_config(config_path: str = None) -> dict:
    """Load configuration from file or return defaults."""
    if config_path:
        path = Path(config_path)
        if path.exists():
            return {**DEFAULT_CONFIG, **json.loads(path.read_text())}
    return DEFAULT_CONFIG.copy()
''',
            },
            "tests/": {
                "__init__.py": "",
                "test_{name}.py": '''"""Tests for {{name}}."""

import pytest
from {{name}}.cli import parse_args, main


class TestCLI:
    def test_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            parse_args(["--version"])
        assert exc_info.value.code == 0

    def test_main_returns_zero(self):
        assert main([]) == 0
''',
            },
            "pyproject.toml": '''[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "{{name}}"
version = "0.1.0"
description = "{{description}}"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=7.0", "ruff>=0.1.0"]

[project.scripts]
{{name}} = "{{name}}.cli:main"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
testpaths = ["tests"]
''',
            ".gitignore": '''__pycache__/
*.pyc
*.pyo
dist/
build/
*.egg-info/
.venv/
.env
.pytest_cache/
.ruff_cache/
.mypy_cache/
''',
            "README.md": '''# {{name}}

{{description}}

## Quick Start

Double-click `run.bat` (Windows) or `run.command` (macOS), or:

```bash
python run.py
```

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

```bash
{{name}} --help
```

## Development

```bash
pytest
ruff check .
```
''',
            "run.py": '''#!/usr/bin/env python3
"""{{name}} — Launcher. Run this file to start the application."""
import io, os, subprocess, sys, time
from datetime import datetime

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    os.system("")

TITLE = """
  +======================================+
  |            {{NAME}}            |
  +======================================+
"""

C = {
    "cyan": "\\033[36m", "yellow": "\\033[33m", "green": "\\033[32m",
    "red": "\\033[31m", "magenta": "\\033[35m", "dim": "\\033[90m",
    "white": "\\033[97m", "reset": "\\033[0m",
} if sys.stdout.isatty() else {k: "" for k in ["cyan","yellow","green","red","magenta","dim","white","reset"]}

def log(msg, level="info"):
    ts = datetime.now().strftime("%H:%M:%S")
    color = {"info": C["cyan"], "success": C["green"], "error": C["red"], "dim": C["dim"]}.get(level, C["cyan"])
    print(f"  {C['dim']}[{ts}]{C['reset']} {color}{level.upper().ljust(7)}{C['reset']} {msg}")

def run_cmd(cmd, label=""):
    log(f"Running: {label or cmd}", "info")
    try:
        p = subprocess.Popen(cmd, shell=True, stdout=sys.stdout, stderr=sys.stderr)
        p.wait()
        if p.returncode == 0:
            log(f"{label or 'Command'} completed.", "success")
        else:
            log(f"{label or 'Command'} exited with code {p.returncode}.", "error")
    except KeyboardInterrupt:
        log("Interrupted.", "info")

def main():
    print(f"{C['cyan']}{TITLE}{C['reset']}")
    print(f"  {C['magenta']}{{description}}{C['reset']}")
    print(f"  {C['dim']}Python {sys.version.split()[0]}{C['reset']}")
    print(f"  {C['dim']}{'─' * 40}{C['reset']}\\n")
    print(f"  {C['white']}Select a run mode:{C['reset']}\\n")
    print(f"  {C['yellow']}[1]{C['reset']}  {C['white']}CLI Mode{C['reset']}")
    print(f"  {C['yellow']}[Q]{C['reset']}  {C['dim']}Quit{C['reset']}\\n")
    while True:
        try:
            choice = input(f"  {C['magenta']}> {C['reset']}").strip()
        except (KeyboardInterrupt, EOFError):
            print(); log("Goodbye!", "info"); return
        if choice.upper() == "Q":
            log("Goodbye!", "info"); return
        elif choice == "1":
            run_cmd("python -m {{name}}.cli", "CLI Mode"); print()
        else:
            log(f"Unknown option: '{choice}'", "error"); print()

if __name__ == "__main__":
    main()
''',
            "run.bat": '''@echo off
title {{name}}
setlocal enabledelayedexpansion
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (set "PY=python" & goto :run)
where python3 >nul 2>&1
if %ERRORLEVEL% equ 0 (set "PY=python3" & goto :run)
echo  ERROR: Python not found. & pause & exit /b 1
:run
cd /d "%~dp0"
%PY% run.py
if %ERRORLEVEL% neq 0 pause
''',
        },
    },
    "python_api": {
        "description": "FastAPI REST API with structured routes, models, and tests",
        "language": "python",
        "structure": {
            "{name}/": {
                "__init__.py": "",
                "main.py": '''"""{{name}} - FastAPI Application."""

from fastapi import FastAPI

app = FastAPI(title="{{name}}", version="0.1.0")


@app.get("/")
async def root():
    return {"message": "Welcome to {{name}}"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
''',
                "routes/": {
                    "__init__.py": "",
                    "api.py": '''"""API routes."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")


@router.get("/items")
async def list_items():
    return {"items": []}
''',
                },
                "models/": {
                    "__init__.py": "",
                    "schemas.py": '''"""Pydantic models."""

from pydantic import BaseModel


class ItemCreate(BaseModel):
    name: str
    description: str = ""


class ItemResponse(BaseModel):
    id: int
    name: str
    description: str
''',
                },
            },
            "tests/": {
                "__init__.py": "",
                "test_api.py": '''"""API tests."""

import pytest
from fastapi.testclient import TestClient
from {{name}}.main import app

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
''',
            },
            "pyproject.toml": '''[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "{{name}}"
version = "0.1.0"
description = "{{description}}"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.100.0",
    "uvicorn[standard]>=0.23.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.0", "httpx>=0.24.0", "ruff>=0.1.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
''',
            ".gitignore": '''__pycache__/
*.pyc
dist/
.venv/
.env
.pytest_cache/
''',
            "README.md": '''# {{name}}

{{description}}

## Quick Start

Double-click `run.bat` (Windows) or `run.command` (macOS), or:

```bash
python run.py
```

## Run Manually

```bash
uvicorn {{name}}.main:app --reload
```

## Test

```bash
pytest
```
''',
            "run.py": '''#!/usr/bin/env python3
"""{{name}} — Launcher. Run this file to start the application."""
import io, os, subprocess, sys, time
from datetime import datetime

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    os.system("")

TITLE = """
  +======================================+
  |            {{NAME}}            |
  +======================================+
"""

C = {
    "cyan": "\\033[36m", "yellow": "\\033[33m", "green": "\\033[32m",
    "red": "\\033[31m", "magenta": "\\033[35m", "dim": "\\033[90m",
    "white": "\\033[97m", "reset": "\\033[0m",
} if sys.stdout.isatty() else {k: "" for k in ["cyan","yellow","green","red","magenta","dim","white","reset"]}

def log(msg, level="info"):
    ts = datetime.now().strftime("%H:%M:%S")
    color = {"info": C["cyan"], "success": C["green"], "error": C["red"], "dim": C["dim"]}.get(level, C["cyan"])
    print(f"  {C['dim']}[{ts}]{C['reset']} {color}{level.upper().ljust(7)}{C['reset']} {msg}")

def run_cmd(cmd, label=""):
    log(f"Running: {label or cmd}", "info")
    try:
        p = subprocess.Popen(cmd, shell=True, stdout=sys.stdout, stderr=sys.stderr)
        p.wait()
        if p.returncode == 0:
            log(f"{label or 'Command'} completed.", "success")
        else:
            log(f"{label or 'Command'} exited with code {p.returncode}.", "error")
    except KeyboardInterrupt:
        log("Interrupted.", "info")

def main():
    print(f"{C['cyan']}{TITLE}{C['reset']}")
    print(f"  {C['magenta']}{{description}}{C['reset']}")
    print(f"  {C['dim']}Python {sys.version.split()[0]}{C['reset']}")
    print(f"  {C['dim']}{'─' * 40}{C['reset']}\\n")
    print(f"  {C['white']}Select a run mode:{C['reset']}\\n")
    print(f"  {C['yellow']}[1]{C['reset']}  {C['white']}API Server{C['reset']}")
    print(f"       {C['dim']}uvicorn on http://127.0.0.1:8000{C['reset']}")
    print(f"  {C['yellow']}[Q]{C['reset']}  {C['dim']}Quit{C['reset']}\\n")
    while True:
        try:
            choice = input(f"  {C['magenta']}> {C['reset']}").strip()
        except (KeyboardInterrupt, EOFError):
            print(); log("Goodbye!", "info"); return
        if choice.upper() == "Q":
            log("Goodbye!", "info"); return
        elif choice == "1":
            run_cmd("uvicorn {{name}}.main:app --reload --host 127.0.0.1 --port 8000", "API Server"); print()
        else:
            log(f"Unknown option: '{choice}'", "error"); print()

if __name__ == "__main__":
    main()
''',
            "run.bat": '''@echo off
title {{name}}
setlocal enabledelayedexpansion
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (set "PY=python" & goto :run)
where python3 >nul 2>&1
if %ERRORLEVEL% equ 0 (set "PY=python3" & goto :run)
echo  ERROR: Python not found. & pause & exit /b 1
:run
cd /d "%~dp0"
%PY% run.py
if %ERRORLEVEL% neq 0 pause
''',
        },
    },
    "node_api": {
        "description": "Express.js REST API with TypeScript, routing, and tests",
        "language": "typescript",
        "structure": {
            "src/": {
                "index.ts": '''import express from "express";
import { router } from "./routes";

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());
app.use("/api", router);

app.get("/health", (_req, res) => {
  res.json({ status: "healthy" });
});

app.listen(PORT, () => {
  console.log(`{{name}} running on port ${PORT}`);
});

export default app;
''',
                "routes/": {
                    "index.ts": '''import { Router } from "express";

export const router = Router();

router.get("/", (_req, res) => {
  res.json({ message: "Welcome to {{name}}" });
});
''',
                },
            },
            "tests/": {
                "api.test.ts": '''import request from "supertest";
import app from "../src/index";

describe("API", () => {
  it("GET /health returns 200", async () => {
    const res = await request(app).get("/health");
    expect(res.status).toBe(200);
    expect(res.body.status).toBe("healthy");
  });
});
''',
            },
            "package.json": '''{
  "name": "{{name}}",
  "version": "0.1.0",
  "description": "{{description}}",
  "main": "dist/index.js",
  "scripts": {
    "dev": "tsx watch src/index.ts",
    "build": "tsc",
    "start": "node dist/index.js",
    "test": "jest"
  },
  "dependencies": {
    "express": "^4.18.0"
  },
  "devDependencies": {
    "@types/express": "^4.17.0",
    "@types/jest": "^29.0.0",
    "@types/supertest": "^6.0.0",
    "jest": "^29.0.0",
    "supertest": "^6.0.0",
    "ts-jest": "^29.0.0",
    "tsx": "^4.0.0",
    "typescript": "^5.0.0"
  }
}
''',
            "tsconfig.json": '''{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "declaration": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "tests"]
}
''',
            ".gitignore": '''node_modules/
dist/
.env
coverage/
''',
            "README.md": '''# {{name}}

{{description}}

## Setup

```bash
npm install
```

## Development

```bash
npm run dev
```

## Test

```bash
npm test
```
''',
        },
    },
    "react_app": {
        "description": "React application with TypeScript and Vite",
        "language": "typescript",
        "structure": {
            "src/": {
                "App.tsx": '''function App() {
  return (
    <div>
      <h1>{{name}}</h1>
      <p>{{description}}</p>
    </div>
  );
}

export default App;
''',
                "main.tsx": '''import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
''',
            },
            "index.html": '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{name}}</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.tsx"></script>
</body>
</html>
''',
            "package.json": '''{
  "name": "{{name}}",
  "version": "0.1.0",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "@vitejs/plugin-react": "^4.0.0",
    "typescript": "^5.0.0",
    "vite": "^5.0.0"
  }
}
''',
            "tsconfig.json": '''{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true
  },
  "include": ["src"]
}
''',
            "vite.config.ts": '''import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
});
''',
            ".gitignore": "node_modules/\ndist/\n.env\n",
            "README.md": "# {{name}}\n\n{{description}}\n\n```bash\nnpm install && npm run dev\n```\n",
        },
    },
}


def list_templates() -> list:
    """List all available templates."""
    return [
        {"name": name, "description": tpl["description"], "language": tpl["language"]}
        for name, tpl in TEMPLATES.items()
    ]


def generate_scaffold(template_name: str, project_name: str,
                      output_path: str, description: str = "") -> dict:
    """Generate a project scaffold from a template."""
    if template_name not in TEMPLATES:
        return {
            "status": "error",
            "error": f"Unknown template: {template_name}",
            "hint": f"Use one of the available templates: {', '.join(TEMPLATES.keys())}",
            "available": list(TEMPLATES.keys()),
        }

    template = TEMPLATES[template_name]
    output_dir = Path(output_path).resolve()
    description = description or f"A {template['language']} project"

    if output_dir.exists() and any(output_dir.iterdir()):
        return {
            "status": "error",
            "error": f"Output directory is not empty: {output_dir}",
            "hint": "Provide an empty or non-existent output path.",
        }

    start_time = time.time()
    files_created = []
    dirs_created = []

    def _render(text: str) -> str:
        return text.replace("{{name}}", project_name).replace("{{description}}", description)

    def _create_structure(structure: dict, base_path: Path):
        for key, value in structure.items():
            # Replace {name} in directory/file names
            key = key.replace("{name}", project_name)

            if key.endswith("/"):
                # It's a directory
                dir_path = base_path / key.rstrip("/")
                dir_path.mkdir(parents=True, exist_ok=True)
                dirs_created.append(str(dir_path.relative_to(output_dir)).replace("\\", "/"))
                if isinstance(value, dict):
                    _create_structure(value, dir_path)
            elif isinstance(value, dict):
                # Nested directory without trailing /
                dir_path = base_path / key
                dir_path.mkdir(parents=True, exist_ok=True)
                dirs_created.append(str(dir_path.relative_to(output_dir)).replace("\\", "/"))
                _create_structure(value, dir_path)
            elif isinstance(value, str):
                # It's a file
                file_name = key.replace("{name}", project_name)
                file_path = base_path / file_name
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(_render(value), encoding="utf-8")
                files_created.append(str(file_path.relative_to(output_dir)).replace("\\", "/"))

    output_dir.mkdir(parents=True, exist_ok=True)
    _create_structure(template["structure"], output_dir)

    duration_ms = (time.time() - start_time) * 1000

    return {
        "status": "success",
        "template": template_name,
        "project_name": project_name,
        "output_path": str(output_dir),
        "project_dir": str(output_dir),
        "language": template["language"],
        "files_created": files_created,
        "dirs_created": dirs_created,
        "total_files": len(files_created),
        "total_dirs": len(dirs_created),
        "duration_ms": round(duration_ms, 1),
    }


# --- CLI Interface ---

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Overlord11 Scaffold Generator")
    parser.add_argument("--template", default=None, help="Template name")
    parser.add_argument("--name", default=None, help="Project name")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--project_dir", default=None, help="Project directory (preferred; alias for --output)")
    parser.add_argument("--description", default="", help="Project description")
    parser.add_argument("--list-templates", action="store_true", help="List available templates")
    parser.add_argument("--session_id", default=None, help="Session ID for logging")

    args = parser.parse_args()
    session_id = args.session_id or "unset"

    if args.list_templates:
        templates = list_templates()
        print(json.dumps(templates, indent=2))
        return

    if not args.template or not args.name:
        parser.error("--template and --name are required")

    layout = ensure_env_task_layout(include_app=True)
    output = args.project_dir or args.output
    if not output:
        output = str(layout["app"]) if layout else f"./{args.name}"

    start = time.time()
    result = generate_scaffold(
        template_name=args.template,
        project_name=args.name,
        output_path=output,
        description=args.description
    )
    duration_ms = (time.time() - start) * 1000

    log_tool_invocation(
        session_id=session_id,
        tool_name="scaffold_generator",
        params={"template": args.template, "name": args.name, "project_dir": output},
        result={"status": result.get("status", "error"),
                "files_created": result.get("total_files", 0)},
        duration_ms=duration_ms
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
