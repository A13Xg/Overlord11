"use client";
/**
 * hooks/useEvents.ts — SSE event stream for a session
 */

import { useEffect, useRef, useState } from "react";
import { createEventSource, EngineEvent } from "@/lib/api";

export function useEvents(sessionId: string | null) {
  const [events, setEvents] = useState<EngineEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setEvents([]);
      setConnected(false);
      return;
    }

    // Close previous connection
    if (esRef.current) {
      esRef.current.close();
    }

    setEvents([]);
    const es = createEventSource(sessionId);
    esRef.current = es;

    es.onopen = () => setConnected(true);

    es.onmessage = (e) => {
      try {
        const event: EngineEvent = JSON.parse(e.data);
        if (event.type === "ping") return;
        setEvents((prev) => [...prev, event]);
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      setConnected(false);
      es.close();
    };

    return () => {
      es.close();
      setConnected(false);
    };
  }, [sessionId]);

  return { events, connected };
}
