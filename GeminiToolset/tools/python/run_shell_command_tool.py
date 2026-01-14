import subprocess
import os

def run_shell_command(command: str, dir_path: str = None) -> dict:
    """
    This tool executes a given shell command as `powershell.exe -NoProfile -Command <command>`.
    Command can start background processes using PowerShell constructs such as `Start-Process -NoNewWindow` or `Start-Job`.

    Args:
        command: Exact command to execute as `powershell.exe -NoProfile -Command <command>`
        dir_path: (OPTIONAL) The path of the directory to run the command in. If not provided, the project root directory is used.

    Returns:
        A dictionary containing:
        - "Command": The executed command.
        - "Directory": The directory where the command was executed.
        - "Stdout": Standard output of the command.
        - "Stderr": Standard error of the command.
        - "Error": Any error message from the subprocess module.
        - "Exit Code": The exit code of the command.
    """
    original_dir = os.getcwd()
    execution_dir = original_dir

    if dir_path:
        if not os.path.isdir(dir_path):
            return {
                "Command": command,
                "Directory": dir_path,
                "Stdout": "(empty)",
                "Stderr": f"Error: Directory not found: {dir_path}",
                "Error": "DirectoryNotFound",
                "Exit Code": 1
            }
        execution_dir = dir_path
        os.chdir(execution_dir)

    stdout_output = "(empty)"
    stderr_output = "(empty)"
    error_message = "(none)"
    exit_code = None

    try:
        # Use powershell.exe -NoProfile -Command for consistency with the tool definition
        # Using shell=True for this specific context, as the command is passed as a string to PowerShell.
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            check=False # Do not raise CalledProcessError for non-zero exit codes
        )
        stdout_output = result.stdout.strip() if result.stdout else "(empty)"
        stderr_output = result.stderr.strip() if result.stderr else "(empty)"
        exit_code = result.returncode

        if result.returncode != 0 and not stderr_output:
            # If there's an error but no stderr, it might be due to a PowerShell-specific error
            stderr_output = f"Command failed with exit code {result.returncode} but no stderr output was captured."

    except FileNotFoundError:
        error_message = "'powershell.exe' not found. Ensure PowerShell is installed and in your PATH."
        exit_code = 1
    except Exception as e:
        error_message = str(e)
        exit_code = 1
    finally:
        # Always change back to the original directory
        os.chdir(original_dir)

    return {
        "Command": command,
        "Directory": execution_dir,
        "Stdout": stdout_output,
        "Stderr": stderr_output,
        "Error": error_message,
        "Exit Code": exit_code
    }

if __name__ == "__main__":
    # Example usage:
    print("--- Running 'echo Hello World' ---")
    result = run_shell_command("echo Hello World")
    for k, v in result.items():
        print(f"{k}: {v}")

    print("\n--- Running 'dir' (or 'ls' on Linux) in current directory ---")
    result = run_shell_command("dir") # Use 'ls' on Linux
    for k, v in result.items():
        print(f"{k}: {v}")

    print("\n--- Running 'dir' in a non-existent directory ---")
    result = run_shell_command("dir", dir_path="non_existent_dir")
    for k, v in result.items():
        print(f"{k}: {v}")

    print("\n--- Running a command that produces stderr ---")
    # This command will produce an error if 'nonexistentcommand' is not found
    result = run_shell_command("nonexistentcommand")
    for k, v in result.items():
        print(f"{k}: {v}")

    print("\n--- Running a Python script and capturing output ---")
    # Create a dummy Python script
    with open("test_script.py", "w") as f:
        f.write("import sys\nprint('Hello from Python')\nsys.stderr.write('Error from Python\n')\nsys.exit(0)")
    result = run_shell_command("python test_script.py")
    for k, v in result.items():
        print(f"{k}: {v}")
    os.remove("test_script.py")
