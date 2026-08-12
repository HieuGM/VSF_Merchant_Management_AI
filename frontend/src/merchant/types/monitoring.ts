export interface TraceObservation {
  id: string;
  parentId: string | null;
  name: string;
  type: string;
  status: string;
  model: string | null;
  promptName: string | null;
  promptVersion: number | null;
  startedAt: string | null;
  finishedAt: string | null;
  latencyMs: number | null;
  timeToFirstTokenMs: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
  costUsd: number | null;
}

export interface TraceTotals {
  latencyMs: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
  totalCostUsd: number | null;
}

export interface RunTrace {
  traceId: string;
  status: string;
  startedAt: string | null;
  finishedAt: string | null;
  totals: TraceTotals;
  observations: TraceObservation[];
}

export interface MerchantMapFeatureCollection {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    geometry: { type: 'Point'; coordinates: [number, number] };
    properties: Record<string, unknown> & { role: 'owner' | 'nearby' | 'recommended' | 'competitor' | 'user_location' };
  }>;
}
