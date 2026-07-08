"use client";

import { useState, type KeyboardEvent } from "react";
import Image from "next/image";
import { SendHorizonal } from "lucide-react";
import { cn } from "@/lib/utils";

interface QueryInputProps {
  onSend: (query: string) => void;
  disabled?: boolean;
  /** Larger, touch-first sizing for the IO MobileShell (steering-docs §9). */
  size?: "default" | "large";
  placeholder?: string;
}

/** Shared, shell-agnostic query input — sized via a prop, not a second component (steering-docs §1). */
export function QueryInput({
  onSend,
  disabled,
  size = "default",
  placeholder = "Ask me Anything...",
}: QueryInputProps) {
  const [value, setValue] = useState("");
  // UI-only for now — no transcription is wired up yet. This will call a
  // backend speech-transcription model in a follow-up; today it just toggles the pressed/listening visual state.
  const [isListening, setIsListening] = useState(false);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="border-t border-border bg-background p-3">
      <div
        className={cn(
          "flex flex-col rounded-3xl border border-white/25 bg-white/10 shadow-lg backdrop-blur-xl",
          "dark:border-white/10 dark:bg-white/5",
        )}
      >
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          rows={size === "large" ? 2 : 1}
          disabled={disabled}
          className={cn(
            "resize-none bg-transparent px-4 pt-3 text-sm outline-none placeholder:text-muted-foreground",
            size === "large" && "text-base",
          )}
        />
        <div className="flex items-center justify-end gap-2 px-2.5 pb-2.5 pt-1">
          <button
            type="button"
            onClick={() => setIsListening((prev) => !prev)}
            disabled={disabled}
            title="Speak your question"
            aria-pressed={isListening}
            className={cn(
              "inline-flex shrink-0 items-center justify-center rounded-full border shadow-sm backdrop-blur-md transition-colors",
              "disabled:opacity-40",
              isListening
                ? "border-accent/50 bg-accent/40 ring-2 ring-accent/40 animate-pulse"
                : "border-black/10 bg-black/6 hover:bg-black/10 dark:border-white/15 dark:bg-white/10 dark:hover:bg-white/20",
              size === "large" ? "size-11" : "size-8",
            )}
            aria-label={isListening ? "Stop voice input" : "Start voice input"}
          >
            <Image
              src="/voice-svgrepo-com.svg"
              alt=""
              width={20}
              height={20}
              className={size === "large" ? "size-5" : "size-4"}
            />
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={disabled || !value.trim()}
            className={cn(
              "inline-flex shrink-0 items-center justify-center rounded-full border border-white/20 bg-primary/85 text-primary-foreground backdrop-blur-md transition-opacity",
              "disabled:opacity-40",
              size === "large" ? "size-11" : "size-8",
            )}
            aria-label="Send"
          >
            <SendHorizonal className={size === "large" ? "size-5" : "size-4"} />
          </button>
        </div>
      </div>
    </div>
  );
}
