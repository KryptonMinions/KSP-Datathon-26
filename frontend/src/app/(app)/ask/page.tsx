"use client";

import { useAuth } from "@/lib/auth/auth-context";
import { ChatThread } from "@/components/chat/ChatThread";

/**
 * The shared conversational surface for every role (steering-docs §1). For
 * IO this is the landing screen itself — there is no separate IO dashboard.
 */
export default function AskPage() {
  const { user } = useAuth();
  const isIo = user?.role === "investigating_officer";

  return (
    <ChatThread
      inputSize={isIo ? "large" : "default"}
      emptyState={
        <div className="flex h-full flex-col items-center justify-center gap-1 py-16 text-center text-muted-foreground">
          <p className="text-sm">Ask about a case, a person, or a trend.</p>
          <p className="text-xs">Every answer carries a citation you can verify.</p>
        </div>
      }
    />
  );
}
