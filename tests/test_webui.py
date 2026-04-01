"""Tests for the Overlord11 Tactical WebUI backend."""
import json
import os
import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from webui.app import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "Overlord11" in data["service"]


def test_list_jobs_empty():
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_jobs_status_filter(tmp_path, monkeypatch):
    import webui.state_store as ss
    monkeypatch.setattr(ss, "JOBS_DIR", tmp_path)

    # Create two jobs: one running, one completed
    for jid, status in [("job-run", "running"), ("job-done", "completed")]:
        jdir = tmp_path / jid
        jdir.mkdir()
        state = {"status": status, "goal": f"Test {status}", "created": time.time(), "updated": time.time()}
        (jdir / "state.json").write_text(json.dumps(state))

    r = client.get("/api/jobs?status=running")
    assert r.status_code == 200
    data = r.json()
    assert all(j["status"] == "running" for j in data)
    assert any(j["job_id"] == "job-run" for j in data)

    r2 = client.get("/api/jobs?status=completed")
    assert r2.status_code == 200
    data2 = r2.json()
    assert all(j["status"] == "completed" for j in data2)


def test_get_job_not_found():
    r = client.get("/api/jobs/nonexistent-job-xyz")
    assert r.status_code == 404


def test_get_job_invalid_id():
    # URL-encoded special chars that survive path normalization
    r = client.get("/api/jobs/job%24invalid%21")
    assert r.status_code in (400, 404, 422)


def test_get_job_invalid_id_special_chars():
    r = client.get("/api/jobs/job%20with%20spaces")
    assert r.status_code in (400, 404, 422)


def test_get_job_detail(tmp_path, monkeypatch):
    import webui.state_store as ss
    monkeypatch.setattr(ss, "JOBS_DIR", tmp_path)

    jdir = tmp_path / "test-job-001"
    jdir.mkdir()
    state = {
        "status": "completed",
        "goal": "Build something great",
        "created": 1700000000.0,
        "updated": 1700001000.0,
        "provider": "gemini",
        "model": "gemini-3.1-flash-lite-preview",
    }
    (jdir / "state.json").write_text(json.dumps(state))

    # Add an event
    event = {"type": "info", "message": "Job started", "timestamp": 1700000001.0}
    (jdir / "events.jsonl").write_text(json.dumps(event) + "\n")

    # Add an artifact
    art_dir = jdir / "artifacts"
    art_dir.mkdir()
    (art_dir / "output.md").write_text("# Result\nHello world")

    r = client.get("/api/jobs/test-job-001")
    assert r.status_code == 200
    data = r.json()
    assert data["job_id"] == "test-job-001"
    assert data["goal"] == "Build something great"
    assert data["status"] == "completed"
    assert data["provider"] == "gemini"
    assert len(data["events"]) == 1
    assert len(data["artifacts"]) == 1
    assert data["artifacts"][0]["path"] == "artifacts/output.md"
    assert data["artifacts"][0]["is_finished_product"] is True


def test_config_active_gemini():
    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert data["active_provider"] == "gemini"
    assert "gemini" in data["providers"]
    assert "gemini-3.1-flash-lite-preview" in data["providers"]["gemini"]["available_models"]
    assert data["default_model"] == "gemini-3.1-flash-lite-preview"


def test_config_no_api_keys():
    r = client.get("/api/config")
    data = r.json()
    for provider, pcfg in data["providers"].items():
        assert "api_key" not in pcfg
        assert "api_key_env" not in pcfg


def test_list_artifacts_not_found():
    r = client.get("/api/jobs/nonexistent-job-xyz/artifacts")
    assert r.status_code == 404


def test_list_artifacts_invalid_id():
    r = client.get("/api/jobs/!!invalid!!/artifacts")
    assert r.status_code in (400, 404, 422)


def test_get_artifact_path_traversal(tmp_path, monkeypatch):
    import webui.state_store as ss
    monkeypatch.setattr(ss, "JOBS_DIR", tmp_path)

    jdir = tmp_path / "safe-job"
    jdir.mkdir()

    # URL-encoded path traversal attempt (%2e%2e = ..)
    r = client.get("/api/jobs/safe-job/artifacts/%2e%2e%2f%2e%2e%2fetc%2fpasswd")
    assert r.status_code == 404


def test_get_artifact_not_found(tmp_path, monkeypatch):
    import webui.state_store as ss
    monkeypatch.setattr(ss, "JOBS_DIR", tmp_path)

    jdir = tmp_path / "safe-job"
    jdir.mkdir()

    r = client.get("/api/jobs/safe-job/artifacts/does_not_exist.txt")
    assert r.status_code == 404


def test_get_artifact_content(tmp_path, monkeypatch):
    import webui.state_store as ss
    monkeypatch.setattr(ss, "JOBS_DIR", tmp_path)

    jdir = tmp_path / "artifact-job"
    jdir.mkdir()
    content = b"Hello from artifact"
    (jdir / "output.txt").write_bytes(content)

    r = client.get("/api/jobs/artifact-job/artifacts/output.txt")
    assert r.status_code == 200
    assert r.content == content


def test_search_jobs(tmp_path, monkeypatch):
    import webui.state_store as ss
    monkeypatch.setattr(ss, "JOBS_DIR", tmp_path)

    for jid, goal in [("job-alpha", "Alpha task"), ("job-beta", "Beta mission")]:
        jdir = tmp_path / jid
        jdir.mkdir()
        (jdir / "state.json").write_text(json.dumps({
            "status": "completed", "goal": goal,
            "created": time.time(), "updated": time.time(),
        }))

    r = client.get("/api/jobs?q=alpha")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["job_id"] == "job-alpha"
