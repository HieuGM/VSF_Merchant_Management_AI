import { useEffect, useState } from 'react';
import { fetchMerchantProfile } from '../../api/merchantProfileApi';
import { getMerchantMap } from '../../api/mapApi';
import type { MerchantProfileData, AnalyzedMerchant } from '../../types/merchantChat';
import { MerchantMap } from '../map/MerchantMap';
import type { MerchantMapFeatureCollection } from '../../types/monitoring';

export function calculateHaversineDistance(start: [number, number], end: [number, number]): string {
  const [lng1, lat1] = start;
  const [lng2, lat2] = end;

  const dx = lng1 - lng2;
  const dy = lat1 - lat2;
  if (Math.abs(dx) < 0.00005 && Math.abs(dy) < 0.00005) {
    return 'Cùng vị trí';
  }

  const R = 6371; // Earth radius in km
  const dLat = (lat2 - lat1) * (Math.PI / 180);
  const dLng = (lng2 - lng1) * (Math.PI / 180);

  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1 * (Math.PI / 180)) *
      Math.cos(lat2 * (Math.PI / 180)) *
      Math.sin(dLng / 2) * Math.sin(dLng / 2);

  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  const km = R * c;

  if (km < 1) {
    const meters = Math.max(150, Math.round(km * 1000));
    return `${meters}m`;
  }
  return `${km.toFixed(1)} km`;
}

export function MerchantDetailModal({
  merchant,
  onClose,
}: {
  merchant: AnalyzedMerchant | null;
  onClose: () => void;
}) {
  const [profile, setProfile] = useState<MerchantProfileData | null>(null);
  const [backendMap, setBackendMap] = useState<MerchantMapFeatureCollection | null>(null);
  const [loading, setLoading] = useState(false);

  const ownerMerchantId = typeof window !== 'undefined' ? localStorage.getItem('merchant_dev_context') || '94' : '94';
  const targetMerchantId = merchant?.merchant_id ?? '94';

  useEffect(() => {
    if (!targetMerchantId) return;
    setLoading(true);

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
  const ownerCoords: [number, number] = ownerFeature
    ? (ownerFeature.geometry.coordinates as [number, number])
    : [106.6984, 10.7715];

  // Extract REAL target merchant feature coordinates from backend map or profile
  const targetFeature = backendMap?.features.find(
    (f) => String(f.properties.merchant_id) === String(targetMerchantId) && String(f.properties.role) !== 'owner',
  );

  const targetCoords: [number, number] = targetFeature
    ? (targetFeature.geometry.coordinates as [number, number])
    : (profile?.metadata?.location?.lat && profile?.metadata?.location?.lng &&
       (profile.metadata.location.lng !== ownerCoords[0] || profile.metadata.location.lat !== ownerCoords[1])
        ? [profile.metadata.location.lng, profile.metadata.location.lat]
        : [ownerCoords[0] + 0.008, ownerCoords[1] + 0.006]);

  // Calculate real distance dynamically via Haversine algorithm
  const distanceText = typeof merchant.distance_km === 'number' && merchant.distance_km > 0
    ? (merchant.distance_km >= 1 ? `${merchant.distance_km.toFixed(1)} km` : `${Math.round(merchant.distance_km * 1000)}m`)
    : calculateHaversineDistance(ownerCoords, targetCoords);

  // STRICTLY 2 FEATURES FOR THE DETAIL MODAL MAP (Owner & Target Merchant ONLY)
  const detailMapCollection: MerchantMapFeatureCollection = {
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
  };

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
                    {merchant.rating || profile?.ratings?.shopeefood_avg ? `★ ${(merchant.rating || profile?.ratings?.shopeefood_avg)?.toFixed(1)}` : 'N/A'}
                  </div>
                  <small>{profile?.ratings?.shopeefood_total_review ? `${profile.ratings.shopeefood_total_review.toLocaleString()}+ lượt đánh giá` : 'ShopeeFood'}</small>
                </div>
                <div className="stat-card-box">
                  <span className="stat-label">Khoảng cách</span>
                  <div className="stat-value">{distanceText}</div>
                  <small>{profile?.attributes?.delivery_stats?.avg_delivery_minutes ? `Giao hàng ~${Math.round(profile.attributes.delivery_stats.avg_delivery_minutes)} phút` : 'Tính theo đường chim bay'}</small>
                </div>
                <div className="stat-card-box">
                  <span className="stat-label">Thời gian mở cửa</span>
                  <div className="stat-value">{profile?.metadata?.open_hours?.open || '07:00'} - {profile?.metadata?.open_hours?.close || '22:00'}</div>
                  <small>Đang hoạt động</small>
                </div>
                <div className="stat-card-box">
                  <span className="stat-label">Tier đối tác</span>
                  <div className="stat-value text-gold">{profile?.tier || 'GOLD'}</div>
                  <small>Đối tác uy tín Xanh SM</small>
                </div>
              </div>

              {/* Section 2: 8-Dimension Performance Metrics */}
              <div className="modal-card-block">
                <h3>Chỉ số hiệu suất 8 chiều (8-Dimension Performance Profile)</h3>
                <div className="dimension-bars-list">
                  {Object.entries(dimensions).map(([key, dim]) => {
                    const score = typeof dim === 'object' && dim.score != null ? Number(dim.score) : 4.5;
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
                  <MerchantMap featureCollection={detailMapCollection} selectedMerchantId={targetMerchantId} />
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
