import { useMemo, useState } from 'react';
import type { JsonRecord, TraceEvent, TraceSpanEvent } from '../../types/monitoring';
import { isTraceSpanEvent } from '../../types/monitoring';

const LABELS: Record<string, string> = {
  context: 'Hiểu yêu cầu',
  policy_decision: 'Kiểm tra policy',
  crewai_agent_started: 'Agent bắt đầu',
  crewai_agent_finished: 'Agent hoàn tất',
  crewai_llm_started: 'Tìm kiếm dữ liệu',
  crewai_llm_finished: 'LLM hoàn tất',
  crewai_tool_started: 'Phân tích & đánh giá',
  crewai_tool_finished: 'Lập danh sách đề xuất',
  tool_call: 'Gọi công cụ',
  tool_result: 'Nhận kết quả',
  cache: 'Truy cập cache',
  sql_query: 'Truy vấn database',
  hitl_requested: 'Chờ người dùng',
  synthesis: 'Tổng hợp kết quả',
  execution_finish: 'Hoàn thành',
  error: 'Lỗi pipeline',
  agent_error: 'Lỗi agent',
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

/** Collapse lifecycle events into one visual node, retaining only safe debug. */
export function buildSemanticSpanTree(events: TraceEvent[]): RenderSpan[] {
  const spans = new Map<string, RenderSpan>();
  for (const event of events.filter(isTraceSpanEvent).sort((left, right) => left.seq - right.seq)) {
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
  return typeof latency === 'number' ? `${latency >= 1000 ? (latency / 1000).toFixed(1) : Math.round(latency)}${latency >= 1000 ? 's' : 'ms'}` : null;
}

function tokenText(metrics: JsonRecord) {
  const usage = metrics.token_usage ?? metrics.tokenUsage;
  if (!usage || typeof usage !== 'object' || Array.isArray(usage)) return null;
  const tokens = usage as JsonRecord;
  const total = tokens.total_tokens ?? tokens.totalTokens;
  return typeof total === 'number' ? `${total} tokens` : null;
}

function SemanticSpanRow({ span, depth, isStreaming }: { span: RenderSpan; depth: number; isStreaming: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const [rawOpen, setRawOpen] = useState(false);
  const { latest } = span;
  const failed = latest.kind === 'failed' || latest.kind === 'cancelled';
  const running = isStreaming && latest.kind === 'started';
  const latency = latencyText(span.metrics);
  const tokens = tokenText(span.metrics);
  const rawDebug = JSON.stringify(span.debug, null, 2);

  return (
    <li className="trace-row-container" style={{ marginLeft: `${Math.min(depth, 5) * 14}px` }}>
      <button
        type="button"
        className={`trace-row ${expanded ? 'is-open' : ''}`}
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        aria-label={`${expanded ? 'Thu gọn' : 'Mở'} trace: ${latest.display.title}`}
      >
        <span className={`trace-node ${failed ? 'is-error' : running ? 'is-running' : 'is-complete'}`} aria-hidden="true">
          {failed ? '!' : running ? '' : '✓'}
        </span>
        <span className="trace-row__copy">
          <span className="trace-header-line">
            <strong className="trace-row-title">{latest.display.title}</strong>
            <span className="trace-agent-badge">{latest.phase} · {latest.actorName}</span>
          </span>
          <span className="trace-row-desc">{latest.display.summary}</span>
        </span>
        <span className="trace-row-right">
          {latency && <span className="trace-row-time">{latency}</span>}
          {tokens && <span className="trace-row-time">{tokens}</span>}
          <span className="trace-chevron" aria-hidden="true">{expanded ? '⌃' : '⌄'}</span>
        </span>
      </button>
      {expanded && (
        <div className="trace-step-expanded-details">
          <div className="step-detail-row"><span className="detail-tag-name">Status:</span><code>{latest.display.status}</code></div>
          <button
            type="button"
            className="trace-raw-toggle"
            onClick={() => setRawOpen((value) => !value)}
            aria-expanded={rawOpen}
            aria-label={`${rawOpen ? 'Ẩn' : 'Hiện'} debug đã được làm sạch`}
          >
            {rawOpen ? 'Hide' : 'View'}
          </button>
          {rawOpen && <pre className="json-code-box">{rawDebug || '{}'}</pre>}
        </div>
      )}
      {span.children.length > 0 && (
        <ol className="trace-nested-timeline">
          {span.children.map((child) => (
            <SemanticSpanRow key={child.spanId} span={child} depth={depth + 1} isStreaming={isStreaming} />
          ))}
        </ol>
      )}
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
        <span className={`trace-node ${failed ? 'is-error' : running ? 'is-running' : 'is-complete'}`} aria-hidden="true">{failed ? '!' : running ? '' : '✓'}</span>
        <span className="trace-row__copy">
          <span className="trace-header-line"><strong className="trace-row-title">{LABELS[event.eventType] ?? event.eventType.replace(/_/g, ' ')}</strong>{event.agentName && <span className="trace-agent-badge">Agent: {event.agentName}</span>}</span>
          <span className="trace-row-desc">{eventDetail(event) || 'Backend event execution'}</span>
        </span>
        <span className="trace-row-right">{duration && <span className="trace-row-time">{duration}</span>}<span className="trace-chevron" aria-hidden="true">{expanded ? '⌃' : '⌄'}</span></span>
      </button>
      {expanded && <div className="trace-step-expanded-details"><pre className="json-code-box">{JSON.stringify(event.outputSummary, null, 2)}</pre></div>}
    </li>
  );
}

export function AgentThinkingAccordion({ events = [], isStreaming = false }: { events?: TraceEvent[]; isStreaming?: boolean }) {
  const [open, setOpen] = useState(true);
  const semanticRoots = useMemo(() => buildSemanticSpanTree(events), [events]);
  const legacy = events.filter((event) => !isTraceSpanEvent(event) && event.eventType !== 'token_chunk');
  const usingSemantic = semanticRoots.length > 0;
  const countSpans = (items: RenderSpan[]): number => items.reduce((total, span) => total + 1 + countSpans(span.children), 0);
  const count = usingSemantic ? countSpans(semanticRoots) : legacy.length;
  const hasError = events.some((event) => isTraceSpanEvent(event) ? event.kind === 'failed' : event.eventType.includes('error') || event.status === 'failed');

  return (
    <section className="trace-card" aria-label="CrewAI trace">
      <button type="button" className="trace-card__header" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <span className="trace-card-icon" aria-hidden="true">◈</span>
        <span className="trace-card-title-group"><strong>{isStreaming ? 'AI đang phân tích…' : hasError ? 'Pipeline có lỗi' : `AI đã thực thi ${count} bước phân tích`}</strong></span>
        <span className="trace-card__toggle" aria-hidden="true">{open ? '⌃' : '⌄'}</span>
      </button>
      {open && (
        <ol className="trace-timeline">
          {count === 0 && <li className="trace-empty"><span>Đang chờ event đầu tiên…</span></li>}
          {usingSemantic
            ? semanticRoots.map((span) => <SemanticSpanRow key={span.spanId} span={span} depth={0} isStreaming={isStreaming} />)
            : legacy.map((event, index) => <LegacyRow key={event.eventId ?? `${event.eventType}-${index}`} event={event} index={index} isStreaming={isStreaming} />)}
        </ol>
      )}
    </section>
  );
}
