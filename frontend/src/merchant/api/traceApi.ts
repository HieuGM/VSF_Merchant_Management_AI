import { apiFetch } from '../../shared/api-client';
import type {
  JsonRecord,
  RunTrace,
  TraceEvent,
  TraceSpanActorType,
  TraceSpanEvent,
  TraceSpanKind,
  TraceSpanPhase,
} from '../types/monitoring';

const asRecord = (value: unknown): JsonRecord =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as JsonRecord : {};

const asNumber = (value: unknown): number => typeof value === 'number' ? value : 0;
const asNullableNumber = (value: unknown): number | null => typeof value === 'number' ? value : null;
const asText = (value: unknown): string | null => typeof value === 'string' ? value : null;

const SPAN_PHASES = new Set<TraceSpanPhase>(['input', 'route', 'coordinator', 'agent', 'tool', 'synthesis']);
const SPAN_KINDS = new Set<TraceSpanKind>(['started', 'finished', 'failed', 'cancelled']);
const SPAN_ACTORS = new Set<TraceSpanActorType>(['system', 'analyzer', 'coordinator', 'agent', 'tool']);

const readText = (record: JsonRecord, snake: string, camel: string): string | null =>
  asText(record[snake]) ?? asText(record[camel]);

/** Parse a backend semantic span without trusting arbitrary developer payloads. */
export function parseTraceSpanEvent(value: unknown): TraceSpanEvent | null {
  const span = asRecord(value);
  const traceId = readText(span, 'trace_id', 'traceId');
  const seq = typeof span.seq === 'number' && Number.isInteger(span.seq) && span.seq > 0 ? span.seq : null;
  const spanId = readText(span, 'span_id', 'spanId');
  const phase = asText(span.phase);
  const kind = asText(span.kind);
  const actorType = readText(span, 'actor_type', 'actorType');
  const actorName = readText(span, 'actor_name', 'actorName');
  const display = asRecord(span.display);
  const title = asText(display.title);
  const summary = asText(display.summary);
  const status = asText(display.status);

  if (!traceId || !seq || !spanId || !title || !summary || !status
    || !phase || !SPAN_PHASES.has(phase as TraceSpanPhase)
    || !kind || !SPAN_KINDS.has(kind as TraceSpanKind)
    || !actorType || !SPAN_ACTORS.has(actorType as TraceSpanActorType)
    || !actorName) {
    return null;
  }

  return {
    eventId: `span_${traceId}_${seq}`,
    eventType: 'trace_span',
    traceId,
    seq,
    spanId,
    parentSpanId: readText(span, 'parent_span_id', 'parentSpanId'),
    phase: phase as TraceSpanPhase,
    kind: kind as TraceSpanKind,
    actorType: actorType as TraceSpanActorType,
    actorName,
    agentName: actorName,
    outputSummary: display,
    status,
    createdAt: readText(span, 'timestamp', 'timestamp'),
    display: { title, summary, status },
    metrics: asRecord(span.metrics),
    debug: asRecord(span.debug),
  };
}

function parseEvent(value: unknown): TraceEvent {
  const event = asRecord(value);
  if (asText(event.event_type) === 'trace_span' || asText(event.eventType) === 'trace_span') {
    const semantic = parseTraceSpanEvent({
      ...event,
      ...asRecord(event.semantic_span),
      trace_id: event.trace_id ?? event.traceId,
      display: event.display ?? event.output_summary,
      metrics: event.metrics ?? event.metrics_json,
      debug: event.debug ?? event.debug_payload,
    });
    if (semantic) return semantic;
  }
  return {
    eventId: asText(event.event_id) ?? undefined,
    eventType: asText(event.event_type) ?? 'unknown',
    agentName: asText(event.agent_name),
    taskName: asText(event.task_name),
    toolName: asText(event.tool_name),
    outputSummary: asRecord(event.output_summary),
    durationMs: asNullableNumber(event.duration_ms),
    status: asText(event.status),
    errorCode: asText(event.error_code),
    createdAt: asText(event.created_at),
  };
}

export function parseRunTrace(value: unknown): RunTrace {
  const trace = asRecord(value);
  const usage = asRecord(trace.llm_usage);
  const chat = asRecord(trace.chat);
  return {
    traceId: asText(trace.trace_id) ?? '',
    status: asText(trace.status) ?? 'unknown',
    sessionId: asText(trace.session_id),
    crewName: asText(trace.crew_name),
    intent: asText(trace.intent),
    startedAt: asText(trace.started_at),
    finishedAt: asText(trace.finished_at),
    summary: asRecord(trace.summary),
    sessionState: asRecord(trace.session_state),
    cache: Array.isArray(trace.cache) ? trace.cache.map(asRecord) : [],
    sqlQueries: Array.isArray(trace.sql_queries) ? trace.sql_queries.map(asRecord) : [],
    llmUsage: {
      promptTokens: asNumber(usage.prompt_tokens),
      completionTokens: asNumber(usage.completion_tokens),
      totalTokens: asNumber(usage.total_tokens),
      estimatedCostUsd: asNullableNumber(usage.estimated_cost_usd),
    },
    performance: asRecord(trace.performance),
    chat: {
      userQuery: asText(chat.user_query),
      rewrittenQuery: asText(chat.rewritten_query),
      finalAnswer: asText(chat.final_answer),
    },
    events: Array.isArray(trace.events) ? trace.events.map(parseEvent) : [],
  };
}

export async function getRunTrace(traceId: string): Promise<RunTrace> {
  const payload = await apiFetch<unknown>(`/api/v1/agent/runs/${encodeURIComponent(traceId)}`);
  return parseRunTrace(payload);
}

export async function getTraceEventsAfter(
  traceId: string,
  afterSeq: number,
): Promise<TraceSpanEvent[]> {
  const payload = await apiFetch<unknown>(
    `/api/v1/agent/runs/${encodeURIComponent(traceId)}/events?after_seq=${Math.max(0, afterSeq)}`,
  );
  const response = asRecord(payload);
  const events = Array.isArray(response.events) ? response.events : [];
  return events
    .map(parseTraceSpanEvent)
    .filter((event): event is TraceSpanEvent => event !== null)
    .sort((left, right) => left.seq - right.seq);
}
