"use client";
/**
 * components/MainView.tsx — Center panel with tabs
 * Tabs: Execution | Artifacts | Product
 */

import React, { useEffect, useState } from "react";
import type { Job, EngineEvent, Artifact } from "@/lib/api";
import { fetchArtifacts } from "@/lib/api";
import EventFeed from "./EventFeed";
import FilePreviewModal from "./FilePreviewModal";

interface MainViewProps {
  job: Job | null;
  events: EngineEvent[];
  connected: boolean;
}

type Tab = "execution" | "artifacts" | "product";

function ArtifactsTab({ job }: { job: Job | null }) {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<Artifact | null>(null);

  useEffect(() => {
    if (!job) return;
    setLoading(true);
    fetchArtifacts(job.job_id)
      .then(setArtifacts)
      .catch(() => setArtifacts([]))
      .finally(() => setLoading(false));
  }, [job]);

  if (!job) {
    return (
      <div style={{ padding: "32px 16px", color: "var(--text-muted)", textAlign: "center" }}>
        Select a job to view artifacts
      </div>
    );
  }

  return (
    <div style={{ padding: "12px", height: "100%", display: "flex", flexDirection: "column" }}>
      <div className="section-label" style={{ marginBottom: "10px" }}>
        Artifacts — {job.job_id}
      </div>

      {loading && (
        <div style={{ color: "var(--text-muted)", fontSize: "11px" }}>Loading…</div>
      )}

      {!loading && artifacts.length === 0 && (
        <div style={{ color: "var(--text-muted)", fontSize: "11px" }}>No artifacts yet</div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
          gap: "8px",
          overflowY: "auto",
        }}
      >
        {artifacts.map((a) => (
          <div
            key={a.path}
            className="panel"
            style={{ padding: "10px", cursor: "pointer", transition: "background 0.1s" }}
            onClick={() => setPreview(a)}
            onMouseEnter={(e) =>
              (e.currentTarget.style.background = "var(--bg-hover)")
            }
            onMouseLeave={(e) =>
              (e.currentTarget.style.background = "var(--bg-panel)")
            }
          >
            <div style={{ color: "var(--accent)", fontSize: "12px", fontWeight: 600 }} className="truncate">
              {a.path}
            </div>
            <div style={{ color: "var(--text-muted)", fontSize: "10px", marginTop: "4px" }}>
              {(a.size / 1024).toFixed(1)} KB · {a.mime.split("/")[1] ?? a.mime}
            </div>
          </div>
        ))}
      </div>

      {preview && (
        <FilePreviewModal
          jobId={job.job_id}
          artifact={preview}
          onClose={() => setPreview(null)}
        />
      )}
    </div>
  );
}

function ProductTab({ job }: { job: Job | null }) {
  if (!job) {
    return (
      <div style={{ padding: "32px 16px", color: "var(--text-muted)", textAlign: "center" }}>
        Select a job to view output
      </div>
    );
  }

  return (
    <div style={{ padding: "12px", height: "100%", display: "flex", flexDirection: "column" }}>
      <div className="section-label" style={{ marginBottom: "10px" }}>
        Product Output — {job.job_id}
      </div>

      {job.state === "completed" && job.result ? (
        <div className="scroll-fill">
          <pre
            style={{
              margin: 0,
              fontSize: "12px",
              color: "var(--text-primary)",
              lineHeight: 1.7,
              whiteSpace: "pre-wrap",
              wordBreak: "break-all",
            }}
          >
            {job.result}
          </pre>
        </div>
      ) : job.state === "failed" ? (
        <div style={{ color: "var(--status-red)", fontSize: "12px" }}>
          <span style={{ fontWeight: 700 }}>FAILED:</span> {job.error ?? "Unknown error"}
        </div>
      ) : (
        <div style={{ color: "var(--text-muted)", fontSize: "11px" }}>
          {job.state === "running" ? "Job is running — result will appear here on completion" : "No output yet"}
        </div>
      )}
    </div>
  );
}

export default function MainView({ job, events, connected }: MainViewProps) {
  const [activeTab, setActiveTab] = useState<Tab>("execution");

  const tabs: { id: Tab; label: string }[] = [
    { id: "execution", label: "Execution" },
    { id: "artifacts", label: "Artifacts" },
    { id: "product",   label: "Product" },
  ];

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        background: "var(--bg-base)",
      }}
    >
      {/* Job info banner */}
      {job && (
        <div
          style={{
            padding: "6px 14px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            gap: "10px",
            flexShrink: 0,
            background: "var(--bg-surface)",
          }}
        >
          <div className={`dot ${job.state === "running" ? "green blink" : job.state === "completed" ? "green" : job.state === "failed" ? "red" : "amber"}`} />
          <span style={{ color: "var(--text-muted)", fontSize: "10px", fontFamily: "var(--font-mono)" }}>
            {job.job_id}
          </span>
          <span
            style={{
              color: "var(--text-primary)",
              fontSize: "12px",
              flex: 1,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {job.task}
          </span>
          <span style={{ color: "var(--text-muted)", fontSize: "10px" }}>
            {job.agent} · {job.provider}
          </span>
        </div>
      )}

      {/* Tab bar */}
      <div className="tab-bar" style={{ flexShrink: 0 }}>
        {tabs.map((t) => (
          <div
            key={t.id}
            className={`tab ${activeTab === t.id ? "active" : ""}`}
            onClick={() => setActiveTab(t.id)}
          >
            {t.label}
          </div>
        ))}
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
        {activeTab === "execution" && (
          <EventFeed events={events} connected={connected} />
        )}
        {activeTab === "artifacts" && <ArtifactsTab job={job} />}
        {activeTab === "product" && <ProductTab job={job} />}
      </div>
    </div>
  );
}
