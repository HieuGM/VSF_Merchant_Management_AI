/**
 * One conversation turn. User turns are a pill (right). Agent turns compose the live
 * progress panel, the answer text (rendered as markdown), ranked restaurant cards,
 * taste-profile suggestions, warnings, and a copy button — inside a glass bubble.
 */
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlertTriangle, Check, Copy, Leaf, Lightbulb } from "lucide-react";
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
  return <AgentTurn msg={msg} />;
}

function AgentTurn({ msg }: { msg: ChatMessage }) {
  const [copied, setCopied] = useState(false);
  const showProgress = msg.streaming && !msg.text;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(msg.text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard blocked — ignore */
    }
  };

  return (
    <div className="cmsg cmsg--agent cust-rise">
      <div className="cmsg__avatar" aria-hidden="true">
        <Leaf size={16} strokeWidth={2.4} />
      </div>
      <div className={`cmsg__bubble ${msg.error ? "is-error" : ""}`}>
        {showProgress && <AgentProgress steps={msg.progress ?? []} />}

        {msg.text && (
          <>
            <div className="cmsg__text">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
            </div>
            {!msg.streaming && !msg.error && (
              <button
                type="button"
                className={`cmsg__copy ${copied ? "is-copied" : ""}`}
                onClick={copy}
                aria-label={copied ? "Đã sao chép" : "Sao chép câu trả lời"}
                title={copied ? "Đã sao chép" : "Sao chép câu trả lời"}
              >
                {copied ? <Check size={15} /> : <Copy size={15} />}
              </button>
            )}
          </>
        )}

        {!!msg.results?.length && (
          <div className="cmsg__results">
            {msg.results.map((r, i) => (
              <RestaurantCard key={r.merchant_id ?? `r${i}`} item={r} rank={i + 1} />
            ))}
          </div>
        )}

        {!!msg.suggestions?.length && (
          <div className="cmsg__suggests">
            <span className="cust-eyebrow cmsg__suggests-eyebrow">
              <Lightbulb size={12} /> Gợi ý cập nhật khẩu vị
            </span>
            {msg.suggestions.map((s, i) => (
              <SuggestionRow key={`${s.field}-${i}`} s={s} />
            ))}
          </div>
        )}

        {!!msg.warnings?.length && (
          <ul className="cmsg__warn">
            {msg.warnings.map((w, i) => (
              <li key={i}>
                <AlertTriangle size={13} /> <span>{w}</span>
              </li>
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
