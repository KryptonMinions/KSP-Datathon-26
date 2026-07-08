import type { ChatMessage } from "@/lib/types/content-blocks";

/**
 * The calm abstention state (steering-docs FRONTEND_UI_STEERING.md §5) —
 * rendered when the mock service (or, later, the real orchestrator) is not
 * confident enough in an answer to produce one.
 */
export function buildNoAnswerResponse(): ChatMessage {
  return {
    id: `no-answer-${Date.now()}`,
    role: "assistant",
    timestamp: new Date().toISOString(),
    blocks: [
      {
        id: `no-answer-block-${Date.now()}`,
        type: "no_answer",
        message:
          "Not enough verified information to answer this. Try rephrasing, or consult the case file directly.",
      },
    ],
  };
}
