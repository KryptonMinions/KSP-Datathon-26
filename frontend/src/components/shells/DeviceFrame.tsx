import type { ReactNode } from "react";

/**
 * Presentational-only phone bezel for the browser-based demo (steering-docs
 * §3). Purely cosmetic — a real on-device build renders `MobileShell`
 * edge-to-edge by simply not wrapping it in this component (see the
 * NEXT_PUBLIC_DEMO_BEZEL check in the (mobile) route group layout). This
 * component itself carries no flag logic so it stays trivial to drop.
 */
export function DeviceFrame({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-neutral-900 p-6">
      <div className="flex h-[820px] w-[390px] max-h-[92dvh] flex-col overflow-hidden rounded-[2.5rem] border-[10px] border-neutral-800 bg-background shadow-2xl">
        <div className="flex h-7 shrink-0 items-center justify-center bg-neutral-900">
          <div className="h-1.5 w-20 rounded-full bg-neutral-700" />
        </div>
        <div className="flex-1 overflow-hidden">{children}</div>
      </div>
    </div>
  );
}
