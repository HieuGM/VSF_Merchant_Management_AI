/** Tappable sample questions to seed a conversation. */
import "./quick-prompts.css";

export const SAMPLE_PROMPTS = [
  { icon: "🍜", text: "Phở ngon gần đây cho bữa tối" },
  { icon: "🧋", text: "Quán trà sữa chill để ngồi làm việc" },
  { icon: "🌧️", text: "Trời mưa, gợi ý món ấm bụng giao tận nơi" },
  { icon: "💸", text: "Ăn trưa tiết kiệm dưới 50k" },
  { icon: "🍣", text: "Quán Nhật sang cho buổi hẹn hò" },
  { icon: "🥗", text: "Món chay thanh đạm, ít dầu mỡ" },
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
      {SAMPLE_PROMPTS.map((p) => (
        <button
          key={p.text}
          type="button"
          className="qprompt"
          onClick={() => onPick(p.text)}
        >
          <span className="qprompt__icon">{p.icon}</span>
          <span>{p.text}</span>
        </button>
      ))}
    </div>
  );
}
