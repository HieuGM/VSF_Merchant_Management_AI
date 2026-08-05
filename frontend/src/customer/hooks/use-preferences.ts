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
 * context_memory.notes (phase-03 long-term memory) are exposed read-only via `notes`.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { getProfile, patchProfile, type UserProfile } from "../api/customer-agent-client";
import { getCustomerUserId } from "./use-customer-identity";

export type Budget = "" | "student" | "standard" | "premium";

export interface Preferences {
  budget: Budget;
  dietary: string[];
  likedCuisines: string[];
  dislikedCuisines: string[];
  useLocation: boolean;
  /** True only after live geolocation or manual coords — gates whether coords are sent. */
  locationReady: boolean;
  lat: number;
  lng: number;
  accuracy: number | null;
}

export type SyncStatus = "idle" | "loading" | "synced" | "offline";

const STORAGE_KEY = "cust_preferences";
/** One-time migration flag: localStorage taste prefs pushed to the server. */
const MIGRATED_KEY = "cust_preferences_migrated";

const DEFAULTS: Preferences = {
  budget: "",
  dietary: [],
  likedCuisines: [],
  dislikedCuisines: [],
  useLocation: false,
  locationReady: false,
  lat: 10.79, // Placeholder only (HCM). Never sent unless `locationReady` is true.
  lng: 106.66,
  accuracy: null,
};

// Taste fields are API-backed; geo fields are localStorage-only.
const TASTE_KEYS = ["budget", "dietary", "likedCuisines", "dislikedCuisines"] as const;

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

/** Backend profile (snake_case) → FE taste subset (camelCase). */
function profileToTaste(p: UserProfile): Partial<Preferences> {
  return {
    budget: (p.budget_level as Budget) || "",
    dietary: p.dietary ?? [],
    likedCuisines: p.liked_cuisines ?? [],
    dislikedCuisines: p.disliked_cuisines ?? [],
  };
}

/** FE taste subset → backend PATCH body (snake_case; empty budget → null to clear). */
function tasteToPatch(taste: Partial<Preferences>) {
  const body: Record<string, unknown> = {};
  if (taste.budget !== undefined) body.budget_level = taste.budget || null;
  if (taste.dietary !== undefined) body.dietary = taste.dietary;
  if (taste.likedCuisines !== undefined) body.liked_cuisines = taste.likedCuisines;
  if (taste.dislikedCuisines !== undefined) body.disliked_cuisines = taste.dislikedCuisines;
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
}

export function usePreferences(): UsePreferences {
  const [prefs, setPrefs] = useState<Preferences>(load);
  const [notes, setNotes] = useState<string[]>([]);
  const [sync, setSync] = useState<SyncStatus>("idle");
  const patchTimer = useRef<number | null>(null);

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
          setNotes(prof.context_memory?.notes ?? []);
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
              cached.dislikedCuisines.length;
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

  // Clear any pending debounced PATCH on unmount — prevents a fetch + setSync firing
  // after the component is gone (e.g. user toggles then navigates away within 500ms).
  useEffect(() => {
    return () => {
      if (patchTimer.current) clearTimeout(patchTimer.current);
    };
  }, []);

  // --- Debounced PATCH for taste changes (geo changes do not hit the API) ---
  const schedulePatch = useCallback((next: Preferences) => {
    const userId = getCustomerUserId();
    if (!userId) return;
    if (patchTimer.current) clearTimeout(patchTimer.current);
    patchTimer.current = window.setTimeout(async () => {
      try {
        await patchProfile(userId, tasteToPatch(next));
        setSync("synced");
      } catch {
        setSync("offline"); // keep local; next change retries
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

  // Cross-tab sync (localStorage event) — another tab editing prefs updates this one.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && e.newValue) {
        try {
          setPrefs({ ...DEFAULTS, ...JSON.parse(e.newValue) });
        } catch {
          /* malformed — ignore */
        }
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  return { prefs, notes, sync, update, toggleIn };
}
