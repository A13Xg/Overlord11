"use client";
/**
 * components/SystemLog.tsx — Collapsible bottom system log panel
 */

import React, { useEffect, useRef, useState } from "react";

export interface LogEntry {
  ts: number;
  level: "info" | "warn" | "error" | "debug";
  message: string;
}

interface SystemLogProps {
  entries: LogEntry[];
}

function levelClass(level: LogEntry["level"]): string {
  switch (level) {
    case "error": return "log-error";
    case "warn":  return "log-warn";
    case "debug": return "log-debug";
    default:      return "log-info";
  }
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function SystemLog({ entries }: SystemLogProps) {
  const [collapsed, setCollapsed] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!collapsed) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [entries.length, collapsed]);

  return (
    <div
      style={{
        borderTop: "1px solid var(--border)",
        background: "var(--bg-panel)",
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        height: collapsed ? "32px" : "140px",
        transition: "height 0.2s ease",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          height: "32px",
          display: "flex",
          alignItems: "center",
          padding: "0 12px",
          gap: "8px",
          cursor: "pointer",
          borderBottom: collapsed ? "none" : "1px solid var(--border)",
          flexShrink: 0,
          userSelect: "none",
        }}
        onClick={() => setCollapsed((v) => !v)}
      >
        <span className="section-label">System Log</span>
        <span
          style={{
            color: "var(--text-muted)",
            fontSize: "10px",
            marginLeft: "4px",
          }}
        >
          {entries.length} entries
        </span>
        <div style={{ flex: 1 }} />
        {/* Error indicator */}
        {entries.some((e) => e.level === "error") && (
          <div className="dot red blink" title="Errors present" />
        )}
        <span style={{ color: "var(--text-muted)", fontSize: "11px" }}>
          {collapsed ? "▲" : "▼"}
        </span>
      </div>

      {/* Log lines */}
      {!collapsed && (
        <div
          className="scroll-fill"
          style={{
            padding: "4px 0",
            fontFamily: "var(--font-mono)",
            fontSize: "11px",
          }}
        >
          {entries.length === 0 ? (
            <div style={{ padding: "8px 12px", color: "var(--text-muted)" }}>
              No system events
            </div>
          ) : (
            entries.map((e, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  gap: "8px",
                  padding: "1px 12px",
                  alignItems: "flex-start",
                }}
              >
                <span style={{ color: "var(--text-muted)", flexShrink: 0, fontSize: "10px" }}>
                  {formatTime(e.ts)}
                </span>
                <span
                  className={levelClass(e.level)}
                  style={{ textTransform: "uppercase", fontSize: "9px", flexShrink: 0, paddingTop: "1px", width: "36px" }}
                >
                  {e.level}
                </span>
                <span className={levelClass(e.level)} style={{ flex: 1, wordBreak: "break-all" }}>
                  {e.message}
                </span>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
