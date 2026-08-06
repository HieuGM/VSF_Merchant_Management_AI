import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { parseTraceSpanEvent } from '../../api/traceApi';
import { AgentThinkingAccordion } from './AgentThinkingAccordion';

afterEach(cleanup);

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

    fireEvent.click(screen.getByRole('button', { name: /open tool: đọc giờ mở cửa/i }));
    fireEvent.click(screen.getByRole('button', { name: /view technical details/i }));
    expect(screen.getByText(/result_summary/)).toBeInTheDocument();
  });

  it('shows tool arguments and output only after expanding the tool row', () => {
    const tool = parseTraceSpanEvent({
      ...rawFinished,
      debug: {
        args: { query: 'phí nền tảng', top_k: 5 },
        result: { status: 'ok', count: 2 },
      },
    });

    const view = render(<AgentThinkingAccordion events={[tool!]} />);
    const timeline = within(view.container);
    expect(timeline.queryByText(/phí nền tảng/)).not.toBeInTheDocument();

    fireEvent.click(timeline.getByRole('button', { name: /open tool: đọc giờ mở cửa/i }));
    expect(timeline.getByText('Arguments')).toBeInTheDocument();
    expect(timeline.getByText('Output')).toBeInTheDocument();
    expect(timeline.getByText(/phí nền tảng/)).toBeInTheDocument();
    expect(timeline.getByText(/"count": 2/)).toBeInTheDocument();
  });

  it('builds request facts and execution waves only from emitted plan metadata', () => {
    const event = (value: Record<string, unknown>) => parseTraceSpanEvent({
      trace_id: 'tr-plan',
      kind: 'finished',
      actor_type: 'system',
      display: { title: 'Step', summary: 'Completed.', status: 'ok' },
      metrics: {},
      debug: {},
      ...value,
    })!;
    const events = [
      event({
        seq: 1,
        span_id: 'input-1',
        phase: 'input',
        actor_type: 'analyzer',
        actor_name: 'input_analyzer',
        display: { title: 'Hiểu yêu cầu người dùng', summary: 'Owner diagnosis requested.', status: 'ok' },
        debug: { rewritten_query: 'Diagnose my store and recommend actions', scope_candidate: 'owner_private' },
      }),
      event({
        seq: 2,
        span_id: 'policy-1',
        phase: 'route',
        actor_name: 'merchant_data_policy',
        debug: { allowed: true, scope: 'owner_private' },
      }),
      event({
        seq: 3,
        span_id: 'route-1',
        phase: 'route',
        actor_name: 'input_router',
        debug: { outcome: 'delegate_owner_analysis' },
      }),
      event({
        seq: 4,
        span_id: 'plan-1',
        phase: 'coordinator',
        actor_type: 'coordinator',
        actor_name: 'coordinator',
        debug: { tasks: ['self_analysis', 'evidence_verifier', 'final_synthesis'] },
      }),
      event({
        seq: 5,
        span_id: 'agent-1',
        phase: 'agent',
        actor_type: 'agent',
        actor_name: 'self_analysis',
        display: { title: 'Owner Performance Analysis Specialist', summary: 'Found two priority actions.', status: 'ok' },
      }),
      event({
        seq: 6,
        span_id: 'verify-1',
        phase: 'agent',
        actor_type: 'agent',
        actor_name: 'evidence_verifier',
        display: { title: 'Evidence and Policy Verifier', summary: 'Evidence references verified.', status: 'ok' },
      }),
      event({
        seq: 7,
        span_id: 'synthesis-1',
        phase: 'synthesis',
        actor_type: 'agent',
        actor_name: 'final_synthesis',
        display: { title: 'Merchant Owner Answer Specialist', summary: 'Answer assembled.', status: 'ok' },
      }),
    ];

    render(<AgentThinkingAccordion events={events} />);

    expect(screen.getByText('Understand request')).toBeInTheDocument();
    expect(screen.getByText('Diagnose my store and recommend actions')).toBeInTheDocument();
    expect(screen.getByText('Owner-private data')).toBeInTheDocument();
    expect(screen.getByText('Build execution plan')).toBeInTheDocument();
    expect(screen.getByText('Wave 1')).toBeInTheDocument();
    expect(screen.getByText('Wave 2')).toBeInTheDocument();
    expect(screen.getByText('Wave 3')).toBeInTheDocument();
    expect(screen.getAllByText('Owner Performance Analysis Specialist')).toHaveLength(2);
    expect(screen.getAllByText('Evidence and Policy Verifier')).toHaveLength(2);
  });

  it('renders policy retrieval results as source-linked evidence cards', () => {
    const tool = parseTraceSpanEvent({
      ...rawFinished,
      span_id: 'policy-tool',
      actor_name: 'search_policy_documents',
      display: { title: 'Tool call: search_policy_documents', summary: 'Found one policy chunk.', status: 'ok' },
      debug: {
        args: { query: 'platform fee', categories: ['fees'], top_k: 5 },
        gateway_agent_name: 'policy_rag',
        result: JSON.stringify({
          status: 'ok',
          count: 1,
          results: [{
            chunk_id: 'chunk-fee-1',
            document_id: 'policy-fees',
            title: 'Merchant Platform Fee Policy',
            source_url: 'https://example.com/policies/fees',
            category: 'fees',
            policy_updated_at: '2026-07-20T00:00:00Z',
            section_path: ['Fees', 'Commission'],
            text: 'The platform fee depends on the active merchant agreement.',
            relevance: 0.93,
          }],
        }),
      },
    });

    render(<AgentThinkingAccordion events={[tool!]} />);
    expect(screen.getByText('Policy Knowledge Specialist')).toBeInTheDocument();
    expect(screen.queryByText('Merchant Platform Fee Policy')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /open tool: tool call: search_policy_documents/i }));

    expect(screen.getByText('Retrieved policy evidence (1)')).toBeInTheDocument();
    expect(screen.getByText('Merchant Platform Fee Policy')).toBeInTheDocument();
    expect(screen.getByText('93% match')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open source' })).toHaveAttribute('href', 'https://example.com/policies/fees');
  });

  it('shows authoritative total latency and token usage at the end', () => {
    render(
      <AgentThinkingAccordion
        events={[parseTraceSpanEvent(rawFinished)!]}
        durationMs={1420}
        tokenUsage={{ total_tokens: 1350, prompt_tokens: 1100, completion_tokens: 250 }}
      />,
    );

    const totals = within(screen.getByRole('contentinfo', { name: 'Execution totals' }));
    expect(totals.getByText('Execution complete')).toBeInTheDocument();
    expect(totals.getByText('Total latency')).toBeInTheDocument();
    expect(totals.getByText('1.4s')).toBeInTheDocument();
    expect(totals.getByText('Total token usage')).toBeInTheDocument();
    expect(totals.getByText('1,350')).toBeInTheDocument();
    expect(totals.getByText('1,100 input · 250 output')).toBeInTheDocument();
  });

  it('recovers totals from a persisted query summary', () => {
    const view = render(<AgentThinkingAccordion events={[{
      eventType: 'query_summary',
      outputSummary: {
        duration_ms: 950,
        token_usage: { total_tokens: 420, prompt_tokens: 300, completion_tokens: 120 },
      },
      durationMs: 950,
      status: 'completed',
    }]} />);

    const totals = within(within(view.container).getByRole('contentinfo', { name: 'Execution totals' }));
    expect(totals.getByText('950ms')).toBeInTheDocument();
    expect(totals.getByText('420')).toBeInTheDocument();
  });
});
