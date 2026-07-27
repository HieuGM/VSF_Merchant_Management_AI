/**
 * Live "thinking" panel for a streaming agent turn — turns the crew wait into visible
 * progress. Each SSE tool step becomes a row (Loader2 → Check). When no steps have
 * arrived yet, a skeleton keeps the bubble from looking empty.
 */
import { Check, Loader2, Sparkles } from "lucide-react";
import type { ProgressStep } from "../hooks/use-customer-chat";
import "./agent-progress.css";

export function AgentProgress({ steps }: { steps: ProgressStep[] }) {
  return (
    <div className="aprog">
      <div className="aprog__head">
        <span className="aprog__dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <Sparkles size={15} className="aprog__spark" aria-hidden="true" />
        <span>Trợ lý đang tìm quán cho bạn…</span>
      </div>

      {steps.length > 0 ? (
        <ul className="aprog__steps">
          {steps.map((s) => (
            <li key={s.id} className={s.done ? "is-done" : "is-active"}>
              <span className="aprog__icon">
                {s.done ? <Check size={13} strokeWidth={3} /> : <Loader2 size={13} className="aprog__spin" />}
              </span>
              <span className="aprog__label">{s.label}</span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="aprog__skeleton" aria-hidden="true">
          <span className="cust-skeleton aprog__sk-line" style={{ width: "82%" }} />
          <span className="cust-skeleton aprog__sk-line" style={{ width: "64%" }} />
        </div>
      )}
    </div>
  );
}
