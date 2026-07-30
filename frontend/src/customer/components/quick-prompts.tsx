/** Tappable sample questions to seed a conversation. Lucide icons (no emoji).
 * variants: "row" = wrapping pills (chat empty-state), "grid3" = aligned 3-column grid
 * with a trailing arrow (landing, fe reference). */
import { ArrowRight, CloudRain, Coins, CupSoda, Fish, Leaf, Soup } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import "./quick-prompts.css";

export interface SamplePrompt {
  icon: LucideIcon;
  text: string;
}

export const SAMPLE_PROMPTS: SamplePrompt[] = [
  { icon: Soup, text: "Phở ngon gần đây cho bữa tối" },
  { icon: CupSoda, text: "Quán trà sữa chill để ngồi làm việc" },
  { icon: CloudRain, text: "Trời mưa, gợi ý món ấm bụng giao tận nơi" },
  { icon: Coins, text: "Ăn trưa tiết kiệm dưới 50k" },
  { icon: Fish, text: "Quán Nhật sang cho buổi hẹn hò" },
  { icon: Leaf, text: "Món chay thanh đạm, ít dầu mỡ" },
];

export function QuickPrompts({
  onPick,
  columns = false,
  variant = "row",
}: {
  onPick: (text: string) => void;
  columns?: boolean;
  variant?: "row" | "grid3";
}) {
  const cls = variant === "grid3" ? "qprompts qprompts--grid3" : `qprompts ${columns ? "qprompts--col" : ""}`;
  return (
    <div className={cls}>
      {SAMPLE_PROMPTS.map((p) => {
        const Icon = p.icon;
        return (
          <button key={p.text} type="button" className="qprompt" onClick={() => onPick(p.text)}>
            <span className="qprompt__icon" aria-hidden="true">
              <Icon size={16} />
            </span>
            <span className="qprompt__text">{p.text}</span>
            {variant === "grid3" && (
              <ArrowRight size={15} className="qprompt__arrow" aria-hidden="true" />
            )}
          </button>
        );
      })}
    </div>
  );
}
