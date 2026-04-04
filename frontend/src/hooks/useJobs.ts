"use client";
/**
 * hooks/useJobs.ts — Job list with polling
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJobs, patchJob, deleteJob, bulkControl, createJob, Job } from "@/lib/api";

const POLL_INTERVAL = 3000; // ms

export function useJobs() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchJobs();
      setJobs(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load jobs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    timerRef.current = setInterval(refresh, POLL_INTERVAL);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [refresh]);

  const submitJob = useCallback(
    async (task: string, agent = "orchestrator", provider = "anthropic") => {
      const job = await createJob({ task, agent, provider });
      setJobs((prev) => [...prev, job]);
      return job;
    },
    []
  );

  const controlJob = useCallback(
    async (jobId: string, action: "start" | "pause" | "resume" | "stop" | "restart") => {
      await patchJob(jobId, action);
      await refresh();
    },
    [refresh]
  );

  const removeJob = useCallback(
    async (jobId: string) => {
      await deleteJob(jobId);
      setJobs((prev) => prev.filter((j) => j.job_id !== jobId));
    },
    []
  );

  const controlAll = useCallback(
    async (action: "start-all" | "pause-all" | "stop-all") => {
      await bulkControl(action);
      await refresh();
    },
    [refresh]
  );

  return { jobs, loading, error, refresh, submitJob, controlJob, removeJob, controlAll };
}
