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

/**
 * Google Maps directions deep-link.
 *
 * PRIORITY: name+address TEXT query, NOT the crawled lat/lng. The crawl-sourced coords
 * are only accurate to the neighborhood level (a representative point — verified: an
 * S209 Vinhomes Ocean Park merchant's stored coords reverse-geocode to a different
 * street ~750m away, so a coords link pins the WRONG block). Google's own geocoder
 * resolves "S209 Vinhomes Ocean Park" exactly. Raw coords remain the fallback for
 * merchants with no address text.
 */
export function mapsUrl(item: Pick<RestaurantResult, "lat" | "lng" | "name" | "address">): string {
  const q = [item.name, item.address].filter(Boolean).join(" ");
  if (q)
    return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(q)}`;
  if (item.lat != null && item.lng != null)
    return `https://www.google.com/maps/dir/?api=1&destination=${item.lat},${item.lng}`;
  return "https://www.google.com/maps";
}
