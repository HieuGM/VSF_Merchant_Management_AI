/**
 * Chat state machine for the Customer Discovery agent.
 * Drives one streamed conversation: pushes a user turn, opens an agent turn, and
 * folds live SSE frames (tool/task progress → answer → final results) into it.
 *
 * Lifted to CustomerHome and shared via ChatProvider so the sidebar's "New chat" and
 * the chat page use one instance. `stop()` aborts an in-flight stream; `reset()`
 * rotates the session id (via identity.regenerate) so a new conversation starts a
 * fresh memory window.
 */
import { useCallback, useRef, useState } from "react";
import {
  getSession,
  streamChat,
  type CustomerChatRequest,
  type Location,
  type PreferenceSuggestion,
  type RestaurantResult,
  type StreamFrame,
} from "../api/customer-agent-client";
import type { CustomerIdentity } from "./use-customer-identity";

export interface ProgressStep {
  id: string;
  label: string;
  tool?: string;
  done: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  text: string;
  results?: RestaurantResult[];
  suggestions?: PreferenceSuggestion[];
  warnings?: string[];
  progress?: ProgressStep[];
  /** What the assistant's long-term memory just learned/forgot THIS turn (SSE
   * memory_updated) — rendered as a toast above the answer. */
  memoryUpdates?: MemoryUpdates;
  /** Hard constraints applied to this turn's results ("Đang lọc: …" chips). */
  activeConstraints?: ActiveConstraint[];
  streaming?: boolean;
  error?: boolean;
}

/** Long-term memory diff for one turn (backend maybe_persist). */
export interface MemoryUpdates {
  added: string[];
  removed: string[];
  expired: string[];
}

/** One hard filter applied to the turn's results. */
export interface ActiveConstraint {
  label: string;
  type: string;
  rationale: string;
}

/** CrewAI tool names → friendly Vietnamese progress captions. */
const TOOL_LABEL: Record<string, string> = {
  merchant_search: "Đang tìm quán ăn phù hợp",
  nearby_merchant_search: "Đang tìm quán gần bạn",
  get_user_profile: "Đang đọc hồ sơ cá nhân của bạn",
  get_session_candidates: "Đang xem lại gợi ý trong phiên",
  get_weather_context: "Đang kiểm tra thời tiết hôm nay",
  propose_profile_delta: "Đang cân nhắc điều chỉnh khẩu vị",
  get_merchant_profile: "Đang phân tích hồ sơ từng quán",
};

const uid = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);

interface SendArgs {
  message: string;
  location?: Location | null;
}

export function useCustomerChat(identity: CustomerIdentity) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  // Sequence guard for openSession: the session_id of the MOST RECENT reopen in flight.
  // A slow earlier getSession must NOT overwrite the view of a newer open (H1).
  const latestOpenRef = useRef<string | null>(null);

  const patchAgent = useCallback((agentId: string, patch: (m: ChatMessage) => ChatMessage) => {
    setMessages((prev) => prev.map((m) => (m.id === agentId ? patch(m) : m)));
  }, []);

  const send = useCallback(
    async ({ message, location }: SendArgs) => {
      const text = message.trim();
      // Bail while a conversation reopen is in flight (H2): the open's setMessages would
      // otherwise overwrite this turn's just-appended bubble. latestOpenRef clears on open
      // completion, so this only blocks during the brief getSession window.
      if (!text || sending || latestOpenRef.current) return;

      const agentId = uid();
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: "user", text },
        { id: agentId, role: "agent", text: "", streaming: true, progress: [] },
      ]);
      setSending(true);

      const controller = new AbortController();
      abortRef.current = controller;

      const req: CustomerChatRequest = {
        user_id: identity.userId,
        session_id: identity.sessionId,
        message: text,
        location: location ?? null,
        // FE never auto-detects weather today (YAGNI); passthrough kept null so the
        // field is wired for tests/future use (see phase-05).
        weather_override: null,
      };

      const onFrame = (frame: StreamFrame) => {
        const { event, data } = frame;
        if (event === "tool_started") {
          const tool = data?.tool as string | undefined;
          const label = (tool && TOOL_LABEL[tool]) ?? `Đang dùng ${tool ?? "công cụ"}`;
          patchAgent(agentId, (m) => ({
            ...m,
            progress: [...(m.progress ?? []), { id: uid(), label, tool, done: false }],
          }));
        } else if (event === "tool_finished") {
          const tool = data?.tool as string | undefined;
          patchAgent(agentId, (m) => ({ ...m, progress: markDone(m.progress, tool) }));
        } else if (event === "answer_delta") {
          // Backend streams the answer token-by-token now (incremental `answer_delta`
          // deltas) → accumulate. The legacy full-`answer` shape is also accepted for
          // backward compat with older backends. run_finished reconciles with the final.
          const delta = (data?.answer_delta ?? data?.answer ?? "") as string;
          if (delta) patchAgent(agentId, (m) => ({ ...m, text: m.text + delta }));
        } else if (event === "memory_updated") {
          // Transparency toast: the assistant's long-term memory changed THIS turn
          // (added / removed / expired). Empty diff → backend sends no event.
          const mem = data?.memory as MemoryUpdates | undefined;
          if (mem) patchAgent(agentId, (m) => ({ ...m, memoryUpdates: mem }));
        } else if (event === "run_finished") {
          // Reconcile with the authoritative final answer — but only when the backend
          // actually sent one. answer is typed `str` (required), so it can legitimately be
          // "" in streaming edge cases; use a truthiness guard (not ??) to keep the text
          // the user already watched stream in rather than blanking the bubble.
          const finalAnswer = data?.answer && String(data.answer).trim() ? data.answer : null;
          patchAgent(agentId, (m) => ({
            ...m,
            text: finalAnswer ?? m.text,
            results: data?.results ?? [],
            suggestions: data?.preference_suggestions ?? [],
            warnings: data?.warnings ?? [],
            activeConstraints: data?.active_constraints ?? [],
            progress: (m.progress ?? []).map((s) => ({ ...s, done: true })),
            streaming: false,
          }));
        } else if (event === "error") {
          // Preserve any answer text that already streamed in — append the error inline
          // instead of overwriting (the user may have started reading the partial answer).
          const errMsg = data?.message ?? "Đã có lỗi khi tìm quán. Bạn thử lại nhé.";
          patchAgent(agentId, (m) => ({
            ...m,
            text: m.text ? `${m.text}\n\n[⚠️ ${errMsg}]` : errMsg,
            error: true,
            streaming: false,
          }));
        }
      };

      try {
        await streamChat(req, onFrame, controller.signal);
      } catch {
        if (!controller.signal.aborted) {
          const dropMsg = "Không kết nối được tới trợ lý. Thử lại sau một lát nhé.";
          patchAgent(agentId, (m) => ({
            ...m,
            text: m.text ? `${m.text}\n\n[⚠️ ${dropMsg}]` : dropMsg,
            error: true,
            streaming: false,
          }));
        }
      } finally {
        // Safety net: never leave the bubble stuck streaming.
        patchAgent(agentId, (m) => (m.streaming ? { ...m, streaming: false } : m));
        setSending(false);
        abortRef.current = null;
      }
    },
    [identity, sending, patchAgent],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setSending(false);
    // Rotate the session id so the next turn starts a fresh memory window (design §11.4).
    identity.regenerate();
  }, [identity]);

  const openSession = useCallback(
    async (sessionId: string) => {
      abortRef.current?.abort(); // cancel any in-flight stream
      // Adopt the reopened session so subsequent turns append to it (not the old one).
      identity.setSessionId(sessionId);
      // Sequence guard: rapid session switches can leave multiple getSession fetches in
      // flight; only the MOST RECENT open may apply its result (else a slow earlier one
      // would overwrite the latest view with stale messages — H1).
      latestOpenRef.current = sessionId;
      setSending(true);
      try {
        const detail = await getSession(sessionId);
        if (latestOpenRef.current !== sessionId) return; // superseded by a newer open
        setMessages(
          detail
            ? detail.messages.map((m) => ({
                id: uid(),
                role: m.sender,
                text: m.text,
                results: m.results ?? [],
                suggestions: [],
                warnings: [],
              }))
            : [],
        );
      } catch {
        if (latestOpenRef.current !== sessionId) return;
        // Network error → blank rather than a stuck partial state (the session is adopted).
        setMessages([]);
      } finally {
        if (latestOpenRef.current === sessionId) {
          latestOpenRef.current = null; // open complete — send may proceed again (H2)
          setSending(false);
        }
      }
    },
    [identity],
  );

  return { messages, sending, send, stop, reset, openSession, sessionId: identity.sessionId };
}

/** Mark a step done — by tool name if given (parallel-safe), else the oldest pending. */
function markDone(steps: ProgressStep[] | undefined, tool?: string): ProgressStep[] {
  if (!steps?.length) return steps ?? [];
  const idx = tool
    ? steps.findIndex((s) => !s.done && s.tool === tool)
    : steps.findIndex((s) => !s.done);
  if (idx === -1) return steps;
  const next = [...steps];
  next[idx] = { ...next[idx], done: true };
  return next;
}
