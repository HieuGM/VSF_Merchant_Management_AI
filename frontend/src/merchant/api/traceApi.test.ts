import { afterEach, describe, expect, it, vi } from 'vitest';
import { getRunTrace } from './traceApi';

describe('getRunTrace', () => {
  afterEach(() => vi.restoreAllMocks());

  it('normalizes a native CrewAI tool event', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          trace_id: 'tr-1',
          status: 'completed',
          events: [
            {
              event_type: 'crewai_tool_requested',
              tool_name: 'search_merchants',
              output_summary: { args: { city: 'da_nang' } },
              status: 'ok',
            },
          ],
        }),
      }),
    );

    await expect(getRunTrace('tr-1')).resolves.toMatchObject({
      traceId: 'tr-1',
      events: [{ toolName: 'search_merchants', outputSummary: { args: { city: 'da_nang' } } }],
    });
  });
});
