import type { ChatMessage, Citation, ContentBlock } from "@/lib/types/content-blocks";
import { getAccessToken } from "@/lib/auth/auth-context";

/**
 * Wire-shape (snake_case) translator, the reverse direction of
 * real-ask-service.ts's wireToBlock. PDF export (2026-07-26) is stateless —
 * the frontend sends the conversation it already has on screen; nothing is
 * persisted server-side (steering-docs/POST_OVERNIGHT.md §4 tracks durable
 * server-side history as future scope).
 */
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function citationToWire(c: Citation) {
  return {
    level: c.level,
    fir_id: c.firId,
    field: c.field ?? null,
    sentence_id: c.sentenceRef ?? null,
    excerpt: c.label ?? null,
  };
}

function blockToWire(block: ContentBlock): Record<string, unknown> {
  const citations = block.citations?.map(citationToWire) ?? null;
  switch (block.type) {
    case "text":
      return { type: "text", id: block.id, content: block.content, citations };
    case "table":
      return {
        type: "table", id: block.id, title: block.title ?? null,
        columns: block.columns, rows: block.rows, citations,
      };
    case "network_graph":
      return {
        type: "network_graph", id: block.id, central_node_id: block.centralNodeId,
        nodes: block.nodes,
        edges: block.edges.map((e) => ({ source: e.source, target: e.target, label: e.label, fir_id: e.firId })),
        citations,
      };
    case "mo_match":
      return {
        type: "mo_match", id: block.id, query_description: block.queryDescription,
        matches: block.matches.map((m) => ({
          fir_id: m.firId, station: m.station, similarity: m.similarity, outcome: m.outcome,
          cracked_by: m.crackedBy ?? null,
        })),
        common_thread: block.commonThread ?? null,
        citations,
      };
    case "case_card":
      return {
        type: "case_card", id: block.id,
        person: block.person ?? null,
        cases: block.cases.map((c) => ({
          fir_id: c.firId, station: c.station, offence: c.offence, section: c.section,
          status: c.status, detail: c.detail ?? null,
        })),
        history_sheet: block.historySheet
          ? {
              id: block.historySheet.id, station: block.historySheet.station,
              opened_on: block.historySheet.openedOn, category: block.historySheet.category,
              risk_level: block.historySheet.riskLevel,
              registered_cases: block.historySheet.registeredCases,
              convictions: block.historySheet.convictions,
              absconding_instances: block.historySheet.abscondingInstances,
            }
          : null,
        citations,
      };
    case "no_answer":
      return { type: "no_answer", id: block.id, message: block.message, reason: null, citations };
    case "pack_report":
      return {
        type: "pack_report", id: block.id, title: block.title, period: block.period,
        metrics: block.metrics.map((m) => ({
          category: m.category, current: m.current, previous: m.previous, delta_pct: m.deltaPct,
          trend: m.trend, anomaly: m.anomaly ?? null, anomaly_note: m.anomalyNote ?? null,
          underlying_fir_ids: m.underlyingFirIds ?? null,
        })),
        exportable: block.exportable ?? null,
        citations,
      };
    case "map":
      return {
        type: "map", id: block.id, title: block.title ?? null,
        center: block.center, zoom: block.zoom ?? null,
        markers: block.markers.map((m) => ({
          id: m.id, lat: m.lat, lng: m.lng, kind: m.kind, label: m.label,
          fir_id: m.firId ?? null, offence: m.offence ?? null, date: m.date ?? null, status: m.status ?? null,
        })),
        radius: block.radius
          ? {
              center_lat: block.radius.centerLat, center_lng: block.radius.centerLng,
              radius_meters: block.radius.radiusMeters, label: block.radius.label ?? null,
            }
          : null,
        citations,
      };
  }
}

function messageToWireTurn(message: ChatMessage) {
  return {
    role: message.role,
    timestamp: message.timestamp,
    text: message.text ?? null,
    blocks: message.blocks ? message.blocks.map(blockToWire) : null,
  };
}

export class ExportPdfError extends Error {}

export async function exportSessionPdf(messages: ChatMessage[], threadId: string | null): Promise<void> {
  const accessToken = getAccessToken();
  if (!accessToken) throw new ExportPdfError("No active session");

  const turns = messages.map(messageToWireTurn);
  let res: Response;
  try {
    res = await fetch(`${API_URL}/export/pdf`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ thread_id: threadId, turns }),
    });
  } catch (err) {
    throw new ExportPdfError((err as Error).message);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ExportPdfError(body?.detail ?? "Export failed");
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `ksp-ask-session-${threadId ?? "export"}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
