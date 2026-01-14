from datetime import datetime

def get_datetime(format_string: str = None) -> str:
    """
    Returns the current date and time, optionally formatted as a string.

    Args:
        format_string: Optional: A format string (e.g., '%Y-%m-%d %H:%M:%S') to specify the output format.
                       If not provided, a default ISO format will be used.

    Returns:
        The current date and time as a formatted string.
    """
    now = datetime.now()
    if format_string:
        return now.strftime(format_string)
    else:
        return now.isoformat()

if __name__ == "__main__":
    # Example usage:
    print(f"Current datetime (default ISO): {get_datetime()}")
    print(f"Current datetime (custom format): {get_datetime('%Y-%m-%d %H:%M:%S')}")
    print(f"Current date: {get_datetime('%Y-%m-%d')}")
    print(f"Current time: {get_datetime('%H:%M:%S')}")
