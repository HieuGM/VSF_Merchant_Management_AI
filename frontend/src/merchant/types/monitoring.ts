export type JsonRecord = Record<string, unknown>;

export interface TraceEvent {
  eventId?: string;
  eventType: string;
  agentName?: string | null;
  taskName?: string | null;
  toolName?: string | null;
  outputSummary: JsonRecord;
  durationMs?: number | null;
  status?: string | null;
  errorCode?: string | null;
  createdAt?: string | null;
}

export type TraceSpanPhase = 'input' | 'route' | 'coordinator' | 'agent' | 'tool' | 'synthesis';
export type TraceSpanKind = 'started' | 'finished' | 'failed' | 'cancelled';
export type TraceSpanActorType = 'system' | 'analyzer' | 'coordinator' | 'agent' | 'tool';

/**
 * Semantic timeline v2 event. It deliberately extends the legacy event shape
 * so older response inspectors can render a mixed history without a migration.
 */
export interface TraceSpanEvent extends TraceEvent {
  eventType: 'trace_span';
  traceId: string;
  seq: number;
  spanId: string;
  parentSpanId?: string | null;
  phase: TraceSpanPhase;
  kind: TraceSpanKind;
  actorType: TraceSpanActorType;
  actorName: string;
  display: {
    title: string;
    summary: string;
    status: string;
  };
  metrics: JsonRecord;
  debug: JsonRecord;
}

export function isTraceSpanEvent(event: TraceEvent): event is TraceSpanEvent {
  return event.eventType === 'trace_span'
    && typeof (event as Partial<TraceSpanEvent>).seq === 'number'
    && typeof (event as Partial<TraceSpanEvent>).spanId === 'string';
}

export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  estimatedCostUsd: number | null;
}

export interface RunTrace {
  traceId: string;
  status: string;
  sessionId?: string | null;
  crewName?: string | null;
  intent?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  summary: JsonRecord;
  sessionState: JsonRecord;
  cache: JsonRecord[];
  sqlQueries: JsonRecord[];
  llmUsage: TokenUsage;
  performance: JsonRecord;
  chat: {
    userQuery?: string | null;
    rewrittenQuery?: string | null;
    finalAnswer?: string | null;
  };
  events: TraceEvent[];
}

export interface MerchantMapFeatureCollection {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    geometry: { type: 'Point'; coordinates: [number, number] };
    properties: JsonRecord & { role: 'owner' | 'nearby' | 'recommended' | 'competitor' | 'user_location' };
  }>;
}
