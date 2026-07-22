export interface AgentStepLog {
  id: string;
  type: 'agent_start' | 'tool_call' | 'tool_result';
  name: string;
  detail: string;
  durationMs?: number;
  timestamp: string;
}

export interface CompetitorItem {
  merchant_id: string;
  name: string;
  distance_km: number;
  cuisine: string;
  score?: number;
  address?: string;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  content: string;
  timestamp: string;
  traceId?: string;
  tokenUsage?: { total_tokens: number; prompt_tokens: number; completion_tokens: number };
  telemetryLogs?: AgentStepLog[];
  competitors?: CompetitorItem[];
  isStreaming?: boolean;
}
