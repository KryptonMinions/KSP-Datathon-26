"use client";

import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "@/lib/types/content-blocks";
import { useAuth } from "@/lib/auth/auth-context";
import { useAsk } from "@/lib/ask/use-ask";
import { MessageBubble } from "./MessageBubble";
import { QueryInput, type SendMeta } from "./QueryInput";
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
  // Null starts a new server-side thread; set once the first response
  // echoes one back (ASK_ENDPOINT_CONTRACT.md §2.3/§2.4). turnIndex is
  // 0-based and monotonic per thread, tracked here since the service layer
  // is stateless between calls.
  const [threadId, setThreadId] = useState<string | null>(null);
  const [turnIndex, setTurnIndex] = useState(0);
  const { mutateAsync, isPending, isError, error } = useAsk();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isPending]);

  const handleSend = async (query: string, meta: SendMeta) => {
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      timestamp: new Date().toISOString(),
      text: query,
    };
    setMessages((prev) => [...prev, userMessage]);

    try {
      const response = await mutateAsync({
        query,
        threadId,
        turnIndex,
        role: user?.role ?? "investigating_officer",
        detectedLanguage: meta.detectedLanguage,
        inputModality: meta.inputModality,
      });
      setMessages((prev) => [...prev, response]);
      if (response.threadId) setThreadId(response.threadId);
      setTurnIndex((i) => i + 1);
    } catch {
      // A transport/validation failure is a distinct, retryable state from
      // `no_answer` (a normal 200 response) -- isError/error below render
      // it; nothing to append to the thread here (§3.5).
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 && emptyState}
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {isPending && <LoadingState />}
        {isError && <ErrorState message={error instanceof Error ? error.message : undefined} />}
        <div ref={bottomRef} />
      </div>
      <QueryInput onSend={handleSend} disabled={isPending} size={inputSize} />
    </div>
  );
}
