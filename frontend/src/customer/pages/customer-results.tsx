/**
 * Explore screen — a browsable grid of restaurant cards backed by the merchant search
 * API (UC-04). Complements the conversational chat with a filter-driven view: cuisine
 * chips, budget, and "near me" (live geolocation). All filters hit
 * /api/v1/merchants/search via the in-vertical explore-client (no boundary leak).
 */
import { useCallback, useEffect, useState } from "react";
import { LocateFixed, SearchX } from "lucide-react";
import { RestaurantCard } from "../components/restaurant-card";
import { searchMerchants } from "../api/explore-client";
import type { Merchant, SearchFilters } from "../api/explore-client";
import { useGeolocation } from "../hooks/use-geolocation";
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
  const { prefs, update } = usePreferences();
  const geo = useGeolocation();
  const [query, setQuery] = useState("");
  const [cuisine, setCuisine] = useState("");
  const [budget, setBudget] = useState("");
  const [nearby, setNearby] = useState(false);
  const [results, setResults] = useState<Merchant[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const toggleNearby = async () => {
    if (nearby) {
      setNearby(false);
      return;
    }
    const coords = await geo.request();
    if (!coords) return; // error surfaced via geo.error
    update({
      lat: coords.lat,
      lng: coords.lng,
      useLocation: true,
      locationReady: true,
      accuracy: coords.accuracy,
    });
    setNearby(true);
  };

  const run = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const filters: SearchFilters = {
        query: query || undefined,
        cuisine: cuisine || undefined,
        budget: budget || undefined,
        limit: 24,
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

  // Debounced reload on any filter change.
  useEffect(() => {
    const t = setTimeout(run, 300);
    return () => clearTimeout(t);
  }, [run]);

  return (
    <div className="cres cust-scroll">
      <div className="cres__inner">
        <header className="cres__head">
          <h2 className="cres__title">Khám phá quán ăn</h2>
          <p className="cres__sub">Lọc theo ẩm thực, ngân sách và vị trí</p>
        </header>

        <div className="cres__filters cust-glass-strong">
          <input
            className="cust-input cres__search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Tìm tên quán, món ăn…"
            aria-label="Tìm kiếm"
          />

          <div className="cres__chiprow">
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
            <button
              type="button"
              className={`cust-chip cres__near ${nearby ? "is-selected" : ""}`}
              onClick={toggleNearby}
              disabled={geo.status === "loading"}
              aria-pressed={nearby}
            >
              <LocateFixed size={14} />
              {geo.status === "loading" ? "Đang định vị…" : "Gần tôi"}
            </button>
          </div>

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

          {geo.error && <p className="cres__geo-error">{geo.error}</p>}
        </div>

        {error && <div className="cres__error">{error}</div>}

        {loading ? (
          <div className="cres__grid">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="cres__skel cust-skeleton" />
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
              <SearchX size={30} />
              <p>Không có quán khớp bộ lọc. Thử nới lỏng điều kiện nhé.</p>
            </div>
          )
        )}
      </div>
    </div>
  );
}
