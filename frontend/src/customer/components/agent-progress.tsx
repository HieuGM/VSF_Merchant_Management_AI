/**
 * Live "thinking" panel for a streaming agent turn — turns the 20–55s crew wait into
 * visible progress. Each SSE tool step becomes a row that spins, then checks off.
 */
import type { ProgressStep } from "../hooks/use-customer-chat";
import "./agent-progress.css";

export function AgentProgress({ steps }: { steps: ProgressStep[] }) {
  return (
    <div className="aprog">
      <div className="aprog__head">
        <span className="aprog__dots">
          <i /> <i /> <i />
        </span>
        <span>Trợ lý đang tìm quán cho bạn…</span>
      </div>
      {steps.length > 0 && (
        <ul className="aprog__steps">
          {steps.map((s) => (
            <li key={s.id} className={s.done ? "is-done" : "is-active"}>
              <span className="aprog__icon">{s.done ? "✓" : <span className="aprog__spin" />}</span>
              <span className="aprog__label">{s.label}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
