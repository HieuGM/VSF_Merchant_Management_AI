/**
 * Preference Center — the user's taste profile. Backend profile endpoints are still
 * stubbed (routes/user_routes.py), so this persists locally (use-preferences) and the
 * chat query is enriched from it. UI is ready to swap to the real profile API later.
 */
import { useCustomerIdentity } from "../hooks/use-customer-identity";
import { usePreferences, type Budget } from "../hooks/use-preferences";
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

  return (
    <div className="cpref cust-scroll">
      <header className="cpref__head">
        <h2 className="cpref__title">Khẩu vị của bạn</h2>
        <p className="cpref__sub">Trợ lý dùng những lựa chọn này để gợi ý sát hơn.</p>
      </header>

      <section className="cpref__card cust-glass">
        <span className="cust-label">Ngân sách ưa thích</span>
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
      </section>

      <section className="cpref__card cust-glass">
        <span className="cust-label">Chế độ ăn</span>
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
      </section>

      <section className="cpref__card cust-glass">
        <span className="cust-label">Ẩm thực yêu thích 💚</span>
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
      </section>

      <section className="cpref__card cust-glass">
        <span className="cust-label">Không thích 🚫</span>
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
      </section>

      <section className="cpref__card cust-glass">
        <label className="cpref__toggle">
          <span>
            <b>Dùng vị trí của tôi</b>
            <small>Ưu tiên quán gần & tính khoảng cách</small>
          </span>
          <input
            type="checkbox"
            checked={prefs.useLocation}
            onChange={(e) => update({ useLocation: e.target.checked })}
          />
        </label>
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
        💾 Lưu cục bộ trên thiết bị này (ID: <code>{userId.slice(0, 14)}…</code>). Sẽ đồng bộ
        với hồ sơ máy chủ khi API hồ sơ sẵn sàng.
      </p>
    </div>
  );
}
