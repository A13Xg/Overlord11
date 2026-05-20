
import json
from typing import Literal, Dict, Any

import requests

from ._common import fail, ok
from .app import mcp


@mcp.tool(
    name="fetch_url",
    description="Send an HTTP request and return status/content_type/body/headers in `data`. Prefer this over run_command curl for predictable, typed HTTP responses.",
)
def fetch_url(
    url: str,
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"] = "GET",
        headers: Dict[str, str] = {},
    body: str = "",
    timeout_seconds: int = 15,
    parse_as: Literal["text", "json", "auto"] = "auto",
    ) -> Dict[str, Any]:
    """Fetch a URL.

    Args:
        url: Full URL including scheme.
        method: HTTP method.
        headers: Request headers.
        body: Request body text.
        timeout_seconds: Timeout in seconds.
        parse_as: Body parsing mode.
    """
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            data=body if body else None,
            timeout=timeout_seconds,
        )
        content_type = response.headers.get("Content-Type", "")
        if parse_as == "json" or (parse_as == "auto" and "json" in content_type.lower()):
            try:
                parsed = response.json()
                body_value = json.dumps(parsed, ensure_ascii=False)
            except Exception:
                body_value = response.text
        else:
            body_value = response.text
        return ok(
            {
                "status_code": response.status_code,
                "content_type": content_type,
                "body": body_value,
                "headers": dict(response.headers),
            }
        )
    except Exception as exc:
        return fail(
            f"HTTP request failed for '{url}': {exc}. Check URL, method, headers, and connectivity."
        )

