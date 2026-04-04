"use client";
/**
 * components/FilePreviewModal.tsx — File preview popup
 */

import React, { useEffect, useState } from "react";
import { artifactDownloadUrl, type Artifact } from "@/lib/api";

interface FilePreviewModalProps {
  jobId: string;
  artifact: Artifact | null;
  onClose: () => void;
}

function isText(mime: string): boolean {
  return (
    mime.startsWith("text/") ||
    mime === "application/json" ||
    mime.includes("javascript") ||
    mime.includes("typescript")
  );
}

function isImage(mime: string): boolean {
  return mime.startsWith("image/");
}

export default function FilePreviewModal({
  jobId,
  artifact,
  onClose,
}: FilePreviewModalProps) {
  const [content, setContent] = useState<string | null>(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    if (!artifact) {
      setContent(null);
      return;
    }
    if (isText(artifact.mime)) {
      const url = artifactDownloadUrl(jobId, artifact.path);
      fetch(url)
        .then((r) => r.text())
        .then(setContent)
        .catch(() => setLoadError(true));
    }
  }, [artifact, jobId]);

  if (!artifact) return null;

  const downloadUrl = artifactDownloadUrl(jobId, artifact.path);

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
          width: "min(900px, 90vw)",
          maxHeight: "80vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 0 40px var(--accent-glow)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: "10px 14px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            gap: "10px",
          }}
        >
          <span className="section-label">FILE PREVIEW</span>
          <span
            style={{
              color: "var(--accent)",
              fontSize: "12px",
              fontWeight: 600,
              flex: 1,
            }}
          >
            {artifact.path}
          </span>
          <span style={{ color: "var(--text-muted)", fontSize: "10px" }}>
            {(artifact.size / 1024).toFixed(1)} KB
          </span>
          <a
            href={downloadUrl}
            download={artifact.path}
            className="btn-tac"
            style={{ textDecoration: "none", padding: "3px 8px", fontSize: "10px" }}
          >
            ↓ DOWNLOAD
          </a>
          <button className="btn-tac danger" style={{ padding: "3px 8px", fontSize: "10px" }} onClick={onClose}>
            ✕ CLOSE
          </button>
        </div>

        {/* Content */}
        <div
          className="scroll-fill"
          style={{ padding: "12px", minHeight: 0 }}
        >
          {loadError && (
            <div style={{ color: "var(--status-red)", fontSize: "12px" }}>
              Failed to load file content.
            </div>
          )}

          {isImage(artifact.mime) && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={downloadUrl}
              alt={artifact.path}
              style={{ maxWidth: "100%", maxHeight: "60vh", objectFit: "contain" }}
            />
          )}

          {isText(artifact.mime) && content !== null && (
            <pre
              style={{
                margin: 0,
                fontSize: "11px",
                color: "var(--text-primary)",
                lineHeight: 1.6,
                whiteSpace: "pre-wrap",
                wordBreak: "break-all",
              }}
            >
              {content}
            </pre>
          )}

          {!isText(artifact.mime) && !isImage(artifact.mime) && (
            <div style={{ color: "var(--text-muted)", fontSize: "12px", padding: "20px 0" }}>
              Binary file — download to view.
              <br />
              <a href={downloadUrl} download className="btn-tac" style={{ display: "inline-block", marginTop: "10px" }}>
                ↓ DOWNLOAD
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
