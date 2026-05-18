import tempfile
import unittest
from pathlib import Path

from engine.tool_cache import ToolCache


class ToolCacheShapeTests(unittest.TestCase):
    def test_cache_stores_inner_payload_and_returns_consistent_shape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            cache = ToolCache(config={"enabled": True, "ttl_seconds": 3600, "cache_file": "cache.json"}, project_root=root)
            result = {
                "status": "success",
                "result": {"status": "success", "file": "x.zip", "file_count": 2},
                "tool": "zip_tool",
                "duration_ms": 1.0,
            }
            cache.put("zip_tool", {"action": "list", "file": "x.zip"}, result)
            hit = cache.get("zip_tool", {"action": "list", "file": "x.zip"})
            self.assertIsInstance(hit, dict)
            self.assertIn("payload", hit)
            self.assertEqual(hit["payload"].get("file"), "x.zip")
            self.assertEqual(hit["payload"].get("file_count"), 2)


if __name__ == "__main__":
    unittest.main()
