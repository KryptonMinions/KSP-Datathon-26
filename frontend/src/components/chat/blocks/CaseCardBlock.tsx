import type { CaseCardBlock as CaseCardBlockType } from "@/lib/types/content-blocks";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CitationChip } from "@/components/shared/CitationChip";
import { EntityChip } from "@/components/shared/EntityChip";

export function CaseCardBlock({ block }: { block: CaseCardBlockType }) {
  return (
    <div className="space-y-3">
      {block.person && (
        <div className="flex items-center gap-2">
          <EntityChip entity={block.person} />
        </div>
      )}

      <div className="grid gap-2 sm:grid-cols-2">
        {block.cases.map((c) => {
          const citation = block.citations?.find((cit) => cit.firId === c.firId);
          return (
            <Card key={c.firId} className="gap-2 py-3">
              <CardHeader className="gap-1 px-3">
                <CardTitle className="flex items-center justify-between text-sm">
                  <span className="tabular-nums">{c.firId}</span>
                  <Badge variant="outline">{c.section}</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 px-3 text-sm">
                <p className="font-medium">{c.offence}</p>
                <p className="text-muted-foreground">{c.station}</p>
                <p className="text-muted-foreground">{c.status}</p>
                {c.detail && <p className="text-muted-foreground">{c.detail}</p>}
                {citation && (
                  <div className="pt-1">
                    <CitationChip citation={citation} />
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {block.historySheet && (
        <Card className="gap-2 py-3">
          <CardHeader className="px-3">
            <CardTitle className="text-sm">History Sheet {block.historySheet.id}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 px-3 text-sm text-muted-foreground">
            <p>{block.historySheet.station}</p>
            <p>
              Category: {block.historySheet.category} · Risk: {block.historySheet.riskLevel}
            </p>
            <p className="tabular-nums">
              {block.historySheet.registeredCases} registered cases ·{" "}
              {block.historySheet.convictions} convictions ·{" "}
              {block.historySheet.abscondingInstances} absconding instance(s)
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
