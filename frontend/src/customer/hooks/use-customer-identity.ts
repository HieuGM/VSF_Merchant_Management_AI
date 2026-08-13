/**
 * Stable anonymous identity for the customer agent.
 * `user_id` persists across visits (localStorage). `session_id` persists across
 * reloads AND can be rotated via `regenerate()` so "New chat" starts a fresh memory
 * window (design §11.4). Both storage keys live here so other modules read the same
 * source (see `getCustomerUserId`).
 */
import { useCallback, useMemo, useState } from "react";

export const CUSTOMER_USER_ID_KEY = "cust_user_id";
export const CUSTOMER_SESSION_ID_KEY = "cust_session_id";

function makeId(prefix: string): string {
  const rand =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
  return `${prefix}_${rand}`;
}

/** Safe localStorage read (SSR / privacy-mode guarded). */
function readKey(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

/** Read the persisted anonymous user id WITHOUT subscribing to React state. */
export function getCustomerUserId(): string | null {
  return readKey(CUSTOMER_USER_ID_KEY);
}

/** Lazily mint+persist a user id once per browser identity. */
function ensureUserId(): string {
  const existing = readKey(CUSTOMER_USER_ID_KEY);
  if (existing) return existing;
  const id = makeId("user");
  try {
    localStorage.setItem(CUSTOMER_USER_ID_KEY, id);
  } catch {
    /* storage unavailable — keep the in-memory id for this session */
  }
  return id;
}

export interface CustomerIdentity {
  userId: string;
  sessionId: string;
  /** Mint a fresh session_id + persist it (called by "New chat"). */
  regenerate: () => void;
  /** Adopt an EXISTING session_id + persist it (called when reopening a past conversation). */
  setSessionId: (id: string) => void;
}

export function useCustomerIdentity(): CustomerIdentity {
  // session_id is reactive so consumers (useCustomerChat) pick up the new id after
  // regenerate()/setSessionId(). Initialized from localStorage so a reload keeps the same session.
  const [sessionId, setSessionIdState] = useState<string>(() => {
    const stored = readKey(CUSTOMER_SESSION_ID_KEY);
    if (stored) return stored;
    const id = makeId("session");
    try {
      localStorage.setItem(CUSTOMER_SESSION_ID_KEY, id);
    } catch {
      /* storage unavailable */
    }
    return id;
  });

  // user_id never changes within a browser identity — compute once.
  const userId = useMemo(() => ensureUserId(), []);

  // Persist + adopt any session_id (used by reopen). regenerate() mints a fresh one via this.
  const setSessionId = useCallback((id: string) => {
    try {
      localStorage.setItem(CUSTOMER_SESSION_ID_KEY, id);
    } catch {
      /* storage unavailable — in-memory switch still applies */
    }
    setSessionIdState(id);
  }, []);

  const regenerate = useCallback(() => {
    setSessionId(makeId("session"));
  }, [setSessionId]);

  // Stable object reference between renders unless sessionId actually changes — keeps
  // useCustomerChat's `send`/`reset`/`openSession` memo from churning every render.
  return useMemo(
    () => ({ userId, sessionId, regenerate, setSessionId }),
    [userId, sessionId, regenerate, setSessionId],
  );
}
