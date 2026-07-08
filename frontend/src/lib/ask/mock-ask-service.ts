import type { AskInput, AskService } from "./ask-service";
import type { ChatMessage } from "@/lib/types/content-blocks";
import {
  STORY1_QUERIES,
  story1Query1Response,
  story1Query2Response,
  story1Query3Response,
} from "@/lib/fixtures/story1-antecedents";
import { STORY4_QUERY, story4Response } from "@/lib/fixtures/story4-network";
import { STORY2_QUERY, story2Response } from "@/lib/fixtures/story2-mo-match";
import { STORY10_QUERY, story10Response } from "@/lib/fixtures/story10-review-pack";
import { buildNoAnswerResponse } from "@/lib/fixtures/no-answer";

function normalize(query: string): string {
  return query.trim().toLowerCase().replace(/\s+/g, " ");
}

const RESPONSE_BY_QUERY: Record<string, ChatMessage> = {
  [STORY1_QUERIES.q1]: story1Query1Response,
  [STORY1_QUERIES.q2]: story1Query2Response,
  [STORY1_QUERIES.q3]: story1Query3Response,
  [STORY4_QUERY]: story4Response,
  [STORY2_QUERY]: story2Response,
  [STORY10_QUERY]: story10Response,
};

function withFreshIds(message: ChatMessage): ChatMessage {
  const suffix = Math.random().toString(36).slice(2, 8);
  return {
    ...message,
    id: `${message.id}-${suffix}`,
    timestamp: new Date().toISOString(),
  };
}

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Deterministic mock implementation of AskService, keyed on the exact
 * verbatim query strings from References/KSP_Demo_Script.pdf so the four
 * demo beats work reliably. Falls back to a calm `no_answer` block for any
 * unmatched query, exercising the abstention state by default rather than
 * leaving it unreachable (steering-docs FRONTEND_UI_STEERING.md §5).
 */
export class MockAskService implements AskService {
  async ask({ query }: AskInput): Promise<ChatMessage> {
    await delay(400 + Math.random() * 400);

    const match = RESPONSE_BY_QUERY[normalize(query)];
    if (match) {
      return withFreshIds(match);
    }

    return buildNoAnswerResponse();
  }
}

export const mockAskService = new MockAskService();
