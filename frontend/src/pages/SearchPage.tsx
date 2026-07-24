/** UC-04 Restaurant Search Page — full-stack integration demo.

Phase 0b: Proves API contract + React integration work end-to-end.
Features:
- Text search + filters (cuisine, city, budget, location)
- Haversine-based nearby search
- Cache status display
- Trace ID for observability
*/
import { useState } from "react";
import { searchMerchants, type Merchant, type SearchFilters } from "../lib/api";
import "./SearchPage.css";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [cuisine, setCuisine] = useState("");
  const [city, setCity] = useState("");
  const [budget, setBudget] = useState("");
  const [useLocation, setUseLocation] = useState(false);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<Merchant[]>([]);
  const [traceId, setTraceId] = useState("");
  const [cacheStatus, setCacheStatus] = useState<"hit" | "miss" | "disabled">("disabled");
  const [error, setError] = useState("");

  const handleSearch = async () => {
    setLoading(true);
    setError("");
    setResults([]);

    try {
      const filters: SearchFilters = {
        query: query || undefined,
        cuisine: cuisine || undefined,
        city: city || undefined,
        budget: budget || undefined,
        limit: 20,
      };

      if (useLocation) {
        // Demo location (Saigon)
        filters.lat = 10.79;
        filters.lng = 106.66;
        filters.radius_km = 5;
      }

      const response = await searchMerchants(filters);

      setResults(response.merchants);
      setTraceId(response.trace_id);
      setCacheStatus(response.cache_status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  };

  const getCacheBadgeClass = () => {
    switch (cacheStatus) {
      case "hit":
        return "badge-hit";
      case "miss":
        return "badge-miss";
      default:
        return "badge-disabled";
    }
  };

  return (
    <div className="search-page">
      <div className="container">
        {/* Header */}
        <div className="header">
          <h1>🍽️ Tìm Nhà Hàng</h1>
          <p>UC-04 Search Demo — Full Stack Integration</p>
        </div>

        {/* Search Form */}
        <div className="card">
          <div className="form-grid">
            {/* Text Search */}
            <div className="form-group">
              <label>Tìm kiếm</label>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Tên, món ăn, cuisine..."
              />
            </div>

            {/* Cuisine */}
            <div className="form-group">
              <label>Cuisine</label>
              <input
                type="text"
                value={cuisine}
                onChange={(e) => setCuisine(e.target.value)}
                placeholder="Vietnamese, Japanese, Italian..."
              />
            </div>

            {/* City */}
            <div className="form-group">
              <label>Thành phố</label>
              <input
                type="text"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Ho Chi Minh City, Hanoi..."
              />
            </div>

            {/* Budget */}
            <div className="form-group">
              <label>Ngân sách</label>
              <select value={budget} onChange={(e) => setBudget(e.target.value)}>
                <option value="">Tất cả</option>
                <option value="student">Tiết kiệm (15k-50k)</option>
                <option value="standard">Trung cấp (50k-150k)</option>
                <option value="premium">Cao cấp (150k+)</option>
              </select>
            </div>
          </div>

          {/* Location Toggle */}
          <div className="checkbox-group">
            <label>
              <input
                type="checkbox"
                checked={useLocation}
                onChange={(e) => setUseLocation(e.target.checked)}
              />
              <span>
                Sử dụng vị trí demo (Saigon: 10.79, 106.66)
              </span>
            </label>
          </div>

          {/* Search Button */}
          <button
            onClick={handleSearch}
            disabled={loading}
            className="btn-search"
          >
            {loading ? "Đang tìm..." : "Tìm Kiếm"}
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="error">
            {error}
          </div>
        )}

        {/* Results */}
        {results.length > 0 && (
          <div className="card">
            {/* Metadata */}
            <div className="results-header">
              <div>
                <h2>Kết quả ({results.length})</h2>
                <p>
                  Cache:{" "}
                  <span className={`badge ${getCacheBadgeClass()}`}>
                    {cacheStatus.toUpperCase()}
                  </span>
                </p>
              </div>
              <div className="trace-info">
                <p>Trace ID:</p>
                <p>{traceId}</p>
              </div>
            </div>

            {/* Merchant List */}
            <div className="merchant-list">
              {results.map((merchant) => (
                <div key={merchant.merchant_id} className="merchant-card">
                  <div className="merchant-header">
                    <div className="merchant-info">
                      <h3>{merchant.name}</h3>
                      <p>{merchant.cuisine} • {merchant.city}</p>
                      {merchant.address && (
                        <p className="address">📍 {merchant.address}</p>
                      )}
                    </div>
                    <div className="merchant-meta">
                      {merchant.avg_rating && (
                        <div className="rating">
                          <span>⭐</span>
                          <span>{merchant.avg_rating.toFixed(1)}</span>
                        </div>
                      )}
                      {merchant.distance_km !== null && (
                        <div className="distance">
                          {merchant.distance_km.toFixed(1)} km
                        </div>
                      )}
                      <div className="match-score">
                        Match: {Math.round(merchant.match_score * 100)}%
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty State */}
        {!loading && results.length === 0 && !error && (
          <div className="card empty-state">
            <div className="icon">🔍</div>
            <h3>Bắt đầu tìm kiếm</h3>
            <p>Nhập từ khóa và bộ lọc để tìm nhà hàng phù hợp</p>
          </div>
        )}
      </div>
    </div>
  );
}
