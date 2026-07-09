import type { ChatMessage } from "@/lib/types/content-blocks";
import type { Role } from "@/lib/types/auth";

export interface AskInput {
  query: string;
  /** Null starts a new thread; the chat container carries forward the
   * `threadId` the server echoes back on the response (ASK_ENDPOINT_CONTRACT.md
   * §2.3/§2.4) so later turns land in the same thread. */
  threadId: string | null;
  /** 0-based, monotonic per thread — the chat container tracks this. */
  turnIndex: number;
  role: Role;
  /** Voice-sourced Ask messages carry these for audit/downstream use (steering-docs/VOICE_INTAKE_STEERING.md §4/§6). */
  detectedLanguage?: "en" | "kn" | null;
  inputModality?: "voice" | "typed";
}

/**
 * The single swap point between the demo's mock data layer and a future
 * real orchestrator/API client — nothing above this interface should need
 * to change when a `RealAskService` is introduced.
 */
export interface AskService {
  ask(input: AskInput): Promise<ChatMessage>;
}

export class UnauthenticatedError extends Error {}
export class InvalidRequestError extends Error {}
export class AskServiceError extends Error {
  code: string;
  /** HTTP status when this came from a response (undefined for network errors) —
   * `use-ask.ts`'s retry policy (§3.6) keys off this, not `code`. */
  status?: number;
  constructor(code: string, message: string, status?: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}
