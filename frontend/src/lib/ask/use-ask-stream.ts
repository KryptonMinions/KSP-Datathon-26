"use client";

import { useCallback, useState } from "react";
import { useAuth } from "@/lib/auth/auth-context";
import type { ChatMessage, ThinkingEvent } from "@/lib/types/content-blocks";
import type { AskInput } from "./ask-service";
import { UnauthenticatedError } from "./ask-service";
import { streamAsk } from "./ask-stream-service";

interface StreamCallbacks {
  onThinking: (event: ThinkingEvent) => void;
  onDone: (message: ChatMessage) => void;
  onError: (error: Error) => void;
}

/**
 * Streaming counterpart to use-ask.ts's useMutation -- not a retrofit of it,
 * since incremental thinking/message updates don't fit React Query's
 * single-resolve model. Callers drive their own message state via the
 * callbacks (see ChatThread.tsx) rather than getting a single resolved
 * value back.
 *
 * No reconnect-on-drop (ASK_STREAM_ENDPOINT_CONTRACT.md §2.5) -- a dropped
 * connection mid-turn surfaces once via onError, same failure class as a
 * failed non-streaming call today.
 */
export function useAskStream() {
  const { logout } = useAuth();
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const send = useCallback(
    async (input: AskInput, callbacks: StreamCallbacks) => {
      setIsStreaming(true);
      setError(null);
      try {
        for await (const evt of streamAsk(input)) {
          if (evt.type === "thinking") {
            callbacks.onThinking(evt.event);
          } else {
            callbacks.onDone(evt.message);
          }
        }
      } catch (err) {
        const asError = err instanceof Error ? err : new Error("Streaming failed");
        setError(asError);
        // Role Authority Rule / auth boundary -- same handling as use-ask.ts.
        if (asError instanceof UnauthenticatedError) {
          logout();
        }
        callbacks.onError(asError);
      } finally {
        setIsStreaming(false);
      }
    },
    [logout],
  );

  return { send, isStreaming, error };
}
