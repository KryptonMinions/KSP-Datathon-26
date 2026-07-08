import type { ChatMessage } from "@/lib/types/content-blocks";
import type { Role } from "@/lib/types/auth";

export interface AskInput {
  query: string;
  sessionId: string;
  role: Role;
}

/**
 * The single swap point between the demo's mock data layer and a future
 * real orchestrator/API client — nothing above this interface should need
 * to change when a `RealAskService` is introduced.
 */
export interface AskService {
  ask(input: AskInput): Promise<ChatMessage>;
}
