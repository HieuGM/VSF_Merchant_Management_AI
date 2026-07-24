/**
 * One conversation turn. User turns are a simple bubble; agent turns compose the
 * live progress panel, the answer text, ranked restaurant cards, taste-profile
 * suggestions, and any warnings — all inside a glass bubble.
 */
import { AgentProgress } from "./agent-progress";
import { RestaurantCard } from "./restaurant-card";
import type { ChatMessage } from "../hooks/use-customer-chat";
import type { PreferenceSuggestion } from "../api/customer-agent-client";
import "./chat-message.css";

export function ChatMessageView({ msg }: { msg: ChatMessage }) {
  if (msg.role === "user") {
    return (
      <div className="cmsg cmsg--user cust-rise">
        <div className="cmsg__bubble">{msg.text}</div>
      </div>
    );
  }

  const showProgress = msg.streaming && !msg.text;
  return (
    <div className="cmsg cmsg--agent cust-rise">
      <div className="cmsg__avatar">🤖</div>
      <div className={`cmsg__bubble ${msg.error ? "is-error" : ""}`}>
        {showProgress && <AgentProgress steps={msg.progress ?? []} />}

        {msg.text && <p className="cmsg__text">{msg.text}</p>}

        {!!msg.results?.length && (
          <div className="cmsg__results">
            {msg.results.map((r, i) => (
              <RestaurantCard key={r.merchant_id ?? i} item={r} rank={i + 1} />
            ))}
          </div>
        )}

        {!!msg.suggestions?.length && (
          <div className="cmsg__suggests">
            <span className="cust-eyebrow">Gợi ý cập nhật khẩu vị</span>
            {msg.suggestions.map((s, i) => (
              <SuggestionRow key={i} s={s} />
            ))}
          </div>
        )}

        {!!msg.warnings?.length && (
          <ul className="cmsg__warn">
            {msg.warnings.map((w, i) => (
              <li key={i}>⚠️ {w}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function SuggestionRow({ s }: { s: PreferenceSuggestion }) {
  const pct = s.confidence != null ? Math.round(s.confidence * 100) : null;
  return (
    <div className="cmsg__suggest">
      <div className="cmsg__suggest-main">
        <b>{s.field}</b>
        {s.value != null && <span className="cmsg__suggest-val">{String(s.value)}</span>}
        {pct != null && <span className="cmsg__suggest-pct">{pct}%</span>}
      </div>
      {s.rationale && <p className="cmsg__suggest-why">{s.rationale}</p>}
    </div>
  );
}
