import type { ReactNode } from "react";
import { AppHeader } from "./AppHeader";
import { Sidebar } from "./Sidebar";

/** Supervisor / Analyst / Admin office shell — sidebar nav, denser layout (steering-docs §7.2–§7.4). */
export function DesktopShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-dvh flex-col">
      <AppHeader />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
