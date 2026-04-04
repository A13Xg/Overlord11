"use client";
/**
 * components/JobQueue.tsx — Left panel job list
 */

import React, { useState } from "react";
import type { Job } from "@/lib/api";

interface JobQueueProps {
  jobs: Job[];
  selectedJobId: string | null;
  onSelect: (job: Job) => void;
  onControl: (jobId: string, action: "start" | "pause" | "resume" | "stop" | "restart") => void;
  onDelete: (jobId: string) => void;
  onNewJob: () => void;
}

function stateColor(state: Job["state"]): string {
  switch (state) {
    case "running":   return "var(--status-green)";
    case "paused":    return "var(--status-amber)";
    case "completed": return "var(--accent-dim)";
    case "failed":    return "var(--status-red)";
    default:          return "var(--text-muted)";
  }
}

function StateChip({ state }: { state: Job["state"] }) {
  return (
    <span className={`chip ${state}`}>{state}</span>
  );
}

function JobItem({
  job,
  selected,
  onSelect,
  onControl,
  onDelete,
}: {
  job: Job;
  selected: boolean;
  onSelect: () => void;
  onControl: (action: "start" | "pause" | "resume" | "stop" | "restart") => void;
  onDelete: () => void;
}) {
  const [showActions, setShowActions] = useState(false);

  return (
    <div
      onClick={onSelect}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
      style={{
        padding: "8px 10px",
        borderBottom: "1px solid var(--border)",
        cursor: "pointer",
        background: selected ? "var(--bg-hover)" : "transparent",
        borderLeft: selected
          ? `2px solid ${stateColor(job.state)}`
          : "2px solid transparent",
        transition: "background 0.1s",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: "6px",
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            className="truncate"
            style={{ color: "var(--text-primary)", fontSize: "12px", lineHeight: 1.4 }}
            title={job.task}
          >
            {job.task}
          </div>
          <div
            style={{
              display: "flex",
              gap: "6px",
              alignItems: "center",
              marginTop: "4px",
            }}
          >
            <StateChip state={job.state} />
            <span style={{ color: "var(--text-muted)", fontSize: "10px" }}>
              {job.agent}
            </span>
            <span style={{ color: "var(--text-muted)", fontSize: "10px" }}>
              {job.provider}
            </span>
          </div>
        </div>
        <span
          style={{
            color: "var(--text-muted)",
            fontSize: "9px",
            flexShrink: 0,
            marginTop: "2px",
          }}
        >
          {job.job_id.slice(0, 6)}
        </span>
      </div>

      {/* Per-job controls (on hover) */}
      {showActions && (
        <div
          style={{
            display: "flex",
            gap: "4px",
            marginTop: "6px",
            flexWrap: "wrap",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {job.state === "queued" && (
            <button className="btn-tac" style={{ padding: "2px 7px", fontSize: "9px" }} onClick={() => onControl("start")}>
              ▶
            </button>
          )}
          {job.state === "running" && (
            <button className="btn-tac amber" style={{ padding: "2px 7px", fontSize: "9px" }} onClick={() => onControl("pause")}>
              ⏸
            </button>
          )}
          {job.state === "paused" && (
            <button className="btn-tac" style={{ padding: "2px 7px", fontSize: "9px" }} onClick={() => onControl("resume")}>
              ▶
            </button>
          )}
          {(job.state === "running" || job.state === "queued" || job.state === "paused") && (
            <button className="btn-tac danger" style={{ padding: "2px 7px", fontSize: "9px" }} onClick={() => onControl("stop")}>
              ■
            </button>
          )}
          <button className="btn-tac amber" style={{ padding: "2px 7px", fontSize: "9px" }} onClick={() => onControl("restart")}>
            ↺
          </button>
          <button className="btn-tac danger" style={{ padding: "2px 7px", fontSize: "9px" }} onClick={onDelete}>
            ✕
          </button>
        </div>
      )}
    </div>
  );
}

export default function JobQueue({
  jobs,
  selectedJobId,
  onSelect,
  onControl,
  onDelete,
  onNewJob,
}: JobQueueProps) {
  const running = jobs.filter((j) => j.state === "running").length;
  const queued = jobs.filter((j) => j.state === "queued").length;

  return (
    <div
      style={{
        width: "260px",
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        borderRight: "1px solid var(--border)",
        background: "var(--bg-panel)",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "10px 10px 8px",
          borderBottom: "1px solid var(--border)",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span className="section-label">Job Queue</span>
          <button className="btn-tac" style={{ fontSize: "10px", padding: "3px 8px" }} onClick={onNewJob}>
            + NEW
          </button>
        </div>
        <div
          style={{
            display: "flex",
            gap: "10px",
            marginTop: "6px",
            fontSize: "10px",
            color: "var(--text-muted)",
          }}
        >
          <span>
            <span style={{ color: "var(--status-green)" }}>{running}</span> running
          </span>
          <span>
            <span style={{ color: "var(--text-secondary)" }}>{queued}</span> queued
          </span>
          <span>{jobs.length} total</span>
        </div>
      </div>

      {/* Job list */}
      <div className="scroll-fill">
        {jobs.length === 0 ? (
          <div
            style={{
              padding: "24px 16px",
              color: "var(--text-muted)",
              textAlign: "center",
              fontSize: "11px",
            }}
          >
            No jobs yet.
            <br />
            <span
              style={{ color: "var(--accent)", cursor: "pointer", marginTop: "6px", display: "inline-block" }}
              onClick={onNewJob}
            >
              + Create one
            </span>
          </div>
        ) : (
          jobs.map((job) => (
            <JobItem
              key={job.job_id}
              job={job}
              selected={job.job_id === selectedJobId}
              onSelect={() => onSelect(job)}
              onControl={(action) => onControl(job.job_id, action)}
              onDelete={() => onDelete(job.job_id)}
            />
          ))
        )}
      </div>
    </div>
  );
}
