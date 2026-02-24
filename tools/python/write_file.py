import argparse
import os
import sys

def write_file(file_path: str, content: str,
               mode: str = "overwrite", encoding: str = "utf-8") -> str:
    """
    Writes content to a specified file in the local filesystem.

    The user has the ability to modify `content`. If modified, this will be stated in the response.

    Args:
        file_path: The path to the file to write to. If the path is relative and doesn't start
                   with 'working-output', it will be automatically placed in the working-output folder.
        content:   The content to write to the file.
        mode:      'overwrite' (default) replaces any existing content;
                   'append' adds content to the end of the file.
        encoding:  File encoding to use when writing. Defaults to 'utf-8'.

    Returns:
        A message indicating the success or failure of the write operation.
    """
    if mode not in ("overwrite", "append"):
        return f"Error: mode must be 'overwrite' or 'append', got '{mode}'"

    open_mode = "a" if mode == "append" else "w"

    try:
        # Get the directory of the current script to resolve paths relative to the project root
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.normpath(os.path.join(script_dir, '..', '..'))

        # Check if the path is absolute or relative
        if not os.path.isabs(file_path):
            # If it's relative and doesn't already start with working-output, prepend it
            if not file_path.startswith('working-output'):
                file_path = os.path.join('working-output', file_path)

            # Make it absolute relative to project root
            file_path = os.path.normpath(os.path.join(project_root, file_path))

        # Ensure the directory exists, but only if a directory is specified in file_path
        dir_name = os.path.dirname(file_path)
        if dir_name:  # Only create directory if dir_name is not an empty string
            os.makedirs(dir_name, exist_ok=True)

        with open(file_path, open_mode, encoding=encoding) as f:
            f.write(content)

        action = "Appended to" if mode == "append" else "Successfully wrote to"
        return f"{action} file: {file_path}"
    except (OSError, LookupError) as e:
        return f"Error writing to file {file_path}: {e}"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Write content to a file")
    p.add_argument("--path", required=True, help="Path to the file to write")
    p.add_argument("--content", required=True, help="Content to write")
    p.add_argument("--mode", default="overwrite", choices=["overwrite", "append"],
                   help="Write mode: overwrite (default) or append")
    p.add_argument("--encoding", default="utf-8", help="File encoding (default: utf-8)")
    args = p.parse_args()
    print(write_file(args.path, args.content, args.mode, args.encoding))
    sys.exit(0)

