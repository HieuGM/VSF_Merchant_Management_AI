/**
 * Base API client — FROZEN Phase 0 seam (design §11).
 * Both verticals call the backend through this client so error-envelope handling,
 * base URL, and X-Request-ID propagation stay consistent. Add typed endpoint helpers
 * inside each vertical's own module (customer/ or merchant/), not here.
 */

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

/** §11.10 error envelope. */
export interface ApiError {
  code: string;
  message: string;
  details: Record<string, unknown>;
  trace_id: string | null;
}

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: ApiError
  ) {
    super(body.message);
    this.name = "ApiRequestError";
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "DELETE" | "PUT";
  body?: unknown;
  params?: Record<string, string | number | undefined>;
  signal?: AbortSignal;
}

function buildUrl(path: string, params?: RequestOptions["params"]): string {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, params, signal } = options;
  const resp = await fetch(buildUrl(path, params), {
    method,
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });

  if (!resp.ok) {
    const payload = await resp.json().catch(() => null);
    const err: ApiError = payload?.error ?? {
      code: "internal_error",
      message: `HTTP ${resp.status}`,
      details: {},
      trace_id: resp.headers.get("X-Request-ID"),
    };
    throw new ApiRequestError(resp.status, err);
  }
  return (await resp.json()) as T;
}
