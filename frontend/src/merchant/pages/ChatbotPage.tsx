import { useEffect, useMemo, useRef, useState } from 'react';
import {
  fetchDemoTargetMerchants,
  fetchMerchantProfile,
} from '../api/merchantProfileApi';
import { ChatHeader } from '../components/chat/ChatHeader';
import { ChatInput } from '../components/chat/ChatInput';
import { MessageList } from '../components/chat/MessageList';
import { DetailSlideOver } from '../components/drawer/DetailSlideOver';
import { FloatingRunState } from '../components/monitoring/FloatingRunState';
import { SidebarNav } from '../components/sidebar/SidebarNav';
import { MerchantDetailModal } from '../components/modal/MerchantDetailModal';
import { useMerchantChat } from '../hooks/useMerchantChat';
import type { MerchantOption } from '../components/sidebar/SidebarNav';
import type { ChatMessage, AnalyzedMerchant } from '../types/merchantChat';

export const ChatbotPage = () => {
  const [bootstrap, setBootstrap] = useState<{
    merchants: MerchantOption[];
    initialMerchantId: string;
  } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchDemoTargetMerchants()
      .then((targets) => {
        if (!active) return;
        if (targets.length === 0) {
          setLoadError('Chưa có merchant nào được bật cho demo.');
          return;
        }
        const merchants = targets.map((merchant) => ({
          id: merchant.merchant_id,
          name: merchant.name,
          city: merchant.city,
          type: merchant.cuisine,
        }));
        const storedId = localStorage.getItem('merchant_dev_context');
        const initialMerchantId = merchants.some((merchant) => merchant.id === storedId)
          ? storedId!
          : merchants[0].id;
        localStorage.setItem('merchant_dev_context', initialMerchantId);
        setBootstrap({ merchants, initialMerchantId });
      })
      .catch(() => {
        if (active) setLoadError('Không thể tải danh sách merchant demo.');
      });
    return () => {
      active = false;
    };
  }, []);

  if (loadError) {
    return <main className="merchant-bootstrap-state" role="alert">{loadError}</main>;
  }
  if (!bootstrap) {
    return <main className="merchant-bootstrap-state" aria-busy="true">Đang tải merchant demo…</main>;
  }
  return (
    <ChatbotWorkspace
      merchants={bootstrap.merchants}
      initialMerchantId={bootstrap.initialMerchantId}
    />
  );
};

function ChatbotWorkspace({
  merchants,
  initialMerchantId,
}: {
  merchants: MerchantOption[];
  initialMerchantId: string;
}) {
  const [merchantId, setMerchantId] = useState(initialMerchantId);
  const [merchantName, setMerchantName] = useState(`Merchant #${initialMerchantId}`);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [inspectedMessage, setInspectedMessage] = useState<ChatMessage | null>(null);
  const [selectedDetailMerchant, setSelectedDetailMerchant] = useState<AnalyzedMerchant | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const {
    messages,
    sessions,
    isThinking,
    sendMessage,
    switchSession,
    createNewSession,
    deleteSession,
    activeSessionId,
    liveTraceEvents = [],
  } = useMerchantChat(merchantId);

  useEffect(() => {
    let active = true;
    fetchMerchantProfile(merchantId)
      .then((profile) => {
        if (active) setMerchantName(profile.metadata?.name || `Merchant #${merchantId}`);
      })
      .catch(() => active && setMerchantName(`Merchant #${merchantId}`));
    return () => { active = false; };
  }, [merchantId]);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  const activeEvents = useMemo(() => {
    const responseEvents = [...messages].reverse().find((message) => message.sender === 'assistant')?.traceEvents;
    return isThinking ? liveTraceEvents : responseEvents ?? liveTraceEvents;
  }, [messages, isThinking, liveTraceEvents]);

  const changeMerchant = (id: string) => {
    localStorage.setItem('merchant_dev_context', id);
    setMerchantId(id);
    setInspectedMessage(null);
    setSelectedDetailMerchant(null);
  };

  return (
    <div className="merchant-observability-shell">
      {/* Left Sidebar Navigation */}
      <SidebarNav
        merchants={merchants}
        selectedMerchantId={merchantId}
        sessions={sessions}
        activeSessionId={activeSessionId}
        mobileOpen={mobileNavOpen}
        onMerchantChange={changeMerchant}
        onSelectSession={(id) => { switchSession(id); setMobileNavOpen(false); }}
        onDeleteSession={deleteSession}
        onNewChat={() => { createNewSession(); setMobileNavOpen(false); setInspectedMessage(null); setSelectedDetailMerchant(null); }}
        onClose={() => setMobileNavOpen(false)}
      />

      {/* Center Main Workspace */}
      <main className="chat-main-workspace">
        <ChatHeader merchantName={merchantName} onOpenMenu={() => setMobileNavOpen(true)} />

        <div className="page-header-banner">
          <h1 className="page-title">AI Chatbot</h1>
          <p className="page-subtitle">Trợ lý AI giúp bạn phân tích và đưa ra gợi ý chiến lược cho nhà hàng của bạn.</p>
        </div>

        <MessageList
          messages={messages}
          endRef={endRef}
          onOpenDetails={setInspectedMessage}
          onPrompt={sendMessage}
          onOpenMerchantDetail={(m) => setSelectedDetailMerchant(m)}
        />

        <ChatInput isThinking={isThinking} onSend={sendMessage} />
      </main>

      {/* Right Column: Session State & Map Panel */}
      <FloatingRunState
        sessionId={activeSessionId}
        events={activeEvents}
        isLive={isThinking}
        merchantId={merchantId}
        messages={messages}
        sessions={sessions}
        onDeleteSession={deleteSession}
        onOpenDetails={setInspectedMessage}
      />

      {/* Drawer overlay when inspected */}
      <DetailSlideOver message={inspectedMessage} merchantId={merchantId} onClose={() => setInspectedMessage(null)} />

      {/* Full Merchant Profile Detail Modal */}
      {selectedDetailMerchant && (
        <MerchantDetailModal
          merchant={selectedDetailMerchant}
          onClose={() => setSelectedDetailMerchant(null)}
        />
      )}
    </div>
  );
}
