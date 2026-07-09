import type { ChatMessage, ContentBlock, Citation } from "@/lib/types/content-blocks";
import type { AskInput, AskService } from "./ask-service";
import { AskServiceError, InvalidRequestError, UnauthenticatedError } from "./ask-service";
import { getAccessToken } from "@/lib/auth/auth-context";

/**
 * Wire types straight off ASK_ENDPOINT_CONTRACT.md §2.4 -- idiomatic
 * snake_case, matching every other backend response in this app
 * (LoginResponse.access_token, VoiceTranscribeResponse.detected_language).
 * `wireToBlock`/`wireToCitations` below translate these into the camelCase
 * shapes content-blocks.ts expects, the same boundary-translation pattern
 * auth-api.ts and voice-api.ts already use.
 */
interface WireCitation {
  level: "fir" | "field" | "sentence";
  fir_id: string;
  field?: string | null;
  sentence_id?: string | null;
  excerpt?: string | null;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type WireBlock = Record<string, any>;

interface WireAssistantMessage {
  role: "assistant";
  text?: string | null;
  blocks: WireBlock[];
}

interface WireAskResponse {
  thread_id: string;
  message_id: string;
  server_ts: string;
  message: WireAssistantMessage;
}

function wireCitations(citations: WireCitation[] | null | undefined): Citation[] | undefined {
  if (!citations) return undefined;
  return citations.map((c) => ({
    level: c.level,
    firId: c.fir_id,
    field: c.field ?? undefined,
    sentenceRef: c.sentence_id ?? undefined,
    label: c.excerpt ?? c.fir_id,
  }));
}

function wireToBlock(block: WireBlock): ContentBlock {
  const citations = wireCitations(block.citations);
  switch (block.type) {
    case "text":
      return { id: block.id, type: "text", content: block.content, citations };
    case "table":
      return {
        id: block.id,
        type: "table",
        title: block.title ?? undefined,
        columns: block.columns,
        rows: block.rows,
        citations,
      };
    case "network_graph":
      return {
        id: block.id,
        type: "network_graph",
        centralNodeId: block.central_node_id,
        nodes: block.nodes,
        edges: block.edges.map((e: WireBlock) => ({
          source: e.source,
          target: e.target,
          label: e.label,
          firId: e.fir_id,
        })),
        citations,
      };
    case "mo_match":
      return {
        id: block.id,
        type: "mo_match",
        queryDescription: block.query_description,
        matches: block.matches.map((m: WireBlock) => ({
          firId: m.fir_id,
          station: m.station,
          similarity: m.similarity,
          outcome: m.outcome,
          crackedBy: m.cracked_by ?? undefined,
        })),
        commonThread: block.common_thread ?? undefined,
        citations,
      };
    case "case_card":
      return {
        id: block.id,
        type: "case_card",
        person: block.person ?? undefined,
        cases: block.cases.map((c: WireBlock) => ({
          firId: c.fir_id,
          station: c.station,
          offence: c.offence,
          section: c.section,
          status: c.status,
          detail: c.detail ?? undefined,
        })),
        historySheet: block.history_sheet
          ? {
              id: block.history_sheet.id,
              station: block.history_sheet.station,
              openedOn: block.history_sheet.opened_on,
              category: block.history_sheet.category,
              riskLevel: block.history_sheet.risk_level,
              registeredCases: block.history_sheet.registered_cases,
              convictions: block.history_sheet.convictions,
              abscondingInstances: block.history_sheet.absconding_instances,
            }
          : undefined,
        citations,
      };
    case "no_answer":
      return { id: block.id, type: "no_answer", message: block.message, citations };
    case "pack_report":
      return {
        id: block.id,
        type: "pack_report",
        title: block.title,
        period: block.period,
        exportable: block.exportable ?? undefined,
        metrics: block.metrics.map((m: WireBlock) => ({
          category: m.category,
          current: m.current,
          previous: m.previous,
          deltaPct: m.delta_pct,
          trend: m.trend,
          anomaly: m.anomaly ?? undefined,
          anomalyNote: m.anomaly_note ?? undefined,
          underlyingFirIds: m.underlying_fir_ids ?? undefined,
        })),
        citations,
      };
    default:
      // Contract §3.7: no block-type feature detection -- assume responses
      // match the union exactly. If we get here, the backend is out of sync
      // with content-blocks.ts.
      throw new AskServiceError("internal_error", `Unknown block type: ${block.type}`);
  }
}

/**
 * Real backend-backed AskService (ASK_ENDPOINT_CONTRACT.md §3). Fixture
 * dispatch happens server-side in this phase -- no query intelligence here,
 * just the HTTP call and wire/camelCase translation.
 */
export class RealAskService implements AskService {
  private readonly apiUrl: string;

  constructor() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!apiUrl) {
      // Fail-fast, not a silent fallback to mock (§3.3).
      throw new Error("NEXT_PUBLIC_API_URL is required for RealAskService");
    }
    this.apiUrl = apiUrl;
  }

  async ask(input: AskInput): Promise<ChatMessage> {
    const accessToken = getAccessToken();
    if (!accessToken) {
      throw new UnauthenticatedError("No active session");
    }

    let res: Response;
    try {
      res = await fetch(`${this.apiUrl}/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          query: input.query,
          thread_id: input.threadId,
          turn_index: input.turnIndex,
          input_modality: input.inputModality === "voice" ? "voice" : "text",
          detected_language: input.detectedLanguage ?? null,
          client_ts: new Date().toISOString(),
        }),
      });
    } catch (err) {
      throw new AskServiceError("network_error", (err as Error).message);
    }

    if (!res.ok) {
      const body = await res.json().catch(() => null);
      const code: string = body?.error?.code ?? "unknown_error";
      const message: string = body?.error?.message ?? "The request could not be completed.";
      if (res.status === 401) throw new UnauthenticatedError(message);
      if (res.status === 422) throw new InvalidRequestError(message);
      throw new AskServiceError(code, message, res.status);
    }

    const wire: WireAskResponse = await res.json();
    return {
      id: wire.message_id,
      role: "assistant",
      timestamp: wire.server_ts,
      text: wire.message.text ?? undefined,
      blocks: wire.message.blocks.map(wireToBlock),
      threadId: wire.thread_id,
    };
  }
}
