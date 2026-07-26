"use client";

import { useEffect, useRef, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import type { ChatMessage, ThinkingEvent } from "@/lib/types/content-blocks";
import { useAuth } from "@/lib/auth/auth-context";
import { useAsk } from "@/lib/ask/use-ask";
import { useAskStream } from "@/lib/ask/use-ask-stream";
import { askService } from "@/lib/ask/index";
import { RealAskService } from "@/lib/ask/real-ask-service";
import { exportSessionPdf } from "@/lib/export/export-pdf";
import { Button } from "@/components/ui/button";
import { MessageBubble } from "./MessageBubble";
import { QueryInput, type SendMeta } from "./QueryInput";
import { LoadingState } from "@/components/shared/LoadingState";
import { ErrorState } from "@/components/shared/ErrorState";

// Resolved once at module load, mirroring the mock/real toggle in
// lib/ask/index.ts -- MockAskService (offline dev, NEXT_PUBLIC_ASK_SERVICE=
// mock) never supports streaming, so this stays a binary check rather than
// a separate capability-flag abstraction (ASK_STREAM_ENDPOINT_CONTRACT.md §3).
const supportsStreaming = askService instanceof RealAskService;

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
  const { mutateAsync, isPending: isMutationPending, isError: isMutationError, error: mutationError } = useAsk();
  const { send: sendStream, isStreaming } = useAskStream();
  // True from send-start until the first thinking/message/error event lands
  // -- keeps the generic skeleton up for just the pre-first-byte gap, then
  // the placeholder assistant message's own ThinkingPanel takes over.
  const [isAwaitingFirstEvent, setIsAwaitingFirstEvent] = useState(false);
  const [streamError, setStreamError] = useState<Error | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const isPending = supportsStreaming ? isStreaming : isMutationPending;
  const isError = supportsStreaming ? streamError !== null : isMutationError;
  const error = supportsStreaming ? streamError : mutationError;
  const showLoadingSkeleton = supportsStreaming ? isPending && isAwaitingFirstEvent : isPending;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isPending]);

  const handleExport = async () => {
    setExportError(null);
    setIsExporting(true);
    try {
      await exportSessionPdf(messages, threadId);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setIsExporting(false);
    }
  };

  const handleSendStreaming = async (query: string, meta: SendMeta) => {
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      timestamp: new Date().toISOString(),
      text: query,
    };
    const placeholderId = `assistant-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      userMessage,
      {
        id: placeholderId,
        role: "assistant",
        timestamp: new Date().toISOString(),
        isStreaming: true,
        thinking: [],
      },
    ]);
    setStreamError(null);
    setIsAwaitingFirstEvent(true);

    await sendStream(
      {
        query,
        threadId,
        turnIndex,
        role: user?.role ?? "investigating_officer",
        detectedLanguage: meta.detectedLanguage,
        inputModality: meta.inputModality,
      },
      {
        onThinking: (event: ThinkingEvent) => {
          setIsAwaitingFirstEvent(false);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === placeholderId ? { ...m, thinking: [...(m.thinking ?? []), event] } : m,
            ),
          );
        },
        onDone: (finalMessage: ChatMessage) => {
          setIsAwaitingFirstEvent(false);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === placeholderId
                ? { ...finalMessage, id: placeholderId, thinking: m.thinking, isStreaming: false }
                : m,
            ),
          );
          if (finalMessage.threadId) setThreadId(finalMessage.threadId);
          setTurnIndex((i) => i + 1);
        },
        onError: (err: Error) => {
          // Same distinct-state rule as the non-streaming path below: a
          // transport failure doesn't leave a ghost bubble in the thread,
          // ErrorState renders it instead.
          setIsAwaitingFirstEvent(false);
          setStreamError(err);
          setMessages((prev) => prev.filter((m) => m.id !== placeholderId));
        },
      },
    );
  };

  const handleSendNonStreaming = async (query: string, meta: SendMeta) => {
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

  const handleSend = supportsStreaming ? handleSendStreaming : handleSendNonStreaming;

  return (
    <div className="flex h-full flex-col">
      {messages.length > 0 && (
        <div className="flex items-center justify-end gap-2 border-b border-border px-4 py-1.5">
          {exportError && <span className="text-xs text-destructive">{exportError}</span>}
          <Button variant="outline" size="sm" onClick={handleExport} disabled={isExporting}>
            {isExporting ? <Loader2 className="animate-spin" /> : <Download />}
            Export PDF
          </Button>
        </div>
      )}
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 && emptyState}
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {showLoadingSkeleton && <LoadingState />}
        {isError && <ErrorState message={error instanceof Error ? error.message : undefined} />}
        <div ref={bottomRef} />
      </div>
      <QueryInput onSend={handleSend} disabled={isPending} size={inputSize} />
    </div>
  );
}
