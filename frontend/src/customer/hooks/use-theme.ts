/**
 * Theme controller — light/dark, persisted, follows system until user chooses.
 * Reads the data-theme attribute that index.html's no-flash script already set,
 * so the first paint matches; keeps <html data-theme> + localStorage in sync afterwards.
 */
import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "cust_theme";

function readInitial(): Theme {
  if (typeof document !== "undefined") {
    const attr = document.documentElement.getAttribute("data-theme");
    if (attr === "light" || attr === "dark") return attr;
  }
  if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    return "dark";
  }
  return "light";
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(readInitial);

  // Apply + persist whenever it changes.
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* storage may be blocked — non-fatal */
    }
  }, [theme]);

  // Follow OS changes only while the user hasn't explicitly chosen a theme.
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      let chosen = false;
      try {
        chosen = localStorage.getItem(STORAGE_KEY) !== null;
      } catch {
        chosen = true;
      }
      if (!chosen) setTheme(mq.matches ? "dark" : "light");
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const toggle = useCallback(() => setTheme((t) => (t === "dark" ? "light" : "dark")), []);

  return { theme, setTheme, toggle };
}
