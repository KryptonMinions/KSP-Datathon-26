import type { ChatMessage } from "@/lib/types/content-blocks";
import { cn } from "@/lib/utils";
import { BlockRenderer } from "./BlockRenderer";

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[92%] space-y-2 sm:max-w-[85%]",
          isUser
            ? "rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground"
            : "w-full",
        )}
      >
        {isUser && message.text && <p>{message.text}</p>}
        {!isUser && (
          <div className="space-y-3">
            {message.text && <p className="text-sm">{message.text}</p>}
            {message.blocks?.map((block) => (
              <BlockRenderer key={block.id} block={block} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
