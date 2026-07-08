"use client";

import { useAuth } from "@/lib/auth/auth-context";
import { useRoleGuard } from "@/lib/auth/use-role-guard";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import {
  SUPERVISOR_STATS,
  ANALYST_STATS,
  ADMIN_STATS,
  RECENT_ACTIVITY,
  type StatTile,
} from "@/lib/fixtures/dashboard";

const STATS_BY_ROLE: Record<string, StatTile[]> = {
  supervisor: SUPERVISOR_STATS,
  analyst: ANALYST_STATS,
  admin: ADMIN_STATS,
};

/** Kept intentionally light — the four demo beats (via Ask) are prioritized over dashboard depth (steering-docs §10). */
export default function DashboardPage() {
  useRoleGuard((role) => role !== "io", "/ask");
  const { user } = useAuth();
  if (!user) return null;

  const stats = STATS_BY_ROLE[user.role] ?? [];

  return (
    <div className="space-y-4 p-4">
      <div className="grid gap-3 sm:grid-cols-3">
        {stats.map((tile) => (
          <Card key={tile.label}>
            <CardHeader>
              <CardTitle className="text-xs font-normal text-muted-foreground">
                {tile.label}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="tabular-nums text-2xl font-semibold">{tile.value}</div>
              {tile.hint && <div className="text-xs text-muted-foreground">{tile.hint}</div>}
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Recent activity</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {RECENT_ACTIVITY.map((item) => (
            <div key={item.id} className="flex items-center justify-between gap-2">
              <span>{item.description}</span>
              <span className="shrink-0 text-xs text-muted-foreground">{item.timestamp}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
