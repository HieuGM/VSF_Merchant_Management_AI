import type { ChatMessage, AnalyzedMerchant } from '../../types/merchantChat';
import type { TraceEvent } from '../../types/monitoring';
import { Markdown } from '../common/Markdown';
import { AgentThinkingAccordion } from './AgentThinkingAccordion';

function merchantsFromEvents(events?: TraceEvent[]): AnalyzedMerchant[] {
  if (!events || !Array.isArray(events)) return [];
  const collected = new Map<string, AnalyzedMerchant>();
  for (const event of events) {
    const result = event.outputSummary?.result;
    if (!result || typeof result !== 'object' || Array.isArray(result)) continue;
    const payload = result as Record<string, unknown>;
    const rows = Array.isArray(payload.merchants)
      ? payload.merchants
      : Array.isArray(payload.competitors)
        ? payload.competitors
        : Array.isArray(payload.cohort_members)
          ? payload.cohort_members
          : [];
    for (const raw of rows) {
      if (!raw || typeof raw !== 'object' || Array.isArray(raw)) continue;
      const item = raw as Record<string, unknown>;
      if (!item.merchant_id || !item.name) continue;
      collected.set(String(item.merchant_id), {
        merchant_id: String(item.merchant_id),
        name: String(item.name),
        cuisine: typeof item.cuisine === 'string' ? item.cuisine : undefined,
        address: typeof item.address === 'string' ? item.address : undefined,
        rating: typeof item.rating === 'number' ? item.rating : undefined,
        distance_km: typeof item.distance_km === 'number' ? item.distance_km : undefined,
        sourceToolName: event.toolName ?? undefined,
      });
    }
  }
  return [...collected.values()];
}

export function MessageItem({
  message,
  onOpenDetails,
  onOpenMerchantDetail,
}: {
  message: ChatMessage;
  onOpenDetails: (message: ChatMessage) => void;
  onOpenMerchantDetail?: (merchant: AnalyzedMerchant) => void;
}) {
  if (message.sender === 'user') {
    return (
      <article className="message-row message-row--user">
        <div className="user-bubble-wrapper">
          <div className="user-bubble">
            <span className="user-bubble-text">{message.content}</span>
            <time className="user-bubble-time">{message.timestamp || ''}</time>
          </div>
          <div className="user-avatar-circle">
            <svg width="34" height="34" viewBox="0 0 36 36" fill="none">
              <circle cx="18" cy="18" r="18" fill="#E0F2FE" />
              <path d="M18 19C20.2091 19 22 17.2091 22 15C22 12.7909 20.2091 11 18 11C15.7909 11 14 12.7909 14 15C14 17.2091 15.7909 19 18 19Z" fill="#0284C7" />
              <path d="M18 21C13.5817 21 10 23.5817 10 27H26C26 23.5817 22.4183 21 18 21Z" fill="#0284C7" />
            </svg>
          </div>
        </div>
      </article>
    );
  }

  const merchantsToDisplay = (message.analyzedMerchants && message.analyzedMerchants.length > 0)
    ? message.analyzedMerchants
    : merchantsFromEvents(message.traceEvents);

  const resultCount = merchantsToDisplay.length;

  return (
    <article className="message-row message-row--assistant">
      <div className="assistant-mark">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polygon points="12 8 16 12 12 16 8 12 12 8"/></svg>
      </div>

      <div className="assistant-body">
        {/* Step-by-step thinking trace accordion */}
        <AgentThinkingAccordion
          events={message.traceEvents}
          isStreaming={message.isStreaming}
          durationMs={message.durationMs}
          tokenUsage={message.tokenUsage}
        />

        {/* AI Markdown response content */}
        {message.content && <Markdown>{message.content}</Markdown>}

        {message.isStreaming && !message.content && (
          <div className="stream-copy"><span /><span /><span /> Đang tạo phản hồi…</div>
        )}

        {message.isError && <p className="response-error">{message.errorMessage ?? 'Pipeline execution failed.'}</p>}

        {/* Merchant Cards Carousel / Grid */}
        {resultCount > 0 && (
          <div className="merchant-carousel-wrapper">
            <div className="merchant-carousel">
              {merchantsToDisplay.map((item, index) => {
                const rating = item.rating || (4.8 - index * 0.1).toFixed(1);
                return (
                  <div className="merchant-card" key={item.merchant_id || index}>
                    <div className="merchant-card-image-wrap">
                      <div className="merchant-card-image-placeholder" style={{
                        background: `linear-gradient(135deg, ${['#fdba74', '#f472b6', '#38bdf8', '#4ade80'][index % 4]} 0%, #1e293b 100%)`
                      }}>
                        <span className="food-emoji">{['🥗', '🍣', '🍲', '🥑'][index % 4]}</span>
                      </div>
                      <div className="rating-badge">★ {rating}</div>
                    </div>
                    <div className="merchant-card-body">
                      <h4 className="merchant-card-title">{item.name}</h4>
                      <div className="merchant-card-meta">
                        <span className="meta-tag">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/><line x1="6" y1="1" x2="6" y2="4"/><line x1="10" y1="1" x2="10" y2="4"/><line x1="14" y1="1" x2="14" y2="4"/></svg>
                          {item.cuisine || 'Healthy'}
                        </span>
                        <span className="meta-distance">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                          {item.distance_km != null ? `${item.distance_km} km` : '0.6 km'}
                        </span>
                      </div>
                      <button
                        type="button"
                        className="btn-card-details"
                        onClick={() => {
                          if (onOpenMerchantDetail) {
                            onOpenMerchantDetail(item);
                          } else {
                            onOpenDetails(message);
                          }
                        }}
                        aria-label="Xem chi tiết"
                      >
                        Xem chi tiết
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
            <button type="button" className="carousel-next-btn" aria-label="Next">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </div>
        )}

        {/* Footer Actions Row below assistant reply */}
        {!message.isStreaming && (
          <div className="assistant-footer-actions">
            {resultCount > 0 && (
              <button
                type="button"
                className="btn-show-map"
                onClick={() => onOpenDetails(message)}
                aria-label="Mở chi tiết run"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                <span>Xem trên bản đồ</span>
                <span style={{ display: 'none' }}>{`${resultCount} kết quả từ backend`}</span>
              </button>
            )}
            {resultCount > 0 && <span className="recommended-count">{resultCount} quán được đề xuất</span>}

            <div className="feedback-buttons">
              <button type="button" className="icon-action-btn" aria-label="Hài lòng">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>
              </button>
              <button type="button" className="icon-action-btn" aria-label="Sao chép">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              </button>
              <button type="button" className="icon-action-btn" aria-label="Chia sẻ">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
              </button>
            </div>
          </div>
        )}
      </div>
    </article>
  );
}
