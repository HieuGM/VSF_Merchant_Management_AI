/**
 * Customer Discovery chat (core screen). Streams the crew run over SSE and renders
 * live progress → answer → ranked restaurant cards. Chat state is shared via context
 * (lifted to CustomerHome); scroll is driven by useStickToBottom (instant pin while
 * near the bottom, otherwise a "jump to latest" pill). Preferences are folded into the
 * query; location is sent when the user opted in.
 */
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { ArrowDown, Leaf } from "lucide-react";
import { ChatMessageView } from "../components/chat-message";
import { Composer } from "../components/composer";
import { QuickPrompts } from "../components/quick-prompts";
import { useChat } from "../context/chat-provider";
import { preferencesToContext, usePreferences } from "../hooks/use-preferences";
import { useStickToBottom } from "../hooks/use-stick-to-bottom";
import "./customer-chat.css";

export default function CustomerChat() {
  const { messages, sending, send, stop } = useChat();
  const { prefs } = usePreferences();
  const [draft, setDraft] = useState("");
  const { ref, atBottom, scrollToBottom, onScroll } = useStickToBottom<HTMLDivElement>();
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

  const empty = messages.length === 0;

  return (
    <div className="cchat">
      <div
        ref={ref}
        className="cchat__stream cust-scroll"
        onScroll={onScroll}
      >
        <div className="cchat__inner">
          {empty ? (
            <div className="cchat__welcome cust-rise">
              <span className="cchat__welcome-logo" aria-hidden="true">
                <Leaf size={26} strokeWidth={2.2} />
              </span>
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
      </div>

      {!atBottom && !empty && (
        <button
          type="button"
          className="cchat__jump cust-btn"
          onClick={() => scrollToBottom("smooth")}
          aria-label="Cuộn xuống tin mới nhất"
        >
          <ArrowDown size={16} /> Xem tin mới
        </button>
      )}

      <div className="cchat__composer-wrap">
        <Composer
          value={draft}
          onChange={setDraft}
          onSubmit={() => submit(draft)}
          onStop={stop}
          streaming={sending}
          placeholder="Nhập món, khẩu vị hoặc tâm trạng…"
          autoFocus={!empty}
        />
        <p className="cchat__hint">Trợ lý có thể sai sót. Hãy kiểm tra thông tin quan trọng.</p>
      </div>
    </div>
  );
}
