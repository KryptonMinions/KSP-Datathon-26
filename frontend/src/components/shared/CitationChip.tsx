"use client";

import { useState } from "react";
import { FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import { useIsMobile } from "@/lib/use-media-query";
import type { Citation } from "@/lib/types/content-blocks";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

const LEVEL_LABEL: Record<Citation["level"], string> = {
  fir: "FIR",
  field: "Field",
  sentence: "Sentence",
};

/**
 * Citations are always on — never a toggle (steering-docs FRONTEND_UI_STEERING.md §5).
 * Tappable/legible on mobile (opens a Sheet); expandable to richer detail on
 * desktop (hover Tooltip). Every inline renderer consumes this component.
 */
export function CitationChip({ citation }: { citation: Citation }) {
  const isMobile = useIsMobile();
  const [open, setOpen] = useState(false);

  const detail = (
    <div className="space-y-1 text-xs">
      <div className="font-medium">{LEVEL_LABEL[citation.level]} citation</div>
      <div className="tabular-nums">FIR: {citation.firId}</div>
      {citation.field && <div>Field: {citation.field}</div>}
      {citation.sentenceRef && <div>Reference: {citation.sentenceRef}</div>}
    </div>
  );

  const chipClassName = cn(
    "inline-flex items-center gap-1 rounded-sm border border-border bg-background px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground",
    "hover:bg-muted hover:text-foreground transition-colors",
  );

  if (isMobile) {
    return (
      <>
        <button type="button" onClick={() => setOpen(true)} className={chipClassName}>
          <FileText className="size-3" />
          <span className="tabular-nums">{citation.label}</span>
        </button>
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetContent side="bottom">
            <SheetHeader>
              <SheetTitle>Source citation</SheetTitle>
            </SheetHeader>
            <div className="px-4 pb-4">{detail}</div>
          </SheetContent>
        </Sheet>
      </>
    );
  }

  return (
    <Tooltip>
      <TooltipTrigger className={chipClassName}>
        <FileText className="size-3" />
        <span className="tabular-nums">{citation.label}</span>
      </TooltipTrigger>
      <TooltipContent>{detail}</TooltipContent>
    </Tooltip>
  );
}
