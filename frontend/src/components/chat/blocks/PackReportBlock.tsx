import { ArrowUp, ArrowDown, Minus, Download } from "lucide-react";
import type { PackReportBlock as PackReportBlockType } from "@/lib/types/content-blocks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "@/components/ui/accordion";
import { cn } from "@/lib/utils";

const TREND_ICON = { up: ArrowUp, down: ArrowDown, stable: Minus } as const;

export function PackReportBlock({ block }: { block: PackReportBlockType }) {
  return (
    <div className="space-y-3 rounded-md border border-border p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">{block.title}</h3>
          <p className="text-xs text-muted-foreground">{block.period}</p>
        </div>
        {block.exportable && (
          <Button variant="outline" size="sm" disabled title="Cited PDF export — stub for v1">
            <Download className="size-3.5" />
            Export
          </Button>
        )}
      </div>

      <Accordion>
        {block.metrics.map((metric) => {
          const TrendIcon = TREND_ICON[metric.trend];
          const trendColor =
            metric.trend === "up"
              ? metric.anomaly
                ? "text-warning"
                : "text-success"
              : metric.trend === "down"
                ? "text-muted-foreground"
                : "text-muted-foreground";

          const row = (
            <div className="flex flex-1 items-center justify-between gap-2 text-sm">
              <span className="font-medium">{metric.category}</span>
              <div className="flex items-center gap-3 tabular-nums">
                <span>
                  {metric.current} <span className="text-muted-foreground">vs {metric.previous}</span>
                </span>
                <span className={cn("flex items-center gap-0.5", trendColor)}>
                  <TrendIcon className="size-3.5" />
                  {Math.abs(metric.deltaPct)}%
                </span>
                {metric.anomaly && (
                  <Badge className="border-warning/40 bg-warning/15 text-warning-foreground">
                    Anomaly
                  </Badge>
                )}
              </div>
            </div>
          );

          if (!metric.underlyingFirIds?.length) {
            return (
              <div key={metric.category} className="border-b py-2.5 not-last:border-b">
                {row}
                {metric.anomalyNote && (
                  <p className="mt-1 text-xs text-muted-foreground">{metric.anomalyNote}</p>
                )}
              </div>
            );
          }

          return (
            <AccordionItem key={metric.category} value={metric.category}>
              <AccordionTrigger>{row}</AccordionTrigger>
              <AccordionContent>
                <div className="space-y-2">
                  {metric.anomalyNote && (
                    <p className="text-xs text-muted-foreground">{metric.anomalyNote}</p>
                  )}
                  <div className="flex flex-wrap gap-1.5">
                    {metric.underlyingFirIds.map((firId) => (
                      <span
                        key={firId}
                        className="tabular-nums rounded-sm border border-border px-1.5 py-0.5 text-xs"
                      >
                        {firId}
                      </span>
                    ))}
                  </div>
                </div>
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>
    </div>
  );
}
