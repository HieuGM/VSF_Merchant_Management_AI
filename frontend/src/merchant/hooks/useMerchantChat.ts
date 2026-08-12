import { useCallback, useEffect, useRef, useState } from 'react';
import { waitForRunTrace } from '../api/traceApi';
import type { AnalyzedMerchant, ChatMessage, ChatSessionItem } from '../types/merchantChat';

const time = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const sessionKey = (merchantId: string) => `merchant_session_id_${merchantId}`;
const newSessionId = () => `sess_${Math.random().toString(36).substring(2, 9)}`;

export function useMerchantChat(merchantId = '94') {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessions, setSessions] = useState<ChatSessionItem[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [lastTraceId, setLastTraceId] = useState<string>();
  const [sessionId, setSessionId] = useState(() => {
    const stored = localStorage.getItem(sessionKey(merchantId));
    if (stored) return stored;
    const id = newSessionId();
    localStorage.setItem(sessionKey(merchantId), id);
    return id;
  });
  const traceControllers = useRef(new Map<string, AbortController>());
  const historyController = useRef<AbortController>();

  const hydrateTrace = useCallback((messageId: string, traceId: string) => {
    traceControllers.current.get(messageId)?.abort();
    const controller = new AbortController();
    traceControllers.current.set(messageId, controller);
    setMessages((current) => current.map((message) => message.id === messageId
      ? { ...message, traceStatus: 'processing' }
      : message));
    waitForRunTrace(traceId, controller.signal)
      .then((trace) => setMessages((current) => current.map((message) => message.id === messageId
        ? { ...message, trace, traceStatus: 'ready' }
        : message)))
      .catch((error) => {
        if (error?.name !== 'AbortError') {
          setMessages((current) => current.map((message) => message.id === messageId
            ? { ...message, traceStatus: 'unavailable' }
            : message));
        }
      })
      .finally(() => {
        if (traceControllers.current.get(messageId) === controller) {
          traceControllers.current.delete(messageId);
        }
      });
  }, []);

  const fetchSessions = useCallback(async () => {
    const response = await fetch(`/api/v1/agent/merchant/sessions?merchant_id=${merchantId}`);
    if (response.ok) setSessions((await response.json()).sessions ?? []);
  }, [merchantId]);

  useEffect(() => {
    fetchSessions().catch(() => undefined);
  }, [fetchSessions]);

  useEffect(() => {
    const controllers = traceControllers.current;
    historyController.current?.abort();
    const historyAbort = new AbortController();
    historyController.current = historyAbort;
    setMessages([]);
    fetch(`/api/v1/agent/merchant/chat/history?session_id=${sessionId}`, { signal: historyAbort.signal })
      .then((response) => response.json())
      .then((data) => {
        const history: ChatMessage[] = (data.messages ?? []).map((message: Record<string, unknown>) => ({
          id: String(message.message_id),
          sender: message.sender === 'user' ? 'user' : 'assistant',
          content: String(message.text ?? ''),
          timestamp: message.timestamp ? new Date(String(message.timestamp)).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : time(),
          traceId: typeof message.trace_id === 'string' ? message.trace_id : undefined,
        }));
        setMessages((current) => current.length > 0 ? current : history);
        history.filter((message) => message.sender === 'assistant' && message.traceId)
          .forEach((message) => hydrateTrace(message.id, message.traceId!));
      })
      .catch(() => undefined);
    return () => {
      historyAbort.abort();
      controllers.forEach((controller) => controller.abort());
    };
  }, [sessionId, hydrateTrace]);

  useEffect(() => {
    const stored = localStorage.getItem(sessionKey(merchantId));
    const id = stored ?? newSessionId();
    if (!stored) localStorage.setItem(sessionKey(merchantId), id);
    setSessionId(id);
    setMessages([]);
    setLastTraceId(undefined);
  }, [merchantId]);

  const switchSession = useCallback((id: string) => {
    if (id === sessionId) return;
    localStorage.setItem(sessionKey(merchantId), id);
    setSessionId(id);
  }, [merchantId, sessionId]);

  const createNewSession = useCallback(() => {
    const id = `sess_draft_${Date.now()}`;
    setSessionId(id);
    setMessages([]);
    return id;
  }, []);

  const deleteSession = useCallback(async (id: string) => {
    if (!id.startsWith('sess_draft_')) await fetch(`/api/v1/agent/merchant/sessions/${id}`, { method: 'DELETE' });
    await fetchSessions();
    if (id === sessionId) createNewSession();
  }, [createNewSession, fetchSessions, sessionId]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isThinking) return;
    let sid = sessionId;
    if (sid.startsWith('sess_draft_')) {
      sid = newSessionId();
      localStorage.setItem(sessionKey(merchantId), sid);
      setSessionId(sid);
      await fetch('/api/v1/agent/merchant/sessions', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ merchant_id: merchantId, title: text.slice(0, 35) }),
      });
    }
    const assistantId = `msg_ast_${Date.now()}`;
    setMessages((current) => [...current,
      { id: `msg_user_${Date.now()}`, sender: 'user', content: text, timestamp: time() },
      { id: assistantId, sender: 'assistant', content: '', timestamp: time(), runStatus: 'running', isStreaming: true },
    ]);
    setIsThinking(true);
    let finished = false;
    try {
      const response = await fetch('/api/v1/agent/merchant/chat/stream', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ merchant_id: merchantId, message: text, session_id: sid }),
      });
      if (!response.ok || !response.body) throw new Error(`Stream request failed (${response.status})`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let eventType = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split('\n');
        buffer = blocks.pop() ?? '';
        for (const line of blocks) {
          if (line.startsWith('event:')) eventType = line.slice(6).trim();
          if (!line.startsWith('data:')) continue;
          const data = JSON.parse(line.slice(5).trim());
          if (eventType === 'token_chunk') {
            setMessages((current) => current.map((message) => message.id === assistantId
              ? { ...message, content: message.content + String(data.text ?? '') }
              : message));
          } else if (eventType === 'execution_finish') {
            finished = true;
            const failed = String(data.status).toUpperCase() === 'FAILED';
            const traceId = typeof data.trace_id === 'string' ? data.trace_id : undefined;
            setLastTraceId(traceId);
            setMessages((current) => current.map((message) => message.id === assistantId ? {
              ...message,
              traceId,
              runStatus: failed ? 'failed' : 'completed',
              isStreaming: false,
              isError: failed,
              errorMessage: failed ? String(data.error ?? 'Lỗi thực thi LLM Model') : undefined,
              analyzedMerchants: (data.merchants ?? []) as AnalyzedMerchant[],
              competitors: data.competitors ?? [],
              evidenceStatus: data.evidence_status,
            } : message));
            if (traceId && !failed) hydrateTrace(assistantId, traceId);
          } else if (eventType === 'agent_error') {
            setMessages((current) => current.map((message) => message.id === assistantId
              ? { ...message, isError: true, errorMessage: String(data.detail ?? data.error ?? 'Lỗi thực thi Agent') }
              : message));
          }
        }
      }
      if (!finished) throw new Error('Luồng phản hồi kết thúc trước execution_finish.');
    } catch (error) {
      if (!finished) setMessages((current) => current.map((message) => message.id === assistantId ? {
        ...message, isStreaming: false, isError: true, runStatus: 'failed',
        errorMessage: error instanceof Error ? error.message : 'Không thể kết nối với Advisor Agent.',
      } : message));
    } finally {
      setIsThinking(false);
    }
  }, [hydrateTrace, isThinking, merchantId, sessionId]);

  const clearSession = useCallback(() => {
    const id = newSessionId();
    localStorage.setItem(sessionKey(merchantId), id);
    setMessages([]);
    setSessionId(id);
  }, [merchantId]);

  return { messages, sessions, isThinking, sendMessage, clearSession, switchSession, createNewSession, deleteSession, activeSessionId: sessionId, sessionId, lastTraceId };
}
