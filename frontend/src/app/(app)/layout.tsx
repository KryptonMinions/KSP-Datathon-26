"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth/auth-context";
import { MobileShell } from "@/components/shells/MobileShell";
import { DesktopShell } from "@/components/shells/DesktopShell";
import { DeviceFrame } from "@/components/shells/DeviceFrame";

// One shared route tree ("/ask", "/dashboard", ...) — the shell (MobileShell
// vs DesktopShell) is chosen here by role, not by separate URL paths, since
// Next.js route groups may not resolve two groups to the same path. This is
// presentation routing only, never a security boundary: RBAC is enforced at
// the DB view layer (steering-docs FRONTEND_UI_STEERING.md §4/§11).
const DEMO_BEZEL = process.env.NEXT_PUBLIC_DEMO_BEZEL !== "false";

export default function AppLayout({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (ready && !user) {
      router.replace("/");
    }
  }, [ready, user, router]);

  if (!ready || !user) return null;

  if (user.role === "investigating_officer") {
    const shell = <MobileShell>{children}</MobileShell>;
    return DEMO_BEZEL ? <DeviceFrame>{shell}</DeviceFrame> : shell;
  }

  return <DesktopShell>{children}</DesktopShell>;
}
