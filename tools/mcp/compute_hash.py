
import hashlib
from pathlib import Path
from typing import Literal, Dict, Any

from ._common import fail, ok
from .app import mcp


@mcp.tool(
    name="compute_hash",
    description="Compute a hash for a string or file and return algorithm/hash/input_type in `data`. Use this instead of shell hashing commands for stable structured output.",
)
def compute_hash(
    input: str,
    input_type: Literal["string", "file"] = "string",
    algorithm: Literal["md5", "sha1", "sha256", "sha512"] = "sha256",
) -> Dict[str, Any]:
    """Compute a hash digest.

    Args:
        input: Raw string content or file path.
        input_type: Indicates whether input is a string or a file path.
        algorithm: Hash algorithm to use.
    """
    try:
        hasher = hashlib.new(algorithm)
        if input_type == "file":
            p = Path(input)
            if not p.exists() or not p.is_file():
                return fail(f"File not found at '{p}'.")
            hasher.update(p.read_bytes())
        else:
            hasher.update(input.encode("utf-8"))
        return ok({"algorithm": algorithm, "hash": hasher.hexdigest(), "input_type": input_type})
    except Exception as exc:
        return fail(f"Hash computation failed: {exc}")

