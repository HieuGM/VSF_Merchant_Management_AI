import { useMemo, useState } from 'react';
import type { JsonRecord, TraceEvent, TraceSpanEvent } from '../../types/monitoring';
import { isTraceSpanEvent } from '../../types/monitoring';

const LABELS: Record<string, string> = {
  context: 'Intent classifying',
  policy_decision: 'Policy check',
  crewai_agent_started: 'Agent started',
  crewai_agent_finished: 'Agent finished',
  crewai_tool_started: 'Tool started',
  crewai_tool_finished: 'Tool finished',
  tool_call: 'Tool call',
  tool_result: 'Tool result',
  cache: 'Cache query',
  sql_query: 'Database query',
  synthesis: 'Synthesis',
  execution_finish: 'Completed',
  error: 'Error',
  agent_error: 'Agent error',
};

const ACTOR_LABELS: Record<string, string> = {
  coordinator: 'Merchant Advisor Coordinator',
  evidence_verifier: 'Evidence and Policy Verifier',
  final_synthesis: 'Merchant Owner Answer Specialist',
  market_search: 'Public Market Search Specialist',
  policy_rag: 'Policy Knowledge Specialist',
  policy_specialist: 'Policy Knowledge Specialist',
  self_analysis: 'Owner Performance Analysis Specialist',
};

const SCOPE_LABELS: Record<string, string> = {
  allowed: 'Allowed merchant scope',
  competitor_private: 'Private competitor data',
  competitor_public: 'Public merchant data',
  owner_private: 'Owner-private data',
};

interface RenderSpan {
  spanId: string;
  parentSpanId?: string | null;
  firstSeq: number;
  latest: TraceSpanEvent;
  metrics: JsonRecord;
  debug: JsonRecord;
  children: RenderSpan[];
}

interface ExecutionStage {
  id: string;
  actorName: string;
  title: string;
  firstSeq: number;
  span?: RenderSpan;
  tools: RenderSpan[];
}

interface PlanTask {
  id: string;
  actorName: string;
  title: string;
  wave: number;
}

interface PolicyChunk {
  chunkId: string;
  title: string;
  sourceUrl: string | null;
  category: string;
  policyUpdatedAt: string | null;
  sectionPath: string[];
  text: string;
  relevance: number | null;
}

interface TraceTotalsValue {
  latencyMs: number | null;
  totalTokens: number | null;
  promptTokens: number | null;
  completionTokens: number | null;
}

interface TokenUsageValue {
  total_tokens?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  totalTokens?: number;
  promptTokens?: number;
  completionTokens?: number;
}

type VisualStatus = 'complete' | 'running' | 'failed' | 'pending';

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as JsonRecord : {};
}

function asText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function humanize(value: string) {
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase());
}

function actorLabel(actorName: string) {
  return ACTOR_LABELS[actorName] ?? humanize(actorName);
}

function eventDetail(event: TraceEvent) {
  const payload = event.outputSummary;
  return String(
    payload.detail
      ?? payload.task
      ?? payload.question
      ?? payload.error_message
      ?? event.taskName
      ?? event.toolName
      ?? event.agentName
      ?? '',
  );
}

function isCyclicParent(candidate: RenderSpan, parentId: string, spans: Map<string, RenderSpan>) {
  const visited = new Set<string>([candidate.spanId]);
  let cursor: string | null | undefined = parentId;
  while (cursor) {
    if (visited.has(cursor)) return true;
    visited.add(cursor);
    cursor = spans.get(cursor)?.parentSpanId;
  }
  return false;
}

function collapseSemanticSpans(events: TraceEvent[]) {
  const spans = new Map<string, RenderSpan>();
  const semantic = events
    .filter(isTraceSpanEvent)
    .filter((event) => !['Gọi LLM', 'LLM response'].includes(event.display.title))
    .sort((left, right) => left.seq - right.seq);

  for (const event of semantic) {
    const current = spans.get(event.spanId);
    if (!current) {
      spans.set(event.spanId, {
        spanId: event.spanId,
        parentSpanId: event.parentSpanId,
        firstSeq: event.seq,
        latest: event,
        metrics: { ...event.metrics },
        debug: { ...event.debug },
        children: [],
      });
      continue;
    }
    current.latest = event;
    current.parentSpanId = event.parentSpanId ?? current.parentSpanId;
    current.metrics = { ...current.metrics, ...event.metrics };
    current.debug = { ...current.debug, ...event.debug };
  }
  return spans;
}

/** Retained for consumers that need the raw semantic parent tree. */
export function buildSemanticSpanTree(events: TraceEvent[]): RenderSpan[] {
  const spans = collapseSemanticSpans(events);
  const roots: RenderSpan[] = [];
  for (const span of spans.values()) {
    const parent = span.parentSpanId ? spans.get(span.parentSpanId) : undefined;
    if (!parent || parent.spanId === span.spanId || isCyclicParent(span, parent.spanId, spans)) {
      roots.push(span);
    } else {
      parent.children.push(span);
    }
  }
  const sort = (items: RenderSpan[]) => {
    items.sort((left, right) => left.firstSeq - right.firstSeq);
    items.forEach((item) => sort(item.children));
  };
  sort(roots);
  return roots;
}

function latencyText(metrics: JsonRecord) {
  const latency = metrics.latency_ms ?? metrics.latencyMs;
  if (typeof latency !== 'number') return null;
  return latency >= 1000 ? `${(latency / 1000).toFixed(1)}s` : `${Math.round(latency)}ms`;
}

function tokenText(metrics: JsonRecord) {
  const usage = metrics.token_usage ?? metrics.tokenUsage;
  if (!usage || typeof usage !== 'object' || Array.isArray(usage)) return null;
  const tokens = usage as JsonRecord;
  const total = tokens.total_tokens ?? tokens.totalTokens;
  return typeof total === 'number' && total > 0 ? `${total} tokens` : null;
}

function spanStatus(span: RenderSpan | undefined, isStreaming: boolean): VisualStatus {
  if (!span) return 'pending';
  if (span.latest.kind === 'failed' || span.latest.kind === 'cancelled') return 'failed';
  if (span.latest.kind === 'started') return isStreaming ? 'running' : 'pending';
  return 'complete';
}

function executionStageStatus(stage: ExecutionStage | undefined, isStreaming: boolean): VisualStatus {
  if (!stage) return 'pending';
  if (stage.span) return spanStatus(stage.span, isStreaming);
  if (stage.tools.some((tool) => spanStatus(tool, isStreaming) === 'failed')) return 'failed';
  if (stage.tools.some((tool) => spanStatus(tool, isStreaming) === 'running')) return 'running';
  return stage.tools.length > 0 ? 'complete' : 'pending';
}

function statusLabel(status: VisualStatus) {
  if (status === 'complete') return 'Completed';
  if (status === 'running') return 'Running';
  if (status === 'failed') return 'Failed';
  return 'Waiting';
}

function StatusNode({ status }: { status: VisualStatus }) {
  return (
    <span className={`trace-node is-${status}`} aria-hidden="true">
      {status === 'complete' ? '✓' : status === 'failed' ? '!' : status === 'pending' ? '·' : ''}
    </span>
  );
}

function readPlanTasks(spans: RenderSpan[]): PlanTask[] {
  const coordinator = spans.find((span) => span.latest.phase === 'coordinator' && Array.isArray(span.debug.tasks));
  if (coordinator) {
    return (coordinator.debug.tasks as unknown[]).flatMap((item, index) => {
      if (typeof item === 'string' && item) {
        return [{ id: `${coordinator.spanId}-${item}-${index}`, actorName: item, title: actorLabel(item), wave: index + 1 }];
      }
      const task = asRecord(item);
      const actorName = asText(task.agent_name) ?? asText(task.actor_name) ?? asText(task.id) ?? asText(task.name);
      if (!actorName) return [];
      const explicitWave = task.wave;
      return [{
        id: `${coordinator.spanId}-${actorName}-${index}`,
        actorName,
        title: asText(task.title) ?? actorLabel(actorName),
        wave: typeof explicitWave === 'number' && explicitWave > 0 ? explicitWave : index + 1,
      }];
    });
  }

  const selected = spans.find((span) => (
    span.latest.phase === 'coordinator'
    && typeof span.debug.agent_name === 'string'
    && span.debug.agent_name !== 'coordinator'
  ));
  const actorName = selected ? asText(selected.debug.agent_name) : null;
  return actorName ? [{ id: `${selected!.spanId}-${actorName}`, actorName, title: actorLabel(actorName), wave: 1 }] : [];
}

function toolOwner(span: RenderSpan, agentsById: Map<string, RenderSpan>) {
  if (span.parentSpanId && agentsById.has(span.parentSpanId)) return agentsById.get(span.parentSpanId)!.latest.actorName;
  return asText(span.debug.gateway_agent_name)
    ?? asText(span.debug.sdk_agent_name)
    ?? asText(span.debug.crewai_agent_name);
}

function buildExecutionStages(spans: RenderSpan[]): ExecutionStage[] {
  const agentSpans = spans.filter((span) => ['agent', 'synthesis'].includes(span.latest.phase));
  const tools = spans.filter((span) => span.latest.phase === 'tool');
  const agentsById = new Map(agentSpans.map((span) => [span.spanId, span]));
  const stages: ExecutionStage[] = agentSpans.map((span) => ({
    id: span.spanId,
    actorName: span.latest.actorName,
    title: span.latest.display.title.startsWith('Agent:') ? actorLabel(span.latest.actorName) : span.latest.display.title,
    firstSeq: span.firstSeq,
    span,
    tools: [],
  }));

  for (const tool of tools) {
    const owner = toolOwner(tool, agentsById);
    const parentStage = tool.parentSpanId ? stages.find((stage) => stage.id === tool.parentSpanId) : undefined;
    const actorStage = owner ? stages.find((stage) => stage.actorName === owner) : undefined;
    const stage = parentStage ?? actorStage;
    if (stage) {
      stage.tools.push(tool);
      continue;
    }
    stages.push({
      id: `tools-${owner ?? tool.spanId}`,
      actorName: owner ?? 'tool',
      title: owner ? actorLabel(owner) : 'Tool execution',
      firstSeq: tool.firstSeq,
      tools: [tool],
    });
  }

  stages.forEach((stage) => stage.tools.sort((left, right) => left.firstSeq - right.firstSeq));
  return stages.sort((left, right) => left.firstSeq - right.firstSeq);
}

function parseJsonValue(value: unknown): unknown {
  if (typeof value !== 'string') return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function policyChunks(value: unknown): PolicyChunk[] {
  const result = asRecord(parseJsonValue(value));
  if (!Array.isArray(result.results)) return [];
  return result.results.flatMap((item) => {
    const chunk = asRecord(item);
    const chunkId = asText(chunk.chunk_id) ?? asText(chunk.chunkId);
    const title = asText(chunk.title);
    const text = asText(chunk.text);
    if (!chunkId || !title || !text) return [];
    const sectionPath = Array.isArray(chunk.section_path)
      ? chunk.section_path.filter((part): part is string => typeof part === 'string')
      : [];
    const relevance = chunk.relevance;
    return [{
      chunkId,
      title,
      sourceUrl: asText(chunk.source_url) ?? asText(chunk.sourceUrl),
      category: asText(chunk.category) ?? 'Policy',
      policyUpdatedAt: asText(chunk.policy_updated_at) ?? asText(chunk.policyUpdatedAt),
      sectionPath,
      text,
      relevance: typeof relevance === 'number' ? relevance : null,
    }];
  });
}

function safeSourceUrl(value: string | null) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.toString() : null;
  } catch {
    return null;
  }
}

function numericValue(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function readTraceTotals(
  events: TraceEvent[],
  durationMs?: number,
  tokenUsage?: TokenUsageValue,
): TraceTotalsValue | null {
  const terminal = [...events].reverse().find((event) => ['execution_finish', 'query_summary'].includes(event.eventType));
  const terminalUsage = asRecord(terminal?.outputSummary.token_usage ?? terminal?.outputSummary.tokenUsage);
  const usage: JsonRecord = tokenUsage && Object.keys(tokenUsage).length > 0 ? { ...tokenUsage } : terminalUsage;
  const latencyMs = numericValue(durationMs)
    ?? numericValue(terminal?.durationMs)
    ?? numericValue(terminal?.outputSummary.duration_ms)
    ?? numericValue(terminal?.outputSummary.durationMs);
  const totalTokens = numericValue(usage.total_tokens) ?? numericValue(usage.totalTokens);
  const promptTokens = numericValue(usage.prompt_tokens) ?? numericValue(usage.promptTokens);
  const completionTokens = numericValue(usage.completion_tokens) ?? numericValue(usage.completionTokens);
  return latencyMs != null || totalTokens != null
    ? { latencyMs, totalTokens, promptTokens, completionTokens }
    : null;
}

function formatTotalLatency(latencyMs: number) {
  if (latencyMs < 1000) return `${Math.round(latencyMs)}ms`;
  return `${(latencyMs / 1000).toFixed(1)}s`;
}

function TraceTotals({ totals }: { totals: TraceTotalsValue | null }) {
  if (!totals) return null;
  return (
    <footer className="trace-totals" aria-label="Execution totals">
      <div className="trace-totals__title"><StatusNode status="complete" /><strong>Execution complete</strong></div>
      <dl>
        {totals.latencyMs != null && <div><dt>Total latency</dt><dd>{formatTotalLatency(totals.latencyMs)}</dd></div>}
        {totals.totalTokens != null && (
          <div>
            <dt>Total token usage</dt>
            <dd>{Math.round(totals.totalTokens).toLocaleString()}</dd>
            {(totals.promptTokens != null || totals.completionTokens != null) && (
              <small>{Math.round(totals.promptTokens ?? 0).toLocaleString()} input · {Math.round(totals.completionTokens ?? 0).toLocaleString()} output</small>
            )}
          </div>
        )}
      </dl>
    </footer>
  );
}

function PolicyResults({ chunks }: { chunks: PolicyChunk[] }) {
  if (chunks.length === 0) return null;
  return (
    <div className="trace-policy-results" aria-label="Retrieved policy evidence">
      <div className="trace-detail-label">Retrieved policy evidence ({chunks.length})</div>
      {chunks.map((chunk) => {
        const sourceUrl = safeSourceUrl(chunk.sourceUrl);
        return (
          <article className="trace-policy-chunk" key={chunk.chunkId}>
            <div className="trace-policy-chunk__header">
              <strong>{chunk.title}</strong>
              {chunk.relevance != null && <span>{Math.round(chunk.relevance * 100)}% match</span>}
            </div>
            <div className="trace-policy-chunk__meta">
              <span>{chunk.category}</span>
              {chunk.sectionPath.length > 0 && <span>{chunk.sectionPath.join(' / ')}</span>}
              {chunk.policyUpdatedAt && <span>Updated {chunk.policyUpdatedAt.slice(0, 10)}</span>}
            </div>
            <p>{chunk.text}</p>
            {sourceUrl && <a href={sourceUrl} target="_blank" rel="noreferrer">Open source</a>}
          </article>
        );
      })}
    </div>
  );
}

function ToolRow({ span, isStreaming }: { span: RenderSpan; isStreaming: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const [rawOpen, setRawOpen] = useState(false);
  const args = span.debug.args;
  const result = span.debug.result;
  const chunks = policyChunks(result);
  const status = spanStatus(span, isStreaming);
  const toolMeta = Object.fromEntries(Object.entries(span.debug).filter(([key]) => !['args', 'result'].includes(key)));

  return (
    <li className="trace-tool">
      <button
        type="button"
        className={`trace-tool__button ${expanded ? 'is-open' : ''}`}
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        aria-label={`${expanded ? 'Close' : 'Open'} tool: ${span.latest.display.title}`}
      >
        <StatusNode status={status} />
        <span className="trace-row__copy">
          <strong className="trace-row-title">{span.latest.display.title}</strong>
          <span className="trace-row-desc">{span.latest.display.summary}</span>
        </span>
        <span className="trace-row-right">
          {latencyText(span.metrics) && <span className="trace-row-time">{latencyText(span.metrics)}</span>}
          <span className="trace-chevron" aria-hidden="true">{expanded ? '−' : '+'}</span>
        </span>
      </button>
      {expanded && (
        <div className="trace-tool__details">
          {args !== undefined && <><div className="trace-detail-label">Arguments</div><pre className="json-code-box">{JSON.stringify(args, null, 2)}</pre></>}
          <PolicyResults chunks={chunks} />
          {result !== undefined && chunks.length === 0 && <><div className="trace-detail-label">Output</div><pre className="json-code-box">{JSON.stringify(parseJsonValue(result), null, 2)}</pre></>}
          {Object.keys(toolMeta).length > 0 && (
            <>
              <button type="button" className="trace-raw-toggle" onClick={() => setRawOpen((value) => !value)} aria-expanded={rawOpen}>
                {rawOpen ? 'Hide technical details' : 'View technical details'}
              </button>
              {rawOpen && <pre className="json-code-box">{JSON.stringify(toolMeta, null, 2)}</pre>}
            </>
          )}
        </div>
      )}
    </li>
  );
}

function RequestStage({ spans, step, isStreaming }: { spans: RenderSpan[]; step: number; isStreaming: boolean }) {
  const input = spans.find((span) => span.latest.phase === 'input');
  const policy = spans.find((span) => span.latest.actorName === 'merchant_data_policy');
  const route = spans.find((span) => span.latest.actorName === 'input_router');
  const policyTool = spans.find((span) => span.latest.phase === 'tool' && span.latest.actorName === 'search_policy_documents');
  const policyArgs = asRecord(policyTool?.debug.args);
  const policyTopics = Array.isArray(policyArgs.categories)
    ? policyArgs.categories.filter((item): item is string => typeof item === 'string')
    : [];
  if (!input && !policy && !route) return null;
  const query = asText(input?.debug.rewritten_query) ?? asText(route?.debug.rewritten_query);
  const scope = asText(policy?.debug.scope) ?? asText(input?.debug.scope_candidate) ?? asText(route?.debug.scope_candidate);
  const missing = Array.isArray(input?.debug.missing_context)
    ? input.debug.missing_context.filter((item): item is string => typeof item === 'string')
    : [];
  const failed = policy?.debug.allowed === false || policy?.latest.kind === 'failed' || route?.latest.kind === 'failed';
  const running = isStreaming && [input, policy, route].some((span) => span?.latest.kind === 'started');
  const status: VisualStatus = failed ? 'failed' : running ? 'running' : 'complete';

  return (
    <li className="trace-stage trace-stage--request">
      <div className="trace-stage__rail"><span className="trace-step-number">{step}</span></div>
      <div className="trace-stage__content">
        <div className="trace-stage__heading">
          <div><strong>Understand request</strong><span>{input?.latest.display.summary ?? route?.latest.display.summary}</span></div>
          <span className={`trace-status is-${status}`}>{statusLabel(status)}</span>
        </div>
        <dl className="trace-fact-grid">
          {query && <div><dt>Interpreted request</dt><dd>{query}</dd></div>}
          {scope && <div><dt>Data scope</dt><dd>{SCOPE_LABELS[scope] ?? humanize(scope)}</dd></div>}
          {policy && <div><dt>Access guardrail</dt><dd>{policy.debug.allowed === false ? 'Denied' : 'Allowed'}</dd></div>}
          {route && <div><dt>Route</dt><dd>{humanize(asText(route.debug.outcome) ?? route.latest.display.status)}</dd></div>}
          {policyTool && <div><dt>Policy context</dt><dd>Retrieved from policy documents</dd></div>}
          {policyTopics.length > 0 && <div><dt>Policy topics</dt><dd>{policyTopics.join(', ')}</dd></div>}
          {missing.length > 0 && <div><dt>Missing context</dt><dd>{missing.join(', ')}</dd></div>}
        </dl>
      </div>
    </li>
  );
}

function PlanStage({ tasks, stages, step, isStreaming }: { tasks: PlanTask[]; stages: ExecutionStage[]; step: number; isStreaming: boolean }) {
  if (tasks.length === 0) return null;
  const waves = [...new Set(tasks.map((task) => task.wave))].sort((left, right) => left - right);
  return (
    <li className="trace-stage trace-stage--plan">
      <div className="trace-stage__rail"><span className="trace-step-number">{step}</span></div>
      <div className="trace-stage__content">
        <div className="trace-stage__heading">
          <div><strong>Build execution plan</strong><span>{waves.length} {waves.length === 1 ? 'wave' : 'waves'} · {tasks.length} specialist {tasks.length === 1 ? 'task' : 'tasks'}</span></div>
          <span className="trace-status is-complete">Planned</span>
        </div>
        <div className="trace-waves">
          {waves.map((wave) => (
            <div className="trace-wave" key={wave}>
              <span className="trace-wave__label">Wave {wave}</span>
              <div className="trace-wave__tasks">
                {tasks.filter((task) => task.wave === wave).map((task) => {
                  const stage = stages.find((candidate) => candidate.actorName === task.actorName);
                  const status = executionStageStatus(stage, isStreaming);
                  return <span className={`trace-plan-task is-${status}`} key={task.id}><StatusNode status={status} />{task.title}</span>;
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </li>
  );
}

function AgentStage({ stage, step, isStreaming }: { stage: ExecutionStage; step: number; isStreaming: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const status = executionStageStatus(stage, isStreaming);
  const summary = stage.span?.latest.display.summary ?? `${stage.tools.length} tool ${stage.tools.length === 1 ? 'call' : 'calls'} observed.`;
  const hasTechnicalDetails = stage.span && Object.keys(stage.span.debug).length > 0;
  const heading = (
    <>
      <StatusNode status={status} />
      <div><strong>{stage.title}</strong><span>{summary}</span></div>
      <span className="trace-agent-badge">{stage.actorName === 'tool' ? 'Tool' : 'Agent'}</span>
      <span className="trace-row-right">
        {stage.span && latencyText(stage.span.metrics) && <span className="trace-row-time">{latencyText(stage.span.metrics)}</span>}
        {stage.span && tokenText(stage.span.metrics) && <span className="trace-row-time">{tokenText(stage.span.metrics)}</span>}
        {hasTechnicalDetails && <span className="trace-chevron" aria-hidden="true">{expanded ? '−' : '+'}</span>}
      </span>
    </>
  );

  return (
    <li className="trace-stage trace-stage--agent">
      <div className="trace-stage__rail"><span className="trace-step-number">{step}</span></div>
      <div className="trace-stage__content">
        {hasTechnicalDetails ? (
          <button
            type="button"
            className="trace-stage__heading trace-stage__heading--button"
            onClick={() => setExpanded((value) => !value)}
            aria-expanded={expanded}
            aria-label={`${expanded ? 'Close' : 'Open'} agent: ${stage.title}`}
          >
            {heading}
          </button>
        ) : <div className="trace-stage__heading trace-stage__heading--static">{heading}</div>}
        {expanded && hasTechnicalDetails && <pre className="json-code-box trace-agent-debug">{JSON.stringify(stage.span!.debug, null, 2)}</pre>}
        {stage.tools.length > 0 && <ol className="trace-tools">{stage.tools.map((tool) => <ToolRow key={tool.spanId} span={tool} isStreaming={isStreaming} />)}</ol>}
      </div>
    </li>
  );
}

function LegacyRow({ event, index, isStreaming }: { event: TraceEvent; index: number; isStreaming: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const failed = event.eventType.includes('error') || event.status === 'failed';
  const running = isStreaming && index === 0;
  const duration = event.durationMs != null ? `${(event.durationMs / 1000).toFixed(1)}s` : null;
  return (
    <li className="trace-row-container">
      <button type="button" className={`trace-row ${expanded ? 'is-open' : ''}`} onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
        <StatusNode status={failed ? 'failed' : running ? 'running' : 'complete'} />
        <span className="trace-row__copy">
          <span className="trace-header-line"><strong className="trace-row-title">{LABELS[event.eventType] ?? humanize(event.eventType)}</strong>{event.agentName && <span className="trace-agent-badge">Agent: {event.agentName}</span>}</span>
          <span className="trace-row-desc">{eventDetail(event) || 'Backend execution event'}</span>
        </span>
        <span className="trace-row-right">{duration && <span className="trace-row-time">{duration}</span>}<span className="trace-chevron" aria-hidden="true">{expanded ? '−' : '+'}</span></span>
      </button>
      {expanded && <div className="trace-step-expanded-details"><pre className="json-code-box">{JSON.stringify(event.outputSummary, null, 2)}</pre></div>}
    </li>
  );
}

export function AgentThinkingAccordion({
  events = [],
  isStreaming = false,
  durationMs,
  tokenUsage,
}: {
  events?: TraceEvent[];
  isStreaming?: boolean;
  durationMs?: number;
  tokenUsage?: TokenUsageValue;
}) {
  const [open, setOpen] = useState(true);
  const semanticSpans = useMemo(() => [...collapseSemanticSpans(events).values()].sort((left, right) => left.firstSeq - right.firstSeq), [events]);
  const executionStages = useMemo(() => buildExecutionStages(semanticSpans), [semanticSpans]);
  const planTasks = useMemo(() => readPlanTasks(semanticSpans), [semanticSpans]);
  const legacy = events.filter((event) => !isTraceSpanEvent(event) && event.eventType !== 'token_chunk');
  const usingSemantic = semanticSpans.length > 0;
  const hasRequestStage = semanticSpans.some((span) => ['input', 'route'].includes(span.latest.phase));
  const visibleStageCount = (hasRequestStage ? 1 : 0) + (planTasks.length > 0 ? 1 : 0) + executionStages.length;
  const displayedCount = usingSemantic ? visibleStageCount : legacy.length;
  const totals = useMemo(() => readTraceTotals(events, durationMs, tokenUsage), [durationMs, events, tokenUsage]);
  let nextStep = 1;

  return (
    <section className="trace-card" aria-label="AI execution trace">
      <button type="button" className="trace-card__header" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <span className={`trace-card-icon ${isStreaming ? 'is-running' : ''}`} aria-hidden="true">◈</span>
        <span className="trace-card-title-group">
          <strong>{isStreaming ? 'AI is working through the request' : `AI completed ${displayedCount} execution ${displayedCount === 1 ? 'stage' : 'stages'}`}</strong>
          {usingSemantic && <span>{executionStages.length} specialist {executionStages.length === 1 ? 'stage' : 'stages'} observed</span>}
        </span>
        <span className="trace-card__toggle" aria-hidden="true">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <>
          {usingSemantic ? (
            <ol className="trace-workflow">
              {hasRequestStage && <RequestStage spans={semanticSpans} step={nextStep++} isStreaming={isStreaming} />}
              {planTasks.length > 0 && <PlanStage tasks={planTasks} stages={executionStages} step={nextStep++} isStreaming={isStreaming} />}
              {executionStages.map((stage) => <AgentStage key={stage.id} stage={stage} step={nextStep++} isStreaming={isStreaming} />)}
              {visibleStageCount === 0 && <li className="trace-empty">Preparing execution trace…</li>}
            </ol>
          ) : (
            <ol className="trace-timeline">
              {legacy.length === 0 && <li className="trace-empty">Preparing execution trace…</li>}
              {legacy.map((event, index) => <LegacyRow key={event.eventId ?? `${event.eventType}-${index}`} event={event} index={index} isStreaming={isStreaming} />)}
            </ol>
          )}
          {!isStreaming && <TraceTotals totals={totals} />}
        </>
      )}
    </section>
  );
}
