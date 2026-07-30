/**
 * Landing / home screen. Hero (headline + composer + sample prompts + a real food
 * photo on the right) and three feature highlights with centered illustrations.
 * Matches the fe.png reference: 3-column prompt grid, leaf ambient, big feature art.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MapPinned, Sparkles, Store, SunMoon } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Composer } from "../components/composer";
import { QuickPrompts } from "../components/quick-prompts";
import { searchMerchants } from "../api/explore-client";
import "./customer-landing.css";

const FEATURES: Array<{ icon: LucideIcon; title: string; desc: string }> = [
  { icon: MapPinned, title: "Hiểu khẩu vị", desc: "Gợi ý theo sở thích & ngân sách của bạn" },
  { icon: Store, title: "Gần & hợp", desc: "Ưu tiên quán gần, chấm điểm độ phù hợp" },
  { icon: SunMoon, title: "Đúng thời điểm", desc: "Cân nhắc thời tiết cho lựa chọn hôm nay" },
];

export default function CustomerLanding() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [heroImg, setHeroImg] = useState<string | null>(null);

  // Pull a real merchant dish photo for the hero visual (fe reference shows a big food
  // photo top-right). Best-effort — if the API/image fails, the hero just drops the photo.
  useEffect(() => {
    let alive = true;
    searchMerchants({ query: "phở", limit: 6 })
      .then((r) => {
        if (!alive) return;
        const withImg = r.merchants.find((m) => m.image_url);
        if (withImg?.image_url) setHeroImg(withImg.image_url);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const go = (prompt?: string) =>
    navigate("/customer/chat", { state: prompt ? { prompt } : undefined });

  return (
    <div className="cland cust-scroll">
      <div className="cland__inner">
        <section className="cland__hero">
          <div className="cland__hero-text">
            <span className="cust-eyebrow">Trợ lý ẩm thực AI</span>
            <h1 className="cland__title">
              Ăn gì hôm nay?
              <br />
              Để mình <span className="cland__title-accent">gợi ý</span> cho.
            </h1>
            <p className="cland__sub">
              Chat với trợ lý để tìm đúng quán theo khẩu vị, ngân sách và tâm trạng của bạn.
            </p>
          </div>

          {heroImg && (
            <div className="cland__hero-photo" aria-hidden="true">
              <img src={heroImg} alt="" onError={(e) => (e.currentTarget.style.display = "none")} />
              <span className="cland__hero-stamp">
                <Sparkles size={14} /> Gợi ý từ quán thật
              </span>
            </div>
          )}

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
            <QuickPrompts onPick={(t) => go(t)} variant="grid3" />
          </div>
        </section>

        <section className="cland__features">
          {FEATURES.map((f) => {
            const Icon = f.icon;
            return (
              <article key={f.title} className="cland__feature cust-glass">
                <span className="cland__feature-icon" aria-hidden="true">
                  <Icon size={30} strokeWidth={1.8} />
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
