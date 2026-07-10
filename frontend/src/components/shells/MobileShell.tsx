"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AppHeader } from "./AppHeader";
import { getMobileNavItems } from "@/lib/nav-config";
import { cn } from "@/lib/utils";

/**
 * IO field persona shell — calm single column with a compact bottom nav.
 * "Ask" is the landing screen; "Cases" lets the officer browse the cases they
 * have worked on. The header avatar remains the sole entry point to
 * profile/sign-out. Frame-agnostic: whether this renders inside the demo bezel
 * or edge-to-edge on a real device is decided by the (app) route group layout,
 * not by this component.
 */
export function MobileShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const items = getMobileNavItems();

  return (
    <div className="flex h-full flex-col">
      <AppHeader compact />
      <main className="flex-1 overflow-hidden">{children}</main>
      <nav className="flex shrink-0 items-stretch border-t border-border bg-background">
        {items.map((item) => {
          const active = pathname?.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex flex-1 flex-col items-center gap-1 py-2 text-xs font-medium transition-colors",
                active
                  ? "text-primary"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="size-5" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
