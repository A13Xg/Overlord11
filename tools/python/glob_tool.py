import glob
import os

def glob(pattern: str, dir_path: str = None, case_sensitive: bool = False, respect_gemini_ignore: bool = True, respect_git_ignore: bool = True) -> list[str]:
    """
    Efficiently finds files matching specific glob patterns (e.g., `src/**/*.ts`, `**/*.md`), returning absolute paths sorted by modification time (newest first).
    Ideal for quickly locating files based on their name or path structure, especially in large codebases.

    Args:
        pattern: The glob pattern to match against (e.g., '**/*.py', 'docs/*.md').
        dir_path: Optional: The absolute path to the directory to search within. If omitted, searches the root directory.
        case_sensitive: Optional: Whether the search should be case-sensitive. Defaults to false. (Advanced filtering not implemented in this basic version).
        respect_gemini_ignore: Optional: Whether to respect .geminiignore patterns when finding files. Defaults to true. (Advanced filtering not implemented in this basic version).
        respect_git_ignore: Optional: Whether to respect .gitignore patterns when finding files. Only available in git repositories. Defaults to true. (Advanced filtering not implemented in this basic version).

    Returns:
        A list of absolute paths to files matching the pattern, sorted by modification time (newest first).
    """
    search_path = dir_path if dir_path else os.getcwd()
    full_pattern = os.path.join(search_path, pattern)

    # glob.glob does not support ** for recursive search prior to Python 3.5.
    # Assuming Python 3.5+ for '**' support.
    # For a more robust solution that handles .gitignore, .geminiignore,
    # and case sensitivity, a library like `pathspec` or `ripgrep` integration would be needed.
    matched_files = glob.glob(full_pattern, recursive=True)

    # Get modification times and sort
    files_with_mtime = []
    for f in matched_files:
        try:
            mtime = os.path.getmtime(f)
            files_with_mtime.append((f, mtime))
        except OSError:
            # Handle cases where file might have been deleted between glob and stat call
            continue

    files_with_mtime.sort(key=lambda x: x[1], reverse=True)

    return [f[0] for f in files_with_mtime]

if __name__ == "__main__":
    # Create some dummy files for testing
    if not os.path.exists("test_dir"):
        os.makedirs("test_dir")
    with open("test_dir/file1.txt", "w") as f:
        f.write("content")
    with open("test_dir/file2.py", "w") as f:
        f.write("import os")
    if not os.path.exists("test_dir/subdir"):
        os.makedirs("test_dir/subdir")
    with open("test_dir/subdir/file3.txt", "w") as f:
        f.write("more content")
    os.utime("test_dir/file1.txt", (os.stat("test_dir/file1.txt").st_atime, os.stat("test_dir/file1.txt").st_mtime + 10)) # Make file1 newer

    print("--- Globbing for all files in current dir and subdirs ---")
    print(glob_tool("**/*"))

    print("\n--- Globbing for .txt files in test_dir ---")
    print(glob_tool("*.txt", dir_path="test_dir"))

    print("\n--- Globbing for .py files recursively from current dir ---")
    print(glob_tool("**/*.py"))

    print("\n--- Globbing for non-existent files ---")
    print(glob_tool("nonexistent/*.xyz"))

    # Clean up dummy files
    os.remove("test_dir/file1.txt")
    os.remove("test_dir/file2.py")
    os.remove("test_dir/subdir/file3.txt")
    os.rmdir("test_dir/subdir")
    os.rmdir("test_dir")
