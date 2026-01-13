import os
import sys
import json
import subprocess
import shutil
import logging
import anthropic
import google.generativeai as genai
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from typing import Dict, Any, Optional, Tuple

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('code_projectgen.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Setup Paths
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR.parent / ".env"

# Load environment variables
logger.info(f"Loading environment variables from: {ENV_PATH}")
if not ENV_PATH.exists():
    logger.warning(f".env file not found at {ENV_PATH}")
    logger.warning("Please create a .env file based on .env.example")
else:
    load_dotenv(dotenv_path=ENV_PATH)
    logger.info("Environment variables loaded successfully")


def get_model_client(config: Dict[str, Any]) -> Tuple[str, Any]:
    """Initialize the appropriate model client based on config.

    Args:
        config: Configuration dictionary containing model settings

    Returns:
        Tuple of (provider_name, client_instance)

    Raises:
        ValueError: If API key is missing or invalid
        RuntimeError: If client initialization fails
    """
    model_config = config.get('model_config', {})
    provider = model_config.get('provider', 'anthropic')

    logger.info(f"Initializing model client for provider: {provider}")

    try:
        if provider == 'gemini':
            env_var = model_config['models']['gemini']['env_var']
            api_key = os.getenv(env_var)

            if not api_key:
                logger.error(f"Environment variable {env_var} is not set")
                raise ValueError(
                    f"Missing API key: {env_var} environment variable is not set. "
                    f"Please create a .env file with your Gemini API key."
                )

            logger.debug(f"Configuring Gemini with API key (length: {len(api_key)})")
            genai.configure(api_key=api_key)
            model_name = model_config['models']['gemini']['model_name']
            client = genai.GenerativeModel(model_name)
            logger.info(f"Successfully initialized Gemini model: {model_name}")
            return 'gemini', client

        else:  # anthropic
            env_var = model_config['models']['anthropic']['env_var']
            api_key = os.getenv(env_var)

            if not api_key:
                logger.error(f"Environment variable {env_var} is not set")
                raise ValueError(
                    f"Missing API key: {env_var} environment variable is not set. "
                    f"Please create a .env file with your Anthropic API key. "
                    f"See .env.example for reference."
                )

            logger.debug(f"Initializing Anthropic client with API key (length: {len(api_key)})")
            client = anthropic.Anthropic(api_key=api_key)
            model_name = model_config['models']['anthropic']['model_name']
            logger.info(f"Successfully initialized Anthropic client for model: {model_name}")
            return 'anthropic', client

    except KeyError as e:
        logger.error(f"Configuration error: missing key {e}")
        raise RuntimeError(f"Invalid configuration: missing key {e}")
    except Exception as e:
        logger.error(f"Failed to initialize model client: {e}")
        raise RuntimeError(f"Failed to initialize {provider} client: {e}")


class CodeGenerationSystem:
    def __init__(self, workspace: str = None, output_dir: str = None):
        """Initialize the Code Generation System.

        Args:
            workspace: Custom workspace directory path. If provided, code will be
                      generated directly in this directory (no session subfolder).
                      If None, uses default workspace with session subfolders.
            output_dir: Custom output directory for session summaries.
                       If None, uses default output directory.
        """
        logger.info("Initializing CodeGenerationSystem")

        self.config_path = BASE_DIR / "config.json"
        logger.debug(f"Loading config from: {self.config_path}")

        try:
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
            logger.info("Configuration loaded successfully")
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {self.config_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in configuration file: {e}")
            raise

        self.agents_dir = BASE_DIR / "agents"
        self.tools_dir = BASE_DIR / "tools"

        # Handle custom output directory
        if output_dir:
            self.output_dir = Path(output_dir).resolve()
            logger.info(f"Using custom output directory: {self.output_dir}")
        else:
            self.output_dir = BASE_DIR / "output"
            logger.debug(f"Using default output directory: {self.output_dir}")

        # Handle custom workspace
        self.custom_workspace = workspace is not None
        if workspace:
            self.workspace_dir = Path(workspace).resolve()
            logger.info(f"Using custom workspace: {self.workspace_dir}")
        else:
            self.workspace_dir = BASE_DIR / "workspace"
            logger.debug(f"Using default workspace: {self.workspace_dir}")

        # Create directories if they don't exist
        logger.debug("Creating necessary directories")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        logger.debug("Loading agent definitions and tools")
        self.agents = self.load_markdown_assets()
        self.tools = self.load_json_assets()
        self.max_loops = self.config['orchestration_logic']['max_loops']
        logger.info(f"Loaded {len(self.agents)} agents and {len(self.tools)} tools")

        # Initialize model client based on config
        try:
            self.provider, self.client = get_model_client(self.config)
            self.model_config = self.config.get('model_config', {})
        except (ValueError, RuntimeError) as e:
            logger.error(f"Failed to initialize model client: {e}")
            raise

        # Session workspace for current run
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"Session ID: {self.session_id}")

        # If custom workspace provided, use it directly; otherwise create session subfolder
        if self.custom_workspace:
            self.session_workspace = self.workspace_dir
            logger.info(f"Using custom workspace directly (no session subfolder)")
        else:
            self.session_workspace = self.workspace_dir / f"session_{self.session_id}"
            self.session_workspace.mkdir(exist_ok=True)
            logger.info(f"Created session workspace: {self.session_workspace}")

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

        logger.debug(f"Calling Anthropic API with model: {model_name}")
        logger.debug(f"Message count: {len(messages)}, Max tokens: {max_tokens}")

        try:
            response = self.client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                system=system_msg,
                tools=self.tools,
                messages=messages
            )

            logger.debug(f"API Response - Stop reason: {response.stop_reason}")

            if response.stop_reason == "tool_use":
                tool_use = next(block for block in response.content if block.type == "tool_use")
                logger.info(f"Tool use detected: {tool_use.name}")
                return {
                    'tool_use': {'name': tool_use.name, 'input': tool_use.input, 'id': tool_use.id},
                    'raw_content': response.content
                }
            else:
                logger.debug("Received final response from API")
                return {'text': response.content[0].text, 'tool_use': None}

        except Exception as e:
            logger.error(f"Anthropic API call failed: {e}")
            raise

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
        logger.info(f"Executing tool: {tool_name}")
        logger.debug(f"Tool input: {json.dumps(tool_input, indent=2)}")

        try:
            if tool_name == "file_management":
                result = self._handle_file_management(tool_input)

            elif tool_name == "code_execution":
                result = self._handle_code_execution(tool_input)

            elif tool_name == "project_scaffold":
                result = self._handle_project_scaffold(tool_input)

            elif tool_name == "code_analysis":
                result = self._handle_code_analysis(tool_input)

            elif tool_name == "dependency_management":
                result = self._handle_dependency_management(tool_input)

            else:
                logger.warning(f"Unknown tool requested: {tool_name}")
                result = json.dumps({"status": "error", "message": f"Unknown tool: {tool_name}"})

            logger.debug(f"Tool execution result: {result[:200]}...")
            return result

        except Exception as e:
            logger.error(f"Tool execution failed: {e}", exc_info=True)
            return json.dumps({"status": "error", "message": f"Tool execution error: {str(e)}"})

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


def select_workspace_interactive() -> str:
    """Interactively select or create a workspace directory.

    Returns:
        Selected workspace path, or None to use default sandbox
    """
    print("\n" + "-" * 50)
    print("WORKSPACE SELECTION")
    print("-" * 50)
    print("\nWhere would you like to generate the project?\n")
    print("  [1] Built-in Agent Sandbox (default)")
    print("      Creates session subfolder in Code-ProjectGen/workspace/")
    print()
    print("  [2] Specify Existing Directory")
    print("      Use an existing directory on your system")
    print()
    print("  [3] Create New Directory")
    print("      Create a new directory and use it")
    print()

    while True:
        choice = input("Select option [1/2/3] (default: 1): ").strip()

        if choice == "" or choice == "1":
            print("\n-> Using built-in agent sandbox")
            return None

        elif choice == "2":
            while True:
                dir_path = input("\nEnter directory path: ").strip()
                if not dir_path:
                    print("  Error: Path cannot be empty.")
                    continue

                path = Path(dir_path).resolve()
                if path.exists():
                    if path.is_dir():
                        # Check if directory is empty
                        contents = list(path.iterdir())
                        if contents:
                            print(f"\n  Warning: Directory is not empty ({len(contents)} items)")
                            confirm = input("  Continue anyway? [y/N]: ").strip().lower()
                            if confirm != 'y':
                                continue
                        print(f"\n-> Using existing directory: {path}")
                        return str(path)
                    else:
                        print(f"  Error: Path exists but is not a directory: {path}")
                        continue
                else:
                    print(f"  Error: Directory does not exist: {path}")
                    create = input("  Would you like to create it? [y/N]: ").strip().lower()
                    if create == 'y':
                        try:
                            path.mkdir(parents=True, exist_ok=True)
                            print(f"\n-> Created and using directory: {path}")
                            return str(path)
                        except Exception as e:
                            print(f"  Error creating directory: {e}")
                            continue
                    continue

        elif choice == "3":
            while True:
                dir_path = input("\nEnter new directory path to create: ").strip()
                if not dir_path:
                    print("  Error: Path cannot be empty.")
                    continue

                path = Path(dir_path).resolve()
                if path.exists():
                    print(f"  Error: Path already exists: {path}")
                    use_existing = input("  Use this existing directory? [y/N]: ").strip().lower()
                    if use_existing == 'y':
                        if path.is_dir():
                            print(f"\n-> Using existing directory: {path}")
                            return str(path)
                        else:
                            print(f"  Error: Path is not a directory")
                    continue

                try:
                    path.mkdir(parents=True, exist_ok=True)
                    print(f"\n-> Created directory: {path}")
                    return str(path)
                except Exception as e:
                    print(f"  Error creating directory: {e}")
                    continue

        else:
            print("  Invalid option. Please enter 1, 2, or 3.")


def select_language_interactive(current: str = "python") -> str:
    """Interactively select programming language.

    Args:
        current: Current/default language

    Returns:
        Selected language
    """
    languages = ["python", "javascript", "typescript", "go", "rust", "java", "csharp"]

    print("\n" + "-" * 50)
    print("LANGUAGE SELECTION")
    print("-" * 50)
    print("\nSelect primary programming language:\n")

    for i, lang in enumerate(languages, 1):
        default_marker = " (default)" if lang == current else ""
        print(f"  [{i}] {lang}{default_marker}")

    print()
    while True:
        choice = input(f"Select option [1-{len(languages)}] (default: {languages.index(current)+1}): ").strip()

        if choice == "":
            return current

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(languages):
                print(f"\n-> Selected: {languages[idx]}")
                return languages[idx]
            else:
                print(f"  Invalid option. Please enter 1-{len(languages)}.")
        except ValueError:
            # Check if they typed the language name
            if choice.lower() in languages:
                print(f"\n-> Selected: {choice.lower()}")
                return choice.lower()
            print(f"  Invalid option. Please enter 1-{len(languages)} or language name.")


def select_template_interactive(language: str, current: str = "python_cli") -> str:
    """Interactively select project template.

    Args:
        language: Selected programming language
        current: Current/default template

    Returns:
        Selected template
    """
    # Templates filtered by language compatibility
    all_templates = {
        "python_cli": {"desc": "Command-line application", "langs": ["python"]},
        "python_api": {"desc": "FastAPI REST API service", "langs": ["python"]},
        "python_package": {"desc": "Installable Python package", "langs": ["python"]},
        "node_api": {"desc": "Express.js REST API", "langs": ["javascript", "typescript"]},
        "react_app": {"desc": "React frontend application", "langs": ["javascript", "typescript"]},
        "fullstack": {"desc": "Full-stack (backend + frontend)", "langs": ["python", "javascript", "typescript"]},
        "custom": {"desc": "Custom structure (you define)", "langs": ["python", "javascript", "typescript", "go", "rust", "java", "csharp"]},
    }

    # Filter templates compatible with selected language
    compatible = {k: v for k, v in all_templates.items() if language in v["langs"]}

    print("\n" + "-" * 50)
    print("TEMPLATE SELECTION")
    print("-" * 50)
    print(f"\nSelect project template (for {language}):\n")

    template_list = list(compatible.keys())
    for i, (name, info) in enumerate(compatible.items(), 1):
        default_marker = " (default)" if name == current and name in compatible else ""
        print(f"  [{i}] {name}{default_marker}")
        print(f"      {info['desc']}")
        print()

    while True:
        default_idx = template_list.index(current) + 1 if current in template_list else 1
        choice = input(f"Select option [1-{len(template_list)}] (default: {default_idx}): ").strip()

        if choice == "":
            selected = current if current in template_list else template_list[0]
            print(f"\n-> Selected: {selected}")
            return selected

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(template_list):
                print(f"\n-> Selected: {template_list[idx]}")
                return template_list[idx]
            else:
                print(f"  Invalid option. Please enter 1-{len(template_list)}.")
        except ValueError:
            if choice in template_list:
                print(f"\n-> Selected: {choice}")
                return choice
            print(f"  Invalid option. Please enter 1-{len(template_list)} or template name.")


def get_features_interactive() -> list:
    """Interactively get list of features.

    Returns:
        List of feature strings
    """
    print("\n" + "-" * 50)
    print("FEATURES (Optional)")
    print("-" * 50)
    print("\nEnter required features (one per line, empty line to finish):")
    print("Examples: 'user authentication', 'database integration', 'logging'\n")

    features = []
    while True:
        feature = input(f"  Feature {len(features)+1}: ").strip()
        if not feature:
            break
        features.append(feature)

    if features:
        print(f"\n-> Added {len(features)} feature(s)")
    else:
        print("\n-> No additional features specified")

    return features


def confirm_settings(workspace: str, description: str, language: str, template: str, features: list) -> bool:
    """Display settings summary and confirm.

    Returns:
        True if confirmed, False otherwise
    """
    print("\n" + "=" * 60)
    print("CONFIGURATION SUMMARY")
    print("=" * 60)
    print(f"\n  Workspace:   {workspace or 'Built-in Agent Sandbox'}")
    print(f"  Description: {description[:50]}{'...' if len(description) > 50 else ''}")
    print(f"  Language:    {language}")
    print(f"  Template:    {template}")
    print(f"  Features:    {len(features)} specified")
    if features:
        for f in features[:3]:
            print(f"               - {f}")
        if len(features) > 3:
            print(f"               ... and {len(features)-3} more")

    print()
    confirm = input("Proceed with code generation? [Y/n]: ").strip().lower()
    return confirm != 'n'


def main():
    """Main entry point with CLI argument parsing."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Code-ProjectGen: AI-powered code generation system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Interactive mode (recommended)
    python run.py -i

    # Generate project in default workspace
    python run.py --description "Create a REST API" --language python

    # Generate project in custom workspace
    python run.py --workspace /path/to/my/project --description "Create a CLI tool"

    # Use a specific template
    python run.py --template python_api --description "Build a FastAPI service"

    # Skip workspace prompt (use default sandbox)
    python run.py -i --use-sandbox
        """
    )
    parser.add_argument(
        "--workspace", "-w",
        type=str,
        help="Custom workspace directory (code generated directly here, no session subfolder)"
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        help="Custom output directory for session summaries"
    )
    parser.add_argument(
        "--description", "-d",
        type=str,
        help="Project description (what to build)"
    )
    parser.add_argument(
        "--language", "-l",
        type=str,
        default="python",
        choices=["python", "javascript", "typescript", "go", "rust", "java", "csharp"],
        help="Primary programming language (default: python)"
    )
    parser.add_argument(
        "--template", "-t",
        type=str,
        default="python_cli",
        choices=["python_cli", "python_api", "python_package", "node_api", "react_app", "fullstack", "custom"],
        help="Project template to use (default: python_cli)"
    )
    parser.add_argument(
        "--features", "-f",
        type=str,
        nargs="*",
        help="List of required features"
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        default=True,
        help="Include test files (default: True)"
    )
    parser.add_argument(
        "--include-docker",
        action="store_true",
        default=False,
        help="Include Docker configuration"
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in full interactive mode (prompt for all options)"
    )
    parser.add_argument(
        "--use-sandbox",
        action="store_true",
        help="Skip workspace prompt and use built-in sandbox"
    )
    parser.add_argument(
        "--no-confirm",
        action="store_true",
        help="Skip confirmation prompt"
    )

    args = parser.parse_args()

    # Header
    print("\n" + "=" * 60)
    print("  CODE-PROJECTGEN: AI-Powered Code Generation")
    print("=" * 60)

    # Determine workspace
    workspace = args.workspace
    if not workspace and not args.use_sandbox and (args.interactive or not args.description):
        workspace = select_workspace_interactive()

    # Get description
    description = args.description
    if not description:
        print("\n" + "-" * 50)
        print("PROJECT DESCRIPTION")
        print("-" * 50)
        description = input("\nDescribe what you want to build:\n> ").strip()
        if not description:
            print("\nError: Project description is required.")
            return

    # Interactive language/template selection
    language = args.language
    template = args.template
    features = args.features or []

    if args.interactive:
        language = select_language_interactive(language)
        template = select_template_interactive(language, template)
        features = get_features_interactive()

    # Confirmation
    if not args.no_confirm:
        if not confirm_settings(workspace, description, language, template, features):
            print("\nGeneration cancelled.")
            return

    # Build project request
    project_request = {
        "description": description,
        "language": language,
        "template": template,
        "features": features,
        "options": {
            "include_tests": args.include_tests,
            "include_docker": args.include_docker,
            "include_documentation": True
        }
    }

    # Initialize system with optional custom workspace
    print("\n" + "=" * 60)
    print("STARTING CODE GENERATION")
    print("=" * 60)

    system = CodeGenerationSystem(
        workspace=workspace,
        output_dir=args.output_dir
    )

    # Run the mission
    result = system.run_mission(project_request)

    print("\n" + "=" * 80)
    print("FINAL OUTPUT:")
    print("=" * 80)
    print(result)

    print("\n" + "-" * 60)
    print(f"Project generated in: {system.session_workspace}")
    print("-" * 60)


if __name__ == "__main__":
    main()
