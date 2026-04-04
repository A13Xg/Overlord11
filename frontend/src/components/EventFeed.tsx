"use client";
/**
 * components/EventFeed.tsx — Real-time execution event feed
 */

import React, { useEffect, useRef } from "react";
import type { EngineEvent } from "@/lib/api";

function eventClass(type: string): string {
  switch (type) {
    case "agent_start": return "log-success";
    case "tool_call":   return "log-tool";
    case "tool_result": return "log-tool";
    case "log":         return "log-info";
    case "complete":    return "log-success";
    case "error":       return "log-error";
    case "healing":     return "log-heal";
    default:            return "log-debug";
  }
}

function eventIcon(type: string): string {
  switch (type) {
    case "agent_start": return "▶";
    case "tool_call":   return "⚙";
    case "tool_result": return "←";
    case "log":         return "·";
    case "complete":    return "✓";
    case "error":       return "✗";
    case "healing":     return "⟳";
    default:            return "·";
  }
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function renderPayload(event: EngineEvent): string {
  const { type, session_id, ts, ...rest } = event;
  switch (type) {
    case "agent_start":
      return `agent=${rest.agent} task="${String(rest.task ?? "").slice(0, 80)}"`;
    case "tool_call":
      return `${rest.tool}(${JSON.stringify(rest.args ?? {}).slice(0, 120)})`;
    case "tool_result":
      return `${rest.tool} → ${JSON.stringify(rest.result ?? "").slice(0, 120)}`;
    case "log":
      return `[${String(rest.level ?? "info").toUpperCase()}] ${rest.message}`;
    case "complete":
      return `Result: ${String(rest.result ?? "").slice(0, 160)}`;
    case "error":
      return `Error: ${rest.error}`;
    case "healing":
      return `Attempt ${rest.attempt} — ${rest.strategy} — orig: ${String(rest.original_error ?? "").slice(0, 80)}`;
    default:
      return JSON.stringify(rest).slice(0, 160);
  }
}

interface EventFeedProps {
  events: EngineEvent[];
  connected: boolean;
}

export default function EventFeed({ events, connected }: EventFeedProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        background: "var(--bg-base)",
      }}
    >
      {/* Feed header */}
      <div
        style={{
          padding: "8px 12px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          flexShrink: 0,
        }}
      >
        <span className="section-label">Execution Feed</span>
        {connected && (
          <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            <div className="dot green blink" />
            <span style={{ fontSize: "10px", color: "var(--accent)" }}>LIVE</span>
          </div>
        )}
        <span style={{ marginLeft: "auto", color: "var(--text-muted)", fontSize: "10px" }}>
          {events.length} events
        </span>
      </div>

      {/* Events */}
      <div
        className="scroll-fill"
        style={{ padding: "6px 0", fontFamily: "var(--font-mono)", fontSize: "11px" }}
      >
        {events.length === 0 ? (
          <div
            style={{
              padding: "32px 16px",
              color: "var(--text-muted)",
              textAlign: "center",
              fontSize: "11px",
            }}
          >
            {connected ? "Waiting for events…" : "Select a running job to see events"}
          </div>
        ) : (
          events.map((ev, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                gap: "8px",
                padding: "2px 12px",
                alignItems: "flex-start",
                borderBottom: "1px solid rgba(0,230,118,0.04)",
              }}
            >
              <span style={{ color: "var(--text-muted)", flexShrink: 0, fontSize: "10px", paddingTop: "1px" }}>
                {formatTime(ev.ts)}
              </span>
              <span className={eventClass(ev.type)} style={{ flexShrink: 0, width: "12px" }}>
                {eventIcon(ev.type)}
              </span>
              <span
                className={eventClass(ev.type)}
                style={{ flex: 1, wordBreak: "break-all", lineHeight: 1.5 }}
              >
                {renderPayload(ev)}
              </span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
