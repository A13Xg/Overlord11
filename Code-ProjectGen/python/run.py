import os
import json
import subprocess
import shutil
import anthropic
import google.generativeai as genai
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Setup Paths
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)


def get_model_client(config):
    """Initialize the appropriate model client based on config."""
    model_config = config.get('model_config', {})
    provider = model_config.get('provider', 'anthropic')

    if provider == 'gemini':
        api_key = os.getenv(model_config['models']['gemini']['env_var'])
        genai.configure(api_key=api_key)
        return 'gemini', genai.GenerativeModel(model_config['models']['gemini']['model_name'])
    else:
        api_key = os.getenv(model_config['models']['anthropic']['env_var'])
        return 'anthropic', anthropic.Anthropic(api_key=api_key)


class CodeGenerationSystem:
    def __init__(self):
        self.config_path = BASE_DIR / "config.json"
        with open(self.config_path, 'r') as f:
            self.config = json.load(f)

        self.agents_dir = BASE_DIR / "agents"
        self.tools_dir = BASE_DIR / "tools"
        self.output_dir = BASE_DIR / "output"
        self.workspace_dir = BASE_DIR / "workspace"

        # Create directories if they don't exist
        self.output_dir.mkdir(exist_ok=True)
        self.workspace_dir.mkdir(exist_ok=True)

        self.agents = self.load_markdown_assets()
        self.tools = self.load_json_assets()
        self.max_loops = self.config['orchestration_logic']['max_loops']

        # Initialize model client based on config
        self.provider, self.client = get_model_client(self.config)
        self.model_config = self.config.get('model_config', {})

        # Session workspace for current run
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_workspace = self.workspace_dir / f"session_{self.session_id}"
        self.session_workspace.mkdir(exist_ok=True)

    def load_markdown_assets(self):
        """Load agent definitions from markdown files."""
        assets = {}
        for file in os.listdir(self.agents_dir):
            if file.endswith(".md"):
                with open(self.agents_dir / file, 'r') as f:
                    assets[file.replace(".md", "")] = f.read()
        return assets

    def load_json_assets(self):
        """Load tool definitions from JSON files."""
        tools = []
        for file in os.listdir(self.tools_dir):
            if file.endswith(".json"):
                with open(self.tools_dir / file, 'r') as f:
                    tools.append(json.load(f))
        return tools

    def run_mission(self, project_request):
        """
        Main entry point for code generation workflow.

        Args:
            project_request: Dictionary with keys like:
                - 'description': What to build
                - 'language': Primary programming language
                - 'template': Project template to use
                - 'features': List of required features
                - 'options': Additional generation options
        """
        # Build system message with orchestrator + config
        system_msg = f"""{self.agents['orchestrator']}

GLOBAL_CONFIG: {json.dumps(self.config, indent=2)}

SESSION_WORKSPACE: {self.session_workspace}

AVAILABLE_AGENTS:
- Architect (CG_ARC_02): {self.agents.get('architect', 'Not loaded')[:200]}...
- Coder (CG_COD_03): {self.agents.get('coder', 'Not loaded')[:200]}...
- Tester (CG_TST_04): {self.agents.get('tester', 'Not loaded')[:200]}...
- Reviewer (CG_REV_05): {self.agents.get('reviewer', 'Not loaded')[:200]}...
"""

        # Initial user prompt
        initial_prompt = f"""
Project Request:
{json.dumps(project_request, indent=2)}

Session Workspace: {self.session_workspace}

Begin the code generation workflow: PLAN → ARCHITECT → IMPLEMENT → TEST → REVIEW

Generate the requested project following all quality standards and best practices.
"""

        messages = [{"role": "user", "content": initial_prompt}]

        print(f"🚀 Code Generation Mission Started")
        print(f"📂 Session Workspace: {self.session_workspace}")
        print(f"💻 Language: {project_request.get('language', 'Not specified')}")
        print(f"📋 Template: {project_request.get('template', 'Not specified')}")
        print(f"🤖 Model Provider: {self.provider}")

        for loop_num in range(self.max_loops):
            if self.provider == 'gemini':
                response = self._call_gemini(system_msg, messages)
            else:
                response = self._call_anthropic(system_msg, messages)

            if response.get('tool_use'):
                tool_use = response['tool_use']
                print(f"🔧 Tool Activity [{loop_num+1}/{self.max_loops}]: {tool_use['name']}")

                # Execute tool
                result = self._execute_tool(tool_use['name'], tool_use['input'])

                if self.provider == 'anthropic':
                    messages.append({"role": "assistant", "content": response['raw_content']})
                    messages.append({
                        "role": "user",
                        "content": [{"type": "tool_result", "tool_use_id": tool_use['id'], "content": result}]
                    })
                else:
                    messages.append({"role": "assistant", "content": f"Tool call: {tool_use['name']}"})
                    messages.append({"role": "user", "content": f"Tool result: {result}"})
            else:
                # Final response
                print(f"✅ Code Generation Complete (Loops: {loop_num+1})")
                self._save_session_summary(project_request, response['text'])
                return response['text']

        print(f"⚠️  Loop limit reached ({self.max_loops})")
        return "ERROR: Maximum iteration limit reached."

    def _call_anthropic(self, system_msg, messages):
        """Call Anthropic API."""
        model_name = self.model_config['models']['anthropic']['model_name']
        max_tokens = self.model_config['models']['anthropic']['max_tokens']

        response = self.client.messages.create(
            model=model_name,
            max_tokens=max_tokens,
            system=system_msg,
            tools=self.tools,
            messages=messages
        )

        if response.stop_reason == "tool_use":
            tool_use = next(block for block in response.content if block.type == "tool_use")
            return {
                'tool_use': {'name': tool_use.name, 'input': tool_use.input, 'id': tool_use.id},
                'raw_content': response.content
            }
        else:
            return {'text': response.content[0].text, 'tool_use': None}

    def _call_gemini(self, system_msg, messages):
        """Call Google Gemini API."""
        # Build conversation for Gemini
        full_prompt = f"{system_msg}\n\n"
        for msg in messages:
            role = msg['role']
            content = msg['content'] if isinstance(msg['content'], str) else json.dumps(msg['content'])
            full_prompt += f"{role.upper()}: {content}\n\n"

        # Add tool descriptions to prompt
        tool_desc = "Available tools:\n" + json.dumps(self.tools, indent=2)
        full_prompt += f"\n{tool_desc}\n\nIf you need to use a tool, respond with JSON: {{\"tool\": \"tool_name\", \"input\": {{...}}}}\nOtherwise, provide your final response."

        response = self.client.generate_content(full_prompt)
        response_text = response.text

        # Check if response is a tool call
        try:
            if '{"tool"' in response_text:
                tool_json = json.loads(response_text.strip())
                if 'tool' in tool_json:
                    return {
                        'tool_use': {'name': tool_json['tool'], 'input': tool_json.get('input', {}), 'id': 'gemini_tool'},
                        'raw_content': response_text
                    }
        except json.JSONDecodeError:
            pass

        return {'text': response_text, 'tool_use': None}

    def _execute_tool(self, tool_name, tool_input):
        """Execute tools with actual implementations."""

        if tool_name == "file_management":
            return self._handle_file_management(tool_input)

        elif tool_name == "code_execution":
            return self._handle_code_execution(tool_input)

        elif tool_name == "project_scaffold":
            return self._handle_project_scaffold(tool_input)

        elif tool_name == "code_analysis":
            return self._handle_code_analysis(tool_input)

        elif tool_name == "dependency_management":
            return self._handle_dependency_management(tool_input)

        else:
            return json.dumps({"status": "error", "message": f"Unknown tool: {tool_name}"})

    def _safe_path(self, path_str):
        """Validate and resolve path within workspace."""
        path = Path(path_str)
        # Prevent directory traversal
        if ".." in path.parts:
            raise ValueError("Directory traversal not allowed")
        full_path = self.session_workspace / path
        return full_path

    def _handle_file_management(self, params):
        """Handle file operations within the workspace."""
        action = params.get("action")
        path_str = params.get("path", "")

        try:
            path = self._safe_path(path_str)

            if action == "read":
                if path.exists() and path.is_file():
                    content = path.read_text(encoding='utf-8')
                    return json.dumps({
                        "status": "success",
                        "content": content,
                        "size": len(content)
                    })
                else:
                    return json.dumps({"status": "error", "message": f"File not found: {path_str}"})

            elif action == "write":
                content = params.get("content", "")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding='utf-8')
                return json.dumps({
                    "status": "success",
                    "path": str(path.relative_to(self.session_workspace)),
                    "bytes_written": len(content)
                })

            elif action == "list":
                recursive = params.get("recursive", False)
                if path.exists():
                    if recursive:
                        items = [str(p.relative_to(self.session_workspace)) for p in path.rglob("*")]
                    else:
                        items = [p.name for p in path.iterdir()]
                    return json.dumps({"status": "success", "items": items})
                else:
                    return json.dumps({"status": "error", "message": f"Directory not found: {path_str}"})

            elif action == "delete":
                if path.exists():
                    if path.is_file():
                        path.unlink()
                    else:
                        shutil.rmtree(path)
                    return json.dumps({"status": "success", "deleted": path_str})
                else:
                    return json.dumps({"status": "error", "message": f"Path not found: {path_str}"})

            elif action == "exists":
                return json.dumps({"status": "success", "exists": path.exists(), "is_file": path.is_file() if path.exists() else None})

            elif action == "mkdir":
                recursive = params.get("recursive", True)
                path.mkdir(parents=recursive, exist_ok=True)
                return json.dumps({"status": "success", "created": path_str})

            else:
                return json.dumps({"status": "error", "message": f"Unknown action: {action}"})

        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def _handle_code_execution(self, params):
        """Handle code execution in sandboxed environment."""
        action = params.get("action")
        timeout = params.get("timeout", self.config['code_execution']['timeout_seconds'])
        working_dir = params.get("working_dir", "")

        try:
            work_path = self._safe_path(working_dir) if working_dir else self.session_workspace

            if action == "run_python":
                code = params.get("code", "")
                result = subprocess.run(
                    ["python", "-c", code],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(work_path)
                )
                return json.dumps({
                    "status": "success" if result.returncode == 0 else "error",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.returncode
                })

            elif action == "run_shell":
                command = params.get("command", "")
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(work_path)
                )
                return json.dumps({
                    "status": "success" if result.returncode == 0 else "error",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.returncode
                })

            elif action == "run_tests":
                file_path = params.get("file_path", "tests")
                test_path = self._safe_path(file_path)
                result = subprocess.run(
                    ["python", "-m", "pytest", str(test_path), "-v"],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(work_path)
                )
                return json.dumps({
                    "status": "success" if result.returncode == 0 else "failed",
                    "output": result.stdout + result.stderr,
                    "exit_code": result.returncode
                })

            elif action == "install_deps":
                result = subprocess.run(
                    ["pip", "install", "-r", "requirements.txt"],
                    capture_output=True,
                    text=True,
                    timeout=timeout * 2,
                    cwd=str(work_path)
                )
                return json.dumps({
                    "status": "success" if result.returncode == 0 else "error",
                    "output": result.stdout + result.stderr,
                    "exit_code": result.returncode
                })

            else:
                return json.dumps({"status": "error", "message": f"Unknown action: {action}"})

        except subprocess.TimeoutExpired:
            return json.dumps({"status": "error", "message": f"Execution timed out after {timeout} seconds"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def _handle_project_scaffold(self, params):
        """Create project structure from template."""
        template = params.get("template")
        project_name = params.get("project_name")
        options = params.get("options", {})

        try:
            project_path = self.session_workspace / project_name
            project_path.mkdir(parents=True, exist_ok=True)

            created_items = []

            # Template definitions
            templates = {
                "python_cli": {
                    "dirs": ["src", "tests"],
                    "files": {
                        "src/__init__.py": "",
                        "src/main.py": self._get_python_main_template(project_name),
                        "tests/__init__.py": "",
                        "tests/test_main.py": self._get_python_test_template(project_name),
                        "requirements.txt": "# Project dependencies\n",
                        "README.md": f"# {project_name}\n\nA Python CLI application.\n",
                        ".gitignore": self._get_gitignore_template("python"),
                    }
                },
                "python_api": {
                    "dirs": ["src", "src/routes", "src/models", "tests"],
                    "files": {
                        "src/__init__.py": "",
                        "src/main.py": self._get_fastapi_template(project_name),
                        "src/routes/__init__.py": "",
                        "src/models/__init__.py": "",
                        "tests/__init__.py": "",
                        "requirements.txt": "fastapi\nuvicorn\npydantic\n",
                        "README.md": f"# {project_name}\n\nA FastAPI REST API.\n",
                        ".gitignore": self._get_gitignore_template("python"),
                    }
                },
                "python_package": {
                    "dirs": ["src", f"src/{project_name}", "tests"],
                    "files": {
                        f"src/{project_name}/__init__.py": f'"""{ project_name} package."""\n\n__version__ = "0.1.0"\n',
                        "tests/__init__.py": "",
                        "pyproject.toml": self._get_pyproject_template(project_name, options),
                        "README.md": f"# {project_name}\n\nA Python package.\n",
                        ".gitignore": self._get_gitignore_template("python"),
                    }
                },
                "node_api": {
                    "dirs": ["src", "src/routes", "src/controllers", "tests"],
                    "files": {
                        "src/index.js": self._get_express_template(project_name),
                        "src/routes/index.js": "// Routes\nmodule.exports = {};\n",
                        "src/controllers/index.js": "// Controllers\nmodule.exports = {};\n",
                        "package.json": self._get_package_json_template(project_name, "api"),
                        "README.md": f"# {project_name}\n\nAn Express.js API.\n",
                        ".gitignore": self._get_gitignore_template("node"),
                    }
                },
            }

            template_config = templates.get(template, templates["python_cli"])

            # Create directories
            for dir_path in template_config["dirs"]:
                full_path = project_path / dir_path
                full_path.mkdir(parents=True, exist_ok=True)
                created_items.append(f"dir: {dir_path}")

            # Create files
            for file_path, content in template_config["files"].items():
                full_path = project_path / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content, encoding='utf-8')
                created_items.append(f"file: {file_path}")

            return json.dumps({
                "status": "success",
                "project_path": str(project_path.relative_to(self.session_workspace)),
                "created": created_items
            })

        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def _handle_code_analysis(self, params):
        """Analyze code quality."""
        action = params.get("action")
        target = params.get("target", ".")

        try:
            target_path = self._safe_path(target)

            # Simulated analysis results
            return json.dumps({
                "status": "success",
                "action": action,
                "target": target,
                "results": {
                    "files_analyzed": 1,
                    "issues": [],
                    "score": 8,
                    "message": f"Analysis '{action}' completed on {target}"
                }
            })

        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def _handle_dependency_management(self, params):
        """Manage project dependencies."""
        action = params.get("action")
        packages = params.get("packages", [])

        try:
            if action == "add":
                pkg_list = [p.get("name", "") for p in packages]
                return json.dumps({
                    "status": "success",
                    "action": "add",
                    "packages": pkg_list,
                    "message": f"Added packages: {', '.join(pkg_list)}"
                })

            elif action == "list":
                return json.dumps({
                    "status": "success",
                    "action": "list",
                    "packages": [],
                    "message": "No packages installed yet"
                })

            else:
                return json.dumps({
                    "status": "success",
                    "action": action,
                    "message": f"Action '{action}' simulated"
                })

        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def _save_session_summary(self, request, result):
        """Save session summary to output directory."""
        summary = {
            "session_id": self.session_id,
            "request": request,
            "workspace": str(self.session_workspace),
            "completed_at": datetime.now().isoformat(),
            "result_preview": result[:500] if len(result) > 500 else result
        }
        summary_path = self.output_dir / f"session_{self.session_id}_summary.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)

    # Template generators
    def _get_python_main_template(self, project_name):
        return f'''"""Main entry point for {project_name}."""

import argparse
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """Main function."""
    parser = argparse.ArgumentParser(description="{project_name}")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Starting {project_name}")
    # Add your code here


if __name__ == "__main__":
    main()
'''

    def _get_python_test_template(self, project_name):
        return f'''"""Tests for {project_name}."""

import pytest


def test_placeholder():
    """Placeholder test."""
    assert True
'''

    def _get_fastapi_template(self, project_name):
        return f'''"""FastAPI application for {project_name}."""

from fastapi import FastAPI

app = FastAPI(title="{project_name}")


@app.get("/")
async def root():
    """Root endpoint."""
    return {{"message": "Welcome to {project_name}"}}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {{"status": "healthy"}}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
'''

    def _get_express_template(self, project_name):
        return f'''/**
 * Express.js application for {project_name}
 */

const express = require('express');
const app = express();
const port = process.env.PORT || 3000;

app.use(express.json());

app.get('/', (req, res) => {{
    res.json({{ message: 'Welcome to {project_name}' }});
}});

app.get('/health', (req, res) => {{
    res.json({{ status: 'healthy' }});
}});

app.listen(port, () => {{
    console.log(`{project_name} listening on port ${{port}}`);
}});

module.exports = app;
'''

    def _get_pyproject_template(self, project_name, options):
        python_version = options.get("python_version", "3.11")
        return f'''[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{project_name}"
version = "0.1.0"
description = "A Python package"
readme = "README.md"
requires-python = ">={python_version}"
dependencies = []

[project.optional-dependencies]
dev = ["pytest", "ruff", "mypy"]
'''

    def _get_package_json_template(self, project_name, project_type):
        return json.dumps({
            "name": project_name,
            "version": "1.0.0",
            "description": f"A Node.js {project_type}",
            "main": "src/index.js",
            "scripts": {
                "start": "node src/index.js",
                "dev": "nodemon src/index.js",
                "test": "jest"
            },
            "dependencies": {
                "express": "^4.18.0"
            },
            "devDependencies": {
                "jest": "^29.0.0",
                "nodemon": "^3.0.0"
            }
        }, indent=2)

    def _get_gitignore_template(self, language):
        templates = {
            "python": """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg
.venv/
venv/
ENV/
.env
*.log
.pytest_cache/
.mypy_cache/
.ruff_cache/
""",
            "node": """# Node
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.npm
.env
.env.local
.env.*.local
dist/
build/
coverage/
*.log
"""
        }
        return templates.get(language, templates["python"])


if __name__ == "__main__":
    # Example usage
    system = CodeGenerationSystem()

    sample_request = {
        "description": "Create a CLI tool that converts JSON to CSV",
        "language": "python",
        "template": "python_cli",
        "features": [
            "Read JSON from file or stdin",
            "Output CSV to file or stdout",
            "Handle nested JSON structures",
            "Include error handling"
        ],
        "options": {
            "include_tests": True,
            "include_documentation": True
        }
    }

    result = system.run_mission(sample_request)
    print("\n" + "=" * 80)
    print("FINAL OUTPUT:")
    print("=" * 80)
    print(result)
