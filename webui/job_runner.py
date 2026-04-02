"""Background job runner for Overlord11 Tactical WebUI.

This worker turns queued jobs in workspace/jobs into full executions by:
- claiming pending jobs
- calling the configured LLM provider/model
- writing events and artifacts
- updating status transitions (pending -> running -> completed/failed)
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from . import provider_health, state_store
from .logging_config import get_agents_logger


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT_DIR / "config.json"
AGENTS_DIR = ROOT_DIR / "agents"

MAX_PROMPT_CHARS = 18000
DEFAULT_TIMEOUT_S = 120

log = get_agents_logger()


@dataclass
class ClaimedJob:
    job_id: str
    job_dir: Path
    state: Dict[str, Any]


class JobRunner:
    """Single-process job runner with a polling loop."""

    def __init__(self, poll_interval_s: float = 2.0):
        self.poll_interval_s = max(0.5, poll_interval_s)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._paused = False
        self._active_job_id: Optional[str] = None
        self._started_at: Optional[float] = None

    def start(self) -> Dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                pass
            else:
                self._stop.clear()
                self._wake.clear()
                self._thread = threading.Thread(
                    target=self._loop,
                    name="overlord11-job-runner",
                    daemon=True,
                )
                self._thread.start()
                self._started_at = time.time()
                log.info("Job runner started", extra={"event": "runner_start"})
        return self.status()

    def stop(self, timeout_s: float = 5.0) -> Dict[str, Any]:
        with self._lock:
            self._stop.set()
            self._wake.set()
            thread = self._thread
        if thread:
            thread.join(timeout=timeout_s)
        with self._lock:
            self._thread = None
            self._active_job_id = None
            log.info("Job runner stopped", extra={"event": "runner_stop"})
        return self.status()

    def pause(self) -> Dict[str, Any]:
        with self._lock:
            self._paused = True
            log.info("Job runner paused", extra={"event": "runner_pause"})
        return self.status()

    def resume(self) -> Dict[str, Any]:
        with self._lock:
            self._paused = False
            self._wake.set()
            log.info("Job runner resumed", extra={"event": "runner_resume"})
        return self.status()

    def trigger_scan(self) -> None:
        self._wake.set()

    def status(self) -> Dict[str, Any]:
        with self._lock:
            alive = bool(self._thread and self._thread.is_alive())
            return {
                "running": alive,
                "paused": self._paused,
                "poll_interval_s": self.poll_interval_s,
                "active_job_id": self._active_job_id,
                "started_at": self._started_at,
            }

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._paused:
                self._wake.wait(timeout=self.poll_interval_s)
                self._wake.clear()
                continue

            claimed = self._claim_next_job()
            if not claimed:
                self._wake.wait(timeout=self.poll_interval_s)
                self._wake.clear()
                continue

            with self._lock:
                self._active_job_id = claimed.job_id
            try:
                self._process_job(claimed)
            except Exception as exc:
                self._append_event(
                    claimed.job_dir,
                    "error",
                    f"Runner crashed while processing job: {exc}",
                )
                self._set_state(
                    claimed.job_dir,
                    {
                        "status": "failed",
                        "error": str(exc),
                        "updated": time.time(),
                    },
                )
                log.error(
                    "Job execution failed",
                    extra={"event": "job_failed", "job_id": claimed.job_id, "exc": str(exc)},
                )
            finally:
                with self._lock:
                    self._active_job_id = None

    def _claim_next_job(self) -> Optional[ClaimedJob]:
        jobs_dir = state_store.JOBS_DIR
        if not jobs_dir.exists():
            return None

        job_dirs = [d for d in jobs_dir.iterdir() if d.is_dir()]
        job_dirs.sort(key=lambda p: p.stat().st_mtime)

        for job_dir in job_dirs:
            state = self._read_state(job_dir)
            if not state:
                continue
            if state.get("status") != "pending":
                continue
            now = time.time()
            state["status"] = "running"
            state["started"] = now
            state["updated"] = now
            self._write_state(job_dir, state)
            self._append_event(job_dir, "info", "Runner claimed job and started execution")
            job_id = state.get("job_id") or job_dir.name
            return ClaimedJob(job_id=job_id, job_dir=job_dir, state=state)
        return None

    def _process_job(self, job: ClaimedJob) -> None:
        state = self._read_state(job.job_dir) or job.state
        goal = (state.get("goal") or "").strip()
        provider = state.get("provider") or "gemini"
        model = state.get("model") or ""
        verify_command = state.get("verify_command") or ""

        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._append_event(job.job_dir, "info", f"Planning execution for goal: {goal}")

        project_context = self._build_project_context(goal)
        plan_prompt = self._build_plan_prompt(goal, project_context)
        plan_text = self._call_provider(provider, model, plan_prompt, self._orchestrator_system_prompt())

        self._append_event(job.job_dir, "info", "Plan generated; drafting deliverable")

        draft_prompt = self._build_draft_prompt(goal, project_context, plan_text)
        draft_text = self._call_provider(provider, model, draft_prompt, self._coder_writer_system_prompt())

        self._append_event(job.job_dir, "info", "Draft generated; running reviewer pass")
        review_prompt = self._build_review_prompt(goal, draft_text)
        reviewed_text = self._call_provider(provider, model, review_prompt, self._reviewer_system_prompt())

        verify_summary = "not requested"
        if verify_command:
            self._append_event(job.job_dir, "info", f"Running verify command: {verify_command}")
            verify_summary = self._run_verify(verify_command)

        artifacts_dir = job.job_dir / "artifacts"
        reports_dir = artifacts_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        (artifacts_dir / "output.md").write_text(reviewed_text, encoding="utf-8")
        (artifacts_dir / "final_report.md").write_text(
            self._build_final_report(job, provider, model, plan_text, reviewed_text, verify_summary),
            encoding="utf-8",
        )
        (reports_dir / "debrief.md").write_text(
            self._build_debrief(job, session_id, provider, model, plan_text, verify_summary),
            encoding="utf-8",
        )

        self._set_state(
            job.job_dir,
            {
                "status": "completed",
                "updated": time.time(),
                "finished": time.time(),
                "verify_summary": verify_summary,
            },
        )
        self._append_event(job.job_dir, "success", "Job completed and artifacts published")
        log.info(
            "Job completed",
            extra={"event": "job_completed", "job_id": job.job_id, "provider": provider, "model": model},
        )

    def _build_project_context(self, goal: str) -> str:
        snippets: List[str] = [f"Goal: {goal}"]
        key_files = [
            "README.md",
            "ONBOARDING.md",
            "Consciousness.md",
            "docs/Architecture.md",
            "docs/Tools-Reference.md",
        ]
        for rel in key_files:
            path = ROOT_DIR / rel
            if not path.exists():
                continue
            snippets.append(f"\n## {rel}\n" + self._read_file_truncated(path, 2400))

        tree_lines: List[str] = []
        for top in sorted(ROOT_DIR.iterdir()):
            if top.name.startswith("."):
                continue
            if top.is_dir():
                tree_lines.append(f"- {top.name}/")
                children = sorted(top.iterdir())[:25]
                for child in children:
                    suffix = "/" if child.is_dir() else ""
                    tree_lines.append(f"  - {top.name}/{child.name}{suffix}")
            else:
                tree_lines.append(f"- {top.name}")

        snippets.append("\n## Project Tree Snapshot\n" + "\n".join(tree_lines[:300]))
        merged = "\n".join(snippets)
        return merged[:MAX_PROMPT_CHARS]

    def _build_plan_prompt(self, goal: str, context: str) -> str:
        return (
            "Create an execution plan for this Overlord11 job. "
            "Return concise markdown with:\n"
            "1. Task classification\n"
            "2. Output tier (0/1/2)\n"
            "3. Delegation plan across specialist agents\n"
            "4. Risks and mitigations\n\n"
            f"Job goal:\n{goal}\n\n"
            f"Project context:\n{context}"
        )

    def _build_draft_prompt(self, goal: str, context: str, plan_text: str) -> str:
        return (
            "Execute the plan and produce the primary user deliverable for the job. "
            "Be concrete, actionable, and tailored to this repository. "
            "If code changes are needed, provide patch-ready snippets and exact file targets.\n\n"
            f"Goal:\n{goal}\n\n"
            f"Plan:\n{plan_text}\n\n"
            f"Context:\n{context}"
        )

    def _build_review_prompt(self, goal: str, draft_text: str) -> str:
        return (
            "Review and improve this deliverable for correctness, safety, and completeness. "
            "Fix weak sections and return final markdown suitable for artifacts/output.md.\n\n"
            f"Goal:\n{goal}\n\n"
            f"Draft:\n{draft_text}"
        )

    def _orchestrator_system_prompt(self) -> str:
        return self._read_file_truncated(AGENTS_DIR / "orchestrator.md", 5000)

    def _coder_writer_system_prompt(self) -> str:
        coder = self._read_file_truncated(AGENTS_DIR / "coder.md", 3500)
        writer = self._read_file_truncated(AGENTS_DIR / "writer.md", 3000)
        return f"# Coder\n{coder}\n\n# Writer\n{writer}"

    def _reviewer_system_prompt(self) -> str:
        return self._read_file_truncated(AGENTS_DIR / "reviewer.md", 4500)

    def _run_verify(self, command: str) -> str:
        try:
            res = subprocess.run(
                command,
                cwd=str(ROOT_DIR),
                shell=True,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except Exception as exc:
            return f"verify command failed to start: {exc}"

        out = (res.stdout or "").strip()
        err = (res.stderr or "").strip()
        merged = "\n".join([x for x in [out, err] if x]).strip()
        merged = merged[:3000]
        return f"exit={res.returncode}; output={merged or '(no output)'}"

    def _build_final_report(
        self,
        job: ClaimedJob,
        provider: str,
        model: str,
        plan_text: str,
        reviewed_text: str,
        verify_summary: str,
    ) -> str:
        return (
            f"# Final Report\n\n"
            f"- Job: {job.job_id}\n"
            f"- Provider: {provider}\n"
            f"- Model: {model}\n"
            f"- Generated: {datetime.now().isoformat()}\n"
            f"- Verify: {verify_summary}\n\n"
            f"## Plan\n\n{plan_text}\n\n"
            f"## Final Deliverable\n\n{reviewed_text}\n"
        )

    def _build_debrief(
        self,
        job: ClaimedJob,
        session_id: str,
        provider: str,
        model: str,
        plan_text: str,
        verify_summary: str,
    ) -> str:
        return (
            f"# Debrief\n\n"
            f"- Session: {session_id}\n"
            f"- Job: {job.job_id}\n"
            f"- Provider/Model: {provider}/{model}\n"
            f"- Verify Summary: {verify_summary}\n\n"
            f"## Execution Plan\n\n{plan_text}\n"
        )

    def _load_config(self) -> Dict[str, Any]:
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _provider_params(self, provider: str, requested_model: str) -> Tuple[dict, str, str]:
        cfg = self._load_config().get("providers", {})
        pcfg = cfg.get(provider, {})
        model = requested_model or pcfg.get("model", "")
        key_env = pcfg.get("api_key_env", "")
        api_key = os.environ.get(key_env, "") if key_env else ""
        if not api_key:
            raise RuntimeError(f"Provider key missing for {provider}: set {key_env}")
        return pcfg, model, api_key

    def _call_provider(self, provider: str, model: str, prompt: str, system_prompt: str) -> str:
        if provider == "gemini":
            return self._call_gemini(model, prompt, system_prompt)
        if provider == "openai":
            return self._call_openai(model, prompt, system_prompt)
        if provider == "anthropic":
            return self._call_anthropic(model, prompt, system_prompt)
        raise RuntimeError(f"Unsupported provider: {provider}")

    def _call_gemini(self, requested_model: str, prompt: str, system_prompt: str) -> str:
        pcfg, model, api_key = self._provider_params("gemini", requested_model)
        base = pcfg.get("api_base", "https://generativelanguage.googleapis.com/v1beta")
        timeout = pcfg.get("timeout_s", DEFAULT_TIMEOUT_S)

        attempt_model = model
        tries = 0
        while attempt_model:
            tries += 1
            url = f"{base}/models/{attempt_model}:generateContent"
            payload = {
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.5,
                    "maxOutputTokens": 4096,
                },
            }
            try:
                r = httpx.post(url, params={"key": api_key}, json=payload, timeout=timeout)
            except Exception as exc:
                raise RuntimeError(f"Gemini request failed: {exc}") from exc

            if r.status_code == 200:
                data = r.json()
                text_parts: List[str] = []
                for c in data.get("candidates", []):
                    for p in c.get("content", {}).get("parts", []):
                        t = p.get("text")
                        if t:
                            text_parts.append(t)
                out = "\n".join(text_parts).strip()
                if out:
                    return out
                raise RuntimeError("Gemini returned empty content")

            body = r.text
            is_rate_limited = r.status_code == 429 and "RESOURCE_EXHAUSTED" in body
            if is_rate_limited and tries <= 8:
                fallback_model = provider_health.get_gemini_fallback_model(attempt_model)
                if fallback_model:
                    attempt_model = fallback_model
                    continue
            raise RuntimeError(f"Gemini HTTP {r.status_code}: {body[:400]}")

        raise RuntimeError("Gemini fallback chain exhausted")

    def _call_openai(self, requested_model: str, prompt: str, system_prompt: str) -> str:
        pcfg, model, api_key = self._provider_params("openai", requested_model)
        base = pcfg.get("api_base", "https://api.openai.com/v1")
        timeout = pcfg.get("timeout_s", DEFAULT_TIMEOUT_S)
        payload = {
            "model": model,
            "temperature": 0.5,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            r = httpx.post(f"{base}/chat/completions", json=payload, headers=headers, timeout=timeout)
        except Exception as exc:
            raise RuntimeError(f"OpenAI request failed: {exc}") from exc
        if r.status_code != 200:
            raise RuntimeError(f"OpenAI HTTP {r.status_code}: {r.text[:400]}")
        data = r.json()
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("OpenAI returned no choices")
        msg = choices[0].get("message", {})
        content = msg.get("content", "")
        if isinstance(content, list):
            out = "\n".join(str(x.get("text", "")) for x in content if isinstance(x, dict)).strip()
        else:
            out = str(content).strip()
        if not out:
            raise RuntimeError("OpenAI returned empty content")
        return out

    def _call_anthropic(self, requested_model: str, prompt: str, system_prompt: str) -> str:
        pcfg, model, api_key = self._provider_params("anthropic", requested_model)
        base = pcfg.get("api_base", "https://api.anthropic.com/v1")
        timeout = pcfg.get("timeout_s", DEFAULT_TIMEOUT_S)
        payload = {
            "model": model,
            "max_tokens": 4096,
            "temperature": 0.5,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            r = httpx.post(f"{base}/messages", json=payload, headers=headers, timeout=timeout)
        except Exception as exc:
            raise RuntimeError(f"Anthropic request failed: {exc}") from exc
        if r.status_code != 200:
            raise RuntimeError(f"Anthropic HTTP {r.status_code}: {r.text[:400]}")
        data = r.json()
        parts = data.get("content", [])
        out_parts: List[str] = []
        for item in parts:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                out_parts.append(item["text"])
        out = "\n".join(out_parts).strip()
        if not out:
            raise RuntimeError("Anthropic returned empty content")
        return out

    def _read_state(self, job_dir: Path) -> Dict[str, Any]:
        state_file = job_dir / "state.json"
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_state(self, job_dir: Path, state: Dict[str, Any]) -> None:
        (job_dir / "state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _set_state(self, job_dir: Path, patch: Dict[str, Any]) -> None:
        state = self._read_state(job_dir)
        state.update(patch)
        if "updated" not in patch:
            state["updated"] = time.time()
        self._write_state(job_dir, state)

    def _append_event(self, job_dir: Path, event_type: str, message: str) -> None:
        event = {
            "type": event_type,
            "message": message,
            "timestamp": time.time(),
        }
        events_file = job_dir / "events.jsonl"
        with events_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _read_file_truncated(self, path: Path, max_chars: int) -> str:
        try:
            txt = path.read_text(encoding="utf-8")
        except Exception:
            return ""
        return txt[:max_chars]
