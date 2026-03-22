"""
Overlord11 - Launcher Generator
====================================
Generates a standardized run.py launcher with ASCII title art, color-coded
console output, in-terminal logging, and an interactive run-mode menu.

Also generates platform shortcuts:
  - Windows: run.bat (auto-finds python and launches run.py)
  - macOS:   run.command (double-clickable shell script)

The launcher is zero-dependency — uses only stdlib (ANSI codes for color).

Usage:
    python launcher_generator.py --project_dir /path/to/project \
        --project_name "TaskForge" --version "0.1.0" \
        --modes '[{"key":"1","label":"CLI Mode","cmd":"python -m taskforge.cli","desc":"Interactive command-line interface"},{"key":"2","label":"API Server","cmd":"python -m uvicorn taskforge.api:app --reload","desc":"REST API on http://127.0.0.1:8000"}]'

    python launcher_generator.py --project_dir /path/to/project \
        --project_name "MyApp" --version "1.0.0" \
        --modes '[{"key":"1","label":"Run App","cmd":"python main.py"}]'
"""

import io
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from textwrap import dedent

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from log_manager import log_tool_invocation


# ---------------------------------------------------------------------------
# ASCII art generator — simple block letters from project name
# ---------------------------------------------------------------------------

def _ascii_title(name: str) -> str:
    """Generate a framed ASCII title block. Keeps it simple and reliable."""
    upper = name.upper()
    width = max(len(upper) + 8, 40)
    pad = (width - len(upper) - 2) // 2
    lines = [
        "+" + "=" * (width - 2) + "+",
        "|" + " " * (width - 2) + "|",
        "|" + " " * pad + " " + upper + " " + " " * (width - len(upper) - pad - 4) + "  |",
        "|" + " " * (width - 2) + "|",
        "+" + "=" * (width - 2) + "+",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# run.py template
# ---------------------------------------------------------------------------

def _generate_run_py(project_name: str, version: str, description: str,
                     modes: list, color_scheme: dict = None) -> str:
    """Generate the complete run.py content."""

    colors = color_scheme or {
        "title": "36",       # cyan
        "menu_key": "33",    # yellow
        "menu_label": "97",  # bright white
        "success": "32",     # green
        "error": "31",       # red
        "info": "34",        # blue
        "dim": "90",         # gray
        "accent": "35",      # magenta
    }

    ascii_art = _ascii_title(project_name)
    # Escape for embedding inside a Python triple-quoted string
    ascii_art_escaped = ascii_art.replace("\\", "\\\\")

    # Build the mode entries as Python source
    modes_src = "    MODES = [\n"
    for m in modes:
        modes_src += "        {{\n"
        modes_src += f'            "key": "{m["key"]}",\n'
        modes_src += f'            "label": "{m["label"]}",\n'
        modes_src += f'            "cmd": {repr(m["cmd"])},\n'
        modes_src += f'            "desc": "{m.get("desc", "")}",\n'
        modes_src += "        }},\n"
    modes_src += "    ]"

    # Check if there's more than one mode (enables "run all" option)
    has_concurrent = len(modes) > 1

    concurrent_block = ""
    if has_concurrent:
        concurrent_block = '''
    def run_concurrent(self):
        """Run all modes concurrently using threads."""
        import threading
        self.log("Starting all modes concurrently...", "info")
        threads = []
        for mode in self.MODES:
            t = threading.Thread(
                target=self._run_command,
                args=(mode["cmd"], mode["label"]),
                daemon=True,
            )
            threads.append((t, mode["label"]))
            t.start()
            self.log(f"  Started: {mode['label']}", "success")

        self.log(f"All {len(threads)} modes running. Press Ctrl+C to stop.", "info")
        try:
            for t, label in threads:
                t.join()
        except KeyboardInterrupt:
            self.log("\\nShutting down...", "info")
'''

    concurrent_menu = ""
    concurrent_dispatch = ""
    if has_concurrent:
        concurrent_menu = f'''
        self._print(f"  {{self._c('{colors['menu_key']}')}}[A]{{self._c('0')}}  {{self._c('{colors['menu_label']}')}}Run All (concurrent){{self._c('0')}}")'''
        concurrent_dispatch = '''
            elif choice.upper() == "A":
                self.run_concurrent()
                return'''

    run_py = f'''#!/usr/bin/env python3
"""
{project_name} — Launcher
{'=' * (len(project_name) + 14)}
Standardized project launcher with interactive mode selection.
Generated by Overlord11 launcher_generator.
"""

import io
import os
import subprocess
import sys
import time
from datetime import datetime

# --- Encoding safety (Windows cp1252 guard) ---
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    # Enable ANSI escape codes on Windows 10+
    os.system("")


class Launcher:
    """Interactive project launcher with colored output and logging."""

    PROJECT_NAME = "{project_name}"
    VERSION = "{version}"
    DESCRIPTION = """{description}"""

    ASCII_ART = """{ascii_art_escaped}"""

    # Color codes (ANSI)
    COLORS = {{
        "title": "{colors['title']}",
        "menu_key": "{colors['menu_key']}",
        "menu_label": "{colors['menu_label']}",
        "success": "{colors['success']}",
        "error": "{colors['error']}",
        "info": "{colors['info']}",
        "dim": "{colors['dim']}",
        "accent": "{colors['accent']}",
    }}

{modes_src}

    def __init__(self):
        self.start_time = time.time()

    # --- ANSI helpers ---

    @staticmethod
    def _c(code: str) -> str:
        """Return ANSI escape sequence. Empty string if not a terminal."""
        if not sys.stdout.isatty():
            return ""
        return f"\\033[{{code}}m"

    def _print(self, msg: str = ""):
        """Print with encoding safety."""
        try:
            print(msg)
        except UnicodeEncodeError:
            print(msg.encode("ascii", errors="replace").decode("ascii"))

    # --- Logging ---

    def log(self, message: str, level: str = "info"):
        """Print a timestamped, color-coded log message."""
        ts = datetime.now().strftime("%H:%M:%S")
        color = self.COLORS.get(level, self.COLORS["info"])
        level_tag = level.upper().ljust(7)
        dim = self._c(self.COLORS["dim"])
        reset = self._c("0")
        clr = self._c(color)
        self._print(f"  {{dim}}[{{ts}}]{{reset}} {{clr}}{{level_tag}}{{reset}} {{message}}")

    # --- Display ---

    def show_header(self):
        """Display the ASCII title and project info."""
        c_title = self._c(self.COLORS["title"])
        c_accent = self._c(self.COLORS["accent"])
        c_dim = self._c(self.COLORS["dim"])
        c_info = self._c(self.COLORS["info"])
        reset = self._c("0")

        self._print()
        for line in self.ASCII_ART.split("\\n"):
            self._print(f"  {{c_title}}{{line}}{{reset}}")
        self._print()
        self._print(f"  {{c_accent}}{{self.DESCRIPTION}}{{reset}}")
        self._print(f"  {{c_dim}}Version {{self.VERSION}} | Python {{sys.version.split()[0]}}{{reset}}")
        self._print(f"  {{c_dim}}{'-' * 40}{{reset}}")
        self._print()

    def show_menu(self):
        """Display the run-mode menu."""
        c_key = self.COLORS["menu_key"]
        c_label = self.COLORS["menu_label"]
        c_dim = self.COLORS["dim"]
        reset = self._c("0")

        self._print(f"  {{self._c(c_label)}}Select a run mode:{{reset}}")
        self._print()
        for mode in self.MODES:
            self._print(f"  {{self._c(c_key)}}[{{mode['key']}}]{{reset}}  {{self._c(c_label)}}{{mode['label']}}{{reset}}")
            if mode.get("desc"):
                self._print(f"       {{self._c(c_dim)}}{{mode['desc']}}{{reset}}")
{concurrent_menu}
        self._print(f"  {{self._c(c_key)}}[Q]{{reset}}  {{self._c(c_dim)}}Quit{{reset}}")
        self._print()

    # --- Execution ---

    def _run_command(self, cmd: str, label: str = ""):
        """Run a shell command with live output."""
        self.log(f"Running: {{label or cmd}}", "info")
        self.log(f"Command: {{cmd}}", "dim")
        self._print()
        try:
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=sys.stdout,
                stderr=sys.stderr,
            )
            process.wait()
            if process.returncode == 0:
                self.log(f"{{label or 'Command'}} completed successfully.", "success")
            else:
                self.log(f"{{label or 'Command'}} exited with code {{process.returncode}}.", "error")
            return process.returncode
        except KeyboardInterrupt:
            self.log("\\nInterrupted by user.", "info")
            return 130
        except Exception as e:
            self.log(f"Failed to run: {{e}}", "error")
            return 1
{concurrent_block}
    def run(self):
        """Main loop: show header, menu, dispatch."""
        self.show_header()

        while True:
            self.show_menu()
            try:
                choice = input(f"  {{self._c(self.COLORS['accent'])}}> {{self._c('0')}}").strip()
            except (KeyboardInterrupt, EOFError):
                self._print()
                self.log("Goodbye!", "info")
                return 0

            if choice.upper() == "Q":
                self.log("Goodbye!", "info")
                return 0
{concurrent_dispatch}
            # Check numbered modes
            matched = [m for m in self.MODES if m["key"] == choice]
            if matched:
                self._print()
                rc = self._run_command(matched[0]["cmd"], matched[0]["label"])
                self._print()
                continue

            self.log(f"Unknown option: '{{choice}}'", "error")
            self._print()


if __name__ == "__main__":
    launcher = Launcher()
    sys.exit(launcher.run())
'''
    return run_py


# ---------------------------------------------------------------------------
# Platform shortcuts
# ---------------------------------------------------------------------------

def _generate_bat(project_name: str) -> str:
    """Generate a Windows .bat launcher that finds Python and runs run.py."""
    return dedent(f"""\
        @echo off
        title {project_name}
        setlocal enabledelayedexpansion

        :: --- Find Python ---
        :: Try PATH first
        where python >nul 2>&1
        if %ERRORLEVEL% equ 0 (
            set "PYTHON_CMD=python"
            goto :found
        )

        where python3 >nul 2>&1
        if %ERRORLEVEL% equ 0 (
            set "PYTHON_CMD=python3"
            goto :found
        )

        :: Try common install locations
        for %%P in (
            "%LOCALAPPDATA%\\Programs\\Python\\Python314\\python.exe"
            "%LOCALAPPDATA%\\Programs\\Python\\Python313\\python.exe"
            "%LOCALAPPDATA%\\Programs\\Python\\Python312\\python.exe"
            "%LOCALAPPDATA%\\Programs\\Python\\Python311\\python.exe"
            "%ProgramFiles%\\Python314\\python.exe"
            "%ProgramFiles%\\Python313\\python.exe"
            "%ProgramFiles%\\Python312\\python.exe"
            "%ProgramFiles%\\Python311\\python.exe"
            "%USERPROFILE%\\AppData\\Local\\Microsoft\\WindowsApps\\python.exe"
        ) do (
            if exist %%P (
                set "PYTHON_CMD=%%P"
                goto :found
            )
        )

        echo.
        echo  ERROR: Python not found.
        echo  Install Python from https://www.python.org/downloads/
        echo  Make sure to check "Add Python to PATH" during installation.
        echo.
        pause
        exit /b 1

        :found
        echo  Found Python: %PYTHON_CMD%
        echo.

        :: --- Run the launcher ---
        cd /d "%~dp0"
        %PYTHON_CMD% run.py
        if %ERRORLEVEL% neq 0 (
            echo.
            echo  run.py exited with error code %ERRORLEVEL%
            pause
        )
    """)


def _generate_command(project_name: str) -> str:
    """Generate a macOS .command launcher (double-clickable shell script)."""
    return dedent(f"""\
        #!/usr/bin/env bash
        # {project_name} — macOS Launcher
        # Double-click this file in Finder to launch.

        cd "$(dirname "$0")"

        # Find Python
        if command -v python3 &>/dev/null; then
            PYTHON_CMD="python3"
        elif command -v python &>/dev/null; then
            PYTHON_CMD="python"
        else
            echo ""
            echo "  ERROR: Python not found."
            echo "  Install from https://www.python.org/downloads/"
            echo ""
            read -p "  Press Enter to close..."
            exit 1
        fi

        echo "  Found Python: $PYTHON_CMD"
        echo ""
        $PYTHON_CMD run.py
    """)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_launcher(project_dir: str, project_name: str, version: str = "0.1.0",
                      description: str = "", modes: list = None,
                      color_scheme: dict = None) -> dict:
    """Generate run.py and platform shortcuts in the project directory."""
    pdir = Path(project_dir).resolve()
    if not pdir.is_dir():
        return {"status": "error", "error": f"Not a directory: {project_dir}"}

    if not modes:
        modes = [{"key": "1", "label": "Run", "cmd": f"python -m {project_name.lower().replace(' ', '_')}", "desc": ""}]

    description = description or f"A {project_name} project"

    files_created = []

    # Generate run.py
    run_py = _generate_run_py(project_name, version, description, modes, color_scheme)
    (pdir / "run.py").write_text(run_py, encoding="utf-8")
    files_created.append("run.py")

    # Generate Windows shortcut
    bat = _generate_bat(project_name)
    (pdir / "run.bat").write_text(bat, encoding="utf-8")
    files_created.append("run.bat")

    # Generate macOS shortcut
    command = _generate_command(project_name)
    command_path = pdir / "run.command"
    command_path.write_text(command, encoding="utf-8")
    files_created.append("run.command")
    # Make it executable (no-op on Windows, works on macOS/Linux)
    try:
        os.chmod(command_path, 0o755)
    except OSError:
        pass

    return {
        "status": "success",
        "project_dir": str(pdir),
        "files_created": files_created,
        "modes": len(modes),
        "has_concurrent": len(modes) > 1,
    }


# ---------------------------------------------------------------------------
# CLI Interface
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Overlord11 Launcher Generator")
    parser.add_argument("--project_dir", required=True, help="Path to project directory")
    parser.add_argument("--project_name", required=True, help="Project name for title")
    parser.add_argument("--version", default="0.1.0", help="Project version")
    parser.add_argument("--description", default="", help="Short project description")
    parser.add_argument("--modes", default="[]",
                        help='JSON array of run modes: [{"key":"1","label":"CLI","cmd":"python cli.py","desc":"..."}]')
    parser.add_argument("--color_scheme", default="{}",
                        help="JSON object overriding default ANSI color codes")
    parser.add_argument("--session_id", default=None, help="Session ID for logging")

    args = parser.parse_args()
    modes = json.loads(args.modes)
    color_scheme = json.loads(args.color_scheme) or None
    start = time.time()

    result = generate_launcher(
        project_dir=args.project_dir,
        project_name=args.project_name,
        version=args.version,
        description=args.description,
        modes=modes,
        color_scheme=color_scheme,
    )

    duration_ms = (time.time() - start) * 1000

    if args.session_id:
        log_tool_invocation(
            session_id=args.session_id,
            tool_name="launcher_generator",
            params={"project_dir": args.project_dir, "project_name": args.project_name},
            result={"status": result.get("status", "unknown")},
            duration_ms=duration_ms,
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
