import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { parseTraceSpanEvent } from '../../api/traceApi';
import { AgentThinkingAccordion } from './AgentThinkingAccordion';

const rawStarted = {
  trace_id: 'tr-ui-1',
  seq: 1,
  span_id: 'tool-hours',
  parent_span_id: 'coordinator-1',
  phase: 'tool',
  kind: 'started',
  actor_type: 'tool',
  actor_name: 'public_hours',
  display: { title: 'Đọc giờ mở cửa', summary: 'Đang lấy giờ hoạt động.', status: 'running' },
  metrics: {},
  debug: { args: { merchant_id: 'masked_abc' } },
};

const rawFinished = {
  ...rawStarted,
  seq: 2,
  kind: 'finished',
  display: { title: 'Đọc giờ mở cửa', summary: 'Đã nhận giờ mở cửa 10:00–22:00', status: 'ok' },
  metrics: { latency_ms: 84, token_usage: { total_tokens: 0 } },
  debug: { result_summary: '10:00–22:00' },
};

describe('AgentThinkingAccordion semantic spans', () => {
  it('updates a running span in place when its finished event arrives', () => {
    const started = parseTraceSpanEvent(rawStarted);
    const finished = parseTraceSpanEvent(rawFinished);
    expect(started).not.toBeNull();
    expect(finished).not.toBeNull();

    render(<AgentThinkingAccordion events={[started!, finished!]} isStreaming />);

    expect(screen.getAllByText('Đọc giờ mở cửa')).toHaveLength(1);
    expect(screen.getByText('Đã nhận giờ mở cửa 10:00–22:00')).toBeInTheDocument();
    expect(screen.getByText('84ms')).toBeInTheDocument();
    expect(screen.queryByText(/result_summary/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /mở trace: đọc giờ mở cửa/i }));
    fireEvent.click(screen.getByRole('button', { name: /hiện debug đã được làm sạch/i }));
    expect(screen.getByText(/result_summary/)).toBeInTheDocument();
  });
});
