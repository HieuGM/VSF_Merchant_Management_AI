/** Tappable sample questions to seed a conversation. Lucide icons (no emoji). */
import { CloudRain, Coins, CupSoda, Fish, Leaf, Soup } from "lucide-react";
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
}: {
  onPick: (text: string) => void;
  columns?: boolean;
}) {
  return (
    <div className={`qprompts ${columns ? "qprompts--col" : ""}`}>
      {SAMPLE_PROMPTS.map((p) => {
        const Icon = p.icon;
        return (
          <button key={p.text} type="button" className="qprompt" onClick={() => onPick(p.text)}>
            <span className="qprompt__icon" aria-hidden="true">
              <Icon size={16} />
            </span>
            <span>{p.text}</span>
          </button>
        );
      })}
    </div>
  );
}
