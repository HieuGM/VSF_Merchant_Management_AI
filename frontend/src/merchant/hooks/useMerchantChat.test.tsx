import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useMerchantChat } from './useMerchantChat';

afterEach(() => vi.unstubAllGlobals());

function fetchForStream(stream: string, trace?: object) {
  return vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/chat/stream')) return Promise.resolve(new Response(stream));
    if (url.includes('/chat/history')) return Promise.resolve(Response.json({ messages: [] }));
    if (url.includes('/agent/runs/')) return Promise.resolve(Response.json(trace));
    return Promise.resolve(Response.json({ sessions: [] }));
  });
}

describe('useMerchantChat', () => {
  it('keeps only terminal business data and hydrates Langfuse trace', async () => {
    const traceId = 'a'.repeat(32);
    const merchants = [{ merchant_id: '585', name: 'Pho Gia Truyen' }];
    const stream = [
      'event: token_chunk', `data: ${JSON.stringify({ text: 'Ket qua.' })}`, '',
      'event: execution_finish', `data: ${JSON.stringify({ trace_id: traceId, status: 'COMPLETED', merchants })}`, '',
    ].join('\n');
    const trace = { trace_id: traceId, status: 'completed', totals: {}, observations: [] };
    vi.stubGlobal('fetch', fetchForStream(stream, trace));
    const { result } = renderHook(() => useMerchantChat('94'));

    await act(async () => { await result.current.sendMessage('Tim quan'); });

    await waitFor(() => expect(result.current.messages.find((message) => message.sender === 'assistant')?.traceStatus).toBe('ready'));
    const assistant = result.current.messages.find((message) => message.sender === 'assistant');
    expect(assistant?.content).toBe('Ket qua.');
    expect(assistant?.analyzedMerchants).toEqual(merchants);
    expect(assistant?.trace?.traceId).toBe(traceId);
  });

  it('keeps a completed answer when trace hydration fails', async () => {
    const traceId = 'b'.repeat(32);
    const stream = ['event: token_chunk', 'data: {"text":"Done"}', '', 'event: execution_finish', `data: {"trace_id":"${traceId}","status":"COMPLETED"}`, ''].join('\n');
    const fetchMock = fetchForStream(stream);
    fetchMock.mockImplementation((input: RequestInfo | URL) => String(input).includes('/agent/runs/')
      ? Promise.resolve(new Response('{}', { status: 502 }))
      : String(input).includes('/chat/stream')
        ? Promise.resolve(new Response(stream))
        : Promise.resolve(Response.json(String(input).includes('/history') ? { messages: [] } : { sessions: [] })));
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useMerchantChat('94'));
    await act(async () => { await result.current.sendMessage('Go'); });
    await waitFor(() => expect(result.current.messages.find((message) => message.sender === 'assistant')?.traceStatus).toBe('unavailable'));
    expect(result.current.messages.find((message) => message.sender === 'assistant')?.content).toBe('Done');
  });
});
