/**
 * Preference Center — the user's taste profile. Taste fields (budget, dietary, liked/disliked
 * cuisines) are backed by the canonical backend profile (GET/PATCH /api/v1/users/{id}/profile)
 * via use-preferences, with localStorage as an offline cache; the assistant's long-term notes
 * come from context_memory. Live geolocation fills lat/lng; manual entry remains as fallback.
 */
import { useState, type ReactNode } from "react";
import { Ban, Database, Eraser, Heart, LocateFixed, MapPin, Salad, Wallet } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { AllergySection } from "../components/allergy-section";
import { NoteList } from "../components/note-list";
import { useCustomerIdentity } from "../hooks/use-customer-identity";
import { useGeolocation } from "../hooks/use-geolocation";
import { usePreferences } from "../hooks/use-preferences";
import type { Budget, SyncStatus } from "../hooks/use-preferences";
import "./preference-center.css";

const BUDGETS: Array<{ v: Budget; label: string; hint: string }> = [
  { v: "student", label: "Tiết kiệm", hint: "15k–50k" },
  { v: "standard", label: "Trung cấp", hint: "50k–150k" },
  { v: "premium", label: "Cao cấp", hint: "150k+" },
];
const DIETARY = ["Chay", "Ít cay", "Không hành", "Ít dầu mỡ", "Không đường", "Healthy"];
const CUISINES = ["Việt", "Nhật", "Hàn", "Ý", "Thái", "Trung", "Đồ uống", "Ăn vặt"];

const SYNC_LABEL: Record<SyncStatus, string> = {
  idle: "Lưu cục bộ trên thiết bị",
  loading: "Đang đồng bộ…",
  synced: "Đã đồng bộ với máy chủ",
  offline: "Ngoại tuyến — lưu tạm trên thiết bị",
};

export default function PreferenceCenter() {
  const { userId } = useCustomerIdentity();
  const { prefs, notes, noteExpiries, sync, update, toggleIn, deleteNote, clearAll } =
    usePreferences();
  const geo = useGeolocation();

  const [clearing, setClearing] = useState(false);

  const onClear = async () => {
    if (!window.confirm("Xóa hết ghi nhớ (dị ứng, ăn kiêng, sở thích) trong hồ sơ để test lại từ đầu?")) return;
    setClearing(true);
    await clearAll();
    setClearing(false);
  };

  const toggleUseLocation = async (checked: boolean) => {
    if (!checked) {
      update({ useLocation: false });
      return;
    }
    // Reveal manual coord inputs and attempt to prefill via live geolocation.
    // locationReady only flips on success — a denied/failed geo leaves chat
    // location-sending OFF until the user enters coords manually.
    update({ useLocation: true });
    const coords = await geo.request();
    if (coords)
      update({ locationReady: true, lat: coords.lat, lng: coords.lng, accuracy: coords.accuracy });
  };

  const useMyLocation = async () => {
    const coords = await geo.request();
    if (coords)
      update({ lat: coords.lat, lng: coords.lng, locationReady: true, accuracy: coords.accuracy });
  };

  return (
    <div className="cpref cust-scroll">
      <div className="cpref__inner">
        <header className="cpref__head">
          <div>
            <h2 className="cpref__title">Hồ sơ cá nhân</h2>
            <p className="cpref__sub">Trợ lý dùng những lựa chọn này để gợi ý sát hơn.</p>
          </div>
          <button
            type="button"
            className="cust-btn cust-btn-ghost cpref__clear"
            onClick={onClear}
            disabled={clearing || sync === "loading"}
            title="Xóa ghi nhớ + khẩu vị trong hồ sơ để test lại"
          >
            <Eraser size={15} />
            {clearing ? "Đang xóa…" : "Xóa ghi nhớ"}
          </button>
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

        <AllergySection
          allergens={prefs.allergens}
          onChange={(next) => update({ allergens: next })}
        />

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
          <div className="cpref__chips cpref__chips--danger">
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
              onChange={(e) => toggleUseLocation(e.target.checked)}
              disabled={geo.status === "loading"}
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
                  onChange={(e) =>
                    update({ lat: Number(e.target.value), locationReady: true, accuracy: null })
                  }
                />
              </label>
              <label>
                Kinh độ
                <input
                  className="cust-input"
                  type="number"
                  value={prefs.lng}
                  step="0.001"
                  onChange={(e) =>
                    update({ lng: Number(e.target.value), locationReady: true, accuracy: null })
                  }
                />
              </label>
            </div>
          )}
        </section>

        <section className="cpref__card cust-glass cpref__notes-card">
          <NoteList notes={notes} expiries={noteExpiries} onDelete={deleteNote} />
        </section>

        <p className="cpref__note" data-sync={sync}>
          <Database size={14} /> {SYNC_LABEL[sync]} (ID <code>{userId.slice(0, 14)}…</code>).
          {sync === "offline" && " Sẽ tự đồng bộ khi có mạng."}
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
