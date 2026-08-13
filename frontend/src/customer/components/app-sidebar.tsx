/**
 * App sidebar (ChatGPT-style). Brand + "New chat" + section nav + theme toggle +
 * anonymous identity footer. On ≤768px it becomes a slide-in drawer with backdrop.
 * Chat state is shared via context — "New chat" resets it without unmounting the page.
 */
import { useState } from "react";
import { NavLink } from "react-router-dom";
import { Check, Compass, Copy, House, MessageCircle, Plus, SlidersHorizontal, X } from "lucide-react";
import { BrandMark } from "./brand-mark";
import { SessionHistoryList } from "./session-history-list";
import { ThemeToggle } from "./theme-toggle";
import type { Theme } from "../hooks/use-theme";
import type { SessionSummary } from "../api/customer-agent-client";
import "./app-sidebar.css";

interface Props {
  theme: Theme;
  onToggleTheme: () => void;
  onNewChat: () => void;
  identity: { userId: string };
  open: boolean;
  onClose: () => void;
  sessions: SessionSummary[];
  activeSessionId: string;
  historyLoading: boolean;
  onOpenSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onRenameSession: (sessionId: string, title: string) => void;
}

const NAV = [
  { to: "/customer", label: "Trang chủ", icon: House, end: true },
  { to: "/customer/chat", label: "Trò chuyện", icon: MessageCircle, end: false },
  { to: "/customer/explore", label: "Khám phá", icon: Compass, end: false },
  { to: "/customer/preferences", label: "Sở thích", icon: SlidersHorizontal, end: false },
];

export function AppSidebar({
  theme,
  onToggleTheme,
  onNewChat,
  identity,
  open,
  onClose,
  sessions,
  activeSessionId,
  historyLoading,
  onOpenSession,
  onDeleteSession,
  onRenameSession,
}: Props) {
  const [copied, setCopied] = useState(false);

  const copyId = async () => {
    try {
      await navigator.clipboard.writeText(identity.userId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard blocked — ignore */
    }
  };

  const handleNew = () => {
    onNewChat();
    onClose();
  };

  const handleOpen = (sessionId: string) => {
    onOpenSession(sessionId);
    onClose();
  };

  return (
    <>
      {open && <div className="app-sidebar__backdrop" onClick={onClose} aria-hidden="true" />}
      <aside className={`app-sidebar cust-scroll ${open ? "is-open" : ""}`} aria-label="Điều hướng">
        <div className="app-sidebar__head">
          <BrandMark />
          <button
            type="button"
            className="cust-btn cust-btn-icon app-sidebar__close"
            onClick={onClose}
            aria-label="Đóng menu"
          >
            <X size={18} />
          </button>
        </div>

        <button type="button" className="cust-btn cust-btn-primary app-sidebar__new" onClick={handleNew}>
          <Plus size={18} strokeWidth={2.4} />
          Trò chuyện mới
        </button>

        <SessionHistoryList
          sessions={sessions}
          activeSessionId={activeSessionId}
          loading={historyLoading}
          onOpen={handleOpen}
          onDelete={onDeleteSession}
          onRename={onRenameSession}
        />

        <nav className="app-sidebar__nav">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={onClose}
              className={({ isActive }) => `app-sidebar__link ${isActive ? "is-active" : ""}`}
            >
              <Icon size={18} strokeWidth={2.1} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="app-sidebar__foot">
          <div className="app-sidebar__theme">
            <span className="app-sidebar__theme-label">Giao diện</span>
            <ThemeToggle theme={theme} onToggle={onToggleTheme} />
          </div>
          <button
            type="button"
            className="app-sidebar__id"
            onClick={copyId}
            title="Sao chép mã người dùng"
            aria-label="Sao chép mã người dùng"
          >
            <span className="app-sidebar__id-label">Mã của bạn</span>
            <span className="app-sidebar__id-value">{identity.userId.slice(0, 10)}…</span>
            {copied ? <Check size={14} className="app-sidebar__id-check" /> : <Copy size={14} />}
          </button>
        </div>
      </aside>
    </>
  );
}
