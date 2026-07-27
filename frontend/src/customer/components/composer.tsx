/** Chat composer — auto-grow textarea, Enter to send / Shift+Enter for newline,
 * IME-safe (won't send mid Vietnamese composition), send→stop swap while streaming.
 * Shared by Landing (large) and Chat (default). */
import { useEffect, useRef } from "react";
import type { KeyboardEvent } from "react";
import { ArrowUp, Square } from "lucide-react";
import "./composer.css";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onStop?: () => void;
  streaming?: boolean;
  disabled?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  size?: "default" | "large";
}

const MAX_HEIGHT = 200;

export function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  streaming = false,
  disabled,
  placeholder,
  autoFocus,
  size = "default",
}: Props) {
  const taRef = useRef<HTMLTextAreaElement>(null);

  const grow = () => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, MAX_HEIGHT)}px`;
  };
  useEffect(grow, [value]);
  useEffect(() => {
    if (autoFocus) taRef.current?.focus();
  }, [autoFocus]);

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends, Shift+Enter newlines. Don't send while the Vietnamese IME is composing.
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (!streaming && value.trim()) onSubmit();
    }
  };

  const canSend = !streaming && !disabled && value.trim().length > 0;

  return (
    <form
      className={`composer composer--${size}`}
      onSubmit={(e) => {
        e.preventDefault();
        if (canSend) onSubmit();
      }}
    >
      <textarea
        ref={taRef}
        className="composer__input cust-scroll"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder ?? "Hỏi bất cứ gì…"}
        rows={1}
        disabled={disabled}
        aria-label="Tin nhắn"
      />
      {streaming ? (
        <button
          type="button"
          className="cust-btn cust-btn-icon composer__stop"
          onClick={onStop}
          aria-label="Dừng tạo câu trả lời"
          title="Dừng"
        >
          <Square size={15} fill="currentColor" strokeWidth={0} />
        </button>
      ) : (
        <button
          type="submit"
          className="cust-btn cust-btn-primary composer__send"
          disabled={!canSend}
          aria-label="Gửi tin nhắn"
          title="Gửi (Enter)"
        >
          <ArrowUp size={18} strokeWidth={2.6} />
        </button>
      )}
    </form>
  );
}
