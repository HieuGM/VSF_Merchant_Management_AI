import { useState, useCallback, useEffect } from 'react';
import { ChatMessage, AgentStepLog, ChatSessionItem, AnalyzedMerchant } from '../types/merchantChat';
import type { TraceEvent, TraceSpanEvent } from '../types/monitoring';
import { isTraceSpanEvent } from '../types/monitoring';
import { getRunTrace, parseTraceSpanEvent } from '../api/traceApi';

/**
 * Semantic seq keeps independently-emitted SSE spans stable and idempotent.
 */
export function reduceTraceEvents(events: TraceEvent[], incoming: TraceEvent): TraceEvent[] {
  if (isTraceSpanEvent(incoming)) {
    if (events.some((event) => isTraceSpanEvent(event) && event.seq === incoming.seq)) {
      return events;
    }
  } else if (incoming.eventId && events.some((event) => event.eventId === incoming.eventId)) {
    return events;
  }

  return [...events, incoming]
    .map((event, index) => ({ event, index }))
    .sort((left, right) => {
      if (isTraceSpanEvent(left.event) && isTraceSpanEvent(right.event)) {
        return left.event.seq - right.event.seq;
      }
      return left.index - right.index;
    })
    .map(({ event }) => event);
}

export function useMerchantChat(merchantId: string = '94') {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessions, setSessions] = useState<ChatSessionItem[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [lastTraceId, setLastTraceId] = useState<string | undefined>();
  const [liveTraceEvents, setLiveTraceEvents] = useState<TraceEvent[]>([]);
  const [sessionId, setSessionId] = useState<string>(() => {
    const key = `merchant_session_id_${merchantId}`;
    const stored = localStorage.getItem(key);
    if (stored) return stored;
    const newSid = `sess_${Math.random().toString(36).substring(2, 9)}`;
    localStorage.setItem(key, newSid);
    return newSid;
  });

  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch(`/api/v1/agent/merchant/sessions?merchant_id=${merchantId}`);
      if (res.ok) {
        const data = await res.json();
        if (data.sessions && Array.isArray(data.sessions)) {
          setSessions(data.sessions);
        }
      }
    } catch (err) {
      console.error('Lỗi khi tải danh sách sessions:', err);
    }
  }, [merchantId]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  useEffect(() => {
    setMessages([]);
    setLiveTraceEvents([]);
    setLastTraceId(undefined);
    const key = `merchant_session_id_${merchantId}`;
    const stored = localStorage.getItem(key);
    if (stored && stored !== sessionId) {
      setSessionId(stored);
    } else if (!stored) {
      const newSid = `sess_${Math.random().toString(36).substring(2, 9)}`;
      localStorage.setItem(key, newSid);
      setSessionId(newSid);
    }
  }, [merchantId]);

  useEffect(() => {
    if (!sessionId) return;
    let isMounted = true;

    fetch(`/api/v1/agent/merchant/chat/history?session_id=${sessionId}`)
      .then((res) => res.json())
      .then(async (data) => {
        if (isMounted && data.messages && Array.isArray(data.messages)) {
          const formatted: ChatMessage[] = data.messages.map((m: any) => ({
            id: m.message_id || `msg_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
            sender: m.sender === 'user' ? 'user' : 'assistant',
            content: m.text || m.content || '',
            timestamp: m.timestamp
              ? new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
              : new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            traceId: m.trace_id,
            analyzedMerchants: m.analyzed_merchants || m.analyzedMerchants || m.merchants || m.metadata?.analyzedMerchants,
            traceEvents: m.trace_events || m.traceEvents,
          }));

          setMessages((current) => (current.length > 0 ? current : formatted));

          // Hydrate trace events for assistant messages that have a traceId
          for (const msg of formatted) {
            if (msg.sender === 'assistant' && msg.traceId) {
              try {
                const runTrace = await getRunTrace(msg.traceId);
                const traceEvents = runTrace.events;
                if (isMounted && traceEvents.length > 0) {
                  setMessages((current) =>
                    current.map((item) =>
                      item.id === msg.id
                        ? { ...item, traceEvents }
                        : item
                    )
                  );
                  setLiveTraceEvents(traceEvents);
                  if (runTrace.traceId) setLastTraceId(runTrace.traceId);
                }
              } catch (err) {
                // Silently skip if trace record is not found in database yet
              }
            }
          }
        }
      })
      .catch((err) => console.error('Lỗi khi tải chat history:', err));

    return () => {
      isMounted = false;
    };
  }, [sessionId]);

  const switchSession = useCallback((targetSessionId: string) => {
    if (targetSessionId === sessionId) return;
    const key = `merchant_session_id_${merchantId}`;
    localStorage.setItem(key, targetSessionId);
    setSessionId(targetSessionId);
    setMessages([]);
  }, [merchantId, sessionId]);

  const createNewSession = useCallback(() => {
    const draftSid = `sess_draft_${Date.now()}`;
    setSessionId(draftSid);
    setMessages([]);
    return draftSid;
  }, []);

  const deleteSession = useCallback(async (targetSessionId: string) => {
    try {
      if (!targetSessionId.startsWith('sess_draft_')) {
        await fetch(`/api/v1/agent/merchant/sessions/${targetSessionId}`, {
          method: 'DELETE',
        });
      }
      await fetchSessions();
      if (targetSessionId === sessionId) {
        setMessages([]);
        const remaining = sessions.filter((s) => s.session_id !== targetSessionId);
        if (remaining.length > 0) {
          switchSession(remaining[0].session_id);
        } else {
          createNewSession();
        }
      }
    } catch (err) {
      console.error('Lỗi khi xóa session:', err);
    }
  }, [sessionId, sessions, fetchSessions, switchSession, createNewSession]);

  /** Merge new merchants into the per-message buffer, deduplicating by merchant_id. */
  function mergeIntoBuffer(
    existing: AnalyzedMerchant[] | undefined,
    incoming: AnalyzedMerchant[]
  ): AnalyzedMerchant[] {
    const map = new Map<string, AnalyzedMerchant>();
    for (const m of existing ?? []) map.set(m.merchant_id, m);
    for (const m of incoming) map.set(m.merchant_id, m);
    return Array.from(map.values());
  }


  const sendMessage = useCallback(
    async (promptText: string) => {
      if (!promptText.trim() || isThinking) return;

      let currentSid = sessionId;
      if (currentSid.startsWith('sess_draft_')) {
        currentSid = `sess_${Math.random().toString(36).substring(2, 9)}`;
        const key = `merchant_session_id_${merchantId}`;
        localStorage.setItem(key, currentSid);
        setSessionId(currentSid);

        try {
          await fetch('/api/v1/agent/merchant/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ merchant_id: merchantId, title: promptText.slice(0, 35) }),
          });
          fetchSessions();
        } catch (e) {
          console.error('Error creating real session on first message:', e);
        }
      }

      const userMsg: ChatMessage = {
        id: `msg_user_${Date.now()}`,
        sender: 'user',
        content: promptText,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      const assistantMsgId = `msg_ast_${Date.now()}`;
      const initialAssistantMsg: ChatMessage = {
        id: assistantMsgId,
        sender: 'assistant',
        content: '',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        telemetryLogs: [],
        traceEvents: [],
        runStatus: 'running',
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMsg, initialAssistantMsg]);
      setIsThinking(true);
      setLastTraceId(undefined);
      setLiveTraceEvents([]);

      let observedTraceId: string | undefined;
      let executionFinished = false;

      const recordSpan = (span: TraceSpanEvent) => {
        observedTraceId = span.traceId;
        setLastTraceId(span.traceId);
        setLiveTraceEvents((current) => reduceTraceEvents(current, span));
        setMessages((current) => current.map((item) => (
          item.id === assistantMsgId
            ? {
                ...item,
                traceId: span.traceId,
                traceEvents: reduceTraceEvents(item.traceEvents ?? [], span),
                runStatus: span.display.status || item.runStatus,
              }
            : item
        )));
      };

      const markInterrupted = (error: unknown) => {
        const message = error instanceof Error ? error.message : 'Luồng theo dõi bị ngắt trước khi hoàn tất.';
        setMessages((prev) =>
          prev.map((item) => (
            item.id === assistantMsgId
              ? {
                  ...item,
                  content: item.content || 'Không thể kết nối với Advisor Agent. Vui lòng thử lại sau.',
                  isStreaming: false,
                  isError: true,
                  runStatus: 'failed',
                  errorMessage: message,
                }
              : item
          ))
        );
      };

      try {
        const response = await fetch('/api/v1/agent/merchant/chat/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            merchant_id: merchantId,
            message: promptText,
            session_id: currentSid,
          }),
        });

        if (!response.ok) {
          throw new Error(`Stream request failed (${response.status})`);
        }
        if (!response.body) {
          throw new Error('No stream body received from backend');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let currentEventType = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed) continue;

            if (trimmed.startsWith('event:')) {
              currentEventType = trimmed.slice(6).trim();
            } else if (trimmed.startsWith('data:')) {
              const jsonStr = trimmed.slice(5).trim();
              if (!jsonStr) continue;

              try {
                const data = JSON.parse(jsonStr);
                const eventType = data.event || data.type || currentEventType;
                const traceId = data.trace_id || data.traceId;
                if (traceId) {
                  observedTraceId = traceId;
                  setLastTraceId(traceId);
                }
                if (eventType) {
                  if (eventType === 'trace_span') {
                    const span = parseTraceSpanEvent(data);
                    if (span) recordSpan(span);
                    continue;
                  }

                  const normalizedEvent: TraceEvent = {
                      eventId: data.event_id || data.eventId || `live_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
                      eventType,
                      agentName: data.agent_name || data.agentName,
                      taskName: data.task || data.task_name || data.taskName,
                      toolName: data.tool_name || data.toolName,
                      outputSummary: data,
                      durationMs: data.duration_ms ?? data.durationMs,
                      status: data.status,
                      errorCode: data.error_code || data.errorCode,
                      createdAt: data.timestamp,
                    };
                    setLiveTraceEvents((current) => reduceTraceEvents(current, normalizedEvent));
                    setMessages((current) => current.map((item) => (
                      item.id === assistantMsgId
                        ? {
                            ...item,
                            traceId: traceId || item.traceId,
                            traceEvents: reduceTraceEvents(item.traceEvents ?? [], normalizedEvent),
                            runStatus: data.status || item.runStatus,
                          }
                        : item
                    )));
                }

                if (eventType === 'plan') {
                  const capabilities: string[] = data.capabilities ?? [];
                  const log: AgentStepLog = {
                    id: `log_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
                    type: 'plan',
                    name: data.agent_name || 'merchant_planner',
                    detail: capabilities.join(', ') || 'general_chat',
                    timestamp: data.timestamp || new Date().toISOString(),
                  };
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId
                        ? {
                            ...m,
                            capabilities,
                            rewrittenQuery: data.rewritten_query || m.rewrittenQuery,
                            telemetryLogs: [...(m.telemetryLogs || []), log],
                          }
                        : m
                    )
                  );
                } else if (eventType === 'policy_decision') {
                  const decision = data.decision || data.status || 'allowed';
                  const scope = data.target_scope || data.step_id || 'merchant_data';
                  const log: AgentStepLog = {
                    id: `log_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
                    type: 'policy_decision',
                    name: data.agent_name || 'merchant_data_policy',
                    detail: `${scope}: ${decision}`,
                    timestamp: data.timestamp || new Date().toISOString(),
                  };
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId
                        ? { ...m, telemetryLogs: [...(m.telemetryLogs || []), log] }
                        : m
                    )
                  );
                } else if (eventType === 'evidence_validation') {
                  const status = data.status || 'unknown';
                  const log: AgentStepLog = {
                    id: `log_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
                    type: 'evidence_validation',
                    name: data.agent_name || 'evidence_resolver',
                    detail: `${status} · ${data.valid_claims ?? 0} hợp lệ · ${data.rejected_claims ?? 0} bị loại`,
                    timestamp: data.timestamp || new Date().toISOString(),
                  };
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId
                        ? {
                            ...m,
                            evidenceStatus: status,
                            telemetryLogs: [...(m.telemetryLogs || []), log],
                          }
                        : m
                    )
                  );
                } else if (eventType === 'agent_start') {
                  const log: AgentStepLog = {
                    id: `log_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
                    type: 'agent_start',
                    name: data.agent_name || data.name || 'MerchantAdvisorAgent',
                    detail: data.task_description || data.task || data.detail || 'Bắt đầu xử lý...',
                    timestamp: data.timestamp || new Date().toISOString(),
                  };
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId
                        ? { ...m, telemetryLogs: [...(m.telemetryLogs || []), log] }
                        : m
                    )
                  );
                } else if (eventType === 'tool_call') {
                  const log: AgentStepLog = {
                    id: `log_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
                    type: 'tool_call',
                    name: data.tool_name || data.tool || data.name || 'Tool Call',
                    detail: data.args || data.input
                      ? typeof (data.args || data.input) === 'string'
                        ? (data.args || data.input)
                        : JSON.stringify(data.args || data.input)
                      : data.detail || '',
                    timestamp: data.timestamp || new Date().toISOString(),
                  };
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId
                        ? { ...m, telemetryLogs: [...(m.telemetryLogs || []), log] }
                        : m
                    )
                  );
                } else if (eventType === 'tool_result' || eventType === 'tool_finished') {
                  const resultPayload = data.result ?? data.output;
                  const competitors = resultPayload?.competitors ?? data.competitors;

                  // Collect ALL merchants from tool result into the per-message buffer
                  const rawMerchants =
                    competitors ??
                    resultPayload?.merchants ??
                    resultPayload?.results?.merchants;
                  const incomingMerchants: AnalyzedMerchant[] = (rawMerchants ?? []).map(
                    (m: any) => ({
                      merchant_id: String(m.merchant_id),
                      name: m.name,
                      cuisine: m.cuisine,
                      distance_km: m.distance_km,
                      rating: m.rating ?? m.score,
                      address: m.address,
                      sourceToolName: data.tool_name || data.tool || data.name,
                    })
                  );

                  const log: AgentStepLog = {
                    id: `log_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
                    type: 'tool_result',
                    name: data.tool_name || data.tool || data.name || 'Tool Result',
                    detail: resultPayload
                      ? typeof resultPayload === 'string'
                        ? resultPayload
                        : rawMerchants
                          ? `Đã tìm thấy ${rawMerchants.length} quán phù hợp.`
                          : JSON.stringify(resultPayload)
                      : data.detail || '',
                    durationMs: data.duration_ms ?? data.durationMs,
                    timestamp: data.timestamp || new Date().toISOString(),
                    // Attach merchants to this log step for accordion context chips
                    merchants: incomingMerchants.length > 0 ? incomingMerchants : undefined,
                  };
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId
                        ? {
                            ...m,
                            telemetryLogs: [...(m.telemetryLogs || []), log],
                            competitors: competitors || m.competitors,
                            // Accumulate into buffer; will be filtered on execution_finish
                            _merchantBuffer:
                              incomingMerchants.length > 0
                                ? mergeIntoBuffer(m._merchantBuffer, incomingMerchants)
                                : m._merchantBuffer,
                          }
                        : m
                    )
                  );
                } else if (eventType === 'agent_retry') {
                  const log: AgentStepLog = {
                    id: `log_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
                    type: 'agent_retry',
                    name: data.agent_name || 'CrewAI Agent',
                    detail: data.detail || data.error || 'Đang tự động thử lại (Retry)...',
                    timestamp: data.timestamp || new Date().toISOString(),
                  };
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId
                        ? { ...m, telemetryLogs: [...(m.telemetryLogs || []), log] }
                        : m
                    )
                  );
                } else if (eventType === 'cache') {
                  const statusStr = String(data.status || data.event || 'HIT').toUpperCase();
                  const log: AgentStepLog = {
                    id: `log_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
                    type: 'cache',
                    name: `Cache ${statusStr.includes('HIT') ? 'HIT' : 'MISS'}`,
                    detail: `${data.key || data.cache_key || 'H3 Cell Index'} · Source: ${data.source || 'Memory Store'}`,
                    timestamp: data.timestamp || new Date().toISOString(),
                  };
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId
                        ? { ...m, telemetryLogs: [...(m.telemetryLogs || []), log] }
                        : m
                    )
                  );
                } else if (eventType === 'sql_query') {
                  const log: AgentStepLog = {
                    id: `log_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
                    type: 'sql_query',
                    name: 'SQL Query',
                    detail: `${data.query || data.sql || 'Database Query'} (${data.duration_ms ?? 0}ms)`,
                    durationMs: data.duration_ms,
                    timestamp: data.timestamp || new Date().toISOString(),
                  };
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId
                        ? { ...m, telemetryLogs: [...(m.telemetryLogs || []), log] }
                        : m
                    )
                  );
                } else if (eventType === 'crewai_llm_finished') {
                  const usage = data.token_usage || {};
                  const log: AgentStepLog = {
                    id: `log_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
                    type: 'llm_call',
                    name: `LLM Call (${data.model || 'Gemini'})`,
                    detail: `Prompt: ${usage.prompt_tokens ?? 0} · Completion: ${usage.completion_tokens ?? 0} · Total: ${usage.total_tokens ?? 0}`,
                    durationMs: data.duration_ms,
                    timestamp: data.timestamp || new Date().toISOString(),
                  };
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId
                        ? { ...m, telemetryLogs: [...(m.telemetryLogs || []), log] }
                        : m
                    )
                  );
                } else if (eventType === 'agent_error') {
                  const log: AgentStepLog = {
                    id: `log_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
                    type: 'agent_error',
                    name: data.agent_name || 'Agent Error',
                    detail: data.detail || data.error || 'Lỗi thực thi Agent',
                    timestamp: data.timestamp || new Date().toISOString(),
                  };
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId
                        ? {
                            ...m,
                            telemetryLogs: [...(m.telemetryLogs || []), log],
                            isError: true,
                            errorMessage: data.detail || data.error,
                          }
                        : m
                    )
                  );
                } else if (eventType === 'token_chunk' || data.text !== undefined) {
                  const text = data.text ?? data.chunk ?? data.content ?? '';
                  if (text) {
                    setMessages((prev) =>
                      prev.map((m) =>
                        m.id === assistantMsgId
                          ? { ...m, content: m.content + text }
                          : m
                      )
                    );
                  }
                } else if (eventType === 'execution_finish') {
                  executionFinished = true;
                  const isFailed = data.status === 'FAILED' || data.status === 'error';
                  setMessages((prev) =>
                    prev.map((m) => {
                      if (m.id !== assistantMsgId) return m;
                      const observedMerchants = m._merchantBuffer ?? [];
                      return {
                        ...m,
                        traceId: data.trace_id || data.traceId || m.traceId,
                        tokenUsage: data.token_usage || data.tokenUsage || m.tokenUsage,
                        capabilities: data.capabilities || m.capabilities,
                        rewrittenQuery:
                          data.rewritten_query || data.rewrittenQuery || m.rewrittenQuery,
                        evidenceStatus:
                          data.evidence_status || data.evidenceStatus || m.evidenceStatus,
                        durationMs: data.duration_ms ?? data.durationMs ?? m.durationMs,
                        competitors: data.competitors || m.competitors,
                        analyzedMerchants: observedMerchants.length > 0 ? observedMerchants : undefined,
                        _merchantBuffer: undefined, // cleanup temp buffer
                        runStatus: data.status || (isFailed ? 'failed' : 'completed'),
                        isStreaming: false,
                        isError: isFailed || m.isError,
                        errorMessage: isFailed ? data.error || 'Lỗi thực thi LLM Model' : m.errorMessage,
                      };
                    })
                  );
                  observedTraceId = data.trace_id || data.traceId || observedTraceId;
                  setLastTraceId(observedTraceId);
                }
              } catch (e) {
                console.error('Error parsing SSE chunk:', e);
              }
            }
          }
        }

        if (!executionFinished) {
          markInterrupted(new Error('Luồng phản hồi kết thúc trước execution_finish.'));
        } else {
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantMsgId ? { ...m, isStreaming: false } : m))
          );
        }
      } catch (err) {
        console.error('Error streaming merchant chat:', err);
        // A transport can reject while the browser is closing the stream after
        // it already delivered the terminal event. The terminal event is the
        // authoritative lifecycle boundary; do not turn that completed answer
        // into a failed one.
        if (!executionFinished) {
          markInterrupted(err);
        }
      } finally {
        setIsThinking(false);
      }
    },
    [merchantId, sessionId, isThinking]
  );

  const clearSession = useCallback(() => {
    const key = `merchant_session_id_${merchantId}`;
    const newSid = `sess_${Math.random().toString(36).substring(2, 9)}`;
    localStorage.setItem(key, newSid);
    setMessages([]);
    setSessionId(newSid);
  }, [merchantId]);

  return {
    messages,
    sessions,
    isThinking,
    sendMessage,
    clearSession,
    switchSession,
    createNewSession,
    deleteSession,
    activeSessionId: sessionId,
    sessionId,
    lastTraceId,
    liveTraceEvents,
  };
}
