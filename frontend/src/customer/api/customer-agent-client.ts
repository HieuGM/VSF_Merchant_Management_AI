/**
 * Customer Discovery agent client (Dev A).
 * Talks to the FROZEN chat contract (design §11.4):
 *   POST /api/v1/agent/customer/chat         — blocking full response
 *   POST /api/v1/agent/customer/chat/stream  — Server-Sent Events over POST
 *   POST /api/v1/users/{userId}/profile/deltas/{deltaId}/confirm  — persist a proposed delta
 *   POST /api/v1/users/{userId}/profile/deltas/{deltaId}/reject   — dismiss a proposed delta
 * EventSource can't POST, so `streamChat` parses the SSE frames off a fetch reader.
 */

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export interface Location {
  lat: number;
  lng: number;
}

/** One candidate restaurant (SearchTaskOutput candidate → §11.4 results[]). */
export interface RestaurantResult {
  merchant_id: string;
  name: string;
  cuisine?: string | null;
  address?: string | null;
  distance_km?: number | null;
  avg_rating?: number | null;
  match_score?: number | null;
  image_url?: string | null;
}

/**
 * A proposed (never auto-saved) tweak to the user's taste profile.
 * `delta_id` is present only when the backend attached a persistable delta — older
 * responses omit it and the FE hides the Lưu/Bỏ qua actions (graceful downgrade).
 */
export interface PreferenceSuggestion {
  delta_id?: string | null;
  field: string;
  operation?: string;
  value?: unknown;
  confidence?: number;
  rationale?: string;
}

export interface CustomerChatResponse {
  trace_id: string;
  session_id?: string | null;
  intent?: string | null;
  answer: string;
  results: RestaurantResult[];
  preference_suggestions: PreferenceSuggestion[];
  evidence: unknown[];
  warnings: string[];
}

export interface CustomerChatRequest {
  user_id: string;
  session_id?: string;
  message: string;
  location?: Location | null;
  /** Client-side weather signal (e.g. {is_rain:true}); FE omits today (null) by design. */
  weather_override?: Record<string, unknown> | null;
}

/** Body for confirming a proposed preference delta (mirrors backend ConfirmDeltaRequest). */
export interface ConfirmDeltaBody {
  user_id: string;
  field: string;
  operation: "set" | "add" | "remove";
  value: unknown;
  confidence?: number | null;
  rationale?: string | null;
  session_id?: string | null;
}

/** SSE frame: `{ event, data }` — event names per STREAM_EVENT_TYPES (§11.4). */
export interface StreamFrame {
  event: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any;
}

/** Blocking call — waits for the full crew run. Used as a fallback. */
export async function chat(req: CustomerChatRequest): Promise<CustomerChatResponse> {
  const resp = await fetch(`${API_BASE}/api/v1/agent/customer/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) throw new Error(`Chat failed: HTTP ${resp.status}`);
  return resp.json();
}

/**
 * Stream a chat run. Invokes `onFrame` for every SSE event as it arrives, so the
 * UI can show live progress (tool_started / task_finished / answer_delta …).
 * Resolves when the stream ends; rejects on network error or abort.
 */
export async function streamChat(
  req: CustomerChatRequest,
  onFrame: (frame: StreamFrame) => void,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch(`${API_BASE}/api/v1/agent/customer/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(req),
    signal,
  });
  if (!resp.ok || !resp.body) throw new Error(`Stream failed: HTTP ${resp.status}`);

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // SSE frames are separated by a blank line; each frame has `event:` + `data:` lines.
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const frame = parseFrame(raw);
      if (frame) onFrame(frame);
    }
  }
}

function parseFrame(raw: string): StreamFrame | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return { event, data: dataLines.join("\n") };
  }
}

/**
 * Persist a proposed preference delta to the user's profile. Idempotent — repeating
 * the same (userId, deltaId) is a no-op on the backend. Resolves to the updated
 * profile (unused by the UI today; the row simply flips to "Đã lưu").
 */
export async function confirmDelta(
  userId: string,
  deltaId: string,
  body: ConfirmDeltaBody,
): Promise<unknown> {
  const resp = await fetch(
    `${API_BASE}/api/v1/users/${encodeURIComponent(userId)}/profile/deltas/${encodeURIComponent(deltaId)}/confirm`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok) throw new Error(`Confirm delta failed: HTTP ${resp.status}`);
  return resp.json();
}

/**
 * Dismiss a proposed preference delta. No profile mutation; the backend records the
 * event as rejected. Best-effort from the UI's side — a failed dismiss still collapses
 * the actions so the user is never blocked on a suggestion they skipped.
 */
export async function rejectDelta(userId: string, deltaId: string): Promise<void> {
  const resp = await fetch(
    `${API_BASE}/api/v1/users/${encodeURIComponent(userId)}/profile/deltas/${encodeURIComponent(deltaId)}/reject`,
    { method: "POST" },
  );
  if (!resp.ok) throw new Error(`Reject delta failed: HTTP ${resp.status}`);
}
