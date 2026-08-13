/**
 * Conversation-history list state for the sidebar. Loads the user's past conversations
 * (newest-first) and exposes optimistic remove/rename so the sidebar updates instantly
 * while the caller's network call + a follow-up refresh reconcile.
 *
 * Degrades to an empty list on error/offline (same philosophy as getLikedMerchants) so the
 * sidebar stays usable without a backend — the history just won't populate.
 */
import { useCallback, useEffect, useState } from "react";
import {
  listSessions,
  type SessionSummary,
} from "../api/customer-agent-client";

export interface UseSessionHistory {
  sessions: SessionSummary[];
  loading: boolean;
  /** Re-fetch the list (call after open / new / delete / rename / a completed exchange). */
  refresh: () => Promise<void>;
  /** Optimistically drop a session from the list (caller fires the network delete). */
  removeOptimistic: (sessionId: string) => void;
  /** Optimistically rename a session in the list (caller fires the network rename). */
  renameOptimistic: (sessionId: string, title: string) => void;
}

export function useSessionHistory(userId: string): UseSessionHistory {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setSessions(await listSessions(userId));
    setLoading(false);
  }, [userId]);

  // Initial load (+ on user change). Guarded against setting state after unmount.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    listSessions(userId).then((rows) => {
      if (alive) {
        setSessions(rows);
        setLoading(false);
      }
    });
    return () => {
      alive = false;
    };
  }, [userId]);

  const removeOptimistic = useCallback((sessionId: string) => {
    setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
  }, []);

  const renameOptimistic = useCallback((sessionId: string, title: string) => {
    setSessions((prev) =>
      prev.map((s) => (s.session_id === sessionId ? { ...s, title } : s)),
    );
  }, []);

  return { sessions, loading, refresh, removeOptimistic, renameOptimistic };
}
