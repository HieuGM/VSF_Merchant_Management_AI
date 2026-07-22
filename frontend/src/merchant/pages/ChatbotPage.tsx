import React, { useState, useRef, useEffect } from 'react';
import { useMerchantChat } from '../hooks/useMerchantChat';
import { useTheme } from '../hooks/useTheme';
import { SVGIcon } from '../components/common/SVGIcon';
import { AgentThinkingAccordion } from '../components/chat/AgentThinkingAccordion';
import { CompetitorCardGrid } from '../components/chat/CompetitorCardGrid';
import { DetailSlideOver } from '../components/drawer/DetailSlideOver';
import { CompetitorItem } from '../types/merchantChat';

const MERCHANT_OPTIONS = [
  { id: '94', name: 'Phở Hà Nội #94' },
  { id: '585', name: 'Bún Chả Sài Gòn #585' },
  { id: '791', name: 'Cơm Tấm Sa Bì Chưởng #791' },
];

const QUICK_PROMPTS = [
  'Chẩn đoán 8 chiều',
  'Tìm đối thủ bán kính 5km',
  'Đề xuất cải thiện điểm waiting_time',
];

export const ChatbotPage: React.FC = () => {
  const { theme, toggleTheme } = useTheme();
  const [selectedMerchantId, setSelectedMerchantId] = useState('94');
  const { messages, isThinking, sendMessage, clearSession } = useMerchantChat(selectedMerchantId);
  const [input, setInput] = useState('');
  const [selectedComp, setSelectedComp] = useState<CompetitorItem | null>(null);
  const [activeTab, setActiveTab] = useState<'chatbot' | 'dashboard' | 'reviews' | 'competitors'>('chatbot');
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isThinking) return;
    sendMessage(input);
    setInput('');
  };

  const handleQuickPromptClick = (prompt: string) => {
    if (isThinking) return;
    sendMessage(prompt);
  };

  return (
    <div className="flex h-screen bg-[#FFFFFF] dark:bg-[#111827] text-[#353535] dark:text-[#FFFFFF] font-sans overflow-hidden">
      {/* Left Sidebar */}
      <aside
        className={`${
          isSidebarOpen ? 'w-64' : 'w-16'
        } border-r border-[#E5E7EB] dark:border-[#374151] bg-[#F9F9FF] dark:bg-[#1F2937] p-4 flex flex-col justify-between transition-all duration-300 relative shrink-0`}
      >
        <div>
          {/* Brand Logo & Sidebar Toggle */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center space-x-2 overflow-hidden">
              <div className="w-8 h-8 bg-[#28BDBF] text-[#FFFFFF] font-bold flex items-center justify-center shrink-0 rounded-none">
                GSM
              </div>
              {isSidebarOpen && (
                <span className="font-bold text-sm text-[#111827] dark:text-[#FFFFFF] truncate">
                  Merchant Advisor
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={() => setIsSidebarOpen((prev) => !prev)}
              className="p-1 text-[#666666] dark:text-[#9CA3AF] hover:text-[#353535] dark:hover:text-[#FFFFFF] focus:outline-none"
              title={isSidebarOpen ? 'Thu gọn sidebar' : 'Mở rộng sidebar'}
            >
              <SVGIcon
                name="chevron-down"
                className={`w-4 h-4 transition-transform duration-200 ${
                  isSidebarOpen ? 'rotate-90' : '-rotate-90'
                }`}
              />
            </button>
          </div>

          {/* New Chat Button */}
          <button
            type="button"
            onClick={clearSession}
            className="w-full py-2 px-3 border border-[#E5E7EB] dark:border-[#374151] bg-[#FFFFFF] dark:bg-[#111827] font-bold text-xs hover:bg-[#EEEEEE] dark:hover:bg-[#374151] text-left mb-4 flex items-center justify-center space-x-2 transition-colors rounded-none"
          >
            <span className="text-base leading-none">+</span>
            {isSidebarOpen && <span>Cuộc trò chuyện mới</span>}
          </button>

          {/* Merchant ID Selector Dropdown */}
          {isSidebarOpen && (
            <div className="mb-6">
              <label className="block text-[11px] font-semibold text-[#666666] dark:text-[#9CA3AF] mb-1 uppercase tracking-wider">
                Chọn Merchant ID
              </label>
              <select
                value={selectedMerchantId}
                onChange={(e) => setSelectedMerchantId(e.target.value)}
                className="w-full p-2 border border-[#E5E7EB] dark:border-[#374151] bg-[#FFFFFF] dark:bg-[#111827] text-xs text-[#353535] dark:text-[#FFFFFF] focus:border-[#28BDBF] outline-none font-medium rounded-none"
              >
                {MERCHANT_OPTIONS.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* 4 Navigation Tabs */}
          <nav className="space-y-1">
            <button
              type="button"
              onClick={() => setActiveTab('chatbot')}
              className={`w-full flex items-center space-x-2 px-3 py-2 text-xs font-semibold transition-colors rounded-none ${
                activeTab === 'chatbot'
                  ? 'bg-[#28BDBF]/10 text-[#00A398] dark:text-[#28BDBF] border-l-2 border-[#28BDBF]'
                  : 'text-[#666666] dark:text-[#9CA3AF] hover:bg-[#EEEEEE] dark:hover:bg-[#374151]'
              }`}
            >
              <SVGIcon name="bot" className="w-4 h-4 shrink-0" />
              {isSidebarOpen && <span>Advisor Chatbot</span>}
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('dashboard')}
              className={`w-full flex items-center space-x-2 px-3 py-2 text-xs font-semibold transition-colors rounded-none ${
                activeTab === 'dashboard'
                  ? 'bg-[#28BDBF]/10 text-[#00A398] dark:text-[#28BDBF] border-l-2 border-[#28BDBF]'
                  : 'text-[#666666] dark:text-[#9CA3AF] hover:bg-[#EEEEEE] dark:hover:bg-[#374151]'
              }`}
            >
              <SVGIcon name="sparkles" className="w-4 h-4 shrink-0" />
              {isSidebarOpen && <span>Dashboard</span>}
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('reviews')}
              className={`w-full flex items-center space-x-2 px-3 py-2 text-xs font-semibold transition-colors rounded-none ${
                activeTab === 'reviews'
                  ? 'bg-[#28BDBF]/10 text-[#00A398] dark:text-[#28BDBF] border-l-2 border-[#28BDBF]'
                  : 'text-[#666666] dark:text-[#9CA3AF] hover:bg-[#EEEEEE] dark:hover:bg-[#374151]'
              }`}
            >
              <SVGIcon name="user" className="w-4 h-4 shrink-0" />
              {isSidebarOpen && <span>Reviews</span>}
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('competitors')}
              className={`w-full flex items-center space-x-2 px-3 py-2 text-xs font-semibold transition-colors rounded-none ${
                activeTab === 'competitors'
                  ? 'bg-[#28BDBF]/10 text-[#00A398] dark:text-[#28BDBF] border-l-2 border-[#28BDBF]'
                  : 'text-[#666666] dark:text-[#9CA3AF] hover:bg-[#EEEEEE] dark:hover:bg-[#374151]'
              }`}
            >
              <SVGIcon name="store" className="w-4 h-4 shrink-0" />
              {isSidebarOpen && <span>Competitors</span>}
            </button>
          </nav>
        </div>

        {/* Theme Toggle Button */}
        <button
          type="button"
          onClick={toggleTheme}
          className="w-full flex items-center space-x-2 p-2 border-t border-[#E5E7EB] dark:border-[#374151] text-xs font-semibold text-[#666666] dark:text-[#9CA3AF] hover:text-[#353535] dark:hover:text-[#FFFFFF] transition-colors rounded-none"
        >
          <SVGIcon name={theme === 'light' ? 'moon' : 'sun'} className="w-4 h-4 shrink-0" />
          {isSidebarOpen && (
            <span>{theme === 'light' ? 'Chế độ Tối (Dark)' : 'Chế độ Sáng (Light)'}</span>
          )}
        </button>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col justify-between items-center relative overflow-hidden bg-[#FFFFFF] dark:bg-[#111827]">
        {/* Header */}
        <header className="w-full px-6 py-3 border-b border-[#E5E7EB] dark:border-[#374151] flex items-center justify-between text-xs font-semibold bg-[#FFFFFF] dark:bg-[#111827] shrink-0">
          <div className="flex items-center space-x-2">
            <span className="text-[#111827] dark:text-[#FFFFFF]">
              Merchant Advisor Chat ({MERCHANT_OPTIONS.find((m) => m.id === selectedMerchantId)?.name})
            </span>
          </div>
          <div className="flex items-center space-x-2 text-[#00A398] dark:text-[#28BDBF]">
            <span className="w-2 h-2 rounded-full bg-[#00A398] dark:bg-[#28BDBF] animate-pulse" />
            <span>● Engine CrewAI Active</span>
          </div>
        </header>

        {/* Tab View Content */}
        {activeTab !== 'chatbot' ? (
          <div className="flex-1 flex items-center justify-center text-sm text-[#666666] dark:text-[#9CA3AF]">
            Đang hiển thị view {activeTab.toUpperCase()}. Hãy chuyển sang Advisor Chatbot để trò chuyện với AI.
          </div>
        ) : (
          /* Centered 850px Message Stream Container */
          <div className="w-full max-w-[850px] flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center p-8 space-y-4">
                <div className="w-12 h-12 bg-[#28BDBF]/10 flex items-center justify-center text-[#28BDBF]">
                  <SVGIcon name="sparkles" className="w-6 h-6" />
                </div>
                <h3 className="font-bold text-lg text-[#111827] dark:text-[#FFFFFF]">
                  Xin chào! Tôi là GSM Merchant Advisor Agent.
                </h3>
                <p className="text-xs text-[#666666] dark:text-[#9CA3AF] max-w-md">
                  Tôi có thể giúp bạn phân tích chẩn đoán 8 chiều, tìm kiếm đối thủ cạnh tranh xung quanh, và đưa ra gợi ý tối ưu kinh doanh.
                </p>
                <div className="flex flex-wrap gap-2 justify-center pt-2">
                  {QUICK_PROMPTS.map((prompt, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => handleQuickPromptClick(prompt)}
                      className="px-3 py-1.5 border border-[#28BDBF] text-[#00A398] dark:text-[#28BDBF] bg-[#28BDBF]/5 hover:bg-[#28BDBF]/10 text-xs font-medium transition-colors rounded-none"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}
                >
                  <div
                    className={`p-4 max-w-[85%] border rounded-none ${
                      msg.sender === 'user'
                        ? 'bg-[#F9F9FF] dark:bg-[#1F2937] border-[#E5E7EB] dark:border-[#374151]'
                        : 'bg-[#FFFFFF] dark:bg-[#111827] border-[#E5E7EB] dark:border-[#374151]'
                    }`}
                  >
                    {msg.sender === 'assistant' && (
                      <AgentThinkingAccordion
                        logs={msg.telemetryLogs}
                        isStreaming={msg.isStreaming}
                        traceId={msg.traceId}
                      />
                    )}
                    <p className="text-sm leading-relaxed whitespace-pre-wrap text-[#353535] dark:text-[#FFFFFF]">
                      {msg.content}
                    </p>
                    {msg.competitors && msg.competitors.length > 0 && (
                      <CompetitorCardGrid
                        competitors={msg.competitors}
                        onSelect={(comp) => setSelectedComp(comp)}
                      />
                    )}
                  </div>
                  <span className="text-[10px] text-[#666666] dark:text-[#9CA3AF] mt-1 px-1">
                    {msg.timestamp}
                  </span>
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>
        )}

        {/* Floating Input Bar & Suggestion Chips */}
        {activeTab === 'chatbot' && (
          <div className="w-full max-w-[850px] p-4 shrink-0 space-y-2">
            {/* Quick Prompt Suggestion Chips */}
            <div className="flex items-center space-x-2 overflow-x-auto pb-1 text-xs">
              <span className="text-[#666666] dark:text-[#9CA3AF] font-medium shrink-0">
                Gợi ý nhanh:
              </span>
              {QUICK_PROMPTS.map((prompt, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleQuickPromptClick(prompt)}
                  disabled={isThinking}
                  className="px-2.5 py-1 border border-[#E5E7EB] dark:border-[#374151] bg-[#F9F9FF] dark:bg-[#1F2937] hover:border-[#28BDBF] text-[#353535] dark:text-[#E5E7EB] shrink-0 transition-colors disabled:opacity-50 rounded-none"
                >
                  {prompt}
                </button>
              ))}
            </div>

            {/* Input Form */}
            <form onSubmit={handleSubmit} className="relative flex items-center">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={isThinking}
                placeholder="Hỏi Advisor về chẩn đoán 8 chiều, đối thủ cạnh tranh..."
                className="w-full py-3 pl-4 pr-12 border border-[#E5E7EB] dark:border-[#374151] bg-[#FFFFFF] dark:bg-[#1F2937] text-sm text-[#353535] dark:text-[#FFFFFF] focus:border-[#28BDBF] outline-none transition-colors disabled:opacity-50 rounded-none"
              />
              <button
                type="submit"
                disabled={!input.trim() || isThinking}
                className="absolute right-2 p-2 text-[#28BDBF] hover:text-[#00A398] disabled:opacity-30 transition-colors focus:outline-none"
                title="Gửi tin nhắn"
              >
                <SVGIcon name="send" className="w-5 h-5" />
              </button>
            </form>
          </div>
        )}
      </main>

      {/* Slide-over Preview Panel */}
      <DetailSlideOver
        item={selectedComp}
        onClose={() => setSelectedComp(null)}
        onAskAgent={(query) => sendMessage(query)}
      />
    </div>
  );
};
