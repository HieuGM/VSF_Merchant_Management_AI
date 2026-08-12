import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { AgentThinkingAccordion } from './AgentThinkingAccordion';

const trace = {
  traceId: 'a'.repeat(32), status: 'completed', startedAt: null, finishedAt: null,
  totals: { latencyMs: 1000, inputTokens: 10, outputTokens: 5, totalTokens: 15, totalCostUsd: 0.01 },
  observations: [
    { id: 'root', parentId: null, name: 'merchant-advisor-flow', type: 'AGENT', status: 'completed', model: null, promptName: null, promptVersion: null, startedAt: null, finishedAt: null, latencyMs: 1000, timeToFirstTokenMs: null, inputTokens: 0, outputTokens: 0, totalTokens: 0, costUsd: null },
    { id: 'gen', parentId: 'root', name: 'openai.chat', type: 'GENERATION', status: 'completed', model: 'model-x', promptName: 'gsm_merchant/SYNTHESIS_PROMPT', promptVersion: 3, startedAt: null, finishedAt: null, latencyMs: 800, timeToFirstTokenMs: 200, inputTokens: 10, outputTokens: 5, totalTokens: 15, costUsd: 0.01 },
  ],
};

describe('AgentThinkingAccordion', () => {
  afterEach(cleanup);

  it('renders safe Langfuse hierarchy and metrics', () => {
    render(<AgentThinkingAccordion trace={trace} status="ready" />);
    expect(screen.getByText('merchant-advisor-flow')).toBeInTheDocument();
    expect(screen.getByText(/model-x/)).toBeInTheDocument();
    expect(screen.getAllByText(/15 tokens/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/prompt v3/i)).toBeInTheDocument();
    expect(screen.queryByText(/raw output/i)).not.toBeInTheDocument();
  });

  it('renders unavailable state without hiding its region', () => {
    render(<AgentThinkingAccordion status="unavailable" />);
    expect(screen.getByRole('region', { name: 'AI execution trace' })).toHaveTextContent('Trace unavailable');
  });
});
