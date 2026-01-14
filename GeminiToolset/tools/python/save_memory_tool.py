import os
from datetime import datetime

def save_memory(fact: str, file_path: str = '../../Memory.md') -> str:
    """
    Saves a specific piece of information or fact to your long-term memory. This tool appends the fact to a designated memory file.

    Args:
        fact: The specific fact or piece of information to remember. Should be a clear, self-contained statement.
        file_path: The path to the memory file. Defaults to '../../Memory.md'.

    Returns:
        A message indicating the success or failure of saving the memory.
    """
    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Construct the absolute path to the memory file
    # file_path is relative to the script_dir, so we join them.
    # os.path.normpath handles '..'
    absolute_file_path = os.path.normpath(os.path.join(script_dir, file_path))

    # Ensure the directory for the memory file exists
    os.makedirs(os.path.dirname(absolute_file_path), exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    memory_entry = f"[{timestamp}] {fact}\n"

    try:
        with open(absolute_file_path, 'a', encoding='utf-8') as f:
            f.write(memory_entry)
        return f"Successfully saved memory to {absolute_file_path}"
    except IOError as e:
        return f"Error saving memory to {absolute_file_path}: {e}"

if __name__ == "__main__":
    # Test cases
    print("--- Saving a test fact to default Memory.md ---")
    result = save_memory("User prefers dark theme.")
    print(result)

    print("\n--- Saving another fact ---")
    result = save_memory("Project uses Python for backend.")
    print(result)

    print("\n--- Saving a fact to a custom file ---")
    custom_memory_file = "../temp_memory.txt"
    result = save_memory("This is a custom memory entry.", custom_memory_file)
    print(result)

    # Verify content of the default Memory.md
    default_memory_path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../Memory.md'))
    print(f"\n--- Content of {default_memory_path} ---")
    try:
        with open(default_memory_path, 'r', encoding='utf-8') as f:
            print(f.read())
    except FileNotFoundError:
        print(f"{default_memory_path} not found.")

    # Verify content of the custom memory file
    custom_memory_absolute_path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), custom_memory_file))
    print(f"\n--- Content of {custom_memory_absolute_path} ---")
    try:
        with open(custom_memory_absolute_path, 'r', encoding='utf-8') as f:
            print(f.read())
    except FileNotFoundError:
        print(f"{custom_memory_absolute_path} not found.")
    
    # Cleanup custom memory file
    if os.path.exists(custom_memory_absolute_path):
        os.remove(custom_memory_absolute_path)
