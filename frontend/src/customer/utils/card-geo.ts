/**
 * Card geo/hours helpers — pure functions extracted from restaurant-card.tsx so they
 * are unit-testable (cross-midnight + VN-timezone logic is easy to get wrong).
 */
import type { RestaurantResult } from "../api/customer-agent-client";

/** "07:00" / "07:00:30.000" → "07:00" (backend sends Time.isoformat()). */
export function hhmm(iso?: string | null): string | null {
  return iso ? iso.slice(0, 5) : null;
}

/** Open-now in the merchant's TZ (VN, UTC+7 — no DST) from ISO opens/closes.
 * Handles the cross-midnight case (closes < opens → open late-night). */
export function openNow(opens?: string | null, closes?: string | null): boolean | null {
  const o = hhmm(opens);
  const c = hhmm(closes);
  if (!o || !c) return null; // hours unknown → no badge (never guess)
  const now = new Date(Date.now() + 7 * 3600_000); // VN time regardless of device TZ
  const cur = `${String(now.getUTCHours()).padStart(2, "0")}:${String(now.getUTCMinutes()).padStart(2, "0")}`;
  return o <= c ? cur >= o && cur < c : cur >= o || cur < c; // cross-midnight
}

/** Google Maps directions deep-link — coords when we have them, else name+address search. */
export function mapsUrl(item: Pick<RestaurantResult, "lat" | "lng" | "name" | "address">): string {
  if (item.lat != null && item.lng != null)
    return `https://www.google.com/maps/dir/?api=1&destination=${item.lat},${item.lng}`;
  const q = encodeURIComponent([item.name, item.address].filter(Boolean).join(" "));
  return `https://www.google.com/maps/search/?api=1&query=${q}`;
}
