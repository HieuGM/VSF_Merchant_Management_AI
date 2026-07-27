/**
 * Customer Discovery shell (Dev A owns everything under src/customer/).
 * ChatGPT-style: ambient background + left sidebar + main viewport. The chat state
 * machine is lifted here (ChatProvider) so the sidebar's "New chat" and the chat page
 * share one conversation. Screens: Landing, streaming Chat (UC-04/05), Explore, Preferences.
 */
import { useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Menu } from "lucide-react";
import { AmbientBackground } from "./components/ambient-background";
import { AppSidebar } from "./components/app-sidebar";
import { BrandMark } from "./components/brand-mark";
import { ThemeToggle } from "./components/theme-toggle";
import { ChatProvider } from "./context/chat-provider";
import { useCustomerChat } from "./hooks/use-customer-chat";
import { useCustomerIdentity } from "./hooks/use-customer-identity";
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
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();

  const newChat = () => {
    chat.reset();
    navigate("/customer/chat");
  };

  return (
    <ChatProvider value={chat}>
      <div className="customer-root customer-shell">
        <AmbientBackground />
        <AppSidebar
          theme={theme}
          onToggleTheme={toggle}
          onNewChat={newChat}
          identity={identity}
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
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
    </ChatProvider>
  );
}
