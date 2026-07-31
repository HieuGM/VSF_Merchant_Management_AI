import { useEffect, useMemo, useState } from 'react';
import { getMerchantMap } from '../../api/mapApi';
import type { ChatMessage, ChatSessionItem } from '../../types/merchantChat';
import type { MerchantMapFeatureCollection, TraceEvent } from '../../types/monitoring';
import { MerchantMap } from '../map/MerchantMap';

export function FloatingRunState({
  sessionId,
  events,
  isLive,
  merchantId = '94',
  messages = [],
  sessions = [],
  selectedMerchantId: externalSelectedId = null,
  onDeleteSession,
}: {
  sessionId: string;
  events: TraceEvent[];
  isLive: boolean;
  merchantId?: string;
  messages?: ChatMessage[];
  sessions?: ChatSessionItem[];
  selectedMerchantId?: string | null;
  onDeleteSession?: (id: string) => void;
  onOpenDetails?: (message: ChatMessage) => void;
}) {
  const [open, setOpen] = useState(true);
  const [activeTab, setActiveTab] = useState<'results' | 'map'>('map');
  const [map, setMap] = useState<MerchantMapFeatureCollection | null>(null);
  const [mapError, setMapError] = useState('');
  const [floatingMapOpen, setFloatingMapOpen] = useState(false);
  const [internalSelectedId, setInternalSelectedId] = useState<string | null>(null);

  const selectedId = externalSelectedId ?? internalSelectedId;

  // Extract real session state & cache activity from events
  const derived = useMemo(() => {
    let state: Record<string, unknown> = {};
    const cache: Record<string, unknown>[] = [];
    let traceId = '';
    for (const event of events) {
      const payload = event.outputSummary;
      traceId = String(payload.trace_id ?? traceId);
      if (event.eventType === 'context' || event.eventType === 'session_state_updated') {
        const next = payload.session_state;
        if (next && typeof next === 'object' && !Array.isArray(next)) state = next as Record<string, unknown>;
      }
      if (event.eventType === 'cache') cache.push(payload);
    }
    return { state, cache, traceId };
  }, [events]);

  // Extract ONLY recommended merchants from the latest assistant response
  const candidates = useMemo(() => {
    const lastWithMerchants = [...messages].reverse().find(
      (m) => m.sender === 'assistant' && m.analyzedMerchants && m.analyzedMerchants.length > 0,
    );
    if (lastWithMerchants?.analyzedMerchants?.length) {
      return lastWithMerchants.analyzedMerchants;
    }
    return [];
  }, [messages]);

  // Real recent user queries
  const userQueries = useMemo(() => {
    const userMsgs = messages.filter((m) => m.sender === 'user').map((m) => m.content);
    if (userMsgs.length > 0) return userMsgs.slice(-3);
    const sessionTitles = sessions.map((s) => s.title || s.last_message).filter(Boolean) as string[];
    return sessionTitles.slice(-3);
  }, [messages, sessions]);

  // Fetch real GeoJSON Map from backend API (unconditionally loads merchant location, plus candidates when available)
  useEffect(() => {
    setMap(null);
    setMapError('');
    let active = true;
    const candidateIds = candidates.length > 0 ? candidates.map((item) => item.merchant_id) : undefined;

    getMerchantMap(merchantId, undefined, { candidateMerchantIds: candidateIds })
      .then((result) => active && setMap(result))
      .catch((error) => active && setMapError(error instanceof Error ? error.message : 'Không tải được bản đồ.'));
    return () => { active = false; };
  }, [merchantId, candidates.map((item) => item.merchant_id).join(',')]);

  useEffect(() => {
    if (externalSelectedId) {
      setFloatingMapOpen(true);
    }
  }, [externalSelectedId]);

  const selectedMerchantObj = candidates.find((c) => String(c.merchant_id) === String(selectedId));

  return (
    <>
      <aside className="right-panel-container" aria-label="Session and map panel">
        {/* Card 1: Real Session State Card (Scrollable) */}
        <div className="right-card session-state-card">
          <div className="right-card-header">
            <div className="card-header-left">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#00a398" strokeWidth="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/></svg>
              <span className="card-title">Session State <small>(Thu gọn)</small></span>
            </div>
            <div className="card-header-actions">
              <button type="button" onClick={() => setOpen(!open)} aria-label="Thu gọn session">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points={open ? "18 15 12 9 6 15" : "6 9 12 15 18 9"}/></svg>
              </button>
            </div>
          </div>

          {open && (
            <div className="right-card-body session-state-body-scroll chat-scrollbar">
              <div className="session-info-row">
                <span className="info-label">Phiên hiện tại</span>
                <span className="info-time">{isLive ? 'Live Stream' : 'Đang kết nối'} {isLive && <span className="live-indicator-dot" title="Live stream" />}</span>
              </div>
              <div className="session-id-tag">
                ID: <span>{sessionId || 'sess_active'}</span>
              </div>

              <div className="cache-items-row">
                <span className="info-label">Cache Items</span>
                <span className="cache-badge-pill">{derived.cache.length}</span>
              </div>
              {derived.cache.map((item, index) => (
                <div key={index} className="cache-item-detail">
                  <code>{String(item.status ?? 'cache')} · {String(item.cache_key ?? item.key ?? 'key')}</code>
                </div>
              ))}

              <div className="entities-section">
                <span className="info-label">Entities đã nhận diện</span>
                <div className="entities-tags">
                  {Object.keys(derived.state).length === 0 ? (
                    <span className="entity-chip text-muted">Chờ dữ liệu context...</span>
                  ) : (
                    Object.entries(derived.state).map(([key, val]) => (
                      <span className="entity-chip" key={key}>
                        {key}: {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                      </span>
                    ))
                  )}
                </div>
              </div>

              <div className="recent-queries-section">
                <span className="info-label">Truy vấn gần đây</span>
                {userQueries.length === 0 ? (
                  <p className="no-queries-text">Chưa có truy vấn trong phiên này.</p>
                ) : (
                  <ul className="queries-list">
                    {userQueries.map((query, idx) => (
                      <li key={idx}>
                        <span>{query}</span>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="9 18 15 12 9 6"/></svg>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {onDeleteSession && (
                <div className="session-footer">
                  <button type="button" className="btn-delete-session" onClick={() => onDeleteSession(sessionId)}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    <span>Xóa phiên</span>
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Card 2: Real Results & Map Panel */}
        <div className="right-card map-results-card">
          <div className="map-card-tabs-header">
            <div className="tabs-list">
              <button
                type="button"
                className={`tab-btn ${activeTab === 'results' ? 'is-active' : ''}`}
                onClick={() => setActiveTab('results')}
              >
                Kết quả ({candidates.length})
              </button>
              <button
                type="button"
                className={`tab-btn ${activeTab === 'map' ? 'is-active' : ''}`}
                onClick={() => setActiveTab('map')}
              >
                Bản đồ
                <div className="tab-indicator" />
              </button>
            </div>
          </div>

          <div className="map-card-body">
            {activeTab === 'map' ? (
              map ? (
                <div className="map-view-wrapper clickable-map-container" onClick={() => setFloatingMapOpen(true)} title="Phóng to bản đồ">
                  <MerchantMap
                    featureCollection={map}
                    selectedMerchantId={selectedId}
                  />
                  <div className="map-zoom-hint">Phóng to bản đồ ⤢</div>
                </div>
              ) : (
                <div className="map-preview-container">
                  <div className="map-vector-graphic">
                    <div className="user-location-pin" style={{ top: '45%', left: '48%' }} />
                  </div>
                  <div className="map-placeholder-hint">
                    {mapError || 'Gửi câu hỏi để hiển thị kết quả bản đồ thực từ backend.'}
                  </div>
                </div>
              )
            ) : (
              <div className="results-tab-content">
                {candidates.length === 0 ? (
                  <p className="no-queries-text">Chưa có danh sách merchant từ backend.</p>
                ) : (
                  <ul className="map-merchants-list">
                    {candidates.map((item, index) => (
                      <li
                        key={item.merchant_id || index}
                        className={`map-merchant-item ${selectedId === item.merchant_id ? 'is-selected' : ''}`}
                        onClick={() => {
                          setInternalSelectedId(item.merchant_id);
                          setFloatingMapOpen(true);
                        }}
                      >
                        <span className="num-circle">{index + 1}</span>
                        <span className="merchant-item-name">{item.name}</span>
                        <span className="merchant-item-distance">{item.distance_km != null ? `${item.distance_km} km` : ''}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {/* User Location Info */}
            <div className="user-location-row">
              <div className="blue-dot" />
              <div className="location-text">
                <strong>Vị trí của bạn</strong>
                <small>Not set</small>
              </div>
            </div>

            {/* Numbered Merchants List when on Map tab */}
            {activeTab === 'map' && candidates.length > 0 && (
              <ul className="map-merchants-list">
                {candidates.slice(0, 4).map((item, index) => (
                  <li
                    key={item.merchant_id || index}
                    className={`map-merchant-item ${selectedId === item.merchant_id ? 'is-selected' : ''}`}
                    onClick={() => {
                      setInternalSelectedId(item.merchant_id);
                      setFloatingMapOpen(true);
                    }}
                  >
                    <span className="num-circle">{index + 1}</span>
                    <span className="merchant-item-name">{item.name}</span>
                    <span className="merchant-item-distance">{item.distance_km != null ? `${item.distance_km} km` : ''}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </aside>

      {/* Floating Map Modal Overlay (Centered with Blurred Backdrop) */}
      {floatingMapOpen && (
        <div className="floating-map-modal-backdrop" onClick={() => setFloatingMapOpen(false)}>
          <div className="floating-map-modal-content" onClick={(e) => e.stopPropagation()}>
            <header className="floating-map-header">
              <div className="floating-map-title">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#00a398" strokeWidth="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                <div>
                  <h3>Bản đồ phân tích vị trí & đối thủ</h3>
                  <small>
                    {selectedMerchantObj ? `Đang chỉ đường tới: ${selectedMerchantObj.name}` : 'Vị trí của bạn & Các địa điểm đề xuất'}
                  </small>
                </div>
              </div>
              <button
                type="button"
                className="btn-close-modal"
                onClick={() => setFloatingMapOpen(false)}
                aria-label="Đóng bản đồ"
              >
                ×
              </button>
            </header>

            <div className="floating-map-body">
              {map ? (
                <MerchantMap
                  featureCollection={map}
                  selectedMerchantId={selectedId}
                />
              ) : (
                <div className="map-placeholder-hint">Đang tải vị trí bản đồ từ backend...</div>
              )}
            </div>

            {candidates.length > 0 && (
              <footer className="floating-map-footer">
                {candidates.map((m, idx) => (
                  <button
                    type="button"
                    key={m.merchant_id || idx}
                    className={`map-chip-btn ${selectedId === m.merchant_id ? 'is-active' : ''}`}
                    onClick={() => setInternalSelectedId(m.merchant_id)}
                  >
                    <span>{idx + 1}. {m.name}</span>
                    {m.distance_km != null && <small>({m.distance_km} km)</small>}
                  </button>
                ))}
              </footer>
            )}
          </div>
        </div>
      )}
    </>
  );
}



