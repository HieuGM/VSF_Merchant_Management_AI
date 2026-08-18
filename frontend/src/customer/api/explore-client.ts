/** Explore client — merchant search (UC-04). Relocated from src/lib/api.ts into the
 * customer vertical so customer/ never imports outside its boundary. Same endpoints
 * (/api/v1/merchants/search). Returns the raw merchant search response. */
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export interface Merchant {
  merchant_id: string;
  name: string;
  cuisine: string;
  address: string | null;
  city: string;
  lat: number | null;
  lng: number | null;
  distance_km: number | null;
  avg_rating: number | null;
  match_score: number;
  image_url?: string | null;
  opens_at?: string | null;
  closes_at?: string | null;
  top_dishes?: Array<{ name: string; price?: number | null; likes?: number | null }>;
}

export interface SearchFilters {
  query?: string;
  cuisine?: string;
  city?: string;
  budget?: string;
  lat?: number;
  lng?: number;
  radius_km?: number;
  limit?: number;
  /** Caller's user id — the backend applies their allergen/diet hard-filters
   * (the same always-on safety filter as the chat path). */
  userId?: string;
}

export interface SearchResponse {
  trace_id: string;
  merchants: Merchant[];
  total: number;
  filters_applied: Record<string, unknown>;
  cache_status: "hit" | "miss" | "disabled";
}

export async function searchMerchants(
  filters: SearchFilters,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  const params = new URLSearchParams();
  if (filters.query) params.set("query", filters.query);
  if (filters.cuisine) params.set("cuisine", filters.cuisine);
  if (filters.city) params.set("city", filters.city);
  if (filters.budget) params.set("budget", filters.budget);
  if (filters.lat != null) params.set("lat", String(filters.lat));
  if (filters.lng != null) params.set("lng", String(filters.lng));
  if (filters.radius_km) params.set("radius_km", String(filters.radius_km));
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.userId) params.set("user_id", filters.userId);

  // `signal` lets the caller abort a superseded search (rapid filter changes) so a slower
  // earlier request can't resolve last and overwrite fresher results (stale-result race).
  const resp = await fetch(`${API_BASE}/api/v1/merchants/search?${params}`, { signal });
  if (!resp.ok) throw new Error(`Tìm kiếm thất bại: ${resp.statusText}`);
  return resp.json();
}
