/** Segmented tab bar for the customer vertical (Home · Chat · Explore · Preferences). */
import { NavLink } from "react-router-dom";
import "./customer-subnav.css";

const TABS = [
  { to: "/customer", icon: "🏠", label: "Trang chủ", end: true },
  { to: "/customer/chat", icon: "💬", label: "Trò chuyện", end: false },
  { to: "/customer/explore", icon: "🧭", label: "Khám phá", end: false },
  { to: "/customer/preferences", icon: "🎛️", label: "Khẩu vị", end: false },
];

export function CustomerSubnav() {
  return (
    <nav className="csubnav cust-glass-strong">
      {TABS.map((t) => (
        <NavLink
          key={t.to}
          to={t.to}
          end={t.end}
          className={({ isActive }) => `csubnav__tab ${isActive ? "is-active" : ""}`}
        >
          <span className="csubnav__icon">{t.icon}</span>
          <span className="csubnav__label">{t.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
