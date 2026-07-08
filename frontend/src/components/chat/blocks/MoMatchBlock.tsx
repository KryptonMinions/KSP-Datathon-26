import { CheckCircle2, Clock, CircleDashed, XCircle } from "lucide-react";
import type {
  MoMatchBlock as MoMatchBlockType,
  MoOutcome,
} from "@/lib/types/content-blocks";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { CitationChip } from "@/components/shared/CitationChip";
import { cn } from "@/lib/utils";

const OUTCOME_META: Record<
  MoOutcome,
  { label: string; icon: typeof CheckCircle2; className: string }
> = {
  convicted: { label: "Convicted", icon: CheckCircle2, className: "text-success" },
  trial_pending: { label: "Trial pending", icon: Clock, className: "text-warning" },
  investigation_ongoing: {
    label: "Investigation ongoing",
    icon: CircleDashed,
    className: "text-muted-foreground",
  },
  closed_false: { label: "Closed — false", icon: XCircle, className: "text-destructive" },
};

export function MoMatchBlock({ block }: { block: MoMatchBlockType }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground italic">{block.queryDescription}</p>

      {/* Common thread — the "money moment," kept above the fold. */}
      {block.commonThread && (
        <Alert className="border-accent/40 bg-accent/10">
          <AlertTitle className="text-sm">Common thread in solved cases</AlertTitle>
          <AlertDescription>{block.commonThread}</AlertDescription>
        </Alert>
      )}

      <div className="space-y-2">
        {block.matches.map((m) => {
          const meta = OUTCOME_META[m.outcome];
          const Icon = meta.icon;
          const citation = block.citations?.find((c) => c.firId === m.firId);
          return (
            <div
              key={m.firId}
              className="flex flex-col gap-1 rounded-md border border-border p-3 text-sm sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex items-center gap-2">
                <Icon className={cn("size-4 shrink-0", meta.className)} />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="tabular-nums font-medium">{m.firId}</span>
                    <span className="text-muted-foreground">{m.station}</span>
                    <Badge variant="secondary" className="tabular-nums">
                      {Math.round(m.similarity * 100)}%
                    </Badge>
                  </div>
                  <div className={cn("text-xs", meta.className)}>{meta.label}</div>
                  {m.crackedBy && (
                    <div className="text-xs text-muted-foreground">{m.crackedBy}</div>
                  )}
                </div>
              </div>
              {citation && <CitationChip citation={citation} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
