/**
 * Preference Center — the user's taste profile. Backend profile endpoints are still
 * stubbed, so this persists locally (use-preferences) and the chat query is enriched
 * from it. Live geolocation fills lat/lng; manual entry remains as fallback.
 */
import type { ReactNode } from "react";
import { Ban, Database, Heart, LocateFixed, MapPin, Salad, Wallet } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useCustomerIdentity } from "../hooks/use-customer-identity";
import { useGeolocation } from "../hooks/use-geolocation";
import { usePreferences } from "../hooks/use-preferences";
import type { Budget } from "../hooks/use-preferences";
import "./preference-center.css";

const BUDGETS: Array<{ v: Budget; label: string; hint: string }> = [
  { v: "student", label: "Tiết kiệm", hint: "15k–50k" },
  { v: "standard", label: "Trung cấp", hint: "50k–150k" },
  { v: "premium", label: "Cao cấp", hint: "150k+" },
];
const DIETARY = ["Chay", "Ít cay", "Không hành", "Ít dầu mỡ", "Không đường", "Healthy"];
const CUISINES = ["Việt", "Nhật", "Hàn", "Ý", "Thái", "Trung", "Đồ uống", "Ăn vặt"];

export default function PreferenceCenter() {
  const { userId } = useCustomerIdentity();
  const { prefs, update, toggleIn } = usePreferences();
  const geo = useGeolocation();

  const useMyLocation = async () => {
    const coords = await geo.request();
    if (coords) update({ lat: coords.lat, lng: coords.lng, useLocation: true });
  };

  return (
    <div className="cpref cust-scroll">
      <div className="cpref__inner">
        <header className="cpref__head">
          <h2 className="cpref__title">Khẩu vị của bạn</h2>
          <p className="cpref__sub">Trợ lý dùng những lựa chọn này để gợi ý sát hơn.</p>
        </header>

        <Section icon={Wallet} label="Ngân sách ưa thích">
          <div className="cpref__chips">
            {BUDGETS.map((b) => (
              <button
                key={b.v}
                type="button"
                className={`cust-chip ${prefs.budget === b.v ? "is-selected" : ""}`}
                onClick={() => update({ budget: prefs.budget === b.v ? "" : b.v })}
              >
                {b.label} · {b.hint}
              </button>
            ))}
          </div>
        </Section>

        <Section icon={Salad} label="Chế độ ăn">
          <div className="cpref__chips">
            {DIETARY.map((d) => (
              <button
                key={d}
                type="button"
                className={`cust-chip ${prefs.dietary.includes(d) ? "is-selected" : ""}`}
                onClick={() => toggleIn("dietary", d)}
              >
                {d}
              </button>
            ))}
          </div>
        </Section>

        <Section icon={Heart} label="Ẩm thực yêu thích">
          <div className="cpref__chips">
            {CUISINES.map((c) => (
              <button
                key={c}
                type="button"
                className={`cust-chip ${prefs.likedCuisines.includes(c) ? "is-selected" : ""}`}
                onClick={() => toggleIn("likedCuisines", c)}
              >
                {c}
              </button>
            ))}
          </div>
        </Section>

        <Section icon={Ban} label="Không thích">
          <div className="cpref__chips">
            {CUISINES.map((c) => (
              <button
                key={c}
                type="button"
                className={`cust-chip ${prefs.dislikedCuisines.includes(c) ? "is-selected" : ""}`}
                onClick={() => toggleIn("dislikedCuisines", c)}
              >
                {c}
              </button>
            ))}
          </div>
        </Section>

        <section className="cpref__card cust-glass">
          <div className="cpref__card-head">
            <span className="cpref__card-icon" aria-hidden="true">
              <MapPin size={18} />
            </span>
            <div>
              <b>Vị trí của tôi</b>
              <p className="cpref__card-desc">Ưu tiên quán gần & tính khoảng cách.</p>
            </div>
          </div>

          <label className="cpref__toggle">
            <span>Dùng vị trí khi trò chuyện</span>
            <input
              type="checkbox"
              checked={prefs.useLocation}
              onChange={(e) => update({ useLocation: e.target.checked })}
            />
          </label>

          <button
            type="button"
            className="cust-btn cust-btn-ghost cpref__geo"
            onClick={useMyLocation}
            disabled={geo.status === "loading"}
          >
            <LocateFixed size={16} />
            {geo.status === "loading" ? "Đang định vị…" : "Dùng vị trí hiện tại"}
          </button>
          {geo.error && <p className="cpref__geo-error">{geo.error}</p>}

          {prefs.useLocation && (
            <div className="cpref__coords">
              <label>
                Vĩ độ
                <input
                  className="cust-input"
                  type="number"
                  value={prefs.lat}
                  step="0.001"
                  onChange={(e) => update({ lat: Number(e.target.value) })}
                />
              </label>
              <label>
                Kinh độ
                <input
                  className="cust-input"
                  type="number"
                  value={prefs.lng}
                  step="0.001"
                  onChange={(e) => update({ lng: Number(e.target.value) })}
                />
              </label>
            </div>
          )}
        </section>

        <p className="cpref__note">
          <Database size={14} /> Lưu cục bộ trên thiết bị này (ID <code>{userId.slice(0, 14)}…</code>).
          Sẽ đồng bộ với máy chủ khi API sẵn sàng.
        </p>
      </div>
    </div>
  );
}

function Section({
  icon: Icon,
  label,
  children,
}: {
  icon: LucideIcon;
  label: string;
  children: ReactNode;
}) {
  return (
    <section className="cpref__card cust-glass">
      <div className="cpref__card-head">
        <span className="cpref__card-icon" aria-hidden="true">
          <Icon size={18} />
        </span>
        <span className="cust-label cpref__card-label">{label}</span>
      </div>
      {children}
    </section>
  );
}
