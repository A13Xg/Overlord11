import os

def write_file(file_path: str, content: str) -> str:
    """
    Writes content to a specified file in the local filesystem.

    The user has the ability to modify `content`. If modified, this will be stated in the response.

    Args:
        file_path: The path to the file to write to. If the path is relative and doesn't start
                   with 'working-output', it will be automatically placed in the working-output folder.
        content: The content to write to the file.

    Returns:
        A message indicating the success or failure of the write operation.
    """
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
        if dir_name: # Only create directory if dir_name is not an empty string
            os.makedirs(dir_name, exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to file: {file_path}"
    except Exception as e:
        return f"Error writing to file {file_path}: {e}"

