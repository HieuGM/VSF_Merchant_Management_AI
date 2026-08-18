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
  /** Geo + hours (FE directions deep-link + open-now badge). */
  lat?: number | null;
  lng?: number | null;
  opens_at?: string | null;
  closes_at?: string | null;
  /** 3 signature dishes w/ price (rendered in the card's expanded detail). */
  top_dishes?: TopDish[];
}

export interface TopDish {
  name: string;
  price?: number | null;
  likes?: number | null;
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

/** Canonical taste profile (mirrors backend UserProfilePublic §6.5). */
export interface UserProfile {
  user_id: string;
  liked_cuisines: string[] | null;
  disliked_cuisines: string[] | null;
  spice_tolerance: string | null;
  dietary: string[] | null;
  /** Durable allergy/avoid facts (no FIFO cap) — hard-filtered on every search. */
  allergens: string[] | null;
  budget_level: string | null;
  distance_preference_km: number;
  current_lat: number | null;
  current_lng: number | null;
  /** Long-term cross-session notes (phase-03). FE reads `.notes` + `.note_expiries`
   * (lowercased note → ISO expiry; present only for TEMPORARY constraints — a note
   * without an entry is durable). */
  context_memory: { notes?: string[]; note_expiries?: Record<string, string> } | null;
  updated_at: string | null;
}

/** Partial taste-profile patch (mirrors backend ProfilePatchRequest; snake_case). */
export type ProfilePatch = Partial<{
  liked_cuisines: string[];
  disliked_cuisines: string[];
  dietary: string[];
  allergens: string[];
  budget_level: string | null;
  distance_preference_km: number;
}>;

/**
 * Read the user's confirmed taste profile. Returns null on 404 (no profile yet — the user
 * has never saved a preference); throws on other errors (caller falls back to cache).
 */
export async function getProfile(userId: string): Promise<UserProfile | null> {
  const resp = await fetch(`${API_BASE}/api/v1/users/${encodeURIComponent(userId)}/profile`);
  if (resp.status === 404) return null;
  if (!resp.ok) throw new Error(`Get profile failed: HTTP ${resp.status}`);
  return (await resp.json()) as UserProfile;
}

/**
 * Partial update of the taste profile (explicit user edit). Returns the updated profile.
 * Backend validates per-field (B5); unknown field → 422, bad value → 400. Optional
 * `signal` aborts the in-flight request (superseded by a newer edit or component unmount).
 */
export async function patchProfile(
  userId: string,
  patch: ProfilePatch,
  signal?: AbortSignal,
): Promise<UserProfile> {
  const resp = await fetch(`${API_BASE}/api/v1/users/${encodeURIComponent(userId)}/profile`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
    signal,
  });
  if (!resp.ok) throw new Error(`Patch profile failed: HTTP ${resp.status}`);
  return (await resp.json()) as UserProfile;
}

/** Clear remembered memory (context_memory notes + taste fields) — the FE 'clear memory' test
 * control. Returns the reset profile. */
export async function clearMemory(userId: string): Promise<UserProfile> {
  const resp = await fetch(
    `${API_BASE}/api/v1/users/${encodeURIComponent(userId)}/memory/clear`,
    { method: "POST", headers: { "Content-Type": "application/json" } },
  );
  if (!resp.ok) throw new Error(`Clear memory failed: HTTP ${resp.status}`);
  return (await resp.json()) as UserProfile;
}

/** Delete ONE remembered note (its lowercased text is the key, URL-encoded). Also drops the
 * note's expiry entry + its allergen twin server-side. 404 when the note is absent. */
export async function deleteNote(userId: string, note: string): Promise<UserProfile> {
  const resp = await fetch(
    `${API_BASE}/api/v1/users/${encodeURIComponent(userId)}/memory/notes/${encodeURIComponent(note.toLowerCase())}`,
    { method: "DELETE" },
  );
  if (!resp.ok) throw new Error(`Delete note failed: HTTP ${resp.status}`);
  return (await resp.json()) as UserProfile;
}

/** A liked merchant (episodic memory) — from GET /liked-merchants. */
export interface LikedMerchant {
  merchant_id: string;
  name: string;
  cuisine: string | null;
}

/** List the user's liked merchants (newest-first). Degrades to [] on error/offline so the FE
 * heart-state stays usable without a backend (the likes just won't persist). */
export async function getLikedMerchants(userId: string): Promise<LikedMerchant[]> {
  try {
    const resp = await fetch(
      `${API_BASE}/api/v1/users/${encodeURIComponent(userId)}/liked-merchants`,
    );
    if (!resp.ok) return [];
    const data = (await resp.json()) as { liked_merchants: LikedMerchant[] };
    return data.liked_merchants ?? [];
  } catch {
    return [];
  }
}

/** Like a merchant (heart on the card) — idempotent. Throws on non-2xx (caller rolls back). */
export async function likeMerchant(userId: string, merchantId: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/api/v1/users/${encodeURIComponent(userId)}/liked-merchants`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ merchant_id: merchantId }),
  });
  if (!resp.ok) throw new Error(`Like merchant failed: HTTP ${resp.status}`);
}

/** Remove a like — idempotent. Throws on non-2xx (caller rolls back). */
export async function unlikeMerchant(userId: string, merchantId: string): Promise<void> {
  const resp = await fetch(
    `${API_BASE}/api/v1/users/${encodeURIComponent(userId)}/liked-merchants/${encodeURIComponent(merchantId)}`,
    { method: "DELETE" },
  );
  if (!resp.ok) throw new Error(`Unlike merchant failed: HTTP ${resp.status}`);
}

// --- Conversation history (ChatGPT-style list / reopen / rename / delete) ---

/** One past conversation in the sidebar history list (GET /users/{id}/sessions). */
export interface SessionSummary {
  session_id: string;
  title: string | null;
  updated_at: string | null;
  created_at: string | null;
}

/** One turn inside a reopened conversation (GET /sessions/{id}). Agent turns carry stored cards. */
export interface SessionMessage {
  sender: "user" | "agent";
  text: string;
  ts: string | null;
  results?: RestaurantResult[];
}

/** A reopened conversation: meta + full message history. */
export interface SessionDetail {
  session_id: string;
  title: string | null;
  updated_at: string | null;
  messages: SessionMessage[];
}

/** List the user's past conversations (newest-first). Degrades to [] on error/offline so the
 * sidebar stays usable without a backend (like getLikedMerchants). */
export async function listSessions(userId: string): Promise<SessionSummary[]> {
  try {
    const resp = await fetch(`${API_BASE}/api/v1/users/${encodeURIComponent(userId)}/sessions`);
    if (!resp.ok) return [];
    const data = (await resp.json()) as { sessions: SessionSummary[] };
    return data.sessions ?? [];
  } catch {
    return [];
  }
}

/** Reopen a conversation: its meta + all messages. null on 404 (unknown / just-deleted id). */
export async function getSession(sessionId: string): Promise<SessionDetail | null> {
  const resp = await fetch(`${API_BASE}/api/v1/sessions/${encodeURIComponent(sessionId)}`);
  if (resp.status === 404) return null;
  if (!resp.ok) throw new Error(`Get session failed: HTTP ${resp.status}`);
  return (await resp.json()) as SessionDetail;
}

/** Delete a conversation + its messages. Throws on non-2xx (caller rolls back the list). */
export async function deleteSession(userId: string, sessionId: string): Promise<void> {
  const resp = await fetch(
    `${API_BASE}/api/v1/users/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" },
  );
  if (!resp.ok) throw new Error(`Delete session failed: HTTP ${resp.status}`);
}

/** Rename a conversation. Returns the updated summary. Throws on non-2xx / empty title (400). */
export async function renameSession(
  userId: string,
  sessionId: string,
  title: string,
): Promise<SessionSummary> {
  const resp = await fetch(
    `${API_BASE}/api/v1/users/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    },
  );
  if (!resp.ok) throw new Error(`Rename session failed: HTTP ${resp.status}`);
  return (await resp.json()) as SessionSummary;
}
