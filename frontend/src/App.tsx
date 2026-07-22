import { Routes, Route, Navigate } from "react-router-dom";
import { AppLayout } from "@shared/layout";
import { CustomerHome } from "./customer/CustomerHome";
import { ChatbotPage } from "./merchant/pages/ChatbotPage";

/**
 * Router shell — FROZEN Phase 0 seam.
 * Dev A owns everything under /customer, Dev B under /merchant. Add nested routes
 * inside each vertical's own module; do not restructure this top-level switch.
 */
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/merchant" replace />} />
      <Route
        path="/customer/*"
        element={
          <AppLayout>
            <CustomerHome />
          </AppLayout>
        }
      />
      <Route path="/merchant/*" element={<ChatbotPage />} />
      <Route path="*" element={<div className="p-6">404 — Không tìm thấy trang</div>} />
    </Routes>
  );
}
