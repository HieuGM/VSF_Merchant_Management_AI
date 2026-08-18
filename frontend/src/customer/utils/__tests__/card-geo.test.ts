/**
 * Pure-logic tests: card geo/hours helpers (VN timezone + cross-midnight), the SSE
 * frame parser, and the parallel-safe progress-step marker.
 */
import { describe, expect, it, vi } from "vitest";
import { hhmm, mapsUrl, openNow } from "../card-geo";
import { parseFrame } from "../../api/customer-agent-client";
import { markDone, type ProgressStep } from "../../hooks/use-customer-chat";

describe("hhmm", () => {
  it("trims ISO time forms to HH:MM", () => {
    expect(hhmm("07:00")).toBe("07:00");
    expect(hhmm("07:00:30.000")).toBe("07:00");
  });
  it("null for missing", () => {
    expect(hhmm(null)).toBeNull();
    expect(hhmm(undefined)).toBeNull();
  });
});

describe("openNow — VN time (UTC+7), cross-midnight aware", () => {
  // Freeze time inside each case: openNow reads Date.now(), so mock it per case.
  const AT = (utcHour: number, utcMin = 0) =>
    vi.setSystemTime(new Date(Date.UTC(2026, 7, 18, utcHour, utcMin)));

  it("normal window: open during, closed after", () => {
    AT(3); // 10:00 VN
    expect(openNow("05:45", "23:59")).toBe(true);
    AT(17); // 00:00 VN next day
    expect(openNow("05:45", "23:59")).toBe(false);
    AT(6); // 13:00 VN
    expect(openNow("05:45", "13:00")).toBe(false); // boundary: cur < closes fails at ==
  });

  it("cross-midnight window (22:00–02:00): open at 23:00 AND at 01:00, closed at 10:00", () => {
    AT(16); // 23:00 VN
    expect(openNow("22:00", "02:00")).toBe(true);
    AT(18); // 01:00 VN
    expect(openNow("22:00", "02:00")).toBe(true);
    AT(3); // 10:00 VN
    expect(openNow("22:00", "02:00")).toBe(false);
  });

  it("unknown hours → null (never guess a badge)", () => {
    expect(openNow(null, null)).toBeNull();
    expect(openNow("05:00", null)).toBeNull();
  });
});

describe("mapsUrl", () => {
  it("directions deep-link when coords exist", () => {
    expect(mapsUrl({ lat: 10.79, lng: 106.66, name: "Phở", address: "S1" })).toBe(
      "https://www.google.com/maps/dir/?api=1&destination=10.79,106.66",
    );
  });
  it("falls back to a name+address search when no coords", () => {
    const url = mapsUrl({ lat: null, lng: null, name: "Phở Phong", address: "123 LVS" });
    expect(url).toContain("google.com/maps/search");
    expect(decodeURIComponent(url)).toContain("Phở Phong 123 LVS");
  });
});

describe("parseFrame (SSE)", () => {
  it("parses event + single-line JSON data", () => {
    const f = parseFrame('event: answer_delta\ndata: {"answer_delta": "Ồ"}');
    expect(f?.event).toBe("answer_delta");
    expect(f?.data?.answer_delta).toBe("Ồ");
  });
  it("multi-line data joins + parses", () => {
    const f = parseFrame('event: run_finished\ndata: {"answer":\ndata: "x"}');
    expect(f?.event).toBe("run_finished");
    expect(f?.data?.answer).toBe("x");
  });
  it("no data line → null (heartbeat comment frames are skipped upstream)", () => {
    expect(parseFrame(": ping")).toBeNull();
  });
  it("non-JSON data degrades to a string payload (never throws)", () => {
    const f = parseFrame("event: message\ndata: plain text");
    expect(f?.event).toBe("message");
    expect(f?.data).toBe("plain text");
  });
});

describe("markDone (parallel-safe progress steps)", () => {
  const steps = (tool?: string): ProgressStep[] => [
    { id: "1", label: "A", tool, done: false },
    { id: "2", label: "B", done: false },
  ];
  it("by tool name — marks the matching pending step only", () => {
    const next = markDone(steps("search"), "search");
    expect(next[0].done).toBe(true);
    expect(next[1].done).toBe(false);
  });
  it("no tool → oldest pending", () => {
    const next = markDone(steps());
    expect(next[0].done).toBe(true);
    expect(next[1].done).toBe(false);
  });
  it("already-done tool → no-op (idempotent)", () => {
    const done: ProgressStep[] = [{ id: "1", label: "A", tool: "t", done: true }];
    expect(markDone(done, "t")).toBe(done);
  });
});
