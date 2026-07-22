import { Routes, Route, Navigate } from "react-router-dom";
import { AppLayout } from "@shared/layout";
import { CustomerHome } from "./customer/CustomerHome";
import { MerchantHome } from "./merchant/MerchantHome";

/**
 * Router shell — FROZEN Phase 0 seam.
 * Dev A owns everything under /customer, Dev B under /merchant. Add nested routes
 * inside each vertical's own module; do not restructure this top-level switch.
 */
export default function App() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<Navigate to="/customer" replace />} />
        <Route path="/customer/*" element={<CustomerHome />} />
        <Route path="/merchant/*" element={<MerchantHome />} />
        <Route path="*" element={<div className="p-6">404 — Không tìm thấy trang</div>} />
      </Routes>
    </AppLayout>
  );
}
