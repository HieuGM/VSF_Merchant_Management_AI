import { NavLink } from "react-router-dom";
import type { ReactNode } from "react";

/**
 * Mobile-first app shell (design §4). Shared chrome both verticals render inside.
 * Replace nav styling with the provided UI design tokens/components.
 */
export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col bg-white shadow-sm">
      <header className="sticky top-0 z-10 bg-brand px-4 py-3 text-white">
        <h1 className="text-lg font-semibold">VSF Merchant AI</h1>
      </header>
      <main className="flex-1">{children}</main>
      <nav className="sticky bottom-0 grid grid-cols-2 border-t bg-white text-center text-sm">
        <NavLink to="/customer" className={tabClass}>
          Khám phá
        </NavLink>
        <NavLink to="/merchant" className={tabClass}>
          Cửa hàng
        </NavLink>
      </nav>
    </div>
  );
}

function tabClass({ isActive }: { isActive: boolean }) {
  return `py-3 ${isActive ? "font-semibold text-brand" : "text-gray-500"}`;
}
