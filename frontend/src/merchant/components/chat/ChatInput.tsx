import { FormEvent, useState } from 'react';

const SUGGESTIONS = [
  { icon: 'refresh', label: 'Gợi ý câu hỏi' },
  { label: 'Phân tích menu' },
  { label: 'Đối thủ gần tôi' },
  { label: 'Xu hướng món ăn' },
];

export function ChatInput({
  isThinking,
  onSend,
}: {
  isThinking: boolean;
  onSend: (message: string) => void;
}) {
  const [value, setValue] = useState('');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!value.trim() || isThinking) return;
    onSend(value.trim());
    setValue('');
  };

  const handleChipClick = (promptLabel: string) => {
    if (promptLabel === 'Gợi ý câu hỏi') {
      onSend('Những quán poke bowl ngon gần tôi ở Quận 1?');
    } else {
      onSend(`${promptLabel} ở Quận 1`);
    }
  };

  return (
    <div className="composer-wrap">
      <form className="composer" onSubmit={submit}>
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          aria-label="Tin nhắn cho AI Advisor"
          placeholder="Nhập câu hỏi của bạn..."
          rows={2}
        />

        <div className="composer__footer">
          <div className="suggestion-chips">
            {SUGGESTIONS.map((chip, index) => (
              <button
                type="button"
                key={index}
                className="chip-btn"
                onClick={() => handleChipClick(chip.label)}
              >
                {chip.icon === 'refresh' && (
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
                )}
                <span>{chip.label}</span>
              </button>
            ))}
          </div>

          <button type="submit" className="send-btn" aria-label="Gửi tin nhắn" disabled={isThinking || !value.trim()}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>
          </button>
        </div>
      </form>

      <p className="composer-disclaimer">
        AI có thể mắc lỗi. Vui lòng kiểm tra thông tin quan trọng.
      </p>
    </div>
  );
}

