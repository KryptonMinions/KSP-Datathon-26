"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { useRoleGuard } from "@/lib/auth/use-role-guard";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getCaseByFir } from "@/lib/fixtures/cases";

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

/**
 * Full-screen detail view for a single case. Reads the FIR id from the route
 * and renders all mock case fields. Back link returns to the cases list.
 */
export default function CaseDetailPage() {
  useRoleGuard((role) => role === "investigating_officer", "/ask");

  const params = useParams<{ firId: string }>();
  const firId = decodeURIComponent(params.firId);
  const c = getCaseByFir(firId);

  return (
    <div className="h-full space-y-4 overflow-y-auto p-4">
      <Link
        href="/cases"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Back to cases
      </Link>

      {!c ? (
        <p className="text-sm text-muted-foreground">Case not found.</p>
      ) : (
        <>
          <div className="space-y-1">
            <div className="flex items-center justify-between gap-2">
              <h1 className="text-lg font-semibold tabular-nums">{c.firId}</h1>
              <Badge variant="outline">{c.section}</Badge>
            </div>
            <p className="text-sm font-medium text-muted-foreground">{c.station}</p>
            <p className="text-sm text-muted-foreground">{c.status}</p>
          </div>

          <Card className="gap-2 py-3">
            <CardHeader className="px-3">
              <CardTitle className="text-sm">Case details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 px-3 text-sm">
              <DetailRow label="Offence" value={c.offence} />
              <DetailRow label="Section" value={c.section} />
              <DetailRow label="Complainant" value={c.complainant} />
              <DetailRow label="Investigating Officer" value={c.ioName} />
              <DetailRow label="Registered on" value={c.registeredOn} />
              <DetailRow label="Last updated" value={c.lastUpdated} />
            </CardContent>
          </Card>

          <Card className="gap-2 py-3">
            <CardHeader className="px-3">
              <CardTitle className="text-sm">Summary</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 px-3 text-sm text-muted-foreground">
              <p>{c.summary}</p>
              {c.nextAction && (
                <p>
                  <span className="font-medium text-foreground">Next action: </span>
                  {c.nextAction}
                </p>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
