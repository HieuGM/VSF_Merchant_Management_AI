/**
 * Customer Discovery chat (core screen). Streams the crew run over SSE and renders
 * live progress → answer → ranked restaurant cards. Preferences from the Preference
 * Center are folded into the query; location is sent when the user opted in.
 */
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { ChatMessageView } from "../components/chat-message";
import { QuickPrompts } from "../components/quick-prompts";
import { useCustomerChat } from "../hooks/use-customer-chat";
import { useCustomerIdentity } from "../hooks/use-customer-identity";
import { preferencesToContext, usePreferences } from "../hooks/use-preferences";
import "./customer-chat.css";

export default function CustomerChat() {
  const identity = useCustomerIdentity();
  const { messages, sending, send } = useCustomerChat(identity);
  const { prefs } = usePreferences();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  // Ref-guard for the seed effect: React StrictMode double-invokes mount effects in dev,
  // so without this the landing-page prompt fires twice and the query is sent duplicated.
  const seededRef = useRef(false);
  const routeState = useLocation().state as { prompt?: string } | null;

  const submit = (raw: string) => {
    const text = raw.trim();
    if (!text || sending) return;
    setDraft("");
    send({
      message: text + preferencesToContext(prefs),
      location: prefs.useLocation ? { lat: prefs.lat, lng: prefs.lng } : null,
    });
  };

  // Seed from a landing-page prompt (navigated with { state: { prompt } }).
  // Idempotent via seededRef — survives StrictMode's dev double-mount.
  useEffect(() => {
    if (routeState?.prompt && !seededRef.current) {
      seededRef.current = true;
      submit(routeState.prompt);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the latest turn in view as content streams in.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const empty = messages.length === 0;

  return (
    <div className="cchat">
      <div ref={scrollRef} className="cchat__stream cust-scroll">
        {empty ? (
          <div className="cchat__welcome cust-rise">
            <div className="cchat__welcome-badge">🍽️</div>
            <h2>Hôm nay bạn muốn ăn gì?</h2>
            <p>Kể cho trợ lý nghe khẩu vị, ngân sách hay tâm trạng — mình lo phần còn lại.</p>
            <QuickPrompts onPick={submit} columns />
          </div>
        ) : (
          <div className="cchat__messages">
            {messages.map((m) => (
              <ChatMessageView key={m.id} msg={m} />
            ))}
          </div>
        )}
      </div>

      <form
        className="cchat__composer cust-glass-strong"
        onSubmit={(e) => {
          e.preventDefault();
          submit(draft);
        }}
      >
        <input
          className="cchat__input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Nhập món, khẩu vị hoặc tâm trạng…"
          disabled={sending}
          aria-label="Tin nhắn"
        />
        <button
          type="submit"
          className="cust-btn cust-btn-primary cchat__send"
          disabled={sending || !draft.trim()}
          aria-label="Gửi"
        >
          {sending ? <span className="cchat__send-spin" /> : "➤"}
        </button>
      </form>
    </div>
  );
}
