/**
 * Customer Discovery shell (Dev A owns everything under src/customer/).
 * ChatGPT-style: ambient background + left sidebar + main viewport. The chat state
 * machine is lifted here (ChatProvider) so the sidebar's "New chat" and the chat page
 * share one conversation. Screens: Landing, streaming Chat (UC-04/05), Explore, Preferences.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Menu } from "lucide-react";
import { deleteSession, renameSession } from "./api/customer-agent-client";
import { AmbientBackground } from "./components/ambient-background";
import { AppSidebar } from "./components/app-sidebar";
import { BrandMark } from "./components/brand-mark";
import { ThemeToggle } from "./components/theme-toggle";
import { ChatProvider } from "./context/chat-provider";
import { useCustomerChat } from "./hooks/use-customer-chat";
import { useCustomerIdentity } from "./hooks/use-customer-identity";
import { LikedMerchantsProvider } from "./hooks/use-liked-merchants";
import { useSessionHistory } from "./hooks/use-session-history";
import { useTheme } from "./hooks/use-theme";
import CustomerLanding from "./pages/customer-landing";
import CustomerChat from "./pages/customer-chat";
import CustomerResults from "./pages/customer-results";
import PreferenceCenter from "./pages/preference-center";
import "./theme/customer-theme.css";
import "./customer-shell.css";

export function CustomerHome() {
  const { theme, toggle } = useTheme();
  const identity = useCustomerIdentity();
  const chat = useCustomerChat(identity);
  const history = useSessionHistory(identity.userId);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();

  const newChat = useCallback(() => {
    chat.reset();
    navigate("/customer/chat");
    void history.refresh();
  }, [chat, navigate, history]);

  // Reopen a past conversation: load its messages into the chat, adopt its session id, then
  // refresh the sidebar (ordering + active highlight).
  const onOpenSession = useCallback(
    async (sessionId: string) => {
      await chat.openSession(sessionId);
      navigate("/customer/chat");
      void history.refresh();
    },
    [chat, navigate, history],
  );

  // Delete: optimistic remove → network delete → if it was the active chat, start fresh.
  const onDeleteSession = useCallback(
    async (sessionId: string) => {
      history.removeOptimistic(sessionId);
      const wasActive = sessionId === identity.sessionId;
      try {
        await deleteSession(identity.userId, sessionId);
      } catch {
        /* best-effort — refresh reconciles (row may already be gone) */
      }
      if (wasActive) chat.reset();
      void history.refresh();
    },
    [history, identity, chat],
  );

  // Rename: optimistic update → network rename → refresh.
  const onRenameSession = useCallback(
    async (sessionId: string, title: string) => {
      history.renameOptimistic(sessionId, title);
      try {
        await renameSession(identity.userId, sessionId, title);
      } catch {
        /* best-effort — refresh reconciles */
      }
      void history.refresh();
    },
    [history, identity],
  );

  // Keep the list fresh after each exchange completes (true→false): surfaces a newly created
  // session + its auto-generated title, and re-orders by last activity.
  const prevSending = useRef(false);
  useEffect(() => {
    if (prevSending.current && !chat.sending) void history.refresh();
    prevSending.current = chat.sending;
  }, [chat.sending, history]);

  return (
    <ChatProvider value={chat}>
      <LikedMerchantsProvider>
        <div className="customer-root customer-shell">
          <AmbientBackground />
          <AppSidebar
            theme={theme}
            onToggleTheme={toggle}
            onNewChat={newChat}
            identity={identity}
            open={sidebarOpen}
            onClose={() => setSidebarOpen(false)}
            sessions={history.sessions}
            activeSessionId={identity.sessionId}
            historyLoading={history.loading}
            onOpenSession={onOpenSession}
            onDeleteSession={onDeleteSession}
            onRenameSession={onRenameSession}
          />
          <main className="customer-main">
            <div className="customer-mobile-bar">
              <button
                type="button"
                className="cust-btn cust-btn-icon"
                onClick={() => setSidebarOpen(true)}
                aria-label="Mở menu"
              >
                <Menu size={18} />
              </button>
              <BrandMark />
              <ThemeToggle theme={theme} onToggle={toggle} />
            </div>
            <div className="customer-viewport">
              <Routes>
                <Route path="/" element={<CustomerLanding />} />
                <Route path="/chat" element={<CustomerChat />} />
                <Route path="/explore" element={<CustomerResults />} />
                <Route path="/preferences" element={<PreferenceCenter />} />
                <Route path="*" element={<Navigate to="/customer" replace />} />
              </Routes>
            </div>
          </main>
        </div>
      </LikedMerchantsProvider>
    </ChatProvider>
  );
}
