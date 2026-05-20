
import json
from pathlib import Path
from typing import Any, Literal, Dict

from ._common import fail, ok
from .app import mcp


MEMORY_FILE = Path(__file__).parent / ".memory_store.json"


@mcp.tool(
    name="store_memory",
    description="Store and retrieve JSON-serializable values in namespaced memory and return operation-specific data. Use this for persistent shared state across agent tool calls.",
)
def store_memory(
    operation: Literal["get", "set", "delete", "list", "search"],
    key: str = "",
    value: Any = None,
    namespace: str = "default",
    query: str = "",
) -> Dict[str, Any]:
    """Operate on namespaced key-value memory.

    Args:
        operation: Memory action (get, set, delete, list, search).
        key: Key for get/set/delete operations.
        value: Value to store for set operation.
        namespace: Logical key namespace.
        query: Search substring for search operation.
    """
    try:
        store = json.loads(MEMORY_FILE.read_text(encoding="utf-8")) if MEMORY_FILE.exists() else {}
        ns = store.setdefault(namespace, {})
        if operation in {"get", "set", "delete"} and not key:
            return fail("key is required for get, set, and delete.")
        if operation == "set" and value is None:
            return fail("value is required for set.")
        if operation == "search" and query == "":
            return fail("query is required for search.")

        if operation == "get":
            data = {"key": key, "value": ns.get(key)}
        elif operation == "set":
            ns[key] = value
            MEMORY_FILE.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")
            data = {"key": key, "stored": True}
        elif operation == "delete":
            existed = key in ns
            if existed:
                del ns[key]
                MEMORY_FILE.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")
            data = {"key": key, "deleted": existed}
        elif operation == "list":
            data = sorted(ns.keys())
        else:
            data = sorted([k for k in ns.keys() if query in k])
        return ok(data)
    except Exception as exc:
        return fail(f"Memory operation failed: {exc}")

