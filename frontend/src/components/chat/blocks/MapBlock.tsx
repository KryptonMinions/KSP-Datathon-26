"use client";

import dynamic from "next/dynamic";
import type { MapBlock as MapBlockType } from "@/lib/types/content-blocks";
import { CitationChip } from "@/components/shared/CitationChip";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Leaflet accesses `window`/`document` at import time, so the react-leaflet
 * subtree is loaded client-only via next/dynamic (`ssr: false`) — the one
 * deviation from the SSR-tolerant Cytoscape (NetworkGraphBlock) renderer.
 * Otherwise this mirrors that block: fixed-height bordered canvas, shared
 * across Mobile/Desktop shells, with a citations row beneath.
 */
const MapCanvas = dynamic(() => import("./MapCanvas"), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full" />,
});

export function MapBlock({ block }: { block: MapBlockType }) {
  return (
    <div className="space-y-2">
      {block.title && (
        <div className="text-sm font-medium text-foreground">{block.title}</div>
      )}

      <div className="h-80 w-full overflow-hidden rounded-md border border-border bg-card sm:h-95">
        <MapCanvas block={block} />
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
