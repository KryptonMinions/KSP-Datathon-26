import type { TableBlock as TableBlockType } from "@/lib/types/content-blocks";
import { CitationChip } from "@/components/shared/CitationChip";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

export function TableBlock({ block }: { block: TableBlockType }) {
  return (
    <div className="space-y-2">
      {block.title && <h3 className="text-sm font-medium">{block.title}</h3>}

      {/* Desktop: dense table */}
      <div className="hidden overflow-x-auto rounded-md border border-border md:block">
        <Table>
          <TableHeader>
            <TableRow>
              {block.columns.map((col) => (
                <TableHead
                  key={col.key}
                  className={cn(col.align === "right" && "text-right")}
                >
                  {col.label}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {block.rows.map((row, i) => (
              <TableRow key={i}>
                {block.columns.map((col) => (
                  <TableCell
                    key={col.key}
                    className={cn(
                      "tabular-nums",
                      col.align === "right" && "text-right",
                    )}
                  >
                    {row[col.key]}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Mobile: stacked card-per-row */}
      <div className="flex flex-col gap-2 md:hidden">
        {block.rows.map((row, i) => (
          <div key={i} className="rounded-md border border-border p-3 text-sm">
            {block.columns.map((col) => (
              <div key={col.key} className="flex justify-between gap-2 py-0.5">
                <span className="text-muted-foreground">{col.label}</span>
                <span className="tabular-nums font-medium">{row[col.key]}</span>
              </div>
            ))}
          </div>
        ))}
      </div>

      {block.citations && block.citations.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {block.citations.map((citation, i) => (
            <CitationChip key={`${citation.firId}-${i}`} citation={citation} />
          ))}
        </div>
      )}
    </div>
  );
}
