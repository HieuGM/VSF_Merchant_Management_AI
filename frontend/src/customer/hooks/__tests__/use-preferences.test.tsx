/**
 * use-preferences tests — the debounced-PATCH sync (single PATCH per burst, abort on
 * supersede, offline fallback to the localStorage cache) and the allergens round-trip.
 *
 * The API client is module-mocked; identity comes from a seeded localStorage user id
 * (same source the hook reads via getCustomerUserId).
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getProfileMock = vi.hoisted(() => vi.fn());
const patchProfileMock = vi.hoisted(() => vi.fn());
const clearMemoryMock = vi.hoisted(() => vi.fn());
const deleteNoteMock = vi.hoisted(() => vi.fn());

vi.mock("../../api/customer-agent-client", () => ({
  getProfile: getProfileMock,
  patchProfile: patchProfileMock,
  clearMemory: clearMemoryMock,
  deleteNote: deleteNoteMock,
}));

import { usePreferences } from "../use-preferences";

/** Seed a user id BEFORE the hook mounts (getCustomerUserId reads localStorage). */
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  localStorage.setItem("cust_user_id", "user_pref_test");
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("usePreferences — profile load", () => {
  it("loads taste + allergens + note expiries from the server profile", async () => {
    getProfileMock.mockResolvedValue({
      user_id: "user_pref_test",
      budget_level: "student",
      dietary: ["Chay"],
      liked_cuisines: ["Việt"],
      disliked_cuisines: [],
      allergens: ["hải sản"],
      context_memory: {
        notes: ["Tôi dị ứng hải sản"],
        note_expiries: {},
      },
    });
    const { result } = renderHook(() => usePreferences());
    await waitFor(() => expect(result.current.sync).toBe("synced"));
    expect(result.current.prefs.budget).toBe("student");
    expect(result.current.prefs.allergens).toEqual(["hải sản"]);
    expect(result.current.notes).toEqual(["Tôi dị ứng hải sản"]);
  });

  it("network failure → offline, keeps localStorage cache (no crash)", async () => {
    localStorage.setItem(
      "cust_preferences",
      JSON.stringify({ budget: "premium", dietary: [], likedCuisines: [], dislikedCuisines: [], allergens: [] }),
    );
    getProfileMock.mockRejectedValue(new Error("net down"));
    const { result } = renderHook(() => usePreferences());
    await waitFor(() => expect(result.current.sync).toBe("offline"));
    expect(result.current.prefs.budget).toBe("premium");
  });
});

describe("usePreferences — debounced PATCH sync", () => {
  it("a BURST of toggles produces exactly ONE PATCH carrying the final state", async () => {
    vi.useFakeTimers();
    try {
      getProfileMock.mockResolvedValue(null); // 404 → no migration, idle
      patchProfileMock.mockResolvedValue({});
      const { result } = renderHook(() => usePreferences());
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      // Burst: 3 rapid edits (500ms debounce must coalesce).
      act(() => result.current.toggleIn("likedCuisines", "Việt"));
      act(() => result.current.toggleIn("likedCuisines", "Nhật"));
      act(() => result.current.update({ allergens: ["đậu phộng"] }));
      expect(patchProfileMock).not.toHaveBeenCalled(); // still inside the debounce
      await act(async () => {
        await vi.advanceTimersByTimeAsync(600);
      });
      expect(patchProfileMock).toHaveBeenCalledTimes(1);
      const body = patchProfileMock.mock.calls[0][1];
      expect(body.liked_cuisines).toEqual(["Việt", "Nhật"]);
      expect(body.allergens).toEqual(["đậu phộng"]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("a failed PATCH flips sync to offline (local value kept, retried on next edit)", async () => {
    vi.useFakeTimers();
    try {
      getProfileMock.mockResolvedValue(null);
      patchProfileMock.mockRejectedValueOnce(new Error("save fail")).mockResolvedValue({});
      const { result } = renderHook(() => usePreferences());
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      act(() => result.current.update({ budget: "standard" }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(600);
      });
      expect(result.current.sync).toBe("offline");
      expect(result.current.prefs.budget).toBe("standard"); // kept locally
      // Next successful edit heals the status.
      act(() => result.current.update({ budget: "premium" }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(600);
      });
      expect(result.current.sync).toBe("synced");
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("usePreferences — note delete (optimistic + rollback)", () => {
  it("deletes locally at once; server failure restores the note (UI never lies)", async () => {
    getProfileMock.mockResolvedValue({
      user_id: "user_pref_test",
      context_memory: { notes: ["A", "B"], note_expiries: { b: "2099-01-01T00:00:00Z" } },
      allergens: [],
    });
    deleteNoteMock.mockRejectedValue(new Error("server down"));
    const { result } = renderHook(() => usePreferences());
    await waitFor(() => expect(result.current.notes).toEqual(["A", "B"]));
    await act(async () => {
      await result.current.deleteNote("B");
    });
    // Rolled back — the backend still enforces it, so the UI must keep showing it.
    expect(result.current.notes).toEqual(["A", "B"]);
    expect(result.current.noteExpiries).toHaveProperty("b");
  });

  it("successful delete drops the note + its expiry entry", async () => {
    getProfileMock.mockResolvedValue({
      user_id: "user_pref_test",
      context_memory: { notes: ["A", "B"], note_expiries: { b: "2099-01-01T00:00:00Z" } },
      allergens: [],
    });
    deleteNoteMock.mockResolvedValue({});
    const { result } = renderHook(() => usePreferences());
    await waitFor(() => expect(result.current.notes).toEqual(["A", "B"]));
    await act(async () => {
      await result.current.deleteNote("B");
    });
    expect(result.current.notes).toEqual(["A"]);
    expect(result.current.noteExpiries).not.toHaveProperty("b");
    expect(deleteNoteMock).toHaveBeenCalledWith("user_pref_test", "B");
  });
});

describe("usePreferences — clearAll", () => {
  it("wipes taste + allergens + notes server-side AND locally (geo survives)", async () => {
    getProfileMock.mockResolvedValue({
      user_id: "user_pref_test",
      budget_level: "student",
      dietary: ["Chay"],
      allergens: ["hải sản"],
      context_memory: { notes: ["N"], note_expiries: {} },
    });
    clearMemoryMock.mockResolvedValue({});
    const { result } = renderHook(() => usePreferences());
    await waitFor(() => expect(result.current.sync).toBe("synced"));
    act(() => result.current.update({ useLocation: true }));
    await act(async () => {
      await result.current.clearAll();
    });
    expect(clearMemoryMock).toHaveBeenCalledWith("user_pref_test");
    expect(result.current.prefs.budget).toBe("");
    expect(result.current.prefs.allergens).toEqual([]);
    expect(result.current.notes).toEqual([]);
    expect(result.current.prefs.useLocation).toBe(true); // geo is device state, survives
  });
});
