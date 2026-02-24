import subprocess
import json
import os
from typing import Optional

def search_file_content(
    pattern: str,
    dir_path: Optional[str] = None,
    include: Optional[str] = None,
    no_ignore: Optional[bool] = False,
    case_sensitive: Optional[bool] = False,
    fixed_strings: Optional[bool] = False,
    before: Optional[int] = 0,
    after: Optional[int] = 0,
    context: Optional[int] = 0
) -> str:
    """
    FAST, optimized search powered by `ripgrep`. Searches for a pattern in files and returns the output.

    Args:
        pattern: The pattern to search for.
        dir_path: Directory or file to search. Defaults to current working directory.
        include: Glob pattern to filter files (e.g., '*.ts').
        no_ignore: If true, searches all files including those usually ignored.
        case_sensitive: If true, search is case-sensitive. Defaults to false.
        fixed_strings: If true, treats the `pattern` as a literal string. Defaults to false.
        before: Show this many lines before each match.
        after: Show this many lines after each match.
        context: Show this many lines of context around each match.

    Returns:
        A JSON string representing the search results, or an error message.
    """
    cmd = ["rg", "--json", pattern]

    if dir_path:
        cmd.append(dir_path)
    else:
        cmd.append(os.getcwd()) # Default to current working directory

    if include:
        cmd.extend(["-g", include])
    if no_ignore:
        cmd.append("--no-ignore")
    if case_sensitive:
        cmd.append("--case-sensitive")
    if fixed_strings:
        cmd.append("--fixed-strings")
    if before > 0:
        cmd.extend(["--before-context", str(before)])
    if after > 0:
        cmd.extend(["--after-context", str(after)])
    if context > 0:
        cmd.extend(["--context", str(context)])
    
    # Max output limit
    cmd.extend(["--max-count", "20000"]) # Corresponds to "max 20k matches" in description

    try:
        process = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8')
        return process.stdout
    except subprocess.CalledProcessError as e:
        return f"Error executing ripgrep: {e.stderr}"
    except FileNotFoundError:
        return "Error: `ripgrep` command not found. Please ensure ripgrep is installed and in your PATH."
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

if __name__ == "__main__":
    # Create some dummy files for testing
    if not os.path.exists("test_search_dir"):
        os.makedirs("test_search_dir")
    with open("test_search_dir/fileA.txt", "w") as f:
        f.write("This is a test line.\nAnother test line.\nFinal line here.\n")
    with open("test_search_dir/fileB.py", "w") as f:
        f.write("def my_function():\n    print('Hello, world!')\n# This is a comment\n")

    print("--- Searching for 'test' in test_search_dir (case-insensitive) ---")
    result = search_file_content(pattern="test", dir_path="test_search_dir")
    print(result)

    print("\n--- Searching for 'line' in fileA.txt with context ---")
    result = search_file_content(pattern="line", dir_path="test_search_dir/fileA.txt", context=1)
    print(result)

    print("\n--- Searching for 'print' in .py files (case-sensitive) ---")
    result = search_file_content(pattern="print", dir_path="test_search_dir", include="*.py", case_sensitive=True)
    print(result)
    
    print("\n--- Searching for non-existent pattern ---")
    result = search_file_content(pattern="nonexistent", dir_path="test_search_dir")
    print(result)

    # Cleanup dummy files
    os.remove("test_search_dir/fileA.txt")
    os.remove("test_search_dir/fileB.py")
    os.rmdir("test_search_dir")
