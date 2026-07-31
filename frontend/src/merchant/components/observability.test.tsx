import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MessageItem } from './chat/MessageItem';
import { FloatingRunState } from './monitoring/FloatingRunState';
import { DetailSlideOver } from './drawer/DetailSlideOver';

describe('response-scoped observability', () => {
  it('renders backend trace, structured results, and live session/cache state', () => {
    const onOpenDetails = vi.fn();
    const traceEvents = [
      {
        eventId: 'event-context',
        eventType: 'context',
        outputSummary: {
          trace_id: 'tr-live',
          session_state: { merchant_id: '94', pending_hitl: false },
        },
      },
      {
        eventId: 'event-cache',
        eventType: 'cache',
        outputSummary: { status: 'cache miss', cache_key: 'merchant:94' },
      },
      {
        eventId: 'event-tool',
        eventType: 'crewai_tool_finished',
        toolName: 'search_merchants',
        outputSummary: { status: 'ok' },
        durationMs: 120,
      },
    ];

    render(
      <>
        <FloatingRunState sessionId="sess-live" events={traceEvents} isLive />
        <MessageItem
          onOpenDetails={onOpenDetails}
          message={{
            id: 'assistant-1',
            sender: 'assistant',
            content: 'Đã tìm thấy kết quả.',
            timestamp: '10:30',
            traceId: 'tr-live',
            traceEvents,
            analyzedMerchants: [{ merchant_id: '585', name: 'Phở thật từ tool' }],
          }}
        />
      </>,
    );

    expect(screen.getByText('sess-live')).toBeInTheDocument();
    expect(screen.getByText(/cache miss/i)).toBeInTheDocument();
    expect(screen.getByText('CrewAI trace')).toBeInTheDocument();
    expect(screen.getByText('1 kết quả từ backend')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Mở chi tiết run' }));
    expect(onOpenDetails).toHaveBeenCalledOnce();
  });

  it('counts completed business tool and LLM calls instead of lifecycle events', () => {
    render(
      <DetailSlideOver
        merchantId="94"
        onClose={vi.fn()}
        message={{
          id: 'assistant-counts',
          sender: 'assistant',
          content: 'Kết quả',
          timestamp: '10:31',
          traceEvents: [
            { eventType: 'crewai_tool_requested', outputSummary: {} },
            { eventType: 'crewai_tool_finished', outputSummary: {} },
            { eventType: 'tool_started', outputSummary: {} },
            { eventType: 'tool_finished', outputSummary: {} },
            { eventType: 'tool_args_normalized', outputSummary: {} },
            { eventType: 'crewai_llm_started', outputSummary: {} },
            { eventType: 'crewai_llm_finished', outputSummary: {} },
          ],
        }}
      />,
    );

    expect(screen.getByRole('tab', { name: 'Tools 1' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'LLM 1' })).toBeInTheDocument();
  });
});
