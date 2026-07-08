import type { ReactNode } from "react";
import { AppHeader } from "./AppHeader";

/**
 * IO field persona shell — calm single column. Ask is the only destination
 * (it's the landing screen itself), so there is no bottom navigation; the
 * header avatar is the sole entry point to profile/sign-out. Frame-agnostic:
 * whether this renders inside the demo bezel or edge-to-edge on a real
 * device is decided by the (mobile) route group layout, not by this
 * component.
 */
export function MobileShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full flex-col">
      <AppHeader compact />
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
