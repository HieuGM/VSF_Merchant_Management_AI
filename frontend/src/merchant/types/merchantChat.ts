export interface AgentStepLog {
  id: string;
  type:
    | 'plan'
    | 'agent_start'
    | 'policy_decision'
    | 'tool_call'
    | 'tool_result'
    | 'evidence_validation'
    | 'agent_retry'
    | 'agent_error'
    | 'cache'
    | 'sql_query'
    | 'llm_call';
  name: string;
  detail: string;
  durationMs?: number;
  timestamp: string;
  /** Merchants returned by this tool step — used for accordion context chips */
  merchants?: AnalyzedMerchant[];
}

export interface DimensionHighlight {
  dimension: string;
  score: number;
  comparisonNote: string;
}

export interface CompetitorItem {
  merchant_id: string;
  name: string;
  distance_km: number;
  cuisine: string;
  score?: number;
  rating?: number;
  address?: string;
  category?: string;
  image_url?: string;
  delivery_time_min?: number;
  review_quotes?: string[];
  dimensions?: DimensionHighlight[];
}

/** Merchant found during agent tool calls, filtered to only those mentioned in the final reply */
export interface AnalyzedMerchant {
  merchant_id: string;
  name: string;
  cuisine?: string;
  category?: string;
  distance_km?: number;
  rating?: number;
  score?: number;
  address?: string;
  image_url?: string;
  delivery_time_min?: number;
  /** Tool that surfaced this merchant, e.g. "search_merchants" */
  sourceToolName?: string;
}

/** Full 8-dimension profile from GET /api/v1/merchants/{id}/profile */
export interface MerchantProfileDimension {
  score: number;
  basis: string;
  evidence?: string[];
}

export interface MerchantProfileData {
  merchant_id: string;
  tier?: string;
  price_level?: string;
  schema_version?: string;
  updated_at?: string;
  metadata?: {
    name: string;
    cuisine?: string;
    category?: string;
    location?: { address: string; city: string; lat: number; lng: number };
    open_hours?: { open: string; close: string };
    taste_tags?: string[];
    diet_tags?: string[];
  };
  dimensions?: {
    food_quality?: MerchantProfileDimension;
    image_quality?: MerchantProfileDimension;
    delivery_quality?: MerchantProfileDimension;
    packaging?: MerchantProfileDimension;
    service?: MerchantProfileDimension;
    waiting_time?: MerchantProfileDimension;
    menu_diversity?: MerchantProfileDimension;
    price_competitiveness?: MerchantProfileDimension;
  };
  ratings?: {
    shopeefood_avg?: number;
    shopeefood_total_review?: number;
    foody_rating?: number;
    foody_review_count?: number;
  };
  attributes?: {
    operation_kpis?: {
      avg_prep_minutes?: number;
      cancel_rate?: number;
      acceptance_rate?: number;
      estimated_daily_orders?: number;
      peak_hours?: string[];
    };
    delivery_stats?: {
      avg_delivery_minutes?: number;
      on_time_rate?: number;
      driver_rating?: number;
    };
    trending_dishes?: Array<{ dish: string; trend_score: number; rank: number }>;
    peak_time?: string[];
  };
}

export interface ChatSessionItem {
  session_id: string;
  title: string;
  created_at?: string;
  updated_at?: string;
  last_message?: string;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  content: string;
  timestamp: string;
  traceId?: string;
  tokenUsage?: { total_tokens: number; prompt_tokens: number; completion_tokens: number };
  capabilities?: string[];
  rewrittenQuery?: string;
  evidenceStatus?: string;
  durationMs?: number;
  telemetryLogs?: AgentStepLog[];
  traceEvents?: import('./monitoring').TraceEvent[];
  runStatus?: string;
  competitors?: CompetitorItem[];
  /** Structured merchants observed in backend tool results for this response. */
  analyzedMerchants?: AnalyzedMerchant[];
  /**
   * @internal — temporary buffer accumulating all merchants seen during tool_result events.
   * Cleared after execution_finish.
   */
  _merchantBuffer?: AnalyzedMerchant[];
  isStreaming?: boolean;
  isError?: boolean;
  errorMessage?: string;
}
