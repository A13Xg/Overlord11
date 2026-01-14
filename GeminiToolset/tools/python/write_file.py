import os

def write_file(file_path: str, content: str) -> str:
    """
    Writes content to a specified file in the local filesystem.

    The user has the ability to modify `content`. If modified, this will be stated in the response.

    Args:
        file_path: The path to the file to write to.
        content: The content to write to the file.

    Returns:
        A message indicating the success or failure of the write operation.
    """
    try:
        # Ensure the directory exists, but only if a directory is specified in file_path
        dir_name = os.path.dirname(file_path)
        if dir_name: # Only create directory if dir_name is not an empty string
            os.makedirs(dir_name, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to file: {file_path}"
    except Exception as e:
        return f"Error writing to file {file_path}: {e}"

