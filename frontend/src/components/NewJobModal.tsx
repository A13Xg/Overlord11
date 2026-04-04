"use client";
/**
 * components/NewJobModal.tsx — Create new job dialog
 */

import React, { useState } from "react";

interface NewJobModalProps {
  onSubmit: (task: string, agent: string, provider: string) => Promise<void>;
  onClose: () => void;
}

const AGENTS = ["orchestrator", "researcher", "coder", "analyst", "writer", "reviewer"];
const PROVIDERS = ["anthropic", "gemini", "openai"];

export default function NewJobModal({ onSubmit, onClose }: NewJobModalProps) {
  const [task, setTask] = useState("");
  const [agent, setAgent] = useState("orchestrator");
  const [provider, setProvider] = useState("anthropic");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!task.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(task.trim(), agent, provider);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create job");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(6,8,16,0.88)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        backdropFilter: "blur(4px)",
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "var(--bg-panel)",
          border: "1px solid var(--border-bright)",
          borderRadius: "4px",
          width: "min(560px, 90vw)",
          boxShadow: "0 0 40px var(--accent-glow)",
          padding: "20px",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="section-label" style={{ marginBottom: "16px", fontSize: "12px" }}>
          ▶ NEW MISSION — CREATE JOB
        </div>

        {/* Task */}
        <div style={{ marginBottom: "14px" }}>
          <label style={{ color: "var(--text-label)", fontSize: "10px", display: "block", marginBottom: "5px" }}>
            TASK / PROMPT
          </label>
          <textarea
            className="input-tac"
            rows={5}
            placeholder="Describe the task for the agent to execute…"
            value={task}
            onChange={(e) => setTask(e.target.value)}
            autoFocus
          />
        </div>

        {/* Agent + Provider row */}
        <div style={{ display: "flex", gap: "12px", marginBottom: "16px" }}>
          <div style={{ flex: 1 }}>
            <label style={{ color: "var(--text-label)", fontSize: "10px", display: "block", marginBottom: "5px" }}>
              AGENT
            </label>
            <select
              className="input-tac"
              value={agent}
              onChange={(e) => setAgent(e.target.value)}
              style={{ cursor: "pointer" }}
            >
              {AGENTS.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ color: "var(--text-label)", fontSize: "10px", display: "block", marginBottom: "5px" }}>
              PROVIDER
            </label>
            <select
              className="input-tac"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              style={{ cursor: "pointer" }}
            >
              {PROVIDERS.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
        </div>

        {error && (
          <div style={{ color: "var(--status-red)", fontSize: "11px", marginBottom: "12px" }}>
            ✗ {error}
          </div>
        )}

        {/* Actions */}
        <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
          <button className="btn-tac" onClick={onClose} style={{ opacity: 0.7 }}>
            CANCEL
          </button>
          <button
            className="btn-tac"
            onClick={handleSubmit}
            disabled={!task.trim() || submitting}
            style={{ opacity: !task.trim() || submitting ? 0.4 : 1 }}
          >
            {submitting ? "LAUNCHING…" : "▶ LAUNCH JOB"}
          </button>
        </div>
      </div>
    </div>
  );
}
