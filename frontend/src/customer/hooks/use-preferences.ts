/**
 * Local taste profile (Preference Center). The backend profile endpoints are still
 * stubbed (routes/user_routes.py → not_implemented), so preferences live in
 * localStorage and are folded into the chat query as soft context. Syncs across tabs
 * via the `storage` event. When the profile API lands, swap the storage layer here
 * without touching the UI.
 */
import { useCallback, useEffect, useState } from "react";

export type Budget = "" | "student" | "standard" | "premium";

export interface Preferences {
  budget: Budget;
  dietary: string[];
  likedCuisines: string[];
  dislikedCuisines: string[];
  useLocation: boolean;
  lat: number;
  lng: number;
}

const STORAGE_KEY = "cust_preferences";

const DEFAULTS: Preferences = {
  budget: "",
  dietary: [],
  likedCuisines: [],
  dislikedCuisines: [],
  useLocation: false,
  lat: 10.79,
  lng: 106.66,
};

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

export function usePreferences() {
  const [prefs, setPrefs] = useState<Preferences>(load);

  // Cross-tab sync: another tab editing preferences updates this one live.
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

  const update = useCallback((patch: Partial<Preferences>) => {
    setPrefs((prev) => {
      const next = { ...prev, ...patch };
      persist(next);
      return next;
    });
  }, []);

  const toggleIn = useCallback(
    (key: "dietary" | "likedCuisines" | "dislikedCuisines", value: string) => {
      setPrefs((prev) => {
        const list = prev[key];
        const next = {
          ...prev,
          [key]: list.includes(value) ? list.filter((v) => v !== value) : [...list, value],
        };
        persist(next as Preferences);
        return next as Preferences;
      });
    },
    [],
  );

  return { prefs, update, toggleIn };
}

const BUDGET_LABEL: Record<Exclude<Budget, "">, string> = {
  student: "tiết kiệm (15k–50k)",
  standard: "trung cấp (50k–150k)",
  premium: "cao cấp (150k+)",
};

/** Build a Vietnamese context clause appended to the raw chat message. */
export function preferencesToContext(p: Preferences): string {
  const parts: string[] = [];
  if (p.budget) parts.push(`ngân sách ${BUDGET_LABEL[p.budget]}`);
  if (p.likedCuisines.length) parts.push(`thích ${p.likedCuisines.join(", ")}`);
  if (p.dislikedCuisines.length) parts.push(`không thích ${p.dislikedCuisines.join(", ")}`);
  if (p.dietary.length) parts.push(`ăn kiêng: ${p.dietary.join(", ")}`);
  return parts.length ? ` (Sở thích của tôi: ${parts.join("; ")}.)` : "";
}
