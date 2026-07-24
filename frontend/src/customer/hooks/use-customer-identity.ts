/**
 * Stable anonymous identity for the customer agent.
 * `user_id` persists across visits (localStorage); `session_id` is minted per browser
 * tab load so each discovery conversation is its own session (design §11.4).
 */
import { useRef } from "react";

function makeId(prefix: string): string {
  const rand =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
  return `${prefix}_${rand}`;
}

export function useCustomerIdentity(): { userId: string; sessionId: string } {
  const ref = useRef<{ userId: string; sessionId: string } | null>(null);
  if (ref.current === null) {
    let userId = localStorage.getItem("cust_user_id");
    if (!userId) {
      userId = makeId("user");
      localStorage.setItem("cust_user_id", userId);
    }
    ref.current = { userId, sessionId: makeId("session") };
  }
  return ref.current;
}
