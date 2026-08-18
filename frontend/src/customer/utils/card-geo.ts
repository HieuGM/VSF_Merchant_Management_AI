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
 * Google Maps link for the "Chỉ đường" action.
 *
 * VERIFIED-FALSE ASSUMPTIONS (tested live against Google Maps, 2026-08-18):
 *   - Raw crawl coords: neighborhood-representative points, off by 200-700m from the
 *     actual unit (an S209 shop's stored coords land on a different street).
 *   - Address text WITH the VN unit code ("S209 ..."): Google's geocoder does NOT know
 *     building codes like S209 — it tokenizes toward "S2" and nearest-matches a
 *     DIFFERENT block (S2.10), pinning the wrong shop. This was the reported bug.
 *
 * What works: a SEARCH by shop name + area (unit code stripped). Google lists matching
 * POIs in the right neighborhood; when it carries the POI (e.g. "Jiro sushi ocean
 * park") the search lands on it directly, otherwise the user taps the exact shop.
 *
 * Fallbacks: coords-only directions when no usable text; Maps homepage when nothing.
 */
const UNIT_CODE_RE = /\b[SRT]\s?-?\d+(\.\d+)?\b|\bHô\s?\d+(-\d+)*\b/gi;

/** Search query = name + address MINUS unit codes (S209 / R1.02 / Hô 06-… stripped). */
export function areaQuery(name: string, address?: string | null): string {
  const cleanedAddr = (address ?? "").replace(UNIT_CODE_RE, " ").replace(/\s+/g, " ").trim();
  return [name, cleanedAddr].filter(Boolean).join(" ").trim();
}

export function mapsUrl(item: Pick<RestaurantResult, "lat" | "lng" | "name" | "address">): string {
  const q = areaQuery(item.name, item.address);
  if (q)
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}`;
  if (item.lat != null && item.lng != null)
    return `https://www.google.com/maps/dir/?api=1&destination=${item.lat},${item.lng}`;
  return "https://www.google.com/maps";
}
