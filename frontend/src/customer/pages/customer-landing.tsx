/**
 * Landing / home screen. Warm hero, a tap-to-start search field, sample prompts, and
 * three feature highlights. Everything routes into the chat with an optional seed prompt.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { QuickPrompts } from "../components/quick-prompts";
import "./customer-landing.css";

const FEATURES = [
  { icon: "🧠", title: "Hiểu khẩu vị", desc: "Gợi ý theo sở thích & ngân sách của bạn" },
  { icon: "📍", title: "Gần & hợp", desc: "Ưu tiên quán gần, tính điểm phù hợp" },
  { icon: "🌦️", title: "Đúng thời điểm", desc: "Cân nhắc thời tiết cho lựa chọn hôm nay" },
];

export default function CustomerLanding() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");

  const go = (prompt?: string) =>
    navigate("/customer/chat", { state: prompt ? { prompt } : undefined });

  return (
    <div className="cland cust-scroll">
      <section className="cland__hero">
        <span className="cust-eyebrow">Trợ lý ẩm thực AI</span>
        <h1 className="cland__title">
          Ăn gì hôm nay?<br />Để mình <span>gợi ý</span> cho.
        </h1>
        <p className="cland__sub">
          Chat với trợ lý để tìm đúng quán theo khẩu vị, ngân sách và tâm trạng của bạn.
        </p>

        <form
          className="cland__search cust-glass-strong"
          onSubmit={(e) => {
            e.preventDefault();
            go(q.trim() || undefined);
          }}
        >
          <span className="cland__search-icon">🔍</span>
          <input
            className="cland__search-input"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Vd: phở bò gần đây, trà sữa ít ngọt…"
            aria-label="Tìm món"
          />
          <button type="submit" className="cust-btn cust-btn-primary">
            Bắt đầu
          </button>
        </form>

        <div className="cland__prompts">
          <QuickPrompts onPick={(t) => go(t)} />
        </div>
      </section>

      <section className="cland__features">
        {FEATURES.map((f) => (
          <div key={f.title} className="cland__feature cust-glass">
            <span className="cland__feature-icon">{f.icon}</span>
            <h3>{f.title}</h3>
            <p>{f.desc}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
