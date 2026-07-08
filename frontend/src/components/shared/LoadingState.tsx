import { Skeleton } from "@/components/ui/skeleton";

/** Institutional-tone loading state — shaped like an incoming message, never a bare spinner. */
export function LoadingState() {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border bg-card p-4">
      <Skeleton className="h-3 w-2/3" />
      <Skeleton className="h-3 w-1/2" />
      <Skeleton className="h-3 w-5/6" />
    </div>
  );
}
