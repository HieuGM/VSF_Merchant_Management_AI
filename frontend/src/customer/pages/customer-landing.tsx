/**
 * Landing / home screen. Hero with a large composer, sample prompts, and three feature
 * highlights (Lucide icons). The composer navigates into the chat with the typed prompt
 * as seed state.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { CloudSun, MapPin, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Composer } from "../components/composer";
import { QuickPrompts } from "../components/quick-prompts";
import "./customer-landing.css";

const FEATURES: Array<{ icon: LucideIcon; title: string; desc: string }> = [
  { icon: Sparkles, title: "Hiểu khẩu vị", desc: "Gợi ý theo sở thích & ngân sách của bạn" },
  { icon: MapPin, title: "Gần & hợp", desc: "Ưu tiên quán gần, chấm điểm độ phù hợp" },
  { icon: CloudSun, title: "Đúng thời điểm", desc: "Cân nhắc thời tiết cho lựa chọn hôm nay" },
];

export default function CustomerLanding() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");

  const go = (prompt?: string) =>
    navigate("/customer/chat", { state: prompt ? { prompt } : undefined });

  return (
    <div className="cland cust-scroll">
      <div className="cland__inner">
        <section className="cland__hero">
          <span className="cust-eyebrow">Trợ lý ẩm thực AI</span>
          <h1 className="cland__title">
            Ăn gì hôm nay?
            <br />
            Để mình <span className="cland__title-accent">gợi ý</span> cho.
          </h1>
          <p className="cland__sub">
            Chat với trợ lý để tìm đúng quán theo khẩu vị, ngân sách và tâm trạng của bạn.
          </p>

          <div className="cland__composer">
            <Composer
              value={q}
              onChange={setQ}
              onSubmit={() => go(q.trim() || undefined)}
              size="large"
              autoFocus
              placeholder="Vd: phở bò gần đây, trà sữa ít ngọt…"
            />
          </div>

          <div className="cland__prompts">
            <QuickPrompts onPick={(t) => go(t)} />
          </div>
        </section>

        <section className="cland__features">
          {FEATURES.map((f) => {
            const Icon = f.icon;
            return (
              <article key={f.title} className="cland__feature cust-glass">
                <span className="cland__feature-icon" aria-hidden="true">
                  <Icon size={20} />
                </span>
                <h3>{f.title}</h3>
                <p>{f.desc}</p>
              </article>
            );
          })}
        </section>
      </div>
    </div>
  );
}
