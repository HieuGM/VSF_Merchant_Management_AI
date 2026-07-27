/**
 * Lifts the Customer chat state machine (useCustomerChat) to the CustomerHome shell so
 * the sidebar's "New chat" action and the chat page share one conversation instance.
 * The chat page consumes `useChat()` instead of instantiating its own hook.
 */
import { createContext, useContext } from "react";
import type { ReactNode } from "react";
import type { useCustomerChat } from "../hooks/use-customer-chat";

export type ChatState = ReturnType<typeof useCustomerChat>;

const ChatContext = createContext<ChatState | null>(null);

export function ChatProvider({ value, children }: { value: ChatState; children: ReactNode }) {
  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat(): ChatState {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat must be used within <ChatProvider>");
  return ctx;
}
