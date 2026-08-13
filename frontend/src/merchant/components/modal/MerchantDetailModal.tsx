import { useEffect, useState } from 'react';
import { fetchMerchantProfile } from '../../api/merchantProfileApi';
import { getMerchantMap } from '../../api/mapApi';
import type { MerchantProfileData, AnalyzedMerchant } from '../../types/merchantChat';
import { MerchantMap } from '../map/MerchantMap';
import type { MerchantMapFeatureCollection } from '../../types/monitoring';

export function MerchantDetailModal({
  merchant,
  onClose,
  routeDistanceKm,
  ownerMerchantId,
}: {
  merchant: AnalyzedMerchant | null;
  onClose: () => void;
  routeDistanceKm?: number;
  ownerMerchantId: string;
}) {
  const [profile, setProfile] = useState<MerchantProfileData | null>(null);
  const [backendMap, setBackendMap] = useState<MerchantMapFeatureCollection | null>(null);
  const [loading, setLoading] = useState(false);

  const targetMerchantId = merchant?.merchant_id ?? '';

  useEffect(() => {
    if (!targetMerchantId) return;
    setLoading(true);
    setProfile(null);
    setBackendMap(null);

    Promise.all([
      fetchMerchantProfile(targetMerchantId).catch(() => null),
      getMerchantMap(ownerMerchantId, undefined, { candidateMerchantIds: [targetMerchantId] }).catch(() => null),
    ])
      .then(([profileData, mapData]) => {
        if (profileData) setProfile(profileData);
        if (mapData) setBackendMap(mapData);
      })
      .finally(() => setLoading(false));
  }, [targetMerchantId, ownerMerchantId]);

  if (!merchant) return null;

  // Extract REAL owner feature coordinates from backend map
  const ownerFeature = backendMap?.features.find(
    (f) => String(f.properties.role) === 'owner' || String(f.properties.role) === 'user_location',
  );
  const ownerCoords = ownerFeature?.geometry.coordinates as [number, number] | undefined;

  // Extract REAL target merchant feature coordinates from backend map or profile
  const targetFeature = backendMap?.features.find(
    (f) => String(f.properties.merchant_id) === String(targetMerchantId) && String(f.properties.role) !== 'owner',
  );

  const targetCoords = targetFeature?.geometry.coordinates as [number, number] | undefined;

  const distanceKm = routeDistanceKm ?? merchant.distance_km;
  const distanceText = distanceKm != null
    ? (distanceKm >= 1 ? `${distanceKm.toFixed(1)} km` : `${Math.round(distanceKm * 1000)}m`)
    : 'N/A';
  const rating = merchant.rating ?? merchant.ratings?.shopeefood ?? merchant.ratings?.foody ?? profile?.ratings?.shopeefood_avg ?? profile?.ratings?.foody_rating;

  const detailMapCollection: MerchantMapFeatureCollection | null = ownerCoords && targetCoords ? {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: ownerCoords },
        properties: { role: 'owner', name: 'Vị trí của bạn (Owner)' },
      },
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: targetCoords },
        properties: {
          role: 'recommended',
          merchant_id: targetMerchantId,
          name: merchant.name,
        },
      },
    ],
  } : null;

  const dimensions = profile?.dimensions ?? {};

  return (
    <div className="floating-map-modal-backdrop" onClick={onClose}>
      <div className="merchant-detail-modal-content" onClick={(e) => e.stopPropagation()}>
        <header className="merchant-modal-header">
          <div className="merchant-modal-title">
            <span className="badge-category-tag">{merchant.cuisine || profile?.metadata?.cuisine || 'F&B'}</span>
            <h2>{merchant.name}</h2>
            <p className="merchant-sub-location">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
              {profile?.metadata?.location?.address || merchant.address || 'Đang cập nhật địa chỉ'}
              {distanceText ? ` · ${distanceText}` : ''}
            </p>
          </div>
          <button type="button" className="btn-close-modal" onClick={onClose} aria-label="Đóng chi tiết">×</button>
        </header>

        <div className="merchant-modal-body chat-scrollbar">
          {loading ? (
            <div className="modal-loading-state">Đang tải hồ sơ merchant...</div>
          ) : (
            <>
              {/* Section 1: Overview Highlights */}
              <div className="modal-section-grid">
                <div className="stat-card-box">
                  <span className="stat-label">Đánh giá chung</span>
                  <div className="stat-value text-teal">
                    {rating != null ? `★ ${rating.toFixed(1)}` : 'N/A'}
                  </div>
                  <small>{profile?.ratings?.shopeefood_total_review ? `${profile.ratings.shopeefood_total_review.toLocaleString()}+ lượt đánh giá` : 'ShopeeFood'}</small>
                </div>
                <div className="stat-card-box">
                  <span className="stat-label">Khoảng cách</span>
                  <div className="stat-value">{distanceText}</div>
                  <small>{profile?.attributes?.delivery_stats?.avg_delivery_minutes ? `Giao hàng ~${Math.round(profile.attributes.delivery_stats.avg_delivery_minutes)} phút` : 'Theo lộ trình OSRM'}</small>
                </div>
                <div className="stat-card-box">
                  <span className="stat-label">Thời gian mở cửa</span>
                  <div className="stat-value">{profile?.metadata?.open_hours ? `${profile.metadata.open_hours.open} - ${profile.metadata.open_hours.close}` : 'N/A'}</div>
                  <small>Dữ liệu merchant</small>
                </div>
                <div className="stat-card-box">
                  <span className="stat-label">Tier đối tác</span>
                  <div className="stat-value text-gold">{profile?.tier || 'N/A'}</div>
                  <small>Dữ liệu merchant</small>
                </div>
              </div>

              {/* Section 2: 8-Dimension Performance Metrics */}
              <div className="modal-card-block">
                <h3>Chỉ số hiệu suất 8 chiều (8-Dimension Performance Profile)</h3>
                <div className="dimension-bars-list">
                  {Object.entries(dimensions).map(([key, dim]) => {
                    if (typeof dim !== 'object' || dim.score == null) return null;
                    const score = Number(dim.score);
                    const pct = Math.min(100, Math.max(0, (score / 5) * 100));
                    const labels: Record<string, string> = {
                      food_quality: 'Chất lượng món ăn',
                      delivery_quality: 'Tốc độ & Giao hàng',
                      packaging: 'Quy cách đóng gói',
                      service: 'Thái độ phục vụ',
                      waiting_time: 'Thời gian chờ làm món',
                      menu_diversity: 'Đa dạng thực đơn',
                      price_competitiveness: 'Cạnh tranh giá',
                    };
                    return (
                      <div className="dim-bar-row" key={key}>
                        <div className="dim-bar-label">
                          <span>{labels[key] || key}</span>
                          <strong>{score.toFixed(1)} / 5.0</strong>
                        </div>
                        <div className="dim-bar-track">
                          <div className="dim-bar-fill" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Section 3: Route Navigation Map */}
              <div className="modal-card-block">
                <h3>Bản đồ chỉ đường thực tế (Đường đi A → B)</h3>
                <div className="modal-map-wrapper">
                  {detailMapCollection
                    ? <MerchantMap featureCollection={detailMapCollection} selectedMerchantId={targetMerchantId} />
                    : <div className="compact-map-empty">Chưa có đủ tọa độ để vẽ đường đi.</div>}
                </div>
              </div>

              {/* Section 4: Trending Dishes */}
              {profile?.attributes?.trending_dishes && profile.attributes.trending_dishes.length > 0 && (
                <div className="modal-card-block">
                  <h3>Món ăn bán chạy & Trending</h3>
                  <ul className="dishes-chips-list">
                    {profile.attributes.trending_dishes.map((dish, idx) => (
                      <li key={idx} className="dish-chip">
                        <span className="dish-rank">#{dish.rank || idx + 1}</span>
                        <span className="dish-name">{dish.dish}</span>
                        <span className="dish-score">Score: {dish.trend_score}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
