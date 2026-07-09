import type { ChatMessage } from "@/lib/types/content-blocks";
import type { Role } from "@/lib/types/auth";

export interface AskInput {
  query: string;
  sessionId: string;
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
