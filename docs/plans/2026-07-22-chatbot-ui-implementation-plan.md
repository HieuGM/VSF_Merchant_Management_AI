# Chatbot UI & Real-Time Agent Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-ready, Claude Web-inspired Chatbot UI with real-time SSE Agent telemetry checklog, rich competitor cards, and right slide-over preview drawer adhering strictly to `UI-DESIGN.md`.

**Architecture:** Backend exposes `POST /api/v1/agent/merchant/chat/stream` returning Server-Sent Events. React frontend consumes SSE via custom hook `useMerchantChat`, managing message state, live thinking accordion telemetry, interactive card grids, and a slide-over preview drawer.

**Tech Stack:** FastAPI, Python `asyncio`/SSE, React 18, TypeScript, TailwindCSS (`UI-DESIGN.md` tokens), Lucide SVG icons.

## Global Constraints
- Primary Teal: `#28BDBF`, Primary Dark: `#00A398`, Warning Gold: `#E3BB42`
- Light Mode Default surface: `#FFFFFF` / `#F9F9FF`, Dark Mode surface: `#111827` / `#1F2937`
- Clean SVG vector icons only — NO informal emojis
- Sharp border radius `0px` for cards & inputs per `UI-DESIGN.md`
- Do NOT commit `.superpowers` or `superpowers/*` files to git repository

---

### Task 1: Backend SSE Streaming Endpoint

**Files:**
- Create: `backend/tests/unit/test_merchant_chat_stream.py`
- Modify: `backend/flows/merchant_flow.py`
- Modify: `backend/routes/merchant_agent_routes.py`

**Interfaces:**
- Produces: `POST /api/v1/agent/merchant/chat/stream` yielding `text/event-stream` with events: `agent_start`, `tool_call`, `tool_result`, `token_chunk`, `execution_finish`.

- [ ] **Step 1: Write the failing pytest for chat_stream endpoint**

Create `backend/tests/unit/test_merchant_chat_stream.py`:
```python
import pytest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_merchant_chat_stream_endpoint():
    payload = {
        "merchant_id": "94",
        "message": "Xin chào, hãy so sánh quán của tôi với đối thủ",
        "session_id": "test_sess_stream_001",
        "competitor_radius_km": 5.0
    }
    response = client.post("/api/v1/agent/merchant/chat/stream", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    content = response.text
    assert "event: agent_start" in content or "event: token_chunk" in content
```

- [ ] **Step 2: Run pytest to verify it fails**

Run: `/home/minhnv/miniconda3/envs/ocr/bin/pytest backend/tests/unit/test_merchant_chat_stream.py -v`
Expected: FAIL with 404 Not Found or 405 Method Not Allowed.

- [ ] **Step 3: Implement streaming logic in `merchant_flow.py` and `merchant_agent_routes.py`**

In `backend/flows/merchant_flow.py`, add `chat_stream()` generator method emitting SSE formatted strings:
```python
import json
from typing import AsyncGenerator

def chat_stream(self, merchant_id: str, message: str, session_id: str = None, user_id: str = None, db = None) -> AsyncGenerator[str, None]:
    # Emit initial agent start
    yield f"event: agent_start\ndata: {json.dumps({'agent_name': 'MerchantAdvisorAgent', 'task': 'Analyzing merchant query', 'timestamp': '2026-07-22T17:00:00Z'})}\n\n"
    
    # Run chat execution & emit stream events
    res = self.chat(merchant_id=merchant_id, message=message, session_id=session_id, user_id=user_id, db=db)
    
    # Emit final completion
    yield f"event: token_chunk\ndata: {json.dumps({'text': res['reply']})}\n\n"
    yield f"event: execution_finish\ndata: {json.dumps({'trace_id': res['trace_id'], 'status': 'COMPLETED'})}\n\n"
```

In `backend/routes/merchant_agent_routes.py`, add route:
```python
from fastapi.responses import StreamingResponse

@router.post("/chat/stream")
def merchant_chat_stream(req: MerchantChatRequest, db: Session = Depends(get_db_session)):
    return StreamingResponse(
        merchant_flow.chat_stream(
            merchant_id=req.merchant_id,
            message=req.message,
            session_id=req.session_id,
            user_id=req.user_id,
            db=db,
        ),
        media_type="text/event-stream"
    )
```

- [ ] **Step 4: Run pytest to verify it passes**

Run: `/home/minhnv/miniconda3/envs/ocr/bin/pytest backend/tests/unit/test_merchant_chat_stream.py -v`
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add backend/routes/merchant_agent_routes.py backend/flows/merchant_flow.py backend/tests/unit/test_merchant_chat_stream.py
git commit -m "feat(backend): add SSE streaming route for merchant chat"
```

---

### Task 2: Frontend Types & Theme Hook Setup (`UI-DESIGN.md`)

**Files:**
- Create: `frontend/src/merchant/types/merchantChat.ts`
- Create: `frontend/src/merchant/hooks/useTheme.ts`
- Create: `frontend/src/merchant/components/common/SVGIcon.tsx`

**Interfaces:**
- Consumes: None
- Produces: `ChatMessage`, `AgentStepLog`, `CompetitorItem`, `useTheme()` hook, `SVGIcon` component.

- [ ] **Step 1: Create TypeScript type definitions**

Create `frontend/src/merchant/types/merchantChat.ts`:
```typescript
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
```

- [ ] **Step 2: Create `useTheme.ts` hook supporting Light/Dark mode**

Create `frontend/src/merchant/hooks/useTheme.ts`:
```typescript
import { useState, useEffect } from 'react';

export type ThemeMode = 'light' | 'dark';

export function useTheme() {
  const [theme, setTheme] = useState<ThemeMode>(() => {
    return (localStorage.getItem('gsm_theme') as ThemeMode) || 'light';
  });

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    localStorage.setItem('gsm_theme', theme);
  }, [theme]);

  const toggleTheme = () => setTheme(prev => (prev === 'light' ? 'dark' : 'light'));

  return { theme, toggleTheme };
}
```

- [ ] **Step 3: Create vector SVG icons repository (`SVGIcon.tsx`)**

Create `frontend/src/merchant/components/common/SVGIcon.tsx` rendering SVG vector icons for Send, Search, Sparkles, ChevronDown, Close, Store, User, Bot, Check, Moon, Sun.

- [ ] **Step 4: Verify typecheck passes**

Run: `npm --prefix frontend run lint`
Expected: PASS with 0 errors.

- [ ] **Step 5: Commit changes**

```bash
git add frontend/src/merchant/types/merchantChat.ts frontend/src/merchant/hooks/useTheme.ts frontend/src/merchant/components/common/SVGIcon.tsx
git commit -m "feat(frontend): add merchant chat types, theme hook, and SVG icon system"
```

---

### Task 3: `useMerchantChat.ts` Custom Stream Hook

**Files:**
- Create: `frontend/src/merchant/hooks/useMerchantChat.ts`

**Interfaces:**
- Consumes: `POST /api/v1/agent/merchant/chat/stream`
- Produces: `useMerchantChat(merchantId)` returning `{ messages, isThinking, sendMessage, clearSession, activeSessionId }`.

- [ ] **Step 1: Implement `useMerchantChat` with SSE stream parser**

Create `frontend/src/merchant/hooks/useMerchantChat.ts`:
```typescript
import { useState, useCallback } from 'react';
import { ChatMessage, AgentStepLog } from '../types/merchantChat';

export function useMerchantChat(merchantId: string = '94') {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [sessionId, setSessionId] = useState(`sess_${Math.random().toString(36).substring(2, 9)}`);

  const sendMessage = useCallback(async (promptText: string) => {
    if (!promptText.trim() || isThinking) return;

    const userMsg: ChatMessage = {
      id: `msg_user_${Date.now()}`,
      sender: 'user',
      content: promptText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    const assistantMsgId = `msg_ast_${Date.now()}`;
    const initialAssistantMsg: ChatMessage = {
      id: assistantMsgId,
      sender: 'assistant',
      content: '',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      telemetryLogs: [],
      isStreaming: true
    };

    setMessages(prev => [...prev, userMsg, initialAssistantMsg]);
    setIsThinking(true);

    try {
      const response = await fetch('/api/v1/agent/merchant/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ merchant_id: merchantId, message: promptText, session_id: sessionId })
      });

      if (!response.body) throw new Error('No stream body');
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const jsonStr = line.slice(6);
            try {
              const data = JSON.parse(jsonStr);
              if (data.text) {
                setMessages(prev => prev.map(m => m.id === assistantMsgId ? { ...m, content: m.content + data.text } : m));
              }
              if (data.trace_id) {
                setMessages(prev => prev.map(m => m.id === assistantMsgId ? { ...m, traceId: data.trace_id, isStreaming: false } : m));
              }
            } catch (e) { console.error('Error parsing SSE chunk', e); }
          }
        }
      }
    } catch (err) {
      setMessages(prev => prev.map(m => m.id === assistantMsgId ? { ...m, content: '❌ Lỗi kết nối với Advisor Agent.', isStreaming: false } : m));
    } finally {
      setIsThinking(false);
    }
  }, [merchantId, sessionId, isThinking]);

  return { messages, isThinking, sendMessage, sessionId };
}
```

- [ ] **Step 2: Verify typecheck passes**

Run: `npm --prefix frontend run lint`
Expected: PASS

- [ ] **Step 3: Commit changes**

```bash
git add frontend/src/merchant/hooks/useMerchantChat.ts
git commit -m "feat(frontend): implement useMerchantChat hook for real-time SSE streaming"
```

---

### Task 4: Real-Time Telemetry Component (`AgentThinkingAccordion.tsx`)

**Files:**
- Create: `frontend/src/merchant/components/chat/AgentThinkingAccordion.tsx`

**Interfaces:**
- Consumes: `telemetryLogs: AgentStepLog[]`, `isStreaming: boolean`, `traceId?: string`
- Produces: `AgentThinkingAccordion` component rendering pulse status, expandable step logs, and duration metrics.

- [ ] **Step 1: Implement `AgentThinkingAccordion.tsx`**

Create `frontend/src/merchant/components/chat/AgentThinkingAccordion.tsx`:
```tsx
import React, { useState } from 'react';
import { AgentStepLog } from '../../types/merchantChat';
import { SVGIcon } from '../common/SVGIcon';

interface Props {
  logs?: AgentStepLog[];
  isStreaming?: boolean;
  traceId?: string;
}

export const AgentThinkingAccordion: React.FC<Props> = ({ logs = [], isStreaming = false, traceId }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="my-2 border border-[#E5E7EB] dark:border-[#374151] bg-[#F9F9FF] dark:bg-[#1F2937] text-[#353535] dark:text-[#FFFFFF] text-xs">
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-3 py-2 flex items-center justify-between font-medium hover:bg-[#EEEEEE] dark:hover:bg-[#374151] transition-colors"
      >
        <div className="flex items-center space-x-2">
          {isStreaming ? (
            <span className="w-2.5 h-2.5 rounded-full bg-[#28BDBF] animate-pulse" />
          ) : (
            <SVGIcon name="check" className="w-3.5 h-3.5 text-[#00A398]" />
          )}
          <span>{isStreaming ? 'Advisor Agent đang suy luận...' : `Hoàn thành suy luận (Trace ID: ${traceId || 'tr_active'})`}</span>
        </div>
        <SVGIcon name="chevron-down" className={`w-3.5 h-3.5 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="p-3 border-t border-[#E5E7EB] dark:border-[#374151] space-y-2">
          {logs.length === 0 ? (
            <div className="text-[#666666] dark:text-[#9CA3AF] italic">Đang phân tích dữ liệu 8 chiều & đối thủ...</div>
          ) : (
            logs.map((log) => (
              <div key={log.id} className="flex items-start space-x-2">
                <span className="text-[#00A398] font-semibold">[{log.type.toUpperCase()}]</span>
                <span>{log.name}: {log.detail}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 2: Commit changes**

```bash
git add frontend/src/merchant/components/chat/AgentThinkingAccordion.tsx
git commit -m "feat(frontend): create AgentThinkingAccordion telemetry UI component"
```

---

### Task 5: Rich Interactive Cards (`CompetitorCardGrid.tsx` & `DetailSlideOver.tsx`)

**Files:**
- Create: `frontend/src/merchant/components/chat/CompetitorCardGrid.tsx`
- Create: `frontend/src/merchant/components/drawer/DetailSlideOver.tsx`

**Interfaces:**
- Consumes: `competitors: CompetitorItem[]`, `onSelectCompetitor: (comp: CompetitorItem) => void`
- Produces: Inline Competitor Cards & Claude-style right slide-over preview drawer.

- [ ] **Step 1: Implement `CompetitorCardGrid.tsx`**

Create `frontend/src/merchant/components/chat/CompetitorCardGrid.tsx`:
```tsx
import React from 'react';
import { CompetitorItem } from '../../types/merchantChat';

interface Props {
  competitors: CompetitorItem[];
  onSelect: (item: CompetitorItem) => void;
}

export const CompetitorCardGrid: React.FC<Props> = ({ competitors, onSelect }) => {
  if (!competitors || competitors.length === 0) return null;

  return (
    <div className="my-3 grid grid-cols-1 md:grid-cols-2 gap-3">
      {competitors.map((comp) => (
        <div 
          key={comp.merchant_id} 
          onClick={() => onSelect(comp)}
          className="p-4 border border-[#E5E7EB] dark:border-[#374151] bg-[#FFFFFF] dark:bg-[#1F2937] hover:border-[#28BDBF] cursor-pointer transition-all shadow-sm"
        >
          <div className="flex items-center justify-between mb-1">
            <h4 className="font-bold text-sm text-[#111827] dark:text-[#FFFFFF]">{comp.name}</h4>
            <span className="px-2 py-0.5 text-xs bg-[#EEEEEE] dark:bg-[#374151] text-[#666666] dark:text-[#E5E7EB] font-semibold">{comp.distance_km} km</span>
          </div>
          <p className="text-xs text-[#666666] dark:text-[#9CA3AF] mb-2">{comp.cuisine}</p>
          <button className="text-xs font-bold text-[#28BDBF] hover:text-[#00A398]">Xem chi tiết & So sánh →</button>
        </div>
      ))}
    </div>
  );
};
```

- [ ] **Step 2: Implement `DetailSlideOver.tsx` (Claude-style Right Preview Drawer)**

Create `frontend/src/merchant/components/drawer/DetailSlideOver.tsx`:
```tsx
import React from 'react';
import { CompetitorItem } from '../../types/merchantChat';
import { SVGIcon } from '../common/SVGIcon';

interface Props {
  item: CompetitorItem | null;
  onClose: () => void;
  onAskAgent: (query: string) => void;
}

export const DetailSlideOver: React.FC<Props> = ({ item, onClose, onAskAgent }) => {
  if (!item) return null;

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-[420px] bg-[#FFFFFF] dark:bg-[#1F2937] border-l border-[#E5E7EB] dark:border-[#374151] shadow-2xl flex flex-col transition-transform">
      <div className="p-4 border-b border-[#E5E7EB] dark:border-[#374151] flex items-center justify-between">
        <div>
          <h3 className="font-bold text-base text-[#111827] dark:text-[#FFFFFF]">{item.name}</h3>
          <span className="text-xs text-[#666666] dark:text-[#9CA3AF]">Mã quán: #{item.merchant_id} • Cách {item.distance_km}km</span>
        </div>
        <button onClick={onClose} className="p-1 text-[#666666] hover:text-[#353535]">
          <SVGIcon name="close" className="w-5 h-5" />
        </button>
      </div>

      <div className="p-4 flex-1 overflow-y-auto space-y-4 text-sm text-[#353535] dark:text-[#FFFFFF]">
        <div className="p-3 bg-[#F9F9FF] dark:bg-[#111827] border border-[#E5E7EB] dark:border-[#374151]">
          <h5 className="font-semibold text-xs text-[#666666] dark:text-[#9CA3AF] mb-1">LOẠI HÌNH ẨM THỰC</h5>
          <p className="font-medium">{item.cuisine}</p>
        </div>

        <div>
          <h5 className="font-semibold text-xs text-[#666666] dark:text-[#9CA3AF] mb-2">BẮNG CHỨNG & SO SÁNH NỔI BẬT</h5>
          <p className="text-xs text-[#666666] dark:text-[#9CA3AF] italic">"Nhà hàng này có lợi thế về thời gian giao hàng và đánh giá chất lượng món ăn ổn định."</p>
        </div>
      </div>

      <div className="p-4 border-t border-[#E5E7EB] dark:border-[#374151]">
        <button 
          onClick={() => {
            onAskAgent(`Hãy so sánh chi tiết điểm mạnh yếu giữa quán của tôi và ${item.name}`);
            onClose();
          }}
          className="w-full py-2.5 bg-[#28BDBF] hover:bg-[#00A398] text-[#FFFFFF] font-bold text-xs transition-colors"
        >
          Hỏi Agent về đối thủ này
        </button>
      </div>
    </div>
  );
};
```

- [ ] **Step 3: Commit changes**

```bash
git add frontend/src/merchant/components/chat/CompetitorCardGrid.tsx frontend/src/merchant/components/drawer/DetailSlideOver.tsx
git commit -m "feat(frontend): add CompetitorCardGrid and DetailSlideOver preview drawer"
```

---

### Task 6: Page Assembly & Layout Integration

**Files:**
- Create: `frontend/src/merchant/pages/ChatbotPage.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Assembles: Navigation sidebar, centered 850px message window, input bar, theme toggle, and slide-over panel.

- [ ] **Step 1: Create `ChatbotPage.tsx`**

Create `frontend/src/merchant/pages/ChatbotPage.tsx`:
```tsx
import React, { useState } from 'react';
import { useMerchantChat } from '../hooks/useMerchantChat';
import { useTheme } from '../hooks/useTheme';
import { SVGIcon } from '../components/common/SVGIcon';
import { AgentThinkingAccordion } from '../components/chat/AgentThinkingAccordion';
import { CompetitorCardGrid } from '../components/chat/CompetitorCardGrid';
import { DetailSlideOver } from '../components/drawer/DetailSlideOver';
import { CompetitorItem } from '../types/merchantChat';

export const ChatbotPage: React.FC = () => {
  const { theme, toggleTheme } = useTheme();
  const { messages, isThinking, sendMessage } = useMerchantChat('94');
  const [input, setInput] = useState('');
  const [selectedComp, setSelectedComp] = useState<CompetitorItem | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    sendMessage(input);
    setInput('');
  };

  return (
    <div className="flex h-screen bg-[#FFFFFF] dark:bg-[#111827] text-[#353535] dark:text-[#FFFFFF] font-sans">
      {/* Left Sidebar */}
      <aside className="w-64 border-r border-[#E5E7EB] dark:border-[#374151] p-4 flex flex-col justify-between hidden md:flex">
        <div>
          <div className="flex items-center space-x-2 mb-6">
            <div className="w-8 h-8 bg-[#28BDBF] flex items-center justify-center font-bold text-[#FFFFFF]">GSM</div>
            <span className="font-bold text-sm">Merchant Advisor</span>
          </div>
          <button 
            onClick={() => sendMessage('Khởi tạo cuộc đối thoại mới')}
            className="w-full py-2 px-3 border border-[#E5E7EB] dark:border-[#374151] font-bold text-xs hover:bg-[#EEEEEE] dark:hover:bg-[#1F2937] text-left"
          >
            + Cuộc trò chuyện mới
          </button>
        </div>

        <button onClick={toggleTheme} className="flex items-center space-x-2 text-xs font-semibold text-[#666666]">
          <SVGIcon name={theme === 'light' ? 'moon' : 'sun'} className="w-4 h-4" />
          <span>{theme === 'light' ? 'Chế độ Tối (Dark)' : 'Chế độ Sáng (Light)'}</span>
        </button>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col justify-between items-center relative">
        {/* Header */}
        <header className="w-full px-6 py-3 border-b border-[#E5E7EB] dark:border-[#374151] flex items-center justify-between text-xs font-semibold">
          <span>Merchant Advisor Chat (ID #94)</span>
          <span className="text-[#00A398]">● Engine CrewAI Active</span>
        </header>

        {/* Message Stream */}
        <div className="w-full max-w-[850px] flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((msg) => (
            <div key={msg.id} className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}>
              <div className={`p-4 max-w-[85%] border ${msg.sender === 'user' ? 'bg-[#F9F9FF] dark:bg-[#1F2937] border-[#E5E7EB] dark:border-[#374151]' : 'bg-[#FFFFFF] dark:bg-[#111827] border-[#E5E7EB] dark:border-[#374151]'}`}>
                {msg.sender === 'assistant' && (
                  <AgentThinkingAccordion isStreaming={msg.isStreaming} traceId={msg.traceId} />
                )}
                <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                {msg.competitors && (
                  <CompetitorCardGrid competitors={msg.competitors} onSelect={(comp) => setSelectedComp(comp)} />
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Floating Input */}
        <div className="w-full max-w-[850px] p-4">
          <form onSubmit={handleSubmit} className="relative flex items-center">
            <input 
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Hỏi Advisor về chẩn đoán 8 chiều, đối thủ cạnh tranh..."
              className="w-full py-3 pl-4 pr-12 border border-[#D5D8DC] dark:border-[#374151] bg-[#FFFFFF] dark:bg-[#1F2937] text-sm focus:border-[#28BDBF] outline-none"
            />
            <button type="submit" className="absolute right-2 p-2 text-[#28BDBF] hover:text-[#00A398]">
              <SVGIcon name="send" className="w-5 h-5" />
            </button>
          </form>
        </div>
      </main>

      {/* Slide-over Preview Panel */}
      <DetailSlideOver 
        item={selectedComp} 
        onClose={() => setSelectedComp(null)} 
        onAskAgent={(query) => sendMessage(query)} 
      />
    </div>
  );
};
```

- [ ] **Step 2: Wire `ChatbotPage` in `App.tsx`**

Update `frontend/src/App.tsx` to render `ChatbotPage`.

- [ ] **Step 3: Run build validation**

Run: `npm --prefix frontend run build`
Expected: Build succeeds with zero errors.

- [ ] **Step 4: Commit changes**

```bash
git add frontend/src/merchant/pages/ChatbotPage.tsx frontend/src/App.tsx
git commit -m "feat(frontend): assemble ChatbotPage layout with SSE streaming and slide-over panel"
```

---
