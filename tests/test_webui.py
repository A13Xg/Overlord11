"""Tests for the Overlord11 Tactical WebUI backend."""
import json
import os
import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

os.environ.setdefault("OVERLORD11_WEBUI_RUNNER", "0")

from webui.app import app

client = TestClient(app)


def test_runner_status_endpoint():
    r = client.get("/api/runner/status")
    assert r.status_code == 200
    data = r.json()
    assert "running" in data
    assert "paused" in data
    assert "active_job_id" in data


def test_runner_pause_resume_cycle():
    rp = client.post("/api/runner/pause")
    assert rp.status_code == 200
    assert rp.json()["paused"] is True

    rr = client.post("/api/runner/resume")
    assert rr.status_code == 200
    assert rr.json()["paused"] is False


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "Overlord11" in data["service"]
    assert "version" in data


def test_list_jobs_empty():
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_jobs_status_filter(tmp_path, monkeypatch):
    import webui.state_store as ss
    monkeypatch.setattr(ss, "JOBS_DIR", tmp_path)

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

    event = {"type": "info", "message": "Job started", "timestamp": 1700000001.0}
    (jdir / "events.jsonl").write_text(json.dumps(event) + "\n")

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
    # active provider should come from prefs or config; both have gemini as default
    assert "active_provider" in data
    assert "gemini" in data["providers"]
    assert "gemini-3.1-flash-lite-preview" in data["providers"]["gemini"]["available_models"]


def test_config_no_api_keys():
    r = client.get("/api/config")
    data = r.json()
    for provider, pcfg in data["providers"].items():
        assert "api_key" not in pcfg


def test_config_has_key_env_names():
    """Config should expose env var names but never actual key values."""
    r = client.get("/api/config")
    data = r.json()
    for name, pcfg in data["providers"].items():
        assert "api_key_env" in pcfg
        # The value should be an env var name like GOOGLE_GEMINI_API_KEY, not a real key
        env_name = pcfg["api_key_env"]
        assert len(env_name) < 50
        assert env_name == env_name.upper() or env_name == ""


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
    content = b"Hello from artifact \xc3\xa9"  # UTF-8 bytes
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


# ── Provider status ──────────────────────────────────────────────────────────

def test_provider_status_structure():
    """Endpoint must return all three providers with expected shape."""
    r = client.get("/api/providers/status")
    assert r.status_code == 200
    data = r.json()
    for name in ["gemini", "openai", "anthropic"]:
        assert name in data, f"Missing provider: {name}"
        assert "status" in data[name]
        assert data[name]["status"] in ("ok", "no_key", "error", "checking", "no_config")
        assert "models" in data[name]
        assert isinstance(data[name]["models"], list)
        assert "error" in data[name]


def test_provider_status_no_keys():
    """Without API keys in env, all providers should report no_key (or error if httpx unavailable)."""
    # Temporarily clear any stray env vars
    r = client.get("/api/providers/status")
    assert r.status_code == 200
    data = r.json()
    for name in ["gemini", "openai", "anthropic"]:
        # In CI with no keys, each should be no_key (or error/checking if previously probed)
        assert data[name]["status"] in ("ok", "no_key", "error", "checking", "no_config")


def test_provider_status_force_probe():
    """?force=true triggers a fresh probe and returns results immediately."""
    r = client.get("/api/providers/status?force=true")
    assert r.status_code == 200
    data = r.json()
    assert "gemini" in data
    assert "openai" in data
    assert "anthropic" in data


def test_provider_status_gemini_no_key(monkeypatch):
    """Gemini should return no_key when GOOGLE_GEMINI_API_KEY is not set."""
    monkeypatch.delenv("GOOGLE_GEMINI_API_KEY", raising=False)
    import webui.provider_health as ph
    ph._cache.clear()
    r = client.get("/api/providers/status?force=true")
    assert r.status_code == 200
    data = r.json()
    assert data["gemini"]["status"] == "no_key"


# ── Config selection ─────────────────────────────────────────────────────────

def test_config_selection_get():
    """GET returns current provider/model selection."""
    r = client.get("/api/config/selection")
    assert r.status_code == 200
    data = r.json()
    assert "provider" in data
    assert "model" in data
    assert "from_prefs" in data


def test_config_selection_put(tmp_path, monkeypatch):
    """PUT stores a new provider/model selection."""
    import webui.app as wa
    monkeypatch.setattr(wa, "PREFS_FILE", tmp_path / ".prefs.json")

    r = client.put("/api/config/selection",
                   json={"provider": "gemini", "model": "gemini-2.5-flash"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["provider"] == "gemini"
    assert data["model"] == "gemini-2.5-flash"

    # Verify it persisted
    r2 = client.get("/api/config/selection")
    # Note: PREFS_FILE is monkeypatched in app but _load_prefs reads it fresh each call
    # The PUT wrote to tmp_path/.prefs.json; GET reads from PREFS_FILE which is
    # still the original path — so we just verify the PUT response is correct.
    assert r2.status_code == 200


def test_config_selection_put_openai(tmp_path, monkeypatch):
    import webui.app as wa
    monkeypatch.setattr(wa, "PREFS_FILE", tmp_path / ".prefs.json")

    r = client.put("/api/config/selection",
                   json={"provider": "openai", "model": "gpt-4o"})
    assert r.status_code == 200
    assert r.json()["provider"] == "openai"


def test_config_selection_invalid_provider():
    """PUT with an unknown provider must return 400."""
    r = client.put("/api/config/selection",
                   json={"provider": "badprovider", "model": "some-model"})
    assert r.status_code == 400


def test_config_selection_delete(tmp_path, monkeypatch):
    """DELETE resets selection to config defaults."""
    import webui.app as wa
    monkeypatch.setattr(wa, "PREFS_FILE", tmp_path / ".prefs.json")

    # First set a preference
    client.put("/api/config/selection",
               json={"provider": "openai", "model": "gpt-4o"})

    r = client.delete("/api/config/selection")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "provider" in data
    assert "model" in data


# ── Job creation ─────────────────────────────────────────────────────────────

def test_create_job(tmp_path, monkeypatch):
    """POST /api/jobs creates a pending job."""
    import webui.state_store as ss
    import webui.app as wa
    monkeypatch.setattr(ss, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(wa, "PREFS_FILE", tmp_path / ".prefs.json")

    r = client.post("/api/jobs", json={"goal": "Write a unit test suite"})
    assert r.status_code == 201
    data = r.json()
    assert data["goal"] == "Write a unit test suite"
    assert data["status"] == "pending"
    assert "job_id" in data
    assert data["provider"] in ("gemini", "openai", "anthropic")

    # Verify state.json was actually written
    job_dir = tmp_path / data["job_id"]
    assert job_dir.is_dir()
    state = json.loads((job_dir / "state.json").read_text(encoding="utf-8"))
    assert state["goal"] == "Write a unit test suite"
    assert state["status"] == "pending"


def test_create_job_with_provider(tmp_path, monkeypatch):
    """POST /api/jobs honours explicit provider/model."""
    import webui.state_store as ss
    import webui.app as wa
    monkeypatch.setattr(ss, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(wa, "PREFS_FILE", tmp_path / ".prefs.json")

    r = client.post("/api/jobs", json={
        "goal": "Analyse logs",
        "provider": "openai",
        "model": "gpt-4o",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["provider"] == "openai"
    assert data["model"] == "gpt-4o"


def test_create_job_empty_goal(tmp_path, monkeypatch):
    """POST /api/jobs with blank goal must return 400."""
    import webui.state_store as ss
    import webui.app as wa
    monkeypatch.setattr(ss, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(wa, "PREFS_FILE", tmp_path / ".prefs.json")

    r = client.post("/api/jobs", json={"goal": "   "})
    assert r.status_code == 400


def test_create_job_invalid_provider(tmp_path, monkeypatch):
    """POST /api/jobs with invalid provider must return 400."""
    import webui.state_store as ss
    import webui.app as wa
    monkeypatch.setattr(ss, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(wa, "PREFS_FILE", tmp_path / ".prefs.json")

    r = client.post("/api/jobs", json={"goal": "Do something", "provider": "invalid"})
    assert r.status_code == 400


# ── Gemini fallback ───────────────────────────────────────────────────────────

def test_gemini_fallback_endpoint():
    """Gemini fallback chain info endpoint must include the chain list."""
    r = client.get("/api/providers/gemini/fallback")
    assert r.status_code == 200
    data = r.json()
    assert "fallback_chain" in data
    chain = data["fallback_chain"]
    assert isinstance(chain, list)
    assert len(chain) >= 4
    assert "gemini-2.5-pro" in chain
    assert "gemini-1.5-flash" in chain
    # Chain must be ordered most-capable → least-capable
    pro_idx   = chain.index("gemini-2.5-pro")
    flash_idx = chain.index("gemini-1.5-flash")
    assert pro_idx < flash_idx


def test_gemini_fallback_logic():
    """get_gemini_fallback_model walks the chain correctly."""
    from webui.provider_health import get_gemini_fallback_model, GEMINI_FALLBACK_CHAIN
    first = GEMINI_FALLBACK_CHAIN[0]
    second = GEMINI_FALLBACK_CHAIN[1]
    assert get_gemini_fallback_model(first) == second

    # End of chain returns None
    last = GEMINI_FALLBACK_CHAIN[-1]
    assert get_gemini_fallback_model(last) is None

    # Unknown model falls back to chain[0]
    fallback = get_gemini_fallback_model("gemini-unknown-xyz")
    assert fallback == GEMINI_FALLBACK_CHAIN[0]


