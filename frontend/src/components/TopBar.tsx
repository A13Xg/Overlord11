"use client";
/**
 * components/TopBar.tsx — OVERLORD11 top navigation bar
 */

import React from "react";
import type { ProviderStatus } from "@/lib/api";

interface TopBarProps {
  providerStatus: Record<string, ProviderStatus>;
  onStartAll: () => void;
  onPauseAll: () => void;
  onStopAll: () => void;
  backendOnline: boolean;
}

function WaveformWidget() {
  return (
    <div className="waveform">
      {[14, 8, 12, 6, 16, 10, 14, 8, 12].map((h, i) => (
        <div
          key={i}
          className="waveform-bar"
          style={{ height: `${h}px`, animationDelay: `${i * 0.08}s` }}
        />
      ))}
    </div>
  );
}

export default function TopBar({
  providerStatus,
  onStartAll,
  onPauseAll,
  onStopAll,
  backendOnline,
}: TopBarProps) {
  return (
    <div
      style={{
        height: "48px",
        background: "var(--bg-panel)",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        padding: "0 16px",
        gap: "16px",
        flexShrink: 0,
      }}
    >
      {/* Logo / Title */}
      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        <div className="radar" style={{ width: "32px", height: "32px" }} />
        <div>
          <div
            style={{
              color: "var(--accent)",
              fontWeight: 700,
              fontSize: "14px",
              letterSpacing: "0.15em",
              lineHeight: 1,
            }}
            className="glow-green"
          >
            OVERLORD11
          </div>
          <div
            style={{
              color: "var(--text-muted)",
              fontSize: "9px",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
            }}
          >
            Tactical Command Interface
          </div>
        </div>
      </div>

      {/* Waveform */}
      <WaveformWidget />

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Provider status indicators */}
      <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
        {Object.entries(providerStatus).map(([prov, info]) => (
          <div
            key={prov}
            style={{ display: "flex", alignItems: "center", gap: "4px" }}
            title={`${prov}: ${info.status} — ${info.model}`}
          >
            <div
              className={`dot ${info.status} ${info.status === "green" && info.is_active ? "blink" : ""}`}
            />
            <span
              style={{
                fontSize: "10px",
                color:
                  info.status === "green" ? "var(--accent)" : "var(--text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
              }}
            >
              {prov}
            </span>
          </div>
        ))}
      </div>

      {/* Backend status */}
      <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
        <div className={`dot ${backendOnline ? "green blink" : "red"}`} />
        <span
          style={{
            fontSize: "10px",
            color: backendOnline ? "var(--accent)" : "var(--status-red)",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
          }}
        >
          {backendOnline ? "ONLINE" : "OFFLINE"}
        </span>
      </div>

      {/* Global controls */}
      <div style={{ display: "flex", gap: "6px" }}>
        <button className="btn-tac" onClick={onStartAll}>
          ▶ START ALL
        </button>
        <button className="btn-tac amber" onClick={onPauseAll}>
          ⏸ PAUSE ALL
        </button>
        <button className="btn-tac danger" onClick={onStopAll}>
          ■ STOP ALL
        </button>
      </div>
    </div>
  );
}
