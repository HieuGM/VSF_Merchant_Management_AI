/** API client for backend integration (§11 contract). */
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
}

export interface SearchResponse {
  trace_id: string;
  merchants: Merchant[];
  total: number;
  filters_applied: Record<string, unknown>;
  cache_status: "hit" | "miss" | "disabled";
}

/**
 * Search merchants with filters (UC-04).
 */
export async function searchMerchants(
  filters: SearchFilters
): Promise<SearchResponse> {
  const params = new URLSearchParams();

  if (filters.query) params.set("query", filters.query);
  if (filters.cuisine) params.set("cuisine", filters.cuisine);
  if (filters.city) params.set("city", filters.city);
  if (filters.budget) params.set("budget", filters.budget);
  if (filters.lat) params.set("lat", filters.lat.toString());
  if (filters.lng) params.set("lng", filters.lng.toString());
  if (filters.radius_km) params.set("radius_km", filters.radius_km.toString());
  if (filters.limit) params.set("limit", filters.limit.toString());

  const response = await fetch(`${API_BASE}/api/v1/merchants/search?${params}`);

  if (!response.ok) {
    throw new Error(`Search failed: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Find nearby merchants (Haversine-based).
 */
export async function findNearbyMerchants(params: {
  lat: number;
  lng: number;
  radius_km?: number;
  cuisine?: string;
  limit?: number;
}): Promise<SearchResponse> {
  const searchParams = new URLSearchParams();
  searchParams.set("lat", params.lat.toString());
  searchParams.set("lng", params.lng.toString());
  if (params.radius_km) searchParams.set("radius_km", params.radius_km.toString());
  if (params.cuisine) searchParams.set("cuisine", params.cuisine);
  if (params.limit) searchParams.set("limit", params.limit.toString());

  const response = await fetch(
    `${API_BASE}/api/v1/merchants/nearby?${searchParams}`
  );

  if (!response.ok) {
    throw new Error(`Nearby search failed: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get health check status.
 */
export async function getHealth(): Promise<{
  redis: string;
  database: string;
  llm_configured: boolean;
}> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.statusText}`);
  }
  return response.json();
}
