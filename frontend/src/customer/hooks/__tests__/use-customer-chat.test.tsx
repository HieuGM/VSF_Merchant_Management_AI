/**
 * use-customer-chat race-guard tests — the hand-rolled concurrency handling this hook
 * carries (sequence guard H1, send-gate H2, abort-on-stop, SSE frame folding) has no
 * other safety net; these pin each behavior down.
 *
 * streamChat/getSession are module-mocked; tests drive the captured onFrame callback
 * with synthetic SSE frames (same shape the real parser emits). Real timers — the
 * frames use millisecond delays, fast enough without fake-timer act() interleaving.
 */
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const streamChatMock = vi.hoisted(() => vi.fn());
const getSessionMock = vi.hoisted(() => vi.fn());

vi.mock("../../api/customer-agent-client", () => ({
  streamChat: streamChatMock,
  getSession: getSessionMock,
}));

import { useCustomerChat } from "../use-customer-chat";
import type { CustomerIdentity } from "../use-customer-identity";

const identity: CustomerIdentity = {
  userId: "user_test",
  sessionId: "sess_a",
  regenerate: vi.fn(),
  setSessionId: vi.fn(),
} as unknown as CustomerIdentity;

/** A streamChat impl emitting frames sequentially (ms delays); abort stops the feed. */
function fakeStream(frames: Array<Record<string, unknown>>) {
  return async (_req: unknown, onFrame: (f: unknown) => void, signal?: AbortSignal) => {
    let i = 0;
    for (const f of frames) {
      if (signal?.aborted) return;
      // eslint-disable-next-line no-await-in-loop
      await new Promise<void>((resolve) => {
        const id = setTimeout(() => {
          if (!signal?.aborted) onFrame(f);
          resolve();
        }, 5);
        signal?.addEventListener("abort", () => {
          clearTimeout(id);
          resolve();
        }, { once: true });
      });
      i += 1;
      void i;
    }
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useCustomerChat — SSE frame folding", () => {
  it("accumulates answer_delta tokens into the agent bubble", async () => {
    streamChatMock.mockImplementation(fakeStream([
      { event: "answer_delta", data: { answer_delta: "Xin " } },
      { event: "answer_delta", data: { answer_delta: "chào" } },
      { event: "run_finished", data: { answer: "", results: [] } },
    ]));
    const { result } = renderHook(() => useCustomerChat(identity));
    await act(async () => {
      await result.current.send({ message: "hi" });
    });
    const agent = result.current.messages.find((m) => m.role === "agent");
    expect(agent?.text).toBe("Xin chào");
    expect(agent?.streaming).toBe(false);
  });

  it("run_finished reconciles with the final answer only when non-empty (streamed text kept)", async () => {
    streamChatMock.mockImplementation(fakeStream([
      { event: "answer_delta", data: { answer_delta: "đã stream" } },
      { event: "run_finished", data: { answer: "", results: [], preference_suggestions: [], warnings: [] } },
    ]));
    const { result } = renderHook(() => useCustomerChat(identity));
    await act(async () => {
      await result.current.send({ message: "hi" });
    });
    const agent = result.current.messages.find((m) => m.role === "agent");
    // Empty final answer must NOT blank the text the user watched stream in.
    expect(agent?.text).toBe("đã stream");
  });

  it("folds tool progress + captures memory diff and active constraints", async () => {
    streamChatMock.mockImplementation(fakeStream([
      { event: "tool_started", data: { tool: "merchant_search" } },
      { event: "memory_updated", data: { memory: { added: ["tôi dị ứng tôm"], removed: [], expired: [] } } },
      { event: "tool_finished", data: { tool: "merchant_search" } },
      {
        event: "run_finished",
        data: {
          answer: "done",
          results: [],
          preference_suggestions: [],
          warnings: [],
          active_constraints: [{ label: "hải sản", type: "allergy", rationale: "dị ứng" }],
        },
      },
    ]));
    const { result } = renderHook(() => useCustomerChat(identity));
    await act(async () => {
      await result.current.send({ message: "hi" });
    });
    const agent = result.current.messages.find((m) => m.role === "agent")!;
    expect(agent.progress?.every((s) => s.done)).toBe(true);
    expect(agent.memoryUpdates?.added).toEqual(["tôi dị ứng tôm"]);
    expect(agent.activeConstraints?.[0]?.label).toBe("hải sản");
    expect(agent.text).toBe("done");
  });

  it("error frame KEEPS partial answer text and marks the bubble error", async () => {
    streamChatMock.mockImplementation(fakeStream([
      { event: "answer_delta", data: { answer_delta: "trả lời dở" } },
      { event: "error", data: { message: "boom" } },
    ]));
    const { result } = renderHook(() => useCustomerChat(identity));
    await act(async () => {
      await result.current.send({ message: "hi" });
    });
    const agent = result.current.messages.find((m) => m.role === "agent")!;
    expect(agent.error).toBe(true);
    expect(agent.text).toContain("trả lời dở");
    expect(agent.text).toContain("boom");
  });

  it("ignores an empty send and a duplicate send while one is in flight", async () => {
    let release: ((f: Record<string, unknown>) => void) | null = null;
    streamChatMock.mockImplementation(
      (_r: unknown, onFrame: (f: unknown) => void) =>
        new Promise<void>((resolve) => {
          release = (f) => {
            onFrame(f);
            resolve();
          };
        }),
    );
    const { result } = renderHook(() => useCustomerChat(identity));
    await act(async () => {
      await result.current.send({ message: "   " }); // blank → no bubble
    });
    expect(result.current.messages).toHaveLength(0);
    // Kick off one send but do NOT await its (never-resolving) stream promise yet.
    let firstSend: Promise<void> | null = null;
    act(() => {
      firstSend = result.current.send({ message: "first" });
    });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 5));
    });
    // A second send while the first is streaming must be dropped by the `sending` guard.
    await act(async () => {
      await result.current.send({ message: "second-while-sending" });
    });
    expect(result.current.messages.filter((m) => m.role === "user")).toHaveLength(1);
    await act(async () => {
      release?.({ event: "run_finished", data: { answer: "ok", results: [] } });
      await firstSend;
    });
  }, 10_000);
});

describe("useCustomerChat — openSession sequence guard (H1)", () => {
  it("a SLOW earlier open must not overwrite the view of a newer open", async () => {
    let releaseFirst: (() => void) | null = null;
    getSessionMock.mockImplementation((sid: string) => {
      if (sid === "sess_slow") {
        return new Promise((resolve) => {
          releaseFirst = () => resolve({
            session_id: sid,
            title: null,
            updated_at: null,
            messages: [{ sender: "user", text: "STALE", ts: null }],
          });
        });
      }
      return Promise.resolve({
        session_id: sid,
        title: null,
        updated_at: null,
        messages: [{ sender: "user", text: "FRESH", ts: null }],
      });
    });

    const { result } = renderHook(() => useCustomerChat(identity));
    const first = result.current.openSession("sess_slow");
    await act(async () => {
      await new Promise((r) => setTimeout(r, 5));
    });
    const second = result.current.openSession("sess_new");
    await act(async () => {
      await second;
    });
    await act(async () => {
      releaseFirst?.();
      await first;
    });
    const texts = result.current.messages.map((m) => m.text);
    expect(texts).toContain("FRESH");
    expect(texts).not.toContain("STALE");
  });

  it("send is GATED while an open is in flight (H2)", async () => {
    let release: (() => void) | null = null;
    getSessionMock.mockImplementation(() => new Promise((r) => {
      release = () => r({ session_id: "s", title: null, updated_at: null, messages: [] });
    }));
    streamChatMock.mockImplementation(fakeStream([]));

    const { result } = renderHook(() => useCustomerChat(identity));
    const opening = result.current.openSession("sess_x");
    await act(async () => {
      await new Promise((r) => setTimeout(r, 5));
    });
    await act(async () => {
      await result.current.send({ message: "during open" });
    });
    expect(result.current.messages.some((m) => m.text === "during open")).toBe(false);
    await act(async () => {
      release?.();
      await opening;
    });
    await act(async () => {
      await result.current.send({ message: "after open" });
    });
    expect(result.current.messages.some((m) => m.text === "after open")).toBe(true);
  });
});
