"""
Overlord11 — Job Conflict Detector
====================================
Analyses job prompts/titles to extract "resource domains" and detect
conflicts between concurrently running or queued jobs.

Conflict Strategy
-----------------
A job owns a set of resource domain strings.  Two jobs conflict when
their domain sets intersect.  Domain types:

  path:<prefix>   — a filesystem path the job appears to operate on
  port:<number>   — a TCP port the job references
  db:<name>       — a database name the job references
  svc:<name>      — a named service (docker container, process name, etc.)
  exclusive       — one-at-a-time operations: deploy, reset, migrate, init…

Conflict Resolution
-------------------
  HARD conflict  — domains overlap → sequence: new job waits for conflicting jobs
  SOFT conflict  — partial/semantic overlap → warn, allow parallel (default)
  NO conflict    — run immediately in available worker slot
"""

import re
from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional

# ---------------------------------------------------------------------------
# Exclusive keywords — ops that should not run alongside anything else
# ---------------------------------------------------------------------------
_EXCLUSIVE_KW = frozenset({
    "deploy", "deployment", "release", "publish",
    "migrate", "migration", "rollback",
    "reset", "rebuild", "reinitialize", "reinit",
    "init", "initialize", "bootstrap", "seed",
    "clean", "purge", "wipe", "flush", "truncate", "drop",
    "shutdown", "restart", "reboot",
    "format", "install",
})

# Soft-exclusive: flag, but don't hard-block
_SOFT_EXCLUSIVE_KW = frozenset({
    "test", "run", "execute", "build", "compile",
    "start", "launch", "serve",
})

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
_PATH_RE = re.compile(
    r"(?:"
    r"[./]{1,2}[a-zA-Z0-9_.-]+(?:[/\\][a-zA-Z0-9_.-]+)+"   # relative paths
    r"|/[a-zA-Z][a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)+"       # absolute unix paths
    r"|[A-Za-z]:\\[A-Za-z0-9_. -]+(?:\\[A-Za-z0-9_. -]+)+"  # Windows paths
    r")"
)
_PORT_RE = re.compile(r"(?:port\s+|:)(\d{4,5})\b", re.IGNORECASE)
_DB_RE = re.compile(
    r"\b(?:database|db|postgres|mysql|sqlite|mongo|redis)\s*[=:\"']?\s*([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)
_SVC_RE = re.compile(
    r"\b(?:container|service|process|daemon|app|server)\s+(?:named?\s+)?[\"']?([a-zA-Z0-9_-]+)[\"']?",
    re.IGNORECASE,
)


@dataclass
class DomainSet:
    """Resource domains extracted from a single job."""
    paths: FrozenSet[str] = field(default_factory=frozenset)
    ports: FrozenSet[str] = field(default_factory=frozenset)
    databases: FrozenSet[str] = field(default_factory=frozenset)
    services: FrozenSet[str] = field(default_factory=frozenset)
    exclusive: bool = False
    soft_exclusive: bool = False

    def all_domains(self) -> FrozenSet[str]:
        domains = set()
        domains.update(f"path:{p}" for p in self.paths)
        domains.update(f"port:{p}" for p in self.ports)
        domains.update(f"db:{d}" for d in self.databases)
        domains.update(f"svc:{s}" for s in self.services)
        if self.exclusive:
            domains.add("exclusive")
        if self.soft_exclusive:
            domains.add("soft_exclusive")
        return frozenset(domains)

    def is_empty(self) -> bool:
        return not (self.paths or self.ports or self.databases or self.services
                    or self.exclusive or self.soft_exclusive)


@dataclass
class ConflictResult:
    """Result of a conflict check between a new job and existing jobs."""
    conflicting_job_ids: List[str]       # Jobs that hard-conflict → must sequence after
    soft_conflict_job_ids: List[str]     # Jobs that soft-conflict → warn only
    overlap_details: dict                # job_id → list of overlapping domain strings
    exclusive_conflict: bool             # True if the exclusive domain triggered
    can_run_parallel: bool               # True if no hard conflicts


def extract_domains(text: str, title: str = "") -> DomainSet:
    """
    Extract resource domains from a job's prompt and title.
    Returns a DomainSet describing what resources this job touches.
    """
    combined = f"{title}\n{text}"
    lower = combined.lower()

    # ── Exclusive / soft-exclusive keywords ─────────────────────────────
    words = set(re.findall(r"\b[a-z]+\b", lower))
    exclusive = bool(words & _EXCLUSIVE_KW)
    soft_exclusive = bool(words & _SOFT_EXCLUSIVE_KW)

    # ── File paths ───────────────────────────────────────────────────────
    raw_paths = _PATH_RE.findall(combined)
    paths = set()
    for p in raw_paths:
        # Normalize: take first 3 segments as the "domain prefix"
        p = p.replace("\\", "/").strip("/")
        parts = [s for s in p.split("/") if s and s not in (".", "..")]
        if len(parts) >= 2:
            paths.add("/".join(parts[:3]))  # up to 3-level prefix

    # ── Ports ────────────────────────────────────────────────────────────
    ports = set(_PORT_RE.findall(combined))

    # ── Databases ────────────────────────────────────────────────────────
    dbs = set()
    for m in _DB_RE.finditer(combined):
        name = m.group(1).lower().strip()
        if name and len(name) > 1 and name not in {"the", "a", "an", "to", "in", "for"}:
            dbs.add(name)

    # ── Named services ───────────────────────────────────────────────────
    services = set()
    for m in _SVC_RE.finditer(combined):
        name = m.group(1).lower().strip()
        if name and len(name) > 2:
            services.add(name)

    return DomainSet(
        paths=frozenset(paths),
        ports=frozenset(ports),
        databases=frozenset(dbs),
        services=frozenset(services),
        exclusive=exclusive,
        soft_exclusive=soft_exclusive,
    )


def detect_conflicts(
    new_domains: DomainSet,
    running_job_domains: dict,  # job_id → DomainSet
) -> ConflictResult:
    """
    Check whether a new job conflicts with already-running/queued jobs.

    Args:
        new_domains:         Domains of the new job.
        running_job_domains: Dict of {job_id: DomainSet} for active jobs.

    Returns:
        ConflictResult with classification and details.
    """
    hard_conflicts: List[str] = []
    soft_conflicts: List[str] = []
    overlap_details: dict = {}
    has_exclusive_conflict = False

    new_all = new_domains.all_domains()

    for job_id, existing_domains in running_job_domains.items():
        existing_all = existing_domains.all_domains()
        overlap = new_all & existing_all

        if not overlap:
            continue

        # Remove soft_exclusive from overlap for hard-conflict determination
        hard_overlap = overlap - {"soft_exclusive"}

        if hard_overlap:
            # Exclusive keyword conflicts are always hard
            if "exclusive" in hard_overlap:
                has_exclusive_conflict = True
            hard_conflicts.append(job_id)
            overlap_details[job_id] = sorted(hard_overlap)
        elif "soft_exclusive" in overlap:
            soft_conflicts.append(job_id)
            overlap_details[job_id] = ["soft_exclusive"]

    return ConflictResult(
        conflicting_job_ids=hard_conflicts,
        soft_conflict_job_ids=soft_conflicts,
        overlap_details=overlap_details,
        exclusive_conflict=has_exclusive_conflict,
        can_run_parallel=len(hard_conflicts) == 0,
    )


def domains_to_dict(domains: DomainSet) -> dict:
    """Serialise a DomainSet to a plain dict for storage."""
    return {
        "paths": sorted(domains.paths),
        "ports": sorted(domains.ports),
        "databases": sorted(domains.databases),
        "services": sorted(domains.services),
        "exclusive": domains.exclusive,
        "soft_exclusive": domains.soft_exclusive,
    }


def domains_from_dict(d: dict) -> DomainSet:
    """Deserialise a DomainSet from a plain dict."""
    return DomainSet(
        paths=frozenset(d.get("paths", [])),
        ports=frozenset(d.get("ports", [])),
        databases=frozenset(d.get("databases", [])),
        services=frozenset(d.get("services", [])),
        exclusive=d.get("exclusive", False),
        soft_exclusive=d.get("soft_exclusive", False),
    )
