import os

def read_file(file_path: str, limit: int = None, offset: int = 0) -> str:
    """
    Reads and returns the content of a specified file. If the file is large, the content will be truncated.
    The tool's response will clearly indicate if truncation has occurred and will provide details on how to read more of the file
    using the 'offset' and 'limit' parameters. Handles text files.
    
    Args:
        file_path: The path to the file to read.
        limit: Optional: For text files, maximum number of lines to read. Use with 'offset' to paginate through large files.
               If omitted, reads the entire file (if feasible, up to a default limit).
        offset: Optional: For text files, the 0-based line number to start reading from. Requires 'limit' to be set.
                Use for paginating through large files.

    Returns:
        The content of the file as a string, or an error message.
    """
    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"
    
    if not os.path.isfile(file_path):
        return f"Error: {file_path} is not a file."

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
            if limit is not None:
                start_line = offset
                end_line = offset + limit
                content_lines = lines[start_line:end_line]
                
                truncated_message = ""
                if start_line > 0 or end_line < len(lines):
                    truncated_message = f"\n(Content truncated. Showing lines {start_line}-{end_line-1} of {len(lines)}. Use offset and limit to paginate.)"
                
                return "".join(content_lines) + truncated_message
            else:
                return "".join(lines)

    except Exception as e:
        return f"Error reading file {file_path}: {e}"

