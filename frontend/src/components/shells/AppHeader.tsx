"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth/auth-context";
import { KspEmblem } from "@/components/shared/KspEmblem";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { ProfilePanel } from "./ProfilePanel";

/**
 * Shared across both shells — KSP emblem, role indicator, and the avatar
 * that opens ProfilePanel. The avatar is the ONLY entry point to profile
 * details and sign-out — there is no separate Profile page/tab.
 */
export function AppHeader({ compact }: { compact?: boolean }) {
  const { user } = useAuth();
  const [profileOpen, setProfileOpen] = useState(false);

  const initials = user?.name
    ?.split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <header className="flex items-center justify-between border-b border-border bg-background px-4 py-2.5">
      <KspEmblem compact={compact} />
      {user && (
        <div className="flex items-center gap-2">
          {!compact && (
            <span className="hidden text-xs text-muted-foreground sm:inline">
              {user.name} | {user.unit}
            </span>
          )}
          <button
            type="button"
            onClick={() => setProfileOpen(true)}
            aria-label="Open profile"
            className="rounded-full focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            <Avatar className="size-8">
              <AvatarFallback>{initials}</AvatarFallback>
            </Avatar>
          </button>
          <ProfilePanel open={profileOpen} onOpenChange={setProfileOpen} />
        </div>
      )}
    </header>
  );
}
