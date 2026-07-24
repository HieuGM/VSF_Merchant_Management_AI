import { NavLink } from "react-router-dom";
import type { ReactNode } from "react";
import "./layout.css";

/**
 * Mobile-first app shell (design §4). Shared chrome both verticals render inside.
 * Replace nav styling with the provided UI design tokens/components.
 */
export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>VSF Merchant AI</h1>
      </header>
      <main className="app-main">{children}</main>
      <nav className="app-nav">
        <NavLink to="/customer" className="nav-link">
          Khám phá
        </NavLink>
        <NavLink to="/merchant" className="nav-link">
          Cửa hàng
        </NavLink>
      </nav>
    </div>
  );
}
