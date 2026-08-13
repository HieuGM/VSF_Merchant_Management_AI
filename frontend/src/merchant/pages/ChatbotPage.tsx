import { useCallback, useEffect, useRef, useState } from 'react';
import {
  fetchDemoTargetMerchants,
  fetchMerchantProfile,
} from '../api/merchantProfileApi';
import { ChatHeader } from '../components/chat/ChatHeader';
import { ChatInput } from '../components/chat/ChatInput';
import { MessageList } from '../components/chat/MessageList';
import { DetailSlideOver } from '../components/drawer/DetailSlideOver';
import { SidebarNav } from '../components/sidebar/SidebarNav';
import { MerchantDetailModal } from '../components/modal/MerchantDetailModal';
import { RightSideMapPanel } from '../components/map/RightSideMapPanel';
import { useMerchantChat } from '../hooks/useMerchantChat';
import type { MerchantOption } from '../components/sidebar/SidebarNav';
import type { ChatMessage, AnalyzedMerchant } from '../types/merchantChat';

import { ReviewAnalysisPage } from './ReviewAnalysisPage';
import { MerchantInfoMenuPage } from './MerchantInfoMenuPage';
import { PolicyDocumentsPage } from './PolicyDocumentsPage';

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
  const [mobileMapOpen, setMobileMapOpen] = useState(false);
  const [activePage, setActivePage] = useState<'chatbot' | 'reviews' | 'info' | 'policies'>('chatbot');
  const [inspectedMessage, setInspectedMessage] = useState<ChatMessage | null>(null);
  const [inspectedTab, setInspectedTab] = useState<'results' | 'map' | 'trace'>('results');
  const [selectedDetailMerchant, setSelectedDetailMerchant] = useState<AnalyzedMerchant | null>(null);
  const [routeDistances, setRouteDistances] = useState<Record<string, number>>({});
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

  const changeMerchant = (id: string) => {
    localStorage.setItem('merchant_dev_context', id);
    setMerchantId(id);
    setInspectedMessage(null);
    setSelectedDetailMerchant(null);
  };

  const handleOpenDetails = (msg: ChatMessage, tab: 'results' | 'map' | 'trace' = 'results') => {
    setInspectedMessage(msg);
    setInspectedTab(tab);
  };
  const handleRouteCalculated = useCallback((id: string, distance: number) => {
    setRouteDistances((current) => current[id] === distance ? current : { ...current, [id]: distance });
  }, []);

  const latestMessageWithMerchants =
    messages.filter((m) => m.sender === 'assistant' && (m.analyzedMerchants?.length ?? 0) > 0).slice(-1)[0] ??
    messages.slice(-1)[0] ??
    null;

  return (
    <div className="merchant-observability-shell">
      {/* Column 1: Left Sidebar Navigation */}
      <SidebarNav
        merchants={merchants}
        selectedMerchantId={merchantId}
        sessions={sessions}
        activeSessionId={activeSessionId}
        mobileOpen={mobileNavOpen}
        activePage={activePage}
        onNavigate={setActivePage}
        onMerchantChange={changeMerchant}
        onSelectSession={(id) => { switchSession(id); setActivePage('chatbot'); setMobileNavOpen(false); }}
        onDeleteSession={deleteSession}
        onNewChat={() => { createNewSession(); setActivePage('chatbot'); setMobileNavOpen(false); setInspectedMessage(null); setSelectedDetailMerchant(null); }}
        onClose={() => setMobileNavOpen(false)}
      />

      {/* Column 2: Center Main Workspace */}
      <main className="chat-main-workspace overflow-y-auto">
        <ChatHeader
          merchantName={merchantName}
          onOpenMenu={() => setMobileNavOpen(true)}
          onOpenMobileMap={() => setMobileMapOpen(true)}
        />

        {activePage === 'reviews' ? (
          <ReviewAnalysisPage merchantId={merchantId} />
        ) : activePage === 'info' ? (
          <MerchantInfoMenuPage merchantId={merchantId} />
        ) : activePage === 'policies' ? (
          <PolicyDocumentsPage />
        ) : (
          <>
            {messages.length > 0 && (
              <div className="page-header-banner">
                <h1 className="page-title">AI Chatbot</h1>
                <p className="page-subtitle">Trợ lý AI giúp bạn phân tích và đưa ra gợi ý chiến lược cho nhà hàng của bạn.</p>
              </div>
            )}

            <MessageList
              messages={messages}
              endRef={endRef}
              onOpenDetails={handleOpenDetails}
              onPrompt={sendMessage}
              onOpenMerchantDetail={(m) => setSelectedDetailMerchant(m)}
              routeDistances={routeDistances}
            />

            <ChatInput isThinking={isThinking} onSend={sendMessage} />
          </>
        )}
      </main>

      {/* Column 3: Fixed Right-Side Map Panel (ALWAYS DISPLAYED ON DESKTOP) */}
      <aside className="right-panel-container">
        <RightSideMapPanel
          merchantId={merchantId}
          latestMessage={latestMessageWithMerchants}
          selectedMerchant={selectedDetailMerchant}
          onSelectMerchant={(m) => setSelectedDetailMerchant(m)}
          onRouteCalculated={handleRouteCalculated}
          routeDistances={routeDistances}
        />
      </aside>

      {/* Responsive Mobile Map Drawer/Sheet */}
      {mobileMapOpen && (
        <div className="mobile-map-modal-backdrop" onClick={() => setMobileMapOpen(false)}>
          <div className="mobile-map-modal-container" onClick={(e) => e.stopPropagation()}>
            <RightSideMapPanel
              merchantId={merchantId}
              latestMessage={latestMessageWithMerchants}
              selectedMerchant={selectedDetailMerchant}
              onSelectMerchant={(m) => setSelectedDetailMerchant(m)}
              onRouteCalculated={handleRouteCalculated}
              routeDistances={routeDistances}
              onCloseMobileMap={() => setMobileMapOpen(false)}
            />
          </div>
        </div>
      )}

      {/* Drawer overlay when inspected */}
      <DetailSlideOver
        message={inspectedMessage}
        merchantId={merchantId}
        initialTab={inspectedTab}
        onClose={() => setInspectedMessage(null)}
      />

      {/* Full Merchant Profile Detail Modal */}
      {selectedDetailMerchant && (
        <MerchantDetailModal
          merchant={selectedDetailMerchant}
          routeDistanceKm={routeDistances[selectedDetailMerchant.merchant_id]}
          ownerMerchantId={merchantId}
          onClose={() => setSelectedDetailMerchant(null)}
        />
      )}
    </div>
  );
}
