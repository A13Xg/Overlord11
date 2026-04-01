"""
tests/test_webui.py — Smoke tests for the Overlord11 Tactical WebUI.

Tests cover:
  - Event schema (schema_version, emit_event helper, event types)
  - State store CRUD, artifact subdirs, list_artifacts metadata
  - Reviewer gate rules
  - LLM interface / provider config
  - Full API surface via FastAPI TestClient
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path):
    """Redirect workspace to a temp directory for every test."""
    with patch("webui.state_store._WORKSPACE", tmp_path / "jobs"):
        yield tmp_path


@pytest.fixture
def client(isolated_workspace):
    from fastapi.testclient import TestClient
    from webui.app import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# 1. Event schema
# ---------------------------------------------------------------------------

class TestEventSchema:
    def test_make_event_fields(self):
        from webui.events import EventType, make_event
        ev = make_event(EventType.JOB_CREATED, "aabbccdd1234")
        assert ev["schema_version"] == "0.1"
        assert ev["type"] == "JOB_CREATED"
        assert ev["job_id"] == "aabbccdd1234"
        assert ev["level"] == "info"
        assert "ts" in ev

    def test_make_event_with_phase_and_iteration(self):
        from webui.events import EventType, make_event
        ev = make_event(EventType.ITERATION, "aabbccdd1234", phase="run", iteration=3)
        assert ev["phase"] == "run"
        assert ev["iteration"] == 3

    def test_serialize_event_is_valid_json(self):
        from webui.events import EventType, make_event, serialize_event
        ev = make_event(EventType.VERIFY_RESULT, "aabbccdd1234", {"passed": True})
        line = serialize_event(ev)
        parsed = json.loads(line)
        assert parsed["type"] == "VERIFY_RESULT"

    def test_make_event_level_override(self):
        from webui.events import EventLevel, EventType, make_event
        ev = make_event(EventType.FAILED, "aabbccdd1234", level=EventLevel.ERROR)
        assert ev["level"] == "error"

    def test_make_event_no_payload(self):
        from webui.events import EventType, make_event
        ev = make_event(EventType.PAUSED, "aabbccdd1234")
        assert ev["type"] == "PAUSED"

    def test_emit_event_helper_calls_fn(self):
        from webui.events import EventType, emit_event
        collected = []
        emit_event(collected.append, "aabbccdd1234", EventType.VERIFY_START, iteration=1)
        assert len(collected) == 1
        assert collected[0]["type"] == "VERIFY_START"
        assert collected[0]["schema_version"] == "0.1"

    def test_all_new_event_types_exist(self):
        from webui.events import EventType
        required = [
            "DEP_INSTALL_START", "DEP_INSTALL_RESULT",
            "VERIFY_RETRY",
            "DIRECTIVES_APPLIED",
            "ARTIFACT_WRITTEN",
            "STOPPED",
            "TIME_BUDGET_EXCEEDED",
            "ITERATION_BUDGET_EXCEEDED",
            "LLM_UNAVAILABLE",
            "PLAN_CREATED",
            "STEP_START",
            "STEP_END",
            "PATCH_APPLY_START",
            "PATCH_APPLY_RESULT",
        ]
        existing = {e.value for e in EventType}
        for name in required:
            assert name in existing, f"Missing EventType: {name}"


# ---------------------------------------------------------------------------
# 2. State store
# ---------------------------------------------------------------------------

class TestStateStore:
    def _make_state(self, job_id: str = "aabbccdd1234"):
        from webui.models import JobState, JobStatus
        from datetime import datetime, timezone
        return JobState(
            job_id=job_id,
            goal="Test mission goal",
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
            max_iterations=5,
            max_time_seconds=300,
        )

    def test_create_and_load(self):
        import webui.state_store as ss
        state = self._make_state()
        ss.create_job(state)
        loaded = ss.load_state("aabbccdd1234")
        assert loaded is not None
        assert loaded.goal == "Test mission goal"
        assert loaded.status == "PENDING"

    def test_save_updates_state(self):
        import webui.state_store as ss
        from webui.models import JobStatus
        state = self._make_state()
        ss.create_job(state)
        state.status = JobStatus.RUNNING
        state.iteration = 3
        ss.save_state(state)
        loaded = ss.load_state("aabbccdd1234")
        assert loaded.status == "RUNNING"
        assert loaded.iteration == 3

    def test_load_nonexistent(self):
        import webui.state_store as ss
        assert ss.load_state("deadbeef1234") is None

    def test_list_jobs(self):
        import webui.state_store as ss
        for jid in ("aabb11223344", "bbcc22334455", "ccdd33445566"):
            ss.create_job(self._make_state(jid))
        listed = ss.list_jobs()
        assert "aabb11223344" in listed
        assert "bbcc22334455" in listed
        assert "ccdd33445566" in listed

    def test_append_and_tail_events(self):
        import webui.state_store as ss
        from webui.events import make_event, EventType
        state = self._make_state()
        ss.create_job(state)
        for i in range(5):
            ss.append_event(make_event(EventType.ITERATION, "aabbccdd1234", {"i": i}))
        tail = ss.tail_events("aabbccdd1234", 3)
        assert len(tail) == 3
        assert all(ev["type"] == "ITERATION" for ev in tail)

    def test_write_artifact_in_subdir(self):
        import webui.state_store as ss
        state = self._make_state()
        ss.create_job(state)
        ss.write_artifact("aabbccdd1234", "verify/iter_001.log", "test output")
        content = ss.read_artifact("aabbccdd1234", "verify/iter_001.log")
        assert content == "test output"

    def test_write_artifact_bare_name(self):
        import webui.state_store as ss
        state = self._make_state()
        ss.create_job(state)
        ss.write_artifact("aabbccdd1234", "test.patch", "diff content")
        assert ss.read_artifact("aabbccdd1234", "test.patch") == "diff content"

    def test_list_artifacts_returns_metadata(self):
        import webui.state_store as ss
        state = self._make_state()
        ss.create_job(state)
        ss.write_artifact("aabbccdd1234", "verify/iter_001.log", "output")
        ss.write_artifact("aabbccdd1234", "diffs/iter_001.patch", "patch")
        arts = ss.list_artifacts("aabbccdd1234")
        paths = [a.path for a in arts]
        assert "verify/iter_001.log" in paths
        assert "diffs/iter_001.patch" in paths
        for a in arts:
            assert a.size > 0
            assert a.mtime > 0

    def test_read_nonexistent_artifact(self):
        import webui.state_store as ss
        state = self._make_state()
        ss.create_job(state)
        assert ss.read_artifact("aabbccdd1234", "verify/nope.txt") is None

    def test_artifact_subdirs_created(self):
        import webui.state_store as ss
        from webui.state_store import _WORKSPACE
        state = self._make_state()
        ss.create_job(state)
        arts_dir = _WORKSPACE / "aabbccdd1234" / "artifacts"
        for sub in ("verify", "install", "diffs", "plans", "reports"):
            assert (arts_dir / sub).is_dir(), f"Missing subdir: {sub}"

    def test_pending_directives_in_state(self):
        import webui.state_store as ss
        state = self._make_state()
        state.pending_directives = [{"text": "do this", "severity": "high", "tags": []}]
        ss.create_job(state)
        loaded = ss.load_state("aabbccdd1234")
        assert len(loaded.pending_directives) == 1
        assert loaded.pending_directives[0]["text"] == "do this"


# ---------------------------------------------------------------------------
# 3. Reviewer gate
# ---------------------------------------------------------------------------

class TestReviewer:
    def test_clean_artifacts_pass(self):
        from webui.reviewer import run_review
        result = run_review("job1", "fix the bug", {"file1.txt": "hello world"})
        assert result.passed

    def test_secret_in_artifact_fails(self):
        from webui.reviewer import run_review
        result = run_review(
            "job1", "fix",
            {"config.txt": "api_key = 'sk-abcdefghijklmnopqrstuvwxyz'"}
        )
        assert not result.passed

    def test_hardcoded_model_warning(self):
        from webui.reviewer import run_review
        result = run_review(
            "job1", "fix",
            {"code.py": 'model = "claude-opus-4-5"'}
        )
        warnings = [f for f in result.findings if f.rule == "no_hardcoded_model"]
        assert len(warnings) > 0

    def test_diff_coverage_warning(self):
        from webui.reviewer import run_review
        result = run_review("job1", "fix the bug", {"report.txt": "done"})
        assert any(f.rule == "diff_coverage" for f in result.findings)

    def test_diff_coverage_ok_with_patch(self):
        from webui.reviewer import run_review
        result = run_review(
            "job1", "fix the bug",
            {"diffs/iter_001.patch": "--- a\n+++ b\n+fix"}
        )
        assert not any(f.rule == "diff_coverage" for f in result.findings)

    def test_empty_artifacts_pass(self):
        from webui.reviewer import run_review
        result = run_review("job1", "fix the bug", {})
        assert result.passed


# ---------------------------------------------------------------------------
# 4. LLM interface / provider config
# ---------------------------------------------------------------------------

class TestLLMInterface:
    def test_get_provider_config_defaults(self):
        from webui.providers.router import get_provider_config
        cfg = get_provider_config()
        assert "provider" in cfg
        assert "model" in cfg
        assert "api_key_env" in cfg

    def test_get_provider_config_explicit(self):
        from webui.providers.router import get_provider_config
        cfg = get_provider_config("anthropic")
        assert cfg["provider"] == "anthropic"

    def test_get_provider_config_unknown_raises(self):
        from webui.providers.router import get_provider_config
        from webui.providers.base import LLMConfigError
        with pytest.raises(LLMConfigError):
            get_provider_config("nonexistent_provider")

    def test_get_provider_config_all_providers(self):
        from webui.providers.router import get_provider_config
        for p in ("anthropic", "gemini", "openai"):
            cfg = get_provider_config(p)
            assert cfg["provider"] == p

    def test_provider_is_available_without_key(self):
        from webui.providers.router import get_provider
        adapter = get_provider("anthropic")
        # In CI, no real API key is set; just check the method exists
        assert hasattr(adapter, "is_available")
        assert isinstance(adapter.is_available(), bool)


# ---------------------------------------------------------------------------
# 5. API smoke tests
# ---------------------------------------------------------------------------

class TestAPI:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["schema_version"] == "0.1"

    def test_create_job(self, client):
        r = client.post(
            "/api/jobs",
            json={"goal": "test goal", "max_iterations": 2, "max_time_seconds": 30},
        )
        assert r.status_code == 201
        data = r.json()
        assert "job_id" in data
        assert data["goal"] == "test goal"
        assert data["status"] == "PENDING"

    def test_list_jobs(self, client):
        client.post("/api/jobs", json={"goal": "g1"})
        client.post("/api/jobs", json={"goal": "g2"})
        r = client.get("/api/jobs")
        assert r.status_code == 200
        assert len(r.json()) >= 2

    def test_get_job(self, client):
        cr = client.post("/api/jobs", json={"goal": "test"})
        job_id = cr.json()["job_id"]
        r = client.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200
        assert r.json()["job_id"] == job_id

    def test_get_job_not_found(self, client):
        r = client.get("/api/jobs/deadbeef000000000000")
        assert r.status_code == 404

    def test_stop_job(self, client):
        cr = client.post("/api/jobs", json={"goal": "test"})
        job_id = cr.json()["job_id"]
        r = client.post(f"/api/jobs/{job_id}/stop")
        assert r.status_code == 200

    def test_directive_injection(self, client):
        cr = client.post("/api/jobs", json={"goal": "test"})
        job_id = cr.json()["job_id"]
        r = client.post(
            f"/api/jobs/{job_id}/directive",
            json={"text": "focus on tests", "severity": "normal", "tags": ["quality"]},
        )
        assert r.status_code == 202
        # Directive should appear in state
        state_r = client.get(f"/api/jobs/{job_id}")
        pending = state_r.json()["pending_directives"]
        assert len(pending) == 1
        assert pending[0]["text"] == "focus on tests"
        assert pending[0]["severity"] == "normal"
        assert "quality" in pending[0]["tags"]

    def test_events_tail(self, client):
        cr = client.post("/api/jobs", json={"goal": "test"})
        job_id = cr.json()["job_id"]
        r = client.get(f"/api/jobs/{job_id}/events/tail?n=10")
        assert r.status_code == 200
        events = r.json()
        assert isinstance(events, list)
        assert events[0]["type"] == "JOB_CREATED"
        assert events[0]["schema_version"] == "0.1"

    def test_artifact_list_empty(self, client):
        cr = client.post("/api/jobs", json={"goal": "test"})
        job_id = cr.json()["job_id"]
        r = client.get(f"/api/jobs/{job_id}/artifacts")
        assert r.status_code == 200
        assert r.json()["artifacts"] == []

    def test_artifact_list_with_metadata(self, client):
        import webui.state_store as ss
        cr = client.post("/api/jobs", json={"goal": "test"})
        job_id = cr.json()["job_id"]
        ss.write_artifact(job_id, "verify/iter_001.log", "test output")
        r = client.get(f"/api/jobs/{job_id}/artifacts")
        assert r.status_code == 200
        arts = r.json()["artifacts"]
        assert len(arts) == 1
        assert arts[0]["path"] == "verify/iter_001.log"
        assert arts[0]["size"] > 0
        assert arts[0]["mtime"] > 0

    def test_artifact_not_found(self, client):
        cr = client.post("/api/jobs", json={"goal": "test"})
        job_id = cr.json()["job_id"]
        r = client.get(f"/api/jobs/{job_id}/artifacts/verify/nope.log")
        assert r.status_code == 404

    def test_pause_uses_query_param(self, client):
        """Pause endpoint accepts ?pause=true (not /pause and /resume)."""
        cr = client.post("/api/jobs", json={"goal": "test"})
        job_id = cr.json()["job_id"]
        # Job is PENDING, not RUNNING — should return 400
        r = client.post(f"/api/jobs/{job_id}/pause?pause=true")
        assert r.status_code == 400  # correct endpoint, wrong state

    def test_pause_resume_nonexistent(self, client):
        r = client.post("/api/jobs/deadbeef000000000000/pause?pause=true")
        assert r.status_code == 404

    def test_create_job_validation(self, client):
        r = client.post("/api/jobs", json={"goal": "", "max_iterations": 200})
        assert r.status_code == 422

    def test_ui_root(self, client):
        r = client.get("/")
        assert r.status_code in (200, 503)

    def test_sse_endpoint_exists(self, client):
        """Check that the SSE endpoint accepts the ?since= query param."""
        cr = client.post("/api/jobs", json={"goal": "test"})
        job_id = cr.json()["job_id"]
        # TestClient doesn't stream SSE, but we can verify the endpoint exists
        # by checking the route is registered
        routes = [r.path for r in client.app.routes]
        sse_routes = [r for r in routes if "events" in r and "tail" not in r]
        assert len(sse_routes) >= 1


# ---------------------------------------------------------------------------
# 6. Patch path validation
# ---------------------------------------------------------------------------

class TestPatchValidation:
    """Tests for _patch_escapes_root() path traversal detection."""

    def _esc(self, diff: str) -> bool:
        from webui.runner import _patch_escapes_root
        return _patch_escapes_root(diff)

    def test_safe_patch_passes(self):
        diff = "--- a/src/foo.py\n+++ b/src/foo.py\n+line"
        assert not self._esc(diff)

    def test_dotdot_traversal_rejected(self):
        diff = "--- a/../etc/passwd\n+++ b/../etc/passwd\n+line"
        assert self._esc(diff)

    def test_dotdot_in_middle_rejected(self):
        diff = "--- a/src/../../etc/passwd\n+++ b/src/../../etc/passwd\n+line"
        assert self._esc(diff)

    def test_absolute_unix_path_rejected(self):
        diff = "--- /etc/passwd\n+++ /etc/passwd\n+line"
        assert self._esc(diff)

    def test_absolute_windows_path_rejected(self):
        diff = "--- C:\\Windows\\System32\\foo.txt\n+++ C:\\Windows\\System32\\foo.txt\n+line"
        assert self._esc(diff)

    def test_unc_windows_path_rejected(self):
        diff = "--- \\\\server\\share\\foo.txt\n+++ \\\\server\\share\\foo.txt\n+line"
        assert self._esc(diff)

    def test_dev_null_allowed(self):
        # /dev/null appears in git diffs for new files — should not be rejected
        diff = "--- /dev/null\n+++ b/newfile.py\n+line"
        assert not self._esc(diff)

    def test_safe_subdir_patch_passes(self):
        diff = "--- a/tests/test_foo.py\n+++ b/tests/test_foo.py\n+line"
        assert not self._esc(diff)


# ---------------------------------------------------------------------------
# 7. Runner unit tests
# ---------------------------------------------------------------------------

class TestRunnerUnit:
    """Tests for runner.py utility functions."""

    def test_parse_action_valid_json(self):
        from webui.runner import _parse_action
        raw = '{"action": "complete", "summary": "done"}'
        result = _parse_action(raw, "aabbccdd1234")
        assert result["action"] == "complete"

    def test_parse_action_with_markdown_fences(self):
        from webui.runner import _parse_action
        raw = '```json\n{"action": "complete", "summary": "done"}\n```'
        result = _parse_action(raw, "aabbccdd1234")
        assert result["action"] == "complete"

    def test_parse_action_invalid_json_defaults_to_complete(self):
        """Malformed JSON should default to complete action and emit ASSUMPTION_LOG."""
        from webui.runner import _parse_action
        from webui.events import EventType
        emitted = []
        # Patch _emit to capture events
        import webui.runner as runner_mod
        orig_emit = runner_mod._emit
        runner_mod._emit = lambda ev: emitted.append(ev)
        try:
            result = _parse_action("not valid json at all", "aabbccdd1234")
        finally:
            runner_mod._emit = orig_emit
        assert result["action"] == "complete"
        types = [ev["type"] for ev in emitted]
        assert EventType.ASSUMPTION_LOG.value in types

    def test_parse_action_plain_text_defaults_to_complete(self):
        from webui.runner import _parse_action
        result = _parse_action("just some plain text", "aabbccdd1234")
        assert result["action"] == "complete"
        assert "just some plain text" in result["summary"]

    def test_control_flags_cleared_after_finish(self):
        """After _finish(), control flags for the job should be removed."""
        import asyncio
        import webui.runner as runner_mod
        from webui.runner import _finish, _control_flags
        from webui.models import JobState, JobStatus
        from datetime import datetime, timezone
        import webui.state_store as ss
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with patch("webui.state_store._WORKSPACE", Path(tmp) / "jobs"):
                state = JobState(
                    job_id="aabbccdd1234",
                    goal="test",
                    status=JobStatus.RUNNING,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
                ss.create_job(state)
                _control_flags["aabbccdd1234"] = "stop"

                asyncio.run(_finish(state, JobStatus.STOPPED, "test stop", ev_type=runner_mod.EventType.STOPPED))

                # Flag should be cleaned up
                assert "aabbccdd1234" not in _control_flags


# ---------------------------------------------------------------------------
# 8. API input validation
# ---------------------------------------------------------------------------

class TestAPIInputValidation:
    """Tests for input validation on API routes."""

    @pytest.fixture
    def client(self, isolated_workspace):
        from fastapi.testclient import TestClient
        from webui.app import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

    def test_create_job_blank_goal_rejected(self, client):
        r = client.post("/api/jobs", json={"goal": "   "})
        assert r.status_code == 422

    def test_create_job_invalid_provider_rejected(self, client):
        r = client.post("/api/jobs", json={"goal": "test", "provider": "badprovider"})
        assert r.status_code == 422

    def test_create_job_max_iterations_too_large(self, client):
        r = client.post("/api/jobs", json={"goal": "test", "max_iterations": 999})
        assert r.status_code == 422

    def test_create_job_with_custom_verify_command(self, client):
        r = client.post(
            "/api/jobs",
            json={"goal": "test", "verify_command": ["echo", "ok"]},
        )
        assert r.status_code == 201
        assert r.json()["verify_command"] == ["echo", "ok"]

    def test_directive_blank_text_rejected(self, client):
        cr = client.post("/api/jobs", json={"goal": "test"})
        job_id = cr.json()["job_id"]
        r = client.post(
            f"/api/jobs/{job_id}/directive",
            json={"text": "  ", "severity": "normal"},
        )
        assert r.status_code == 422

    def test_directive_invalid_severity_rejected(self, client):
        cr = client.post("/api/jobs", json={"goal": "test"})
        job_id = cr.json()["job_id"]
        r = client.post(
            f"/api/jobs/{job_id}/directive",
            json={"text": "do this", "severity": "critical"},
        )
        assert r.status_code == 422

    def test_directive_valid_severities(self, client):
        cr = client.post("/api/jobs", json={"goal": "test"})
        job_id = cr.json()["job_id"]
        for sev in ("normal", "high"):
            r = client.post(
                f"/api/jobs/{job_id}/directive",
                json={"text": "do this", "severity": sev},
            )
            assert r.status_code == 202, f"Expected 202 for severity={sev!r}, got {r.status_code}"

    def test_sse_since_negative_rejected(self, client):
        cr = client.post("/api/jobs", json={"goal": "test"})
        job_id = cr.json()["job_id"]
        # Negative `since` should be rejected by query validation
        r = client.get(f"/api/jobs/{job_id}/events?since=-1")
        assert r.status_code == 422
