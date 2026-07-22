import { useState, useCallback } from 'react';
import { ChatMessage, AgentStepLog } from '../types/merchantChat';

export function useMerchantChat(merchantId: string = '94') {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [sessionId, setSessionId] = useState(
    () => `sess_${Math.random().toString(36).substring(2, 9)}`
  );

  const sendMessage = useCallback(
    async (promptText: string) => {
      if (!promptText.trim() || isThinking) return;

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
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMsg, initialAssistantMsg]);
      setIsThinking(true);

      try {
        const response = await fetch('/api/v1/agent/merchant/chat/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            merchant_id: merchantId,
            message: promptText,
            session_id: sessionId,
          }),
        });

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

                if (eventType === 'agent_start') {
                  const log: AgentStepLog = {
                    id: `log_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
                    type: 'agent_start',
                    name: data.agent_name || data.name || 'MerchantAdvisorAgent',
                    detail: data.task || data.detail || 'Bắt đầu xử lý...',
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
                    name: data.tool || data.name || 'Tool Call',
                    detail: data.input
                      ? typeof data.input === 'string'
                        ? data.input
                        : JSON.stringify(data.input)
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
                } else if (eventType === 'tool_result') {
                  const log: AgentStepLog = {
                    id: `log_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
                    type: 'tool_result',
                    name: data.tool || data.name || 'Tool Result',
                    detail: data.output
                      ? typeof data.output === 'string'
                        ? data.output
                        : JSON.stringify(data.output)
                      : data.detail || '',
                    durationMs: data.duration_ms ?? data.durationMs,
                    timestamp: data.timestamp || new Date().toISOString(),
                  };
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId
                        ? { ...m, telemetryLogs: [...(m.telemetryLogs || []), log] }
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
                } else if (eventType === 'execution_finish' || data.trace_id !== undefined) {
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId
                        ? {
                            ...m,
                            traceId: data.trace_id || data.traceId || m.traceId,
                            tokenUsage: data.token_usage || data.tokenUsage || m.tokenUsage,
                            competitors: data.competitors || m.competitors,
                            isStreaming: false,
                          }
                        : m
                    )
                  );
                }
              } catch (e) {
                console.error('Error parsing SSE chunk:', e);
              }
            }
          }
        }

        setMessages((prev) =>
          prev.map((m) => (m.id === assistantMsgId ? { ...m, isStreaming: false } : m))
        );
      } catch (err) {
        console.error('Error streaming merchant chat:', err);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? {
                  ...m,
                  content: m.content || '❌ Lỗi kết nối với Advisor Agent.',
                  isStreaming: false,
                }
              : m
          )
        );
      } finally {
        setIsThinking(false);
      }
    },
    [merchantId, sessionId, isThinking]
  );

  const clearSession = useCallback(() => {
    setMessages([]);
    setSessionId(`sess_${Math.random().toString(36).substring(2, 9)}`);
  }, []);

  return {
    messages,
    isThinking,
    sendMessage,
    clearSession,
    activeSessionId: sessionId,
    sessionId,
  };
}
