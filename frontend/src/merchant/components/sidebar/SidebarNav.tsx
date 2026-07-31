import type { ChatSessionItem } from '../../types/merchantChat';

export interface MerchantOption {
  id: string;
  name: string;
  city?: string;
  type?: string;
}

export function SidebarNav({
  merchants,
  selectedMerchantId,
  sessions,
  activeSessionId,
  mobileOpen,
  onMerchantChange,
  onSelectSession,
  onDeleteSession,
  onNewChat,
  onClose,
}: {
  merchants: MerchantOption[];
  selectedMerchantId: string;
  sessions: ChatSessionItem[];
  activeSessionId: string;
  mobileOpen: boolean;
  onMerchantChange: (id: string) => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onNewChat: () => void;
  onClose: () => void;
}) {
  const selectedMerchant = merchants.find((m) => m.id === selectedMerchantId) || merchants[0];

  return (
    <>
      {mobileOpen && <button className="nav-scrim" type="button" onClick={onClose} aria-label="Đóng điều hướng" />}
      <aside className={`merchant-nav ${mobileOpen ? 'is-open' : ''}`}>
        {/* Brand Header */}
        <header className="nav-brand">
          <div className="brand-logo-text">
            <span className="brand-name">Xanh SM</span>
            <span className="brand-sub">Merchant AI</span>
          </div>
        </header>

        {/* Prominent New Chat Button */}
        <div className="new-chat-btn-wrap">
          <button type="button" className="btn-primary-new-chat" onClick={onNewChat} aria-label="Cuộc trò chuyện mới">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            <span>Cuộc trò chuyện mới</span>
          </button>
        </div>

        {/* Main Navigation Menu */}
        <nav className="nav-menu">
          <button type="button" className="nav-item">
            <svg className="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>
            <span>Overview</span>
          </button>

          <button type="button" className="nav-item">
            <svg className="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 20V10M12 20V4M6 20v-6"/></svg>
            <span>Review Analysis</span>
          </button>

          <button type="button" className="nav-item">
            <svg className="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            <span>Competitors</span>
          </button>

          <button type="button" className="nav-item">
            <svg className="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><circle cx="8" cy="16" r="1" fill="currentColor"/><circle cx="16" cy="16" r="1" fill="currentColor"/></svg>
            <span>AI Advisor</span>
          </button>

          <button type="button" className="nav-item">
            <svg className="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>
            <span>Discovery</span>
          </button>

          {/* Active Chatbot Item */}
          <button type="button" className="nav-item is-active" onClick={onNewChat}>
            <svg className="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            <span>AI Chatbot</span>
            <span className="nav-badge">Beta</span>
            <div className="active-indicator" />
          </button>
        </nav>

        {/* Sessions Sub-List */}
        {sessions.length > 0 && (
          <div className="sidebar-sessions">
            <div className="session-heading"><span>PHIÊN GẦN ĐÂY</span><b>{sessions.length}</b></div>
            <nav className="session-list chat-scrollbar">
              {sessions.map((session) => (
                <div className={`session-row ${session.session_id === activeSessionId ? 'is-active' : ''}`} key={session.session_id}>
                  <button type="button" onClick={() => onSelectSession(session.session_id)}>
                    <strong>{session.title || session.session_id}</strong>
                    <small>{session.last_message || session.updated_at || 'No message'}</small>
                  </button>
                  <button type="button" onClick={() => onDeleteSession(session.session_id)} aria-label={`Xóa ${session.title}`}>×</button>
                </div>
              ))}
            </nav>
          </div>
        )}

        {/* Bottom Menu & Demo Merchant Selector */}
        <div className="nav-bottom">
          <button type="button" className="nav-item">
            <svg className="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            <span>Settings</span>
          </button>

          <button type="button" className="nav-item">
            <svg className="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            <span>Support</span>
          </button>

          {/* Merchant Profile Selector Box (5-6 Demo Merchants) */}
          <div className="merchant-profile-card">
            <div className="merchant-avatar">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#28bdbf" strokeWidth="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
            </div>
            <div className="merchant-info">
              <span className="merchant-name">{selectedMerchant.name}</span>
              <span className="merchant-location">{selectedMerchant.city || 'TP. HCM'} · {selectedMerchant.type || 'F&B Merchant'}</span>
            </div>
            <select
              aria-label="Chọn Merchant"
              className="merchant-select-native"
              value={selectedMerchantId}
              onChange={(e) => onMerchantChange(e.target.value)}
            >
              {merchants.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({m.city || 'TP. HCM'})
                </option>
              ))}
            </select>
            <svg className="chevron-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 12 15 18 9"/></svg>
          </div>
        </div>
      </aside>
    </>
  );
}

