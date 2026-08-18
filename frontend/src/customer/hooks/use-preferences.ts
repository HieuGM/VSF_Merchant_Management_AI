/**
 * Taste profile + geolocation state (phase-04 cutover).
 *
 * TASTE fields (budget, dietary, likedCuisines, dislikedCuisines) are now backed by the
 * canonical backend profile (GET/PATCH /api/v1/users/{id}/profile) — loaded on mount,
 * PATCHed on change (debounced), and mirrored to localStorage as an offline cache. Existing
 * localStorage taste prefs are migrated up to the server once (first 404).
 *
 * GEO state (useLocation, locationReady, lat, lng, accuracy) stays localStorage-only — it is
 * ephemeral device state, not a portable preference.
 *
 * context_memory.notes (phase-03 long-term memory) are exposed read-only via `notes` and
 * mirrored to localStorage so the cross-tab `storage` listener keeps them fresh too.
 *
 * In-flight PATCH is abortable (carryover M-1): a newer edit or unmount aborts the previous
 * request via an AbortController instead of letting it fire setSync on a gone/superseded call.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { getProfile, patchProfile, clearMemory, type UserProfile } from "../api/customer-agent-client";
import { getCustomerUserId } from "./use-customer-identity";

export type Budget = "" | "student" | "standard" | "premium";

export interface Preferences {
  budget: Budget;
  dietary: string[];
  likedCuisines: string[];
  dislikedCuisines: string[];
  /** Durable allergy/avoid facts (backend `allergens`, no FIFO cap) — editable via the
   * allergy section; hard-filtered on every search, so edits change future results. */
  allergens: string[];
  useLocation: boolean;
  /** True only after live geolocation or manual coords — gates whether coords are sent. */
  locationReady: boolean;
  lat: number;
  lng: number;
  accuracy: number | null;
}

export type SyncStatus = "idle" | "loading" | "synced" | "offline";

const STORAGE_KEY = "cust_preferences";
/** Mirror of context_memory.notes for cross-tab sync (carryover M-2). */
const NOTES_KEY = "cust_context_notes";
/** One-time migration flag: localStorage taste prefs pushed to the server. */
const MIGRATED_KEY = "cust_preferences_migrated";

const DEFAULTS: Preferences = {
  budget: "",
  dietary: [],
  likedCuisines: [],
  dislikedCuisines: [],
  allergens: [],
  useLocation: false,
  locationReady: false,
  lat: 10.79, // Placeholder only (HCM). Never sent unless `locationReady` is true.
  lng: 106.66,
  accuracy: null,
};

// Taste fields are API-backed; geo fields are localStorage-only.
const TASTE_KEYS = ["budget", "dietary", "likedCuisines", "dislikedCuisines", "allergens"] as const;

function load(): Preferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS;
  } catch {
    return DEFAULTS;
  }
}

function persist(next: Preferences) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    /* storage full / disabled — keep in-memory only */
  }
}

function persistNotes(notes: string[]) {
  try {
    localStorage.setItem(NOTES_KEY, JSON.stringify(notes));
  } catch {
    /* storage unavailable */
  }
}

/** Backend profile (snake_case) → FE taste subset (camelCase). */
function profileToTaste(p: UserProfile): Partial<Preferences> {
  return {
    budget: (p.budget_level as Budget) || "",
    dietary: p.dietary ?? [],
    likedCuisines: p.liked_cuisines ?? [],
    dislikedCuisines: p.disliked_cuisines ?? [],
    allergens: p.allergens ?? [],
  };
}

/** FE taste subset → backend PATCH body (snake_case; empty budget → null to clear). */
function tasteToPatch(taste: Partial<Preferences>) {
  const body: Record<string, unknown> = {};
  if (taste.budget !== undefined) body.budget_level = taste.budget || null;
  if (taste.dietary !== undefined) body.dietary = taste.dietary;
  if (taste.likedCuisines !== undefined) body.liked_cuisines = taste.likedCuisines;
  if (taste.dislikedCuisines !== undefined) body.disliked_cuisines = taste.dislikedCuisines;
  if (taste.allergens !== undefined) body.allergens = taste.allergens;
  return body;
}

export interface UsePreferences {
  prefs: Preferences;
  /** Long-term context_memory notes (phase-03), read-only. */
  notes: string[];
  /** Server-sync status for the taste profile. */
  sync: SyncStatus;
  update: (patch: Partial<Preferences>) => void;
  toggleIn: (key: "dietary" | "likedCuisines" | "dislikedCuisines", value: string) => void;
  /** Clear remembered memory (notes + taste) server-side + locally. Keeps geo. For testing. */
  clearAll: () => Promise<void>;
}

export function usePreferences(): UsePreferences {
  const [prefs, setPrefs] = useState<Preferences>(load);
  const [notes, setNotes] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(NOTES_KEY) ?? "[]") as string[];
    } catch {
      return [];
    }
  });
  const [sync, setSync] = useState<SyncStatus>("idle");
  const patchTimer = useRef<number | null>(null);
  const patchAbort = useRef<AbortController | null>(null);

  // --- Load profile from backend on mount; fall back to localStorage cache offline ---
  useEffect(() => {
    const userId = getCustomerUserId();
    if (!userId) return;
    let cancelled = false;
    setSync("loading");
    (async () => {
      try {
        const prof = await getProfile(userId);
        if (cancelled) return;
        if (prof) {
          const taste = profileToTaste(prof);
          setPrefs((prev) => ({ ...prev, ...taste }));
          const loadedNotes = prof.context_memory?.notes ?? [];
          setNotes(loadedNotes);
          persistNotes(loadedNotes);
          persist({ ...load(), ...taste });
          setSync("synced");
        } else {
          // 404: no server profile yet. Migrate existing localStorage taste up ONCE so a
          // returning user doesn't lose prefs they set before the API landed. The flag is
          // set synchronously BEFORE the await so StrictMode's dev double-mount can't race
          // a second migration through. No retry on failure — the next user edit re-syncs
          // the full taste via schedulePatch anyway.
          setSync("idle");
          if (!localStorage.getItem(MIGRATED_KEY)) {
            try {
              localStorage.setItem(MIGRATED_KEY, "1");
            } catch {
              /* storage unavailable */
            }
            const cached = load();
            const hasTaste =
              cached.budget ||
              cached.dietary.length ||
              cached.likedCuisines.length ||
              cached.dislikedCuisines.length ||
              cached.allergens.length;
            if (hasTaste) {
              try {
                await patchProfile(userId, tasteToPatch(cached));
              } catch {
                /* best-effort migrate — next user edit re-syncs via schedulePatch */
              }
            }
          }
        }
      } catch {
        if (!cancelled) setSync("offline"); // network error → keep localStorage cache
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // --- Debounced PATCH for taste changes (geo changes do not hit the API) ---
  const schedulePatch = useCallback((next: Preferences) => {
    const userId = getCustomerUserId();
    if (!userId) return;
    if (patchTimer.current) clearTimeout(patchTimer.current);
    patchTimer.current = window.setTimeout(async () => {
      // Abort any in-flight PATCH (a newer edit supersedes it). Carryover M-1.
      patchAbort.current?.abort();
      const ac = new AbortController();
      patchAbort.current = ac;
      try {
        await patchProfile(userId, tasteToPatch(next), ac.signal);
        if (!ac.signal.aborted) setSync("synced");
      } catch (err) {
        if (ac.signal.aborted) return; // superseded/unmounted — don't flip sync
        setSync("offline"); // keep local; next change retries
      } finally {
        if (patchAbort.current === ac) patchAbort.current = null;
      }
    }, 500);
  }, []);

  const update = useCallback(
    (patch: Partial<Preferences>) => {
      setPrefs((prev) => {
        const next = { ...prev, ...patch };
        persist(next);
        if (TASTE_KEYS.some((k) => patch[k] !== undefined)) {
          setSync("loading");
          schedulePatch(next);
        }
        return next;
      });
    },
    [schedulePatch],
  );

  const toggleIn = useCallback(
    (key: "dietary" | "likedCuisines" | "dislikedCuisines", value: string) => {
      setPrefs((prev) => {
        const list = prev[key];
        const next = {
          ...prev,
          [key]: list.includes(value) ? list.filter((v) => v !== value) : [...list, value],
        } as Preferences;
        persist(next);
        setSync("loading");
        schedulePatch(next);
        return next;
      });
    },
    [schedulePatch],
  );

  // Cross-tab sync (localStorage event) — another tab editing prefs/notes updates this one.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && e.newValue) {
        try {
          setPrefs({ ...DEFAULTS, ...JSON.parse(e.newValue) });
        } catch {
          /* malformed — ignore */
        }
      } else if (e.key === NOTES_KEY && e.newValue) {
        try {
          setNotes(JSON.parse(e.newValue) as string[]);
        } catch {
          /* malformed — ignore */
        }
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  // Clear any pending debounced PATCH + abort the in-flight request on unmount — prevents a
  // fetch + setSync firing after the component is gone (e.g. toggle then navigate < 500ms).
  useEffect(() => {
    return () => {
      if (patchTimer.current) clearTimeout(patchTimer.current);
      patchAbort.current?.abort();
    };
  }, []);

  // Clear remembered memory (context_memory notes + taste) — server-side + local. Geo survives.
  const clearAll = useCallback(async () => {
    const userId = getCustomerUserId();
    if (!userId) return;
    setSync("loading");
    try {
      await clearMemory(userId);
      setPrefs((prev) => ({
        ...prev,
        budget: "",
        dietary: [],
        likedCuisines: [],
        dislikedCuisines: [],
        allergens: [],
      }));
      setNotes([]);
      persistNotes([]);
      persist({
        ...load(),
        budget: "",
        dietary: [],
        likedCuisines: [],
        dislikedCuisines: [],
        allergens: [],
      });
      setSync("synced");
    } catch {
      setSync("offline");
    }
  }, []);

  return { prefs, notes, sync, update, toggleIn, clearAll };
}
