/**
 * Explore screen — a browsable grid of restaurant cards backed by the merchant search
 * API (UC-04). Complements the conversational chat with a filter-driven view: cuisine
 * chips, budget, and "near me" all hit /api/v1/merchants/search.
 */
import { useCallback, useEffect, useState } from "react";
import { RestaurantCard } from "../components/restaurant-card";
import { searchMerchants, type Merchant, type SearchFilters } from "../../lib/api";
import { usePreferences } from "../hooks/use-preferences";
import "./customer-results.css";

const CUISINES = ["Việt", "Nhật", "Hàn", "Ý", "Thái", "Chay"];
const BUDGETS: Array<{ v: string; label: string }> = [
  { v: "", label: "Mọi giá" },
  { v: "student", label: "Tiết kiệm" },
  { v: "standard", label: "Trung cấp" },
  { v: "premium", label: "Cao cấp" },
];

export default function CustomerResults() {
  const { prefs } = usePreferences();
  const [query, setQuery] = useState("");
  const [cuisine, setCuisine] = useState("");
  const [budget, setBudget] = useState("");
  const [nearby, setNearby] = useState(prefs.useLocation);
  const [results, setResults] = useState<Merchant[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const run = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const filters: SearchFilters = {
        query: query || undefined,
        cuisine: cuisine || undefined,
        budget: budget || undefined,
        limit: 20,
      };
      if (nearby) {
        filters.lat = prefs.lat;
        filters.lng = prefs.lng;
        filters.radius_km = 5;
      }
      const res = await searchMerchants(filters);
      setResults(res.merchants);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được kết quả");
    } finally {
      setLoading(false);
    }
  }, [query, cuisine, budget, nearby, prefs.lat, prefs.lng]);

  // Initial + filter-change load (debounced lightly for typing).
  useEffect(() => {
    const t = setTimeout(run, 300);
    return () => clearTimeout(t);
  }, [run]);

  return (
    <div className="cres cust-scroll">
      <header className="cres__head">
        <h2 className="cres__title">Khám phá quán ăn</h2>
        <p className="cres__sub">Lọc theo ẩm thực, ngân sách và vị trí</p>
      </header>

      <div className="cres__filters cust-glass-strong">
        <input
          className="cust-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Tìm tên quán, món ăn…"
        />
        <div className="cres__chips">
          {CUISINES.map((c) => (
            <button
              key={c}
              type="button"
              className={`cust-chip ${cuisine === c ? "is-selected" : ""}`}
              onClick={() => setCuisine(cuisine === c ? "" : c)}
            >
              {c}
            </button>
          ))}
        </div>
        <div className="cres__row">
          <div className="cres__chips">
            {BUDGETS.map((b) => (
              <button
                key={b.v}
                type="button"
                className={`cust-chip ${budget === b.v ? "is-selected" : ""}`}
                onClick={() => setBudget(b.v)}
              >
                {b.label}
              </button>
            ))}
          </div>
          <label className="cres__near">
            <input
              type="checkbox"
              checked={nearby}
              onChange={(e) => setNearby(e.target.checked)}
            />
            <span>Gần tôi</span>
          </label>
        </div>
      </div>

      {error && <div className="cres__error">{error}</div>}

      {loading ? (
        <div className="cres__skeletons">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="cres__skel" />
          ))}
        </div>
      ) : results.length > 0 ? (
        <div className="cres__grid">
          {results.map((m, i) => (
            <RestaurantCard key={m.merchant_id} item={m} rank={i + 1} />
          ))}
        </div>
      ) : (
        !error && (
          <div className="cres__empty">
            <span>🔍</span>
            <p>Không có quán khớp bộ lọc. Thử nới lỏng điều kiện nhé.</p>
          </div>
        )
      )}
    </div>
  );
}
