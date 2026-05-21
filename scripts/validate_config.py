#!/usr/bin/env python3
"""
validate_config.py — Validate config.json against expected schema.

Usage:
    python scripts/validate_config.py [path/to/config.json]

Exit codes:
    0 = valid (may have warnings)
    1 = invalid / errors found
    2 = file not found / parse error
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG = _PROJECT_ROOT / "config.json"

_KNOWN_PROVIDERS = {"anthropic", "openai", "gemini"}
_KNOWN_TOP_KEYS = {"version", "name", "description", "providers", "agents", "orchestration",
                   "notifications", "quality", "workspace", "logging"}

_PROVIDER_REQUIRED = ["model", "available_models", "api_key_env"]
_OPTIONAL_ORCH_INT = [
    ("orchestration.max_loops", int, "Max orchestrator loops"),
    ("orchestration.parallel.max_concurrent_jobs", int, "Max parallel job slots"),
    ("orchestration.parallel.max_concurrent_tools", int, "Max parallel tool calls"),
    ("orchestration.max_retries_per_agent", int, "Max retries per agent"),
]


def _get_nested(obj: dict, dotpath: str) -> tuple[bool, Any]:
    parts = dotpath.split(".")
    cur = obj
    for part in parts:
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def validate_config(config: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    # Top-level required keys
    for key in ("providers",):
        if key not in config:
            errors.append(f"MISSING required field: {key!r}")

    # Validate providers block
    providers = config.get("providers")
    if not isinstance(providers, dict):
        errors.append(f"'providers' must be an object (dict), got {type(providers).__name__}")
    else:
        # Check active provider
        active = providers.get("active")
        if not active:
            errors.append("'providers.active' is missing — must name the default provider")
        elif active not in _KNOWN_PROVIDERS:
            warnings.append(f"providers.active = {active!r} is not a known provider ({_KNOWN_PROVIDERS})")

        # Check each provider
        for pname in _KNOWN_PROVIDERS:
            if pname not in providers:
                warnings.append(f"Provider {pname!r} is not configured in providers")
                continue
            pobj = providers[pname]
            if not isinstance(pobj, dict):
                errors.append(f"providers.{pname} must be an object")
                continue
            for field in _PROVIDER_REQUIRED:
                if field not in pobj:
                    errors.append(f"providers.{pname} missing required field: {field!r}")
            # Warn if api_key env var is not set
            api_key_env = pobj.get("api_key_env", "")
            if api_key_env and not os.environ.get(api_key_env, "").strip():
                warnings.append(f"providers.{pname}.api_key_env={api_key_env!r} is not set in environment")

        # Cross-check active model
        if active and active in providers and isinstance(providers.get(active), dict):
            prov_conf = providers[active]
            active_model = prov_conf.get("model", "")
            avail = prov_conf.get("available_models", {})
            if active_model and isinstance(avail, dict) and avail and active_model not in avail:
                warnings.append(
                    f"providers.{active}.model={active_model!r} not listed in available_models"
                )

        # Unexpected keys in providers
        for key in providers:
            if key != "active" and key not in _KNOWN_PROVIDERS:
                warnings.append(f"Unknown key in providers: {key!r}")

    # Validate orchestration optional int fields
    for dotpath, expected_type, desc in _OPTIONAL_ORCH_INT:
        found, val = _get_nested(config, dotpath)
        if found and not isinstance(val, expected_type):
            warnings.append(
                f"WRONG TYPE for {dotpath!r}: expected {expected_type.__name__}, "
                f"got {type(val).__name__} ({desc})"
            )

    # Warn about unknown top-level keys
    for key in config:
        if key not in _KNOWN_TOP_KEYS:
            warnings.append(f"Unknown top-level key: {key!r}")

    return errors, warnings


def main() -> int:
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_CONFIG

    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        return 2

    try:
        raw = config_path.read_text(encoding="utf-8")
        config = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: JSON parse error in {config_path}:", file=sys.stderr)
        print(f"  {exc}", file=sys.stderr)
        return 2

    print(f"Validating: {config_path}")

    errors, warnings = validate_config(config)

    for w in warnings:
        print(f"  ⚠ WARN  {w}")
    for e in errors:
        print(f"  ✗ ERROR {e}")

    if errors:
        print(f"\n✗ INVALID — {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    elif warnings:
        print(f"\n✓ VALID with {len(warnings)} warning(s)")
    else:
        print("\n✓ VALID — config looks good")
    return 0


if __name__ == "__main__":
    sys.exit(main())



def _get_nested(obj: dict, dotpath: str) -> tuple[bool, Any]:
    """Return (found, value) for a dotted path like 'a.b.c'."""
    parts = dotpath.split(".")
    cur = obj
    for part in parts:
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def validate_config(config: dict) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    # Check required fields
    for dotpath, expected_type, required, desc in _REQUIRED_FIELDS:
        found, val = _get_nested(config, dotpath)
        if not found:
            if required:
                errors.append(f"MISSING required field: {dotpath!r} ({desc})")
            continue
        if not isinstance(val, expected_type):
            errors.append(
                f"WRONG TYPE for {dotpath!r}: expected {expected_type.__name__}, "
                f"got {type(val).__name__}"
            )

    # Check providers list
    found_prov, providers = _get_nested(config, "providers")
    if found_prov and isinstance(providers, list):
        if len(providers) == 0:
            errors.append("providers list is empty — at least one provider required")
        for i, prov in enumerate(providers):
            if not isinstance(prov, dict):
                errors.append(f"providers[{i}] must be an object")
                continue
            for field, ftype, req, fdesc in _PROVIDER_FIELDS:
                if field not in prov:
                    if req:
                        errors.append(f"providers[{i}] missing required field: {field!r} ({fdesc})")
                elif not isinstance(prov[field], ftype):
                    errors.append(
                        f"providers[{i}].{field}: expected {ftype.__name__}, "
                        f"got {type(prov[field]).__name__}"
                    )
            name = prov.get("name", "")
            if name and name not in _KNOWN_PROVIDERS:
                warnings.append(f"providers[{i}].name = {name!r} is not a known provider ({_KNOWN_PROVIDERS})")

    # Cross-check active_provider / active_model vs providers list
    if found_prov and isinstance(providers, list):
        provider_names = [p.get("name") for p in providers if isinstance(p, dict)]
        active_prov = config.get("active_provider", "")
        if active_prov and active_prov not in provider_names:
            errors.append(f"active_provider={active_prov!r} not found in providers list: {provider_names}")

        active_model = config.get("active_model", "")
        if active_model and active_prov:
            prov_obj = next((p for p in providers if isinstance(p, dict) and p.get("name") == active_prov), None)
            if prov_obj:
                models = prov_obj.get("models", [])
                if models and active_model not in models:
                    errors.append(
                        f"active_model={active_model!r} not in {active_prov}.models: {models}"
                    )

    # Check optional fields types
    for dotpath, expected_type, desc in _OPTIONAL_FIELDS:
        found, val = _get_nested(config, dotpath)
        if found and not isinstance(val, expected_type):
            warnings.append(
                f"WRONG TYPE for optional field {dotpath!r}: expected {expected_type.__name__}, "
                f"got {type(val).__name__} ({desc})"
            )

    # Check for unknown top-level keys
    known_top = {"providers", "active_provider", "active_model", "orchestration"}
    for key in config:
        if key not in known_top:
            warnings.append(f"Unknown top-level key: {key!r}")

    return errors, warnings


def main() -> int:
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_CONFIG

    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        return 2

    try:
        raw = config_path.read_text(encoding="utf-8")
        config = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: JSON parse error in {config_path}:", file=sys.stderr)
        print(f"  {exc}", file=sys.stderr)
        return 2

    print(f"Validating: {config_path}")

    errors, warnings = validate_config(config)

    for w in warnings:
        print(f"  ⚠ WARN  {w}")
    for e in errors:
        print(f"  ✗ ERROR {e}")

    if errors:
        print(f"\n✗ INVALID — {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    elif warnings:
        print(f"\n✓ VALID with {len(warnings)} warning(s)")
    else:
        print("\n✓ VALID — config looks good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
