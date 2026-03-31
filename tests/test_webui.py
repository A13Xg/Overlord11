"""
tests/test_webui.py — Smoke tests for the Overlord11 Tactical WebUI.

Covers:
  - Event schema: make_event / serialize_event
  - State store: create, save, load, list, append_event, tail_events, artifacts
  - Reviewer gate: secrets scan, hardcoded model detection, diff coverage
  - LLM interface: get_provider_config (config reading)
  - FastAPI API: health, create job, list jobs, get job, start/stop controls,
                 directive injection, artifact endpoints (via TestClient)

Usage (from repo root):
    pip install -r requirements-webui.txt
    python -m pytest tests/test_webui.py -v

Or via the existing test runner (will skip web):
    python tests/test.py --skip-web --quiet
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Skip if FastAPI/httpx not installed (keeps test.py compatible)
# ---------------------------------------------------------------------------

try:
    from fastapi.testclient import TestClient
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


# ════════════════════════════════════════════════════════════════════════════
# 1. Event schema
# ════════════════════════════════════════════════════════════════════════════

class TestEventSchema:
    def test_make_event_fields(self):
        from webui.events import make_event, EventType, EventLevel
        ev = make_event(EventType.JOB_CREATED, "abc123", {"goal": "test"})
        assert ev["type"] == "JOB_CREATED"
        assert ev["job_id"] == "abc123"
        assert ev["level"] == "info"
        assert "ts" in ev
        assert ev["goal"] == "test"

    def test_serialize_event_is_valid_json(self):
        from webui.events import make_event, serialize_event, EventType
        ev = make_event(EventType.COMPLETE, "xyz", {"summary": "done \u2713"})
        line = serialize_event(ev)
        parsed = json.loads(line)
        assert parsed["type"] == "COMPLETE"
        assert "✓" in parsed["summary"]

    def test_make_event_level_override(self):
        from webui.events import make_event, EventLevel
        ev = make_event("FAILED", "j1", {}, level=EventLevel.ERROR)
        assert ev["level"] == "error"

    def test_make_event_no_payload(self):
        from webui.events import make_event
        ev = make_event("STATUS", "j2")
        assert ev["job_id"] == "j2"


# ════════════════════════════════════════════════════════════════════════════
# 2. State store
# ════════════════════════════════════════════════════════════════════════════

class TestStateStore:
    """Uses a temporary workspace directory to avoid polluting the real one."""

    @pytest.fixture(autouse=True)
    def patch_workspace(self, tmp_path, monkeypatch):
        """Redirect state_store._WORKSPACE to a temp dir."""
        import webui.state_store as ss
        monkeypatch.setattr(ss, "_WORKSPACE", tmp_path / "jobs")

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
        # Valid hex format but does not exist on disk
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
        # JOB_CREATED + 5 ITERATION = 6, tail of 3 = last 3
        assert len(tail) == 3
        assert all(ev["type"] == "ITERATION" for ev in tail)

    def test_write_and_read_artifact(self):
        import webui.state_store as ss
        state = self._make_state()
        ss.create_job(state)
        ss.write_artifact("aabbccdd1234", "test.patch", "--- a\n+++ b\n@@ 1 @@\n+x\n")
        content = ss.read_artifact("aabbccdd1234", "test.patch")
        assert content is not None
        assert "@@" in content

    def test_list_artifacts(self):
        import webui.state_store as ss
        state = self._make_state()
        ss.create_job(state)
        ss.write_artifact("aabbccdd1234", "file1.txt", "hello")
        ss.write_artifact("aabbccdd1234", "file2.txt", "world")
        arts = ss.list_artifacts("aabbccdd1234")
        assert "file1.txt" in arts
        assert "file2.txt" in arts

    def test_read_nonexistent_artifact(self):
        import webui.state_store as ss
        state = self._make_state()
        ss.create_job(state)
        assert ss.read_artifact("aabbccdd1234", "nope.txt") is None


# ════════════════════════════════════════════════════════════════════════════
# 3. Reviewer gate
# ════════════════════════════════════════════════════════════════════════════

class TestReviewer:
    def test_clean_artifacts_pass(self):
        from webui.reviewer import run_review
        result = run_review("j1", "add logging", {"main.py": "import logging\nlogging.info('hi')"})
        assert result.passed

    def test_secret_in_artifact_fails(self):
        from webui.reviewer import run_review
        result = run_review(
            "j1", "test",
            {"config.py": "api_key = 'sk-ant-abc123XYZ456DEF789GHI012JKL345MNO678PQR'"}
        )
        assert not result.passed
        assert any(f.rule == "secrets_scan" for f in result.findings)

    def test_hardcoded_model_warning(self):
        from webui.reviewer import run_review
        result = run_review(
            "j1", "test",
            {"runner.py": "model = 'claude-opus-4-5'  # wrong pattern"}
        )
        warnings = [f for f in result.findings if f.rule == "no_hardcoded_model"]
        assert len(warnings) > 0

    def test_diff_coverage_warning(self):
        from webui.reviewer import run_review
        # Goal implies fix but no patch artifact
        result = run_review(
            "j1",
            "fix the broken test",
            {"output.txt": "some output"},
        )
        warns = [f for f in result.findings if f.rule == "diff_coverage"]
        assert len(warns) > 0

    def test_diff_coverage_ok_with_patch(self):
        from webui.reviewer import run_review
        result = run_review(
            "j1",
            "fix the broken test",
            {"repair.patch": "--- a\n+++ b\n@@ @@\n+fix"},
        )
        warns = [f for f in result.findings if f.rule == "diff_coverage"]
        assert len(warns) == 0

    def test_empty_artifacts_pass(self):
        from webui.reviewer import run_review
        result = run_review("j1", "research task", {})
        assert result.passed


# ════════════════════════════════════════════════════════════════════════════
# 4. LLM interface — config reading
# ════════════════════════════════════════════════════════════════════════════

class TestLLMInterface:
    def test_get_provider_config_defaults(self):
        from webui.llm_interface import get_provider_config
        cfg = get_provider_config()
        # Should return something without raising
        assert "provider" in cfg
        assert "model" in cfg
        assert "api_key_env" in cfg

    def test_get_provider_config_explicit(self):
        from webui.llm_interface import get_provider_config
        cfg = get_provider_config("openai", "gpt-4o")
        assert cfg["provider"] == "openai"
        assert cfg["model"] == "gpt-4o"

    def test_get_provider_config_unknown_raises(self):
        from webui.llm_interface import get_provider_config, LLMConfigError
        with pytest.raises(LLMConfigError):
            get_provider_config("nonexistent_provider_xyz")

    def test_get_provider_config_all_providers(self):
        from webui.llm_interface import get_provider_config
        for p in ("anthropic", "gemini", "openai"):
            cfg = get_provider_config(p)
            assert cfg["provider"] == p


# ════════════════════════════════════════════════════════════════════════════
# 5. API smoke tests (requires FastAPI + httpx)
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi/httpx not installed")
class TestAPI:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        """Create a TestClient with a fresh temporary workspace."""
        import webui.state_store as ss
        monkeypatch.setattr(ss, "_WORKSPACE", tmp_path / "jobs")
        from webui.app import app
        return TestClient(app, raise_server_exceptions=True)

    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_create_job(self, client):
        r = client.post("/api/jobs", json={"goal": "Run a quick test"})
        assert r.status_code == 201
        body = r.json()
        assert body["goal"] == "Run a quick test"
        assert body["status"] == "PENDING"
        assert "job_id" in body

    def test_list_jobs(self, client):
        client.post("/api/jobs", json={"goal": "Mission Alpha"})
        client.post("/api/jobs", json={"goal": "Mission Beta"})
        r = client.get("/api/jobs")
        assert r.status_code == 200
        jobs = r.json()
        assert len(jobs) >= 2

    def test_get_job(self, client):
        cr = client.post("/api/jobs", json={"goal": "Get test"})
        job_id = cr.json()["job_id"]
        r = client.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200
        assert r.json()["job_id"] == job_id

    def test_get_job_not_found(self, client):
        # Valid hex format but does not exist — should be 404
        r = client.get("/api/jobs/deadbeef000000000000")
        assert r.status_code == 404

    def test_stop_job(self, client):
        cr = client.post("/api/jobs", json={"goal": "Stop test"})
        job_id = cr.json()["job_id"]
        r = client.post(f"/api/jobs/{job_id}/stop")
        assert r.status_code == 200

    def test_directive_injection(self, client):
        cr = client.post("/api/jobs", json={"goal": "Directive test"})
        job_id = cr.json()["job_id"]
        r = client.post(
            f"/api/jobs/{job_id}/directive",
            json={"message": "Focus on the edge cases"},
        )
        assert r.status_code == 200
        # Verify directive saved in state
        state = client.get(f"/api/jobs/{job_id}").json()
        assert len(state["directives"]) == 1
        assert state["directives"][0]["message"] == "Focus on the edge cases"

    def test_events_tail(self, client):
        cr = client.post("/api/jobs", json={"goal": "Events test"})
        job_id = cr.json()["job_id"]
        r = client.get(f"/api/jobs/{job_id}/events/tail?n=10")
        assert r.status_code == 200
        events = r.json()
        # Should have at least the JOB_CREATED event
        assert isinstance(events, list)
        assert len(events) >= 1
        assert events[0]["type"] == "JOB_CREATED"

    def test_artifact_list_empty(self, client):
        cr = client.post("/api/jobs", json={"goal": "Artifacts test"})
        job_id = cr.json()["job_id"]
        r = client.get(f"/api/jobs/{job_id}/artifacts")
        assert r.status_code == 200
        assert r.json()["artifacts"] == []

    def test_artifact_not_found(self, client):
        cr = client.post("/api/jobs", json={"goal": "Art 404"})
        job_id = cr.json()["job_id"]
        r = client.get(f"/api/jobs/{job_id}/artifacts/nope.txt")
        assert r.status_code == 404

    def test_pause_resume_nonexistent(self, client):
        # Valid hex format job that does not exist — 404
        r = client.post("/api/jobs/deadbeef000000000000/pause")
        assert r.status_code == 404

    def test_create_job_validation(self, client):
        # Missing goal
        r = client.post("/api/jobs", json={"max_iterations": 5})
        assert r.status_code == 422

    def test_ui_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "OVERLORD11" in r.text


# ════════════════════════════════════════════════════════════════════════════
# Standalone runner (for use with test.py harness or direct execution)
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=str(PROJECT_ROOT),
    )
    sys.exit(result.returncode)
