import type { ContentBlock } from "@/lib/types/content-blocks";
import { TextBlock } from "./blocks/TextBlock";
import { TableBlock } from "./blocks/TableBlock";
import { CaseCardBlock } from "./blocks/CaseCardBlock";
import { MoMatchBlock } from "./blocks/MoMatchBlock";
import { NoAnswerBlock } from "./blocks/NoAnswerBlock";
import { PackReportBlock } from "./blocks/PackReportBlock";
import { NetworkGraphBlock } from "./blocks/NetworkGraphBlock";
import { MapBlock } from "./blocks/MapBlock";

/**
 * The renderer switch over block type — the core extensibility pattern of
 * the frontend (steering-docs FRONTEND_UI_STEERING.md §2). Adding a new
 * answer type = adding a new union member in content-blocks.ts and a new
 * case here, not a new page.
 */
export function BlockRenderer({ block }: { block: ContentBlock }) {
  switch (block.type) {
    case "text":
      return <TextBlock block={block} />;
    case "table":
      return <TableBlock block={block} />;
    case "case_card":
      return <CaseCardBlock block={block} />;
    case "mo_match":
      return <MoMatchBlock block={block} />;
    case "no_answer":
      return <NoAnswerBlock block={block} />;
    case "pack_report":
      return <PackReportBlock block={block} />;
    case "network_graph":
      return <NetworkGraphBlock block={block} />;
    case "map":
      return <MapBlock block={block} />;
  }
}
