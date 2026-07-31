import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { reduceTraceEvents, useMerchantChat } from './useMerchantChat';
import { parseTraceSpanEvent } from '../api/traceApi';

afterEach(() => vi.unstubAllGlobals());

function mockFetchForStream(stream: string) {
  return vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/chat/stream')) {
      return Promise.resolve(
        new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } }),
      );
    }
    if (url.includes('/chat/history')) {
      return Promise.resolve(Response.json({ messages: [] }));
    }
    return Promise.resolve(Response.json({ sessions: [] }));
  });
}

describe('useMerchantChat', () => {
  it('orders semantic spans by sequence and ignores a replay duplicate', () => {
    const later = parseTraceSpanEvent({
      trace_id: 'tr-reduce', seq: 2, span_id: 'tool-1', phase: 'tool', kind: 'finished',
      actor_type: 'tool', actor_name: 'public_hours',
      display: { title: 'Đọc giờ', summary: 'Đã xong', status: 'ok' }, metrics: {}, debug: {},
    });
    const first = parseTraceSpanEvent({
      trace_id: 'tr-reduce', seq: 1, span_id: 'input-1', phase: 'input', kind: 'started',
      actor_type: 'analyzer', actor_name: 'Input Analyzer',
      display: { title: 'Chuẩn bị yêu cầu', summary: 'Đang đọc ngữ cảnh', status: 'running' }, metrics: {}, debug: {},
    });
    expect(later).not.toBeNull();
    expect(first).not.toBeNull();

    const ordered = reduceTraceEvents(reduceTraceEvents([], later!), first!);
    const replayed = reduceTraceEvents(ordered, first!);
    expect(replayed).toHaveLength(2);
    expect(replayed.map((event) => ('seq' in event ? event.seq : null))).toEqual([1, 2]);
  });

  it('attaches competitors emitted in a tool_result payload', async () => {
    const competitors = [{ merchant_id: '585', name: 'Phở Gia Truyền', distance_km: 1.2, cuisine: 'Phở' }];
    const stream = [
      'event: tool_finished',
      `data: ${JSON.stringify({ tool_name: 'compare_competitors', result: { competitors }, duration_ms: 320 })}`,
      '',
      'event: token_chunk',
      `data: ${JSON.stringify({ text: 'Đã tìm thấy đối thủ.' })}`,
      '',
      'event: execution_finish',
      `data: ${JSON.stringify({ trace_id: 'tr_test', token_usage: { total_tokens: 100, prompt_tokens: 80, completion_tokens: 20 } })}`,
      '',
    ].join('\n');
    vi.stubGlobal('fetch', mockFetchForStream(stream));
    const { result } = renderHook(() => useMerchantChat('94'));
    await act(async () => { await result.current.sendMessage('Tìm đối thủ'); });
    await waitFor(() => expect(result.current.messages.find((message) => message.sender === 'assistant')?.competitors).toEqual(competitors));
  });

  it('captures structured plan, privacy policy, evidence and finish telemetry', async () => {
    const stream = [
      'event: plan',
      `data: ${JSON.stringify({
        agent_name: 'merchant_planner',
        rewritten_query: 'Tìm và phân tích quán sushi ở Đà Nẵng',
        capabilities: ['restaurant_search', 'market_cohort_analysis'],
      })}`,
      '',
      'event: policy_decision',
      `data: ${JSON.stringify({
        agent_name: 'merchant_data_policy',
        target_scope: 'competitor_public',
        decision: 'allowed',
      })}`,
      '',
      'event: evidence_validation',
      `data: ${JSON.stringify({
        agent_name: 'evidence_resolver',
        status: 'valid',
        valid_claims: 2,
        rejected_claims: 0,
      })}`,
      '',
      'event: token_chunk',
      `data: ${JSON.stringify({ text: 'Kết quả phân tích.' })}`,
      '',
      'event: execution_finish',
      `data: ${JSON.stringify({
        trace_id: 'tr_structured',
        capabilities: ['restaurant_search', 'market_cohort_analysis'],
        rewritten_query: 'Tìm và phân tích quán sushi ở Đà Nẵng',
        evidence_status: 'valid',
        duration_ms: 1420,
        token_usage: { total_tokens: 100, prompt_tokens: 80, completion_tokens: 20 },
      })}`,
      '',
    ].join('\n');
    vi.stubGlobal('fetch', mockFetchForStream(stream));
    const { result } = renderHook(() => useMerchantChat('94'));

    await act(async () => {
      await result.current.sendMessage('Tìm và phân tích quán sushi');
    });

    const assistant = result.current.messages.find((message) => message.sender === 'assistant');
    expect(assistant?.capabilities).toEqual(['restaurant_search', 'market_cohort_analysis']);
    expect(assistant?.rewrittenQuery).toBe('Tìm và phân tích quán sushi ở Đà Nẵng');
    expect(assistant?.evidenceStatus).toBe('valid');
    expect(assistant?.durationMs).toBe(1420);
    expect(assistant?.telemetryLogs?.map((log) => log.type)).toEqual([
      'plan',
      'policy_decision',
      'evidence_validation',
    ]);
  });

  it('keeps native CrewAI events as a live trace and only finishes on execution_finish', async () => {
    const stream = [
      'event: crewai_agent_started',
      `data: ${JSON.stringify({
        trace_id: 'tr_live',
        agent_name: 'Merchant Advisory Coordinator',
        task: 'advisory_task',
        goal_prompt: 'Coordinate the merchant request.',
      })}`,
      '',
      'event: execution_finish',
      `data: ${JSON.stringify({ trace_id: 'tr_live', status: 'completed' })}`,
      '',
    ].join('\n');
    vi.stubGlobal('fetch', mockFetchForStream(stream));
    const { result } = renderHook(() => useMerchantChat('94'));

    await act(async () => {
      await result.current.sendMessage('Tìm quán sushi ở Đà Nẵng');
    });

    expect(result.current.lastTraceId).toBe('tr_live');
    expect(result.current.liveTraceEvents).toEqual(expect.arrayContaining([
      expect.objectContaining({
        eventType: 'crewai_agent_started',
        agentName: 'Merchant Advisory Coordinator',
        taskName: 'advisory_task',
      }),
    ]));
    const assistant = result.current.messages.find((message) => message.sender === 'assistant');
    expect(assistant?.traceId).toBe('tr_live');
    expect(assistant?.traceEvents?.map((event) => event.eventType)).toEqual([
      'crewai_agent_started',
      'execution_finish',
    ]);
    expect(assistant?.isStreaming).toBe(false);
  });

  it('keeps directly received trace spans without requesting a persistence replay', async () => {
    const firstSpan = {
      trace_id: 'tr-disconnect', seq: 1, span_id: 'input-1', phase: 'input', kind: 'started',
      actor_type: 'analyzer', actor_name: 'Input Analyzer',
      display: { title: 'Chuẩn bị yêu cầu', summary: 'Đang đọc ngữ cảnh', status: 'running' }, metrics: {}, debug: {},
    };
    const stream = ['event: trace_span', `data: ${JSON.stringify(firstSpan)}`, ''].join('\n');
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/chat/stream')) return Promise.resolve(new Response(stream));
      if (url.includes('/chat/history')) return Promise.resolve(Response.json({ messages: [] }));
      return Promise.resolve(Response.json({ sessions: [] }));
    });
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useMerchantChat('94'));

    await act(async () => { await result.current.sendMessage('Quán này mở lúc nào?'); });

    await waitFor(() => expect(result.current.liveTraceEvents.map((event) => ('seq' in event ? event.seq : null))).toEqual([1]));
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/events?after_seq='))).toBe(false);
    expect(result.current.messages.find((message) => message.sender === 'assistant')?.isError).toBe(true);
  });

  it('keeps a completed response when the reader fails after execution_finish', async () => {
    const stream = [
      'event: execution_finish',
      `data: ${JSON.stringify({ trace_id: 'tr-terminal', status: 'completed' })}`,
      '',
    ].join('\n');
    const reader = {
      read: vi.fn()
        .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode(stream) })
        .mockRejectedValueOnce(new Error('connection closed after terminal event')),
    };
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/chat/stream')) {
        return Promise.resolve({ ok: true, status: 200, body: { getReader: () => reader } } as unknown as Response);
      }
      if (url.includes('/chat/history')) return Promise.resolve(Response.json({ messages: [] }));
      return Promise.resolve(Response.json({ sessions: [] }));
    });
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useMerchantChat('94'));

    await act(async () => { await result.current.sendMessage('Đã xong chưa?'); });

    const assistant = result.current.messages.find((message) => message.sender === 'assistant');
    expect(assistant?.runStatus).toBe('completed');
    expect(assistant?.isError).toBeFalsy();
    expect(assistant?.isStreaming).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/events?after_seq='))).toBe(false);
    errorSpy.mockRestore();
  });
});
