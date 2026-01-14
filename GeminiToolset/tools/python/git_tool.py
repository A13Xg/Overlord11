import subprocess

def git_tool(command: str) -> str:
    """
    Executes a specified git command in the current working directory and returns the output.

    Args:
        command: The git command to execute (e.g., 'status', 'add .', 'commit -m "message"').
                 Do not include the 'git' prefix.

    Returns:
        The standard output and standard error of the git command.
        Returns an error message if the command fails.
    """
    full_command = f"git {command}"
    try:
        # Use shell=True for simpler command parsing if the command contains multiple arguments
        # and relies on shell features. However, it can be a security risk if the command
        # comes from untrusted user input directly. For this tool, we assume the command
        # is constructed internally or validated.
        result = subprocess.run(full_command, shell=True, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Error executing git command: {e}\nStdout: {e.stdout}\nStderr: {e.stderr}"
    except FileNotFoundError:
        return "Error: 'git' command not found. Please ensure Git is installed and in your PATH."

if __name__ == "__main__":
    # Example usage:
    print("--- Git Status ---")
    print(git_tool("status"))

    # Assuming there are changes to add/commit for these examples to work
    # print("\n--- Git Add (example) ---")
    # print(git_tool("add ."))
    # print("\n--- Git Commit (example) ---")
    # print(git_tool("commit -m \"Test commit from git_tool\""))

    print("\n--- Git Log (last 2 commits) ---")
    print(git_tool("log -n 2 --oneline"))

    print("\n--- Git Invalid Command Example ---")
    print(git_tool("invalid-git-command"))
