"use client";
/**
 * app/page.tsx — OVERLORD11 Tactical Command Interface
 *
 * Layout:
 *   [ TOP BAR                                ]
 *   [ JOB QUEUE ] | [ MAIN VIEW              ]
 *   [ COLLAPSIBLE SYSTEM LOG                 ]
 */

import React, { useCallback, useEffect, useState } from "react";
import { fetchProviderStatus, fetchHealth, type ProviderStatus, type Job } from "@/lib/api";
import { useJobs } from "@/hooks/useJobs";
import { useEvents } from "@/hooks/useEvents";
import TopBar from "@/components/TopBar";
import JobQueue from "@/components/JobQueue";
import MainView from "@/components/MainView";
import SystemLog, { type LogEntry } from "@/components/SystemLog";
import NewJobModal from "@/components/NewJobModal";

export default function Dashboard() {
  const { jobs, loading, submitJob, controlJob, removeJob, controlAll } = useJobs();
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [showNewJob, setShowNewJob] = useState(false);
  const [providerStatus, setProviderStatus] = useState<Record<string, ProviderStatus>>({});
  const [backendOnline, setBackendOnline] = useState(false);
  const [sysLog, setSysLog] = useState<LogEntry[]>([]);

  // Derive session_id for event streaming from selected job
  const sessionId = selectedJob?.session_id ?? null;
  const { events, connected } = useEvents(sessionId);

  // Keep selected job in sync with job list updates
  useEffect(() => {
    if (selectedJob) {
      const updated = jobs.find((j) => j.job_id === selectedJob.job_id);
      if (updated) setSelectedJob(updated);
    } else if (jobs.length > 0 && !loading) {
      // Auto-select the most recently active job
      const running = jobs.find((j) => j.state === "running");
      if (running) setSelectedJob(running);
    }
  }, [jobs, loading]); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll provider status
  useEffect(() => {
    const load = async () => {
      try {
        const status = await fetchProviderStatus();
        setProviderStatus(status);
      } catch {
        // ignore
      }
      try {
        await fetchHealth();
        setBackendOnline(true);
      } catch {
        setBackendOnline(false);
        addLog("error", "Backend offline — retrying…");
      }
    };
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  // Feed engine log events into system log
  useEffect(() => {
    if (events.length === 0) return;
    const last = events[events.length - 1];
    if (last.type === "log") {
      addLog(
        (last.level as LogEntry["level"]) ?? "info",
        String(last.message ?? "")
      );
    } else if (last.type === "error") {
      addLog("error", String(last.error ?? "Engine error"));
    } else if (last.type === "healing") {
      addLog("warn", `Healing attempt ${last.attempt}: ${last.strategy}`);
    }
  }, [events]);

  const addLog = useCallback(
    (level: LogEntry["level"], message: string) => {
      setSysLog((prev) => [
        ...prev.slice(-499), // keep last 500
        { ts: Date.now(), level, message },
      ]);
    },
    []
  );

  const handleSubmitJob = async (task: string, agent: string, provider: string) => {
    const job = await submitJob(task, agent, provider);
    setSelectedJob(job);
    addLog("info", `Job ${job.job_id} created: ${task.slice(0, 80)}`);
    setShowNewJob(false);
  };

  const handleControl = async (
    jobId: string,
    action: "start" | "pause" | "resume" | "stop" | "restart"
  ) => {
    try {
      await controlJob(jobId, action);
      addLog("info", `Job ${jobId} → ${action}`);
    } catch (e) {
      addLog("error", `Failed to ${action} job ${jobId}: ${e}`);
    }
  };

  const handleDelete = async (jobId: string) => {
    try {
      await removeJob(jobId);
      if (selectedJob?.job_id === jobId) setSelectedJob(null);
      addLog("info", `Job ${jobId} deleted`);
    } catch (e) {
      addLog("error", `Failed to delete job ${jobId}: ${e}`);
    }
  };

  const handleBulk = async (action: "start-all" | "pause-all" | "stop-all") => {
    try {
      await controlAll(action);
      addLog("info", `Bulk action: ${action}`);
    } catch (e) {
      addLog("error", `Bulk action ${action} failed: ${e}`);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        overflow: "hidden",
        background: "var(--bg-base)",
      }}
    >
      {/* TOP BAR */}
      <TopBar
        providerStatus={providerStatus}
        onStartAll={() => handleBulk("start-all")}
        onPauseAll={() => handleBulk("pause-all")}
        onStopAll={() => handleBulk("stop-all")}
        backendOnline={backendOnline}
      />

      {/* MAIN ROW */}
      <div style={{ flex: 1, display: "flex", minHeight: 0, overflow: "hidden" }}>
        {/* LEFT: Job Queue */}
        <JobQueue
          jobs={jobs}
          selectedJobId={selectedJob?.job_id ?? null}
          onSelect={setSelectedJob}
          onControl={handleControl}
          onDelete={handleDelete}
          onNewJob={() => setShowNewJob(true)}
        />

        {/* RIGHT: Main View */}
        <MainView
          job={selectedJob}
          events={events}
          connected={connected}
        />
      </div>

      {/* BOTTOM: System Log */}
      <SystemLog entries={sysLog} />

      {/* NEW JOB MODAL */}
      {showNewJob && (
        <NewJobModal
          onSubmit={handleSubmitJob}
          onClose={() => setShowNewJob(false)}
        />
      )}
    </div>
  );
}
