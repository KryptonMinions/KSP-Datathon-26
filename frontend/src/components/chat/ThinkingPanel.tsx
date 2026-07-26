import { useMemo } from "react";
import { AlertCircle, Check, ChevronDown, Loader2 } from "lucide-react";
import type { ThinkingEvent } from "@/lib/types/content-blocks";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

/**
 * `tool_started`/`tool_finished` are two separate raw events for the same
 * call (ASK_STREAM_ENDPOINT_CONTRACT.md §2.2) -- merge each finished event
 * into its matching started row (FIFO by `tool` name) so the UI shows one
 * row per tool call that updates in place, not two permanent rows.
 */
function buildThinkingRows(events: ThinkingEvent[]): ThinkingEvent[] {
  const rows: ThinkingEvent[] = [];
  const openIndexQueues = new Map<string, number[]>();

  for (const evt of events) {
    if (evt.kind === "tool_started" && evt.tool) {
      rows.push(evt);
      const queue = openIndexQueues.get(evt.tool) ?? [];
      queue.push(rows.length - 1);
      openIndexQueues.set(evt.tool, queue);
    } else if (evt.kind === "tool_finished" && evt.tool) {
      const queue = openIndexQueues.get(evt.tool);
      const idx = queue?.shift();
      if (idx !== undefined) {
        rows[idx] = { ...rows[idx], status: evt.status, detail: evt.detail ?? rows[idx].detail, ts: evt.ts };
      } else {
        rows.push(evt);
      }
    } else {
      rows.push(evt);
    }
  }
  return rows;
}

function StatusIcon({ status }: { status: ThinkingEvent["status"] }) {
  if (status === "in_progress") return <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" />;
  if (status === "error") return <AlertCircle className="size-3.5 shrink-0 text-destructive" />;
  return <Check className="size-3.5 shrink-0 text-muted-foreground" />;
}

function ThinkingRow({ row, isStreaming }: { row: ThinkingEvent; isStreaming?: boolean }) {
  // `thought` events (unlike tool_started/tool_finished pairs) never get a
  // terminal status from the backend -- once the turn itself is done, a
  // still-"in_progress" row means "resolved", not "still spinning".
  const status = !isStreaming && row.status === "in_progress" ? "done" : row.status;
  return (
    <div className="flex items-start gap-2 text-xs text-muted-foreground">
      <span className="mt-0.5">
        <StatusIcon status={status} />
      </span>
      <span>
        <span className="text-foreground">{row.label}</span>
        {row.detail && <span className="ml-1">— {row.detail}</span>}
      </span>
    </div>
  );
}

interface ThinkingPanelProps {
  thinking?: ThinkingEvent[];
  isStreaming?: boolean;
}

/** Live activity trace while streaming; collapses to a one-line disclosure
 * once the final answer has landed -- the familiar Claude/ChatGPT/Gemini
 * "thinking" pattern, sourced from the agent's own tool-use trail rather
 * than provider chain-of-thought (ASK_STREAM_ENDPOINT_CONTRACT.md §1.1). */
export function ThinkingPanel({ thinking, isStreaming }: ThinkingPanelProps) {
  const rows = useMemo(() => buildThinkingRows(thinking ?? []), [thinking]);
  if (rows.length === 0) return null;

  if (isStreaming) {
    // Plain inline trace while live -- no bordered box, just a spinner per
    // in-flight row, closer to a lightweight chat "thinking" indicator than
    // a boxed reasoning panel. The bordered/collapsible treatment only
    // applies once the turn is done (below).
    return (
      <div className="space-y-1.5">
        {rows.map((row) => (
          <ThinkingRow key={row.id} row={row} isStreaming={isStreaming} />
        ))}
      </div>
    );
  }

  return (
    <Collapsible className="rounded-md border border-border/60">
      <CollapsibleTrigger className="group/thinking-trigger flex items-center gap-1.5 px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground">
        <ChevronDown className="size-3.5 shrink-0 transition-transform group-aria-expanded/thinking-trigger:rotate-180" />
        Worked through {rows.length} step{rows.length === 1 ? "" : "s"}
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-1.5 px-3 pb-2">
        {rows.map((row) => (
          <ThinkingRow key={row.id} row={row} isStreaming={isStreaming} />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}
