import { useEffect, useState } from 'react';
import { getMerchantMap } from '../../api/mapApi';
import type { ChatMessage, AnalyzedMerchant } from '../../types/merchantChat';
import type { MerchantMapFeatureCollection } from '../../types/monitoring';
import { MerchantMap } from './MerchantMap';

export function RightSideMapPanel({
  merchantId,
  latestMessage,
  selectedMerchant,
  onSelectMerchant,
  onCloseMobileMap,
}: {
  merchantId: string;
  latestMessage?: ChatMessage | null;
  selectedMerchant?: AnalyzedMerchant | null;
  onSelectMerchant?: (merchant: AnalyzedMerchant) => void;
  onCloseMobileMap?: () => void;
}) {
  const [featureCollection, setFeatureCollection] = useState<MerchantMapFeatureCollection | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isFloatingOpen, setIsFloatingOpen] = useState<boolean>(false);

  const candidates: AnalyzedMerchant[] = latestMessage?.analyzedMerchants ?? [];
  const selectedMerchantId = selectedMerchant?.merchant_id ?? null;

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    const candidateIds = candidates
      .map((item) => item.merchant_id)
      .filter((id): id is string => Boolean(id));

    getMerchantMap(merchantId, undefined, { candidateMerchantIds: candidateIds })
      .then((result) => {
        if (active) {
          setFeatureCollection(result);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : 'Không tải được bản đồ.');
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [merchantId, latestMessage?.id, candidates.length]);

  return (
    <>
      {/* Compact Right Side Panel Container */}
      <div className="compact-right-panel-shell">
        <div className="compact-panel-header">
          <div className="panel-header-copy">
            <h3>🗺️ Mini-Map</h3>
            <span className="panel-header-sub">
              {candidates.length > 0
                ? `${candidates.length} quán đề xuất`
                : 'Vị trí nhà hàng'}
            </span>
          </div>

          <div className="panel-header-actions">
            {/* Phóng to Floating Map button */}
            <button
              type="button"
              className="btn-expand-floating-map"
              onClick={() => setIsFloatingOpen(true)}
              title="Phóng to bản đồ"
              aria-label="Phóng to bản đồ"
            >
              <span>Phóng to</span>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="15 3 21 3 21 9"/>
                <polyline points="9 21 3 21 3 15"/>
                <line x1="21" y1="3" x2="14" y2="10"/>
                <line x1="3" y1="21" x2="10" y2="14"/>
              </svg>
            </button>

            {onCloseMobileMap && (
              <button
                type="button"
                className="mobile-panel-close-btn"
                onClick={onCloseMobileMap}
                aria-label="Đóng bản đồ"
              >
                ×
              </button>
            )}
          </div>
        </div>

        {/* Compact Map Box (height ~240px) */}
        <div className="compact-map-box" onClick={() => setIsFloatingOpen(true)}>
          {loading ? (
            <div className="compact-map-loading">
              <span className="spinner">⏳</span>
              <span>Đang tải bản đồ…</span>
            </div>
          ) : error ? (
            <div className="compact-map-error">
              <p>{error}</p>
            </div>
          ) : featureCollection && featureCollection.features.length > 0 ? (
            <>
              <MerchantMap
                featureCollection={featureCollection}
                selectedMerchantId={selectedMerchantId}
              />
              <div className="compact-map-overlay-badge">
                <span>Bấm để phóng to ⤢</span>
              </div>
            </>
          ) : (
            <div className="compact-map-empty">
              <p>Chưa có dữ liệu bản đồ.</p>
            </div>
          )}
        </div>

        {/* Candidate Chips List */}
        {candidates.length > 0 && (
          <div className="compact-candidates-box">
            <div className="candidates-title">Đề xuất ({candidates.length})</div>
            <div className="candidates-scroll-list">
              {candidates.map((merchant, idx) => {
                const isSelected = selectedMerchantId === merchant.merchant_id;
                return (
                  <button
                    type="button"
                    key={merchant.merchant_id || idx}
                    className={`candidate-map-card-btn ${isSelected ? 'is-selected' : ''}`}
                    onClick={() => onSelectMerchant?.(merchant)}
                  >
                    <span className="card-badge-num">{idx + 1}</span>
                    <div className="card-info-text">
                      <strong className="card-name">{merchant.name}</strong>
                      <span className="card-sub">{merchant.cuisine || merchant.city || 'F&B'}</span>
                    </div>
                    {merchant.distance_km != null && (
                      <span className="card-dist-pill">{merchant.distance_km} km</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Floating Map Modal with Blurred Backdrop (Giống Mobile UI / Glassmorphism) */}
      {isFloatingOpen && (
        <div className="floating-map-modal-backdrop" onClick={() => setIsFloatingOpen(false)}>
          <div className="floating-map-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="floating-map-header">
              <div className="floating-map-title">
                <h3>🗺️ Bản đồ Chi tiết & Vị trí</h3>
                <small>
                  {candidates.length > 0
                    ? `${candidates.length} nhà hàng đề xuất trên bản đồ`
                    : 'Tọa độ vị trí nhà hàng'}
                </small>
              </div>
              <button
                type="button"
                className="btn-close-floating-modal"
                onClick={() => setIsFloatingOpen(false)}
                aria-label="Đóng bản đồ phóng to"
              >
                ×
              </button>
            </div>

            <div className="floating-map-canvas-wrapper">
              {featureCollection && (
                <MerchantMap
                  featureCollection={featureCollection}
                  selectedMerchantId={selectedMerchantId}
                />
              )}
            </div>

            {candidates.length > 0 && (
              <div className="floating-map-footer">
                <span className="footer-label">Chọn quán để xem đường đi:</span>
                <div className="footer-chips-scroll">
                  {candidates.map((item, idx) => {
                    const isSelected = selectedMerchantId === item.merchant_id;
                    return (
                      <button
                        type="button"
                        key={item.merchant_id || idx}
                        className={`floating-chip-btn ${isSelected ? 'is-active' : ''}`}
                        onClick={() => onSelectMerchant?.(item)}
                      >
                        <span>{idx + 1}. {item.name}</span>
                        {item.distance_km != null && <small>{item.distance_km} km</small>}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
