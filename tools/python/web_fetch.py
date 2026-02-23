import requests

def web_fetch(url: str) -> str:
    """
    Performs a basic HTTP GET request to a specified URL and returns the response content as plain text.

    Args:
        url: The URL to fetch content from (e.g., 'https://example.com').

    Returns:
        The content of the web page as a string, or an error message if the request fails.
    """
    try:
        response = requests.get(url, timeout=10) # 10-second timeout
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
        return response.text
    except requests.exceptions.HTTPError as errh:
        return f"HTTP Error: {errh}"
    except requests.exceptions.ConnectionError as errc:
        return f"Error Connecting: {errc}"
    except requests.exceptions.Timeout as errt:
        return f"Timeout Error: {errt}"
    except requests.exceptions.RequestException as err:
        return f"An unexpected error occurred: {err}"

if __name__ == "__main__":
    # Example usage:
    print("--- Fetching content from example.com ---")
    content = web_fetch("https://example.com")
    print(content[:500]) # Print first 500 characters

    print("\n--- Fetching content from a non-existent URL (expect error) ---")
    error_content = web_fetch("https://nonexistent-website-12345.com")
    print(error_content)

    print("\n--- Fetching content from an invalid URL format (expect error) ---")
    invalid_url_content = web_fetch("htp://invalid-url")
    print(invalid_url_content)

    print("\n--- Fetching content from a valid URL (e.g., a JSON endpoint if available) ---")
    # You might need to change this URL to a publicly available one that returns some text or JSON
    # For instance, a simple API endpoint like 'https://jsonplaceholder.typicode.com/todos/1'
    # if you want to test JSON parsing.
    json_content = web_fetch("https://jsonplaceholder.typicode.com/todos/1")
    print(json_content)
