/**
 * Customer Discovery shell (Dev A owns everything under src/customer/).
 * Warm-glass app: ambient background + segmented sub-nav wrapping four screens —
 * Landing, streaming Chat (UC-04/05), Explore grid, and the Preference Center.
 */
import { Routes, Route, Navigate } from "react-router-dom";
import { AmbientBackground } from "./components/ambient-background";
import { CustomerSubnav } from "./components/customer-subnav";
import CustomerLanding from "./pages/customer-landing";
import CustomerChat from "./pages/customer-chat";
import CustomerResults from "./pages/customer-results";
import PreferenceCenter from "./pages/preference-center";
import "./theme/customer-theme.css";

export function CustomerHome() {
  return (
    <div className="customer-root">
      <AmbientBackground />
      <CustomerSubnav />
      <div className="customer-viewport">
        <Routes>
          <Route path="/" element={<CustomerLanding />} />
          <Route path="/chat" element={<CustomerChat />} />
          <Route path="/explore" element={<CustomerResults />} />
          <Route path="/preferences" element={<PreferenceCenter />} />
          <Route path="*" element={<Navigate to="/customer" replace />} />
        </Routes>
      </div>
    </div>
  );
}
