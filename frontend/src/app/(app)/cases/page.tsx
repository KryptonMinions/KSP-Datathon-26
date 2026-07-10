"use client";

import Link from "next/link";
import { useRoleGuard } from "@/lib/auth/use-role-guard";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { IO_CASES } from "@/lib/fixtures/cases";

/**
 * Cases the investigating officer has worked on (past + ongoing), shown as
 * tappable case cards. FIR number + police station lead each card; tapping
 * opens the full-screen detail page.
 */
export default function CasesPage() {
  useRoleGuard((role) => role === "investigating_officer", "/ask");

  return (
    <div className="h-full space-y-4 overflow-y-auto p-4">
      <div>
        <h1 className="text-lg font-semibold">Cases</h1>
        <p className="text-sm text-muted-foreground">
          Cases you have worked on — past and ongoing.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {IO_CASES.map((c) => (
          <Link
            key={c.firId}
            href={`/cases/${encodeURIComponent(c.firId)}`}
            className="rounded-md focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            <Card className="h-full gap-2 py-3 transition-colors hover:border-primary/40">
              <CardHeader className="gap-1 px-3">
                <CardTitle className="flex items-center justify-between gap-2 text-sm">
                  <span className="tabular-nums">{c.firId}</span>
                  <Badge variant="outline">{c.section}</Badge>
                </CardTitle>
                <p className="text-sm font-medium text-muted-foreground">{c.station}</p>
              </CardHeader>
              <CardContent className="space-y-1 px-3 text-sm">
                <p className="font-medium">{c.offence}</p>
                <p className="text-muted-foreground">{c.status}</p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
