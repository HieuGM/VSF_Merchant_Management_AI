import { afterEach, describe, expect, it, vi } from 'vitest';
import { getRunTrace, parseRunTrace, waitForRunTrace } from './traceApi';

const validTrace = {
  trace_id: 'a'.repeat(32),
  status: 'completed',
  started_at: '2026-08-12T08:00:00Z',
  finished_at: '2026-08-12T08:00:01Z',
  totals: { latency_ms: 1000, input_tokens: 10, output_tokens: 5, total_tokens: 15, total_cost_usd: 0.01 },
  observations: [{ id: 'gen', parent_id: 'root', name: 'openai.chat', type: 'GENERATION', status: 'completed', model: 'model-x', prompt_name: 'gsm_merchant/SYNTHESIS_PROMPT', prompt_version: 3, started_at: '2026-08-12T08:00:00Z', finished_at: '2026-08-12T08:00:01Z', latency_ms: 1000, time_to_first_token_ms: 200, input_tokens: 10, output_tokens: 5, total_tokens: 15, cost_usd: 0.01 }],
};

describe('Langfuse trace API', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('parses the safe observation projection', () => {
    const trace = parseRunTrace(validTrace);
    expect(trace.observations[0].promptVersion).toBe(3);
    expect(trace.totals.totalTokens).toBe(15);
  });

  it('returns pending with Retry-After', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', {
      status: 202,
      headers: { 'Retry-After': '1' },
    })));
    await expect(getRunTrace('a'.repeat(32))).resolves.toEqual({ state: 'pending', retryAfterMs: 1000 });
  });

  it('defaults pending polling to three seconds without Retry-After', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 202 })));
    await expect(getRunTrace('a'.repeat(32))).resolves.toEqual({ state: 'pending', retryAfterMs: 3000 });
  });

  it('rejects immediately when already aborted', async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(waitForRunTrace('a'.repeat(32), controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('polls pending traces until available', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response('{}', { status: 202, headers: { 'Retry-After': '1' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(validTrace), { status: 200 })));
    const promise = waitForRunTrace('a'.repeat(32), undefined, 5000);
    await vi.advanceTimersByTimeAsync(1000);
    await expect(promise).resolves.toMatchObject({ traceId: 'a'.repeat(32) });
  });
});
