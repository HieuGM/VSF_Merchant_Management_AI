import type { ReactNode } from "react";
import "./layout.css";

/**
 * Full-height chrome-free shell. Each vertical (customer/merchant) renders its own
 * chrome inside. No header/bottom-nav — the customer app owns a ChatGPT-style sidebar.
 */
export function AppLayout({ children }: { children: ReactNode }) {
  return <div className="app-shell">{children}</div>;
}
