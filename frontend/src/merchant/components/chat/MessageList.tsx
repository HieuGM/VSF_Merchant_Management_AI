import type { RefObject } from 'react';
import type { ChatMessage, AnalyzedMerchant } from '../../types/merchantChat';
import { MessageItem } from './MessageItem';

export function MessageList({
  messages,
  endRef,
  onOpenDetails,
  onPrompt,
  onOpenMerchantDetail,
}: {
  messages: ChatMessage[];
  endRef: RefObject<HTMLDivElement>;
  onOpenDetails: (message: ChatMessage) => void;
  onPrompt?: (prompt: string) => void;
  onOpenMerchantDetail?: (merchant: AnalyzedMerchant) => void;
}) {
  if (messages.length === 0) {
    return (
      <div className="conversation-scroll chat-scrollbar">
        <div className="empty-conversation">
          <div className="empty-conversation__mark">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polygon points="12 8 16 12 12 16 8 12 12 8"/></svg>
          </div>
          <p>MERCHANT AI ASSISTANT</p>
          <h2>Hôm nay bạn muốn phân tích điều gì?</h2>
          <span>Đặt câu hỏi để phân tích đối thủ, tìm kiếm địa điểm, xem review và nhận gợi ý chiến lược.</span>
          <div className="empty-prompts">
            {[
              'Những quán poke bowl ngon gần tôi ở Quận 1?',
              'Đánh giá chất lượng quán của tôi',
              'Tìm đối thủ trong bán kính 5 km',
              'Khách đang nói gì trong review?',
            ].map((prompt) => (
              <button
                type="button"
                key={prompt}
                onClick={() => onPrompt?.(prompt)}
              >
                {prompt}
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
          />
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}


