"use client";

import { useState, type ReactNode } from "react";
import { User, Folder, ScrollText, MapPin, Users, Phone } from "lucide-react";
import { cn } from "@/lib/utils";
import { useIsMobile } from "@/lib/use-media-query";
import type { EntitySummary } from "@/lib/types/domain";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

const KIND_ICON: Record<EntitySummary["kind"], typeof User> = {
  person: User,
  case: Folder,
  fir: ScrollText,
  location: MapPin,
  gang: Users,
  phone: Phone,
  address: MapPin,
};

/**
 * People, cases, FIRs, locations render as consistent, tappable chips
 * (steering-docs FRONTEND_UI_STEERING.md §5). Opens a detail Dialog on
 * desktop, a bottom Sheet on mobile — same component in both shells.
 */
export function EntityChip({
  entity,
  detail,
}: {
  entity: EntitySummary;
  detail?: ReactNode;
}) {
  const isMobile = useIsMobile();
  const [open, setOpen] = useState(false);
  const Icon = KIND_ICON[entity.kind];

  const trigger = (
    <button
      type="button"
      onClick={() => setOpen(true)}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border border-border bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground",
        "hover:bg-muted transition-colors",
      )}
    >
      <Icon className="size-3.5" />
      {entity.name}
    </button>
  );

  const body = detail ?? (entity.subtitle && <p>{entity.subtitle}</p>);

  if (isMobile) {
    return (
      <>
        {trigger}
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetContent side="bottom">
            <SheetHeader>
              <SheetTitle>{entity.name}</SheetTitle>
            </SheetHeader>
            <div className="space-y-1 px-4 pb-4 text-sm text-muted-foreground">
              {body}
            </div>
          </SheetContent>
        </Sheet>
      </>
    );
  }

  return (
    <>
      {trigger}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{entity.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-1 text-sm text-muted-foreground">{body}</div>
        </DialogContent>
      </Dialog>
    </>
  );
}
