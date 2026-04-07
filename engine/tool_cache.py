"""
Overlord11 Engine — Tool Result Cache
=======================================
Hash-keyed persistent cache for tool results.

Cache key   = sha256(tool_name + canonical_json(params))
Cache store = workspace/tool_cache.json   (survives across sessions)
Eviction    = LRU when max_entries is reached
Expiry      = per-entry TTL checked on read (lazy expiry)

Tools with side-effects are excluded by default and can be extended
via the `excluded_tools` config list.  Only status="success" results
are ever stored.

Thread safety: all public methods acquire a threading.Lock so the
cache is safe to call from the engine's thread-pool executor.
"""

import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("overlord11.tool_cache")

# Tools that must never be cached — they have side-effects or
# return time/state-dependent results.
_DEFAULT_EXCLUDED: frozenset[str] = frozenset({
    "write_file",
    "replace",
    "run_shell_command",
    "git_tool",
    "datetime_tool",
    "web_fetch",
    "web_scraper",
    "http_request",
    "database_tool",
    "computer_control",
    "session_clean",
    "cleanup_tool",
    "launcher_generator",
    "scaffold_generator",
    "project_docs_init",
    "notification_tool",
})


class ToolCache:
    """
    Persistent LRU tool result cache.

    Config dict (from config.json → cache):
        enabled        (bool)  default True
        ttl_seconds    (int)   default 3600  (1 hour; 0 = never expire)
        max_entries    (int)   default 500
        excluded_tools (list)  additional tools to skip (merged with defaults)
        cache_file     (str)   default "workspace/tool_cache.json"
    """

    def __init__(self, config: dict, project_root: Path) -> None:
        self.enabled: bool = config.get("enabled", True)
        self.ttl_seconds: int = int(config.get("ttl_seconds", 3600))
        self.max_entries: int = int(config.get("max_entries", 500))

        extra_excluded = set(config.get("excluded_tools", []))
        self._excluded: frozenset[str] = _DEFAULT_EXCLUDED | extra_excluded

        cache_file_rel = config.get("cache_file", "workspace/tool_cache.json")
        self._cache_file: Path = project_root / cache_file_rel
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)

        # In-memory store: key → {result, tool, params_hash, stored_at, hits}
        # Ordered by insertion / last-access for LRU eviction.
        self._store: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._dirty = False  # track whether store has unsaved changes

        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_cacheable(self, tool_name: str) -> bool:
        """Return True if this tool's results can be cached."""
        return self.enabled and tool_name not in self._excluded

    def get(self, tool_name: str, params: dict) -> Optional[dict]:
        """
        Look up a cached result.

        Returns the stored result dict (with an extra `cached=True` key)
        if a valid, non-expired entry exists; None otherwise.
        """
        if not self.is_cacheable(tool_name):
            return None

        key = self._make_key(tool_name, params)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None

            # Check TTL
            if self.ttl_seconds > 0:
                age = time.time() - entry["stored_at"]
                if age > self.ttl_seconds:
                    del self._store[key]
                    self._dirty = True
                    log.debug("Cache expired: %s (age=%.0fs)", tool_name, age)
                    return None

            # LRU: move to end by re-inserting
            self._store.pop(key)
            self._store[key] = entry
            entry["hits"] = entry.get("hits", 0) + 1
            self._dirty = True

            log.debug("Cache hit: %s (hits=%d)", tool_name, entry["hits"])
            return {**entry["result"], "cached": True, "cache_age_s": round(time.time() - entry["stored_at"])}

    def put(self, tool_name: str, params: dict, result: dict) -> None:
        """
        Store a successful tool result.

        Only stores when status == "success".  Evicts the oldest entry
        (LRU) when max_entries is reached.
        """
        if not self.is_cacheable(tool_name):
            return
        if result.get("status") != "success":
            return

        key = self._make_key(tool_name, params)
        with self._lock:
            # Remove existing entry so insertion order reflects recency
            self._store.pop(key, None)

            # LRU eviction
            while len(self._store) >= self.max_entries:
                oldest_key = next(iter(self._store))
                evicted = self._store.pop(oldest_key)
                log.debug("Cache evict (LRU): %s", evicted.get("tool", oldest_key))

            self._store[key] = {
                "tool": tool_name,
                "result": result,
                "stored_at": time.time(),
                "hits": 0,
            }
            self._dirty = True
            log.debug("Cache store: %s (entries=%d)", tool_name, len(self._store))

        self._save()

    def invalidate(self, tool_name: Optional[str] = None) -> int:
        """
        Remove cache entries for a specific tool (or all entries if None).
        Returns the count of entries removed.
        """
        with self._lock:
            if tool_name is None:
                count = len(self._store)
                self._store.clear()
            else:
                keys = [k for k, v in self._store.items() if v.get("tool") == tool_name]
                for k in keys:
                    del self._store[k]
                count = len(keys)
            if count:
                self._dirty = True
        if count:
            self._save()
        return count

    def stats(self) -> dict:
        """Return cache statistics."""
        with self._lock:
            entries = list(self._store.values())
        total_hits = sum(e.get("hits", 0) for e in entries)
        tools = {}
        for e in entries:
            t = e.get("tool", "unknown")
            tools[t] = tools.get(t, 0) + 1
        return {
            "enabled": self.enabled,
            "entries": len(entries),
            "max_entries": self.max_entries,
            "ttl_seconds": self.ttl_seconds,
            "total_hits": total_hits,
            "tools": tools,
            "cache_file": str(self._cache_file),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load cache from disk. Silently ignores missing or corrupt files."""
        if not self._cache_file.exists():
            return
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
            self._store = data.get("entries", {})
            log.info("Tool cache loaded: %d entries from %s", len(self._store), self._cache_file)
        except Exception as exc:
            log.warning("Tool cache load failed (%s) — starting empty", exc)
            self._store = {}

    def _save(self) -> None:
        """Persist cache to disk. Called after every put/evict/invalidate."""
        with self._lock:
            if not self._dirty:
                return
            snapshot = dict(self._store)
            self._dirty = False
        try:
            payload = json.dumps(
                {"entries": snapshot, "saved_at": time.time()},
                ensure_ascii=False,
                indent=2,
                default=str,
            )
            self._cache_file.write_text(payload, encoding="utf-8")
        except Exception as exc:
            log.warning("Tool cache save failed: %s", exc)

    # ------------------------------------------------------------------
    # Key generation
    # ------------------------------------------------------------------

    @staticmethod
    def _make_key(tool_name: str, params: dict) -> str:
        """
        Produce a stable SHA-256 cache key from the tool name and params.

        Params are serialized with sorted keys so that insertion order
        differences do not produce different keys.
        """
        canonical = json.dumps(
            {"tool": tool_name, "params": params},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
