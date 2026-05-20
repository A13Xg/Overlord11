
from typing import Any, Dict


def ok(data: Any) -> Dict[str, Any]:
    return {"success": True, "data": data, "error": None}


def fail(message: str) -> Dict[str, Any]:
    return {"success": False, "data": None, "error": message}

