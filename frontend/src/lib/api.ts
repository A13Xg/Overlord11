/**
 * lib/api.ts — Overlord11 API client
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

export interface Job {
  job_id: string;
  task: string;
  agent: string;
  provider: string;
  state: "queued" | "running" | "paused" | "completed" | "failed";
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  result: string | null;
  error: string | null;
  session_id: string | null;
  metadata: Record<string, unknown>;
}

export interface EngineEvent {
  type: string;
  session_id: string;
  ts: number;
  [key: string]: unknown;
}

export interface Model {
  id: string;
  description: string;
  active: boolean;
}

export interface ModelsResponse {
  provider: string;
  current_model: string;
  models: Model[];
}

export interface ProviderStatus {
  status: "green" | "red";
  is_active: boolean;
  model: string;
}

export interface Artifact {
  path: string;
  size: number;
  mtime: number;
  mime: string;
}

// ─── Jobs ────────────────────────────────────────────────────────────────────

export async function fetchJobs(state?: string): Promise<Job[]> {
  const url = new URL(`${API_BASE}/api/jobs`);
  if (state) url.searchParams.set("state", state);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`fetchJobs failed: ${res.status}`);
  return res.json();
}

export async function createJob(payload: {
  task: string;
  agent?: string;
  provider?: string;
  metadata?: Record<string, unknown>;
  autostart?: boolean;
}): Promise<Job> {
  const res = await fetch(`${API_BASE}/api/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`createJob failed: ${res.status}`);
  return res.json();
}

export async function patchJob(
  jobId: string,
  action: "start" | "pause" | "resume" | "stop" | "restart"
): Promise<Job | { message: string; job: Job }> {
  const res = await fetch(`${API_BASE}/api/jobs/${jobId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
  if (!res.ok) throw new Error(`patchJob failed: ${res.status}`);
  return res.json();
}

export async function deleteJob(jobId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/jobs/${jobId}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) throw new Error(`deleteJob failed: ${res.status}`);
}

export async function bulkControl(action: "start-all" | "pause-all" | "stop-all"): Promise<unknown> {
  const res = await fetch(`${API_BASE}/api/jobs/control/${action}`, { method: "POST" });
  if (!res.ok) throw new Error(`bulkControl failed: ${res.status}`);
  return res.json();
}

// ─── Events ──────────────────────────────────────────────────────────────────

export function createEventSource(sessionId: string, since = 0): EventSource {
  return new EventSource(`${API_BASE}/api/events/${sessionId}?since=${since}`);
}

export async function fetchEventHistory(
  sessionId: string,
  since = 0
): Promise<EngineEvent[]> {
  const res = await fetch(
    `${API_BASE}/api/events/${sessionId}/history?since=${since}`
  );
  if (!res.ok) throw new Error(`fetchEventHistory failed: ${res.status}`);
  const data = await res.json();
  return data.events ?? [];
}

// ─── Models ──────────────────────────────────────────────────────────────────

export async function fetchModels(provider?: string): Promise<ModelsResponse> {
  const url = provider
    ? `${API_BASE}/api/models/${provider}`
    : `${API_BASE}/api/models`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`fetchModels failed: ${res.status}`);
  return res.json();
}

export async function fetchProviderStatus(): Promise<
  Record<string, ProviderStatus>
> {
  const res = await fetch(`${API_BASE}/api/providers/status`);
  if (!res.ok) throw new Error(`fetchProviderStatus failed: ${res.status}`);
  return res.json();
}

export async function updateConfig(payload: {
  provider?: string;
  model?: string;
}): Promise<unknown> {
  const res = await fetch(`${API_BASE}/api/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`updateConfig failed: ${res.status}`);
  return res.json();
}

// ─── Artifacts ───────────────────────────────────────────────────────────────

export async function fetchArtifacts(jobId: string): Promise<Artifact[]> {
  const res = await fetch(`${API_BASE}/api/artifacts/${jobId}`);
  if (!res.ok) throw new Error(`fetchArtifacts failed: ${res.status}`);
  return res.json();
}

export function artifactDownloadUrl(jobId: string, filename: string): string {
  return `${API_BASE}/api/artifacts/${jobId}/${encodeURIComponent(filename)}`;
}

// ─── Health ──────────────────────────────────────────────────────────────────

export async function fetchHealth(): Promise<{ status: string; version: string }> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error("health check failed");
  return res.json();
}
