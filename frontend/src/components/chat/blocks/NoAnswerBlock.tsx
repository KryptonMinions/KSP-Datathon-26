import { Info, ShieldAlert } from "lucide-react";
import type { NoAnswerBlock as NoAnswerBlockType } from "@/lib/types/content-blocks";

/**
 * The calm abstention state — never styled as an error. If the system is
 * not confident, it withholds the answer entirely rather than hedging
 * (steering-docs FRONTEND_UI_STEERING.md §5). The message copy already
 * differs per `reason` (composer.py) — the icon swap for `out_of_scope` is
 * the one further distinction worth making: it's a permission boundary, not
 * an empty search result, and should read differently at a glance.
 */
export function NoAnswerBlock({ block }: { block: NoAnswerBlockType }) {
  const Icon = block.reason === "out_of_scope" ? ShieldAlert : Info;
  return (
    <div className="flex items-start gap-2 rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
      <Icon className="mt-0.5 size-4 shrink-0" />
      <p>{block.message}</p>
    </div>
  );
}
