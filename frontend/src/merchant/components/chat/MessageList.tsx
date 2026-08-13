import type { RefObject } from 'react';
import type { ChatMessage, AnalyzedMerchant } from '../../types/merchantChat';
import { MessageItem } from './MessageItem';

interface SuggestionItem {
  icon: string;
  category: string;
  title: string;
  prompt: string;
}

const SUGGESTIONS: SuggestionItem[] = [
  {
    icon: '📍',
    category: 'Cạnh tranh & Địa điểm',
    title: 'Tìm đối thủ khu vực xung quanh',
    prompt: 'Những quán poke bowl ngon gần tôi ở Quận 1?',
  },
  {
    icon: '📊',
    category: 'Phân tích Hiệu suất',
    title: 'Đánh giá chất lượng nhà hàng',
    prompt: 'Đánh giá hiệu suất và chất lượng quán của tôi',
  },
  {
    icon: '🔍',
    category: 'Bán kính Cạnh tranh',
    title: 'Quét đối thủ bán kính 5 km',
    prompt: 'Tìm các đối thủ cạnh tranh trong bán kính 5 km',
  },
  {
    icon: '💬',
    category: 'Lắng nghe Khách hàng',
    title: 'Tổng hợp đánh giá Review',
    prompt: 'Khách hàng đang nói gì về nhà hàng trong review?',
  },
];

export function MessageList({
  messages,
  endRef,
  onOpenDetails,
  onPrompt,
  onOpenMerchantDetail,
  routeDistances,
}: {
  messages: ChatMessage[];
  endRef: RefObject<HTMLDivElement>;
  onOpenDetails: (message: ChatMessage, tab?: 'results' | 'map' | 'trace') => void;
  onPrompt?: (prompt: string) => void;
  onOpenMerchantDetail?: (merchant: AnalyzedMerchant) => void;
  routeDistances?: Record<string, number>;
}) {
  if (messages.length === 0) {
    return (
      <div className="conversation-scroll chat-scrollbar">
        <div className="hero-empty-state">
          <div className="hero-badge">
            <span className="hero-sparkle">✨</span>
            <span>MERCHANT AI ASSISTANT</span>
          </div>

          <h2 className="hero-headline">Hôm nay bạn muốn phân tích điều gì?</h2>
          <p className="hero-description">
            Đặt câu hỏi để phân tích đối thủ cạnh tranh, tìm kiếm vị trí địa lý, xem tổng hợp review và nhận gợi ý chiến lược tăng trưởng.
          </p>

          <div className="suggestions-grid">
            {SUGGESTIONS.map((item) => (
              <button
                type="button"
                key={item.title}
                className="suggestion-prompt-card"
                onClick={() => onPrompt?.(item.prompt)}
              >
                <div className="card-top-row">
                  <span className="suggestion-icon">{item.icon}</span>
                  <span className="suggestion-category">{item.category}</span>
                  <span className="arrow-icon">→</span>
                </div>
                <strong className="suggestion-title">{item.title}</strong>
                <p className="suggestion-prompt-text">"{item.prompt}"</p>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="conversation-scroll chat-scrollbar">
      <div className="conversation-column">
        {messages.map((message) => (
          <MessageItem
            key={message.id}
            message={message}
            onOpenDetails={onOpenDetails}
            onOpenMerchantDetail={onOpenMerchantDetail}
            routeDistances={routeDistances}
          />
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}
