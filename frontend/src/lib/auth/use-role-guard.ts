"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "./auth-context";
import type { Role } from "@/lib/types/auth";

/**
 * Presentation-only route guard — redirects away from a page that isn't
 * meant for the current role (e.g. IO has no Dashboard). This is NOT
 * access control; the DB view layer is the real RBAC boundary
 * (steering-docs FRONTEND_UI_STEERING.md §4/§11).
 */
export function useRoleGuard(allowed: (role: Role) => boolean, redirectTo: string) {
  const { user, ready } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (ready && user && !allowed(user.role)) {
      router.replace(redirectTo);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, user, router]);
}
