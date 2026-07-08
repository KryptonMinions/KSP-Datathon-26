import { MessageSquare, LayoutDashboard, Users, ScrollText } from "lucide-react";
import type { Role } from "@/lib/types/auth";

export interface NavItem {
  label: string;
  href: string;
  icon: typeof MessageSquare;
}

const DESKTOP_BASE_NAV: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Ask", href: "/ask", icon: MessageSquare },
];

const ADMIN_EXTRA_NAV: NavItem[] = [
  { label: "Users & Roles", href: "/admin/users", icon: Users },
  { label: "Audit / Activity", href: "/admin/audit", icon: ScrollText },
];

export function getDesktopNavItems(role: Role): NavItem[] {
  return role === "admin" ? [...DESKTOP_BASE_NAV, ...ADMIN_EXTRA_NAV] : DESKTOP_BASE_NAV;
}
