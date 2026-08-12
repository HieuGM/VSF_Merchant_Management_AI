import { ApiRequestError, type ApiError } from '../../shared/api-client';
import type { RunTrace, TraceObservation } from '../types/monitoring';

const API_BASE = import.meta.env.VITE_API_BASE ?? '';
const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const text = (value: unknown): string | null => typeof value === 'string' ? value : null;
const number = (value: unknown): number | null => typeof value === 'number' ? value : null;

function parseObservation(value: unknown): TraceObservation {
  const item = record(value);
  return {
    id: text(item.id) ?? '',
    parentId: text(item.parent_id),
    name: text(item.name) ?? 'observation',
    type: text(item.type) ?? 'SPAN',
    status: text(item.status) ?? 'unknown',
    model: text(item.model),
    promptName: text(item.prompt_name),
    promptVersion: number(item.prompt_version),
    startedAt: text(item.started_at),
    finishedAt: text(item.finished_at),
    latencyMs: number(item.latency_ms),
    timeToFirstTokenMs: number(item.time_to_first_token_ms),
    inputTokens: number(item.input_tokens),
    outputTokens: number(item.output_tokens),
    totalTokens: number(item.total_tokens),
    costUsd: number(item.cost_usd),
  };
}

export function parseRunTrace(value: unknown): RunTrace {
  const trace = record(value);
  const totals = record(trace.totals);
  return {
    traceId: text(trace.trace_id) ?? '',
    status: text(trace.status) ?? 'unknown',
    startedAt: text(trace.started_at),
    finishedAt: text(trace.finished_at),
    totals: {
      latencyMs: number(totals.latency_ms),
      inputTokens: number(totals.input_tokens),
      outputTokens: number(totals.output_tokens),
      totalTokens: number(totals.total_tokens),
      totalCostUsd: number(totals.total_cost_usd),
    },
    observations: Array.isArray(trace.observations) ? trace.observations.map(parseObservation) : [],
  };
}

export type TraceFetchResult =
  | { state: 'ready'; trace: RunTrace }
  | { state: 'pending'; retryAfterMs: number };

export async function getRunTrace(traceId: string, signal?: AbortSignal): Promise<TraceFetchResult> {
  const response = await fetch(`${API_BASE}/api/v1/agent/runs/${encodeURIComponent(traceId)}`, { signal });
  if (response.status === 202) {
    const header = response.headers.get('Retry-After');
    const seconds = header === null ? NaN : Number(header);
    return { state: 'pending', retryAfterMs: Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : 3000 };
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const body: ApiError = payload?.error ?? {
      code: 'trace_request_failed',
      message: `HTTP ${response.status}`,
      details: {},
      trace_id: traceId,
    };
    throw new ApiRequestError(response.status, body);
  }
  return { state: 'ready', trace: parseRunTrace(await response.json()) };
}

export async function waitForRunTrace(
  traceId: string,
  signal?: AbortSignal,
  timeoutMs = 45_000,
): Promise<RunTrace> {
  const deadline = Date.now() + timeoutMs;
  while (true) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    const remaining = deadline - Date.now();
    if (remaining <= 0) throw new Error('Trace polling timed out');
    const timeout = new AbortController();
    const timer = window.setTimeout(() => timeout.abort(), remaining);
    const abort = () => timeout.abort();
    signal?.addEventListener('abort', abort, { once: true });
    let result: TraceFetchResult;
    try {
      result = await getRunTrace(traceId, timeout.signal);
    } catch (error) {
      if (!signal?.aborted && timeout.signal.aborted) throw new Error('Trace polling timed out');
      throw error;
    } finally {
      window.clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
    }
    if (result.state === 'ready') return result.trace;
    if (Date.now() + result.retryAfterMs > deadline) throw new Error('Trace polling timed out');
    await new Promise<void>((resolve, reject) => {
      if (signal?.aborted) return reject(new DOMException('Aborted', 'AbortError'));
      const timer = window.setTimeout(resolve, result.retryAfterMs);
      signal?.addEventListener('abort', () => {
        window.clearTimeout(timer);
        reject(new DOMException('Aborted', 'AbortError'));
      }, { once: true });
    });
  }
}
