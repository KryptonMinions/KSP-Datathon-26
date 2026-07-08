"use client";

import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "@/lib/types/content-blocks";
import { useAuth } from "@/lib/auth/auth-context";
import { useAsk } from "@/lib/ask/use-ask";
import { MessageBubble } from "./MessageBubble";
import { QueryInput } from "./QueryInput";
import { LoadingState } from "@/components/shared/LoadingState";
import { ErrorState } from "@/components/shared/ErrorState";

interface ChatThreadProps {
  /** Larger touch targets for the IO MobileShell (steering-docs §9). */
  inputSize?: "default" | "large";
  emptyState?: React.ReactNode;
}

/** The core conversational surface, shared identically by every role (steering-docs §1). */
export function ChatThread({ inputSize = "default", emptyState }: ChatThreadProps) {
  const { user } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId] = useState(
    () => `session-${Math.random().toString(36).slice(2)}`,
  );
  const { mutateAsync, isPending, isError } = useAsk();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isPending]);

  const handleSend = async (query: string) => {
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      timestamp: new Date().toISOString(),
      text: query,
    };
    setMessages((prev) => [...prev, userMessage]);

    const response = await mutateAsync({
      query,
      sessionId,
      role: user?.role ?? "io",
    });
    setMessages((prev) => [...prev, response]);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 && emptyState}
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {isPending && <LoadingState />}
        {isError && <ErrorState />}
        <div ref={bottomRef} />
      </div>
      <QueryInput onSend={handleSend} disabled={isPending} size={inputSize} />
    </div>
  );
}
